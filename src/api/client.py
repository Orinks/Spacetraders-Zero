import os
import sys
import time
import logging
import requests
from typing import Dict, Any, Optional, List, Tuple, Sequence, TypeVar, cast, Union
import json
from src.config import settings, CONFIG_PATH, ENV_PATH
from collections import deque
import statistics
from datetime import datetime, timedelta
from enum import Enum
import random
from functools import lru_cache
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

T = TypeVar('T')

class CircuitState(Enum):
    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"      # Not allowing requests
    HALF_OPEN = "HALF_OPEN"  # Testing if service is healthy

class CacheEntry:
    def __init__(self, data: Dict[str, Any], etag: Optional[str] = None, last_modified: Optional[str] = None):
        self.data = data
        self.etag = etag
        self.last_modified = last_modified
        self.timestamp = time.time()

class SpaceTradersClient:
    """Client for interacting with SpaceTraders API"""
    
    def __init__(self):
        # Configure logging with more detailed format
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        
        self.base_url = settings.api_url
        self.token = settings.spacetraders_token
        
        # Rate limiting setup
        self.requests_per_second: float = 2.0  # Default to 2 requests per second
        self.request_window: float = 1.0  # Window in seconds
        self.request_timestamps: deque[float] = deque(maxlen=10)  # Keep track of last 10 requests
        self.burst_limit: int = 10  # Maximum burst requests
        self.min_request_interval: float = 1.0 / self.requests_per_second
        
        # Adaptive rate limiting
        self.response_times: deque[float] = deque(maxlen=50)  # Track last 50 response times
        self.rate_adjustment_threshold: float = 1.0  # Seconds, threshold for rate adjustment
        self.last_rate_adjustment: Optional[float] = None
        self.rate_adjustment_interval: int = 60  # Adjust rates every 60 seconds
        
        # Circuit breaker setup
        self.circuit_state: CircuitState = CircuitState.CLOSED
        self.error_threshold: int = 5  # Number of errors before opening circuit
        self.reset_timeout: int = 60  # Seconds to wait before attempting reset
        self.last_error_time: Optional[float] = None
        self.error_count: int = 0
        self.success_threshold: int = 3  # Successful requests needed to close circuit
        self.success_count: int = 0
        
        # Cache settings
        self.cache: Dict[str, CacheEntry] = {}
        self.cache_ttl: int = 60  # Default TTL of 60 seconds
        self.cache_enabled: bool = True
        
        # Async client session
        self.async_session: Optional[aiohttp.ClientSession] = None
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        
        # Don't auto-register on init, let the UI handle it
        if not self.token:
            self.logger.info("No token found. Please register a new agent through the UI.")
                
        self.request_count: int = 0
        self.error_history: List[Tuple[float, str]] = []  # List of (timestamp, endpoint) tuples
        self.last_error_reset: float = time.time()

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limits"""
        current_time = time.time()
        
        # Clean up old timestamps
        while self.request_timestamps and current_time - self.request_timestamps[0] > self.request_window:
            self.request_timestamps.popleft()
        
        # Check if we need to wait
        if len(self.request_timestamps) >= self.burst_limit:
            # Calculate required delay
            oldest_timestamp = self.request_timestamps[0]
            time_passed = current_time - oldest_timestamp
            if time_passed < self.request_window:
                sleep_time = self.request_window - time_passed
                time.sleep(sleep_time)
        
        # Always wait minimum interval from last request
        if self.request_timestamps:
            time_since_last = current_time - self.request_timestamps[-1]
            if time_since_last < self.min_request_interval:
                time.sleep(self.min_request_interval - time_since_last)
        
        self.request_timestamps.append(current_time)

    def _check_circuit_breaker(self, endpoint: str) -> bool:
        """Check if circuit breaker allows the request"""
        current_time = time.time()
        
        if self.circuit_state == CircuitState.OPEN:
            if current_time - (self.last_error_time or 0) > self.reset_timeout:
                self.logger.info("Circuit breaker entering half-open state")
                self.circuit_state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                return False
                
        return True

    def _update_circuit_state(self, success: bool, endpoint: str):
        """Update circuit breaker state based on request result"""
        if success:
            if self.circuit_state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.logger.info("Circuit breaker closing - service recovered")
                    self.circuit_state = CircuitState.CLOSED
                    self.error_count = 0
            else:
                self.error_count = max(0, self.error_count - 1)
        else:
            self.error_count += 1
            self.last_error_time = time.time()
            if self.error_count >= self.error_threshold:
                if self.circuit_state != CircuitState.OPEN:
                    self.logger.warning(f"Circuit breaker opening for endpoint pattern: {endpoint}")
                    self.circuit_state = CircuitState.OPEN

    def _handle_error(self, endpoint: str, error: Exception) -> None:
        """Handle API errors and track error rate"""
        current_time = time.time()
        
        # Record error
        self.error_count += 1
        self.error_history.append((current_time, endpoint))
        
        # Reset error count if enough time has passed
        if self.last_error_time is not None and current_time - self.last_error_time > self.reset_timeout:
            self.error_count = 1
            self.last_error_reset = current_time
        
        self.last_error_time = current_time
        
        # Log the error with appropriate severity
        if isinstance(error, requests.exceptions.HTTPError):
            if error.response is not None and error.response.status_code >= 500:
                self.logger.error(f"Server error for {endpoint}: {str(error)}")
            else:
                self.logger.warning(f"HTTP error for {endpoint}: {str(error)}")
        else:
            self.logger.error(f"Network error for {endpoint}: {str(error)}")

    def _get_cache_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate a cache key from endpoint and params"""
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            return f"{endpoint}?{param_str}"
        return endpoint

    def _get_cached_response(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Get cached response if available and not expired"""
        if not self.cache_enabled:
            return None
            
        cache_key = self._get_cache_key(endpoint, params)
        if cache_key not in self.cache:
            return None
            
        cached = self.cache[cache_key]
        if time.time() - cached.timestamp > self.cache_ttl:
            del self.cache[cache_key]
            return None
            
        return cached.data

    def _update_cache(self, endpoint: str, data: Dict, response: requests.Response, params: Optional[Dict] = None) -> None:
        """Update cache with response data and validation headers"""
        cache_key = self._get_cache_key(endpoint, params)
        etag = response.headers.get('ETag')
        last_modified = response.headers.get('Last-Modified')
        
        self.cache[cache_key] = CacheEntry(data, etag, last_modified)
        self.logger.debug(f"Updated cache for {cache_key}")

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Make a request to the SpaceTraders API with rate limiting and error handling."""
        if not self._check_circuit_breaker(endpoint):
            raise RuntimeError(f"Circuit breaker is open for {endpoint}")

        retries = 0
        max_retries = 2
        success = False
        
        while retries <= max_retries:
            try:
                self._wait_for_rate_limit()
                start_time = time.time()
                
                url = f"{self.base_url}/{endpoint}"
                headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
                
                # Add data to request if provided
                if data is not None:
                    kwargs["json"] = data
                
                response = requests.request(method, url, headers=headers, **kwargs)
                
                # Log response details for debugging
                duration = time.time() - start_time
                self.response_times.append(duration)
                while len(self.response_times) > 100:  # Keep last 100 response times
                    self.response_times.popleft()
                    
                self._log_response(response, duration)
                
                # Adjust rate limits based on response times
                if len(self.response_times) > 0:
                    avg_response_time = statistics.mean(self.response_times)
                    if avg_response_time > self.rate_adjustment_threshold:
                        self.requests_per_second = max(0.1, self.requests_per_second * 0.5)
                        self.min_request_interval = 1.0 / self.requests_per_second
                        self.logger.info(f"Reduced rate limit to {self.requests_per_second:.1f} requests/second due to high response times")
                
                response.raise_for_status()
                success = True
                return response.json()
                
            except Exception as e:
                retries += 1
                if retries > max_retries:
                    self._handle_request_error(e, endpoint)
                    raise
                
                # Exponential backoff with jitter - using random is acceptable here as it's not for security purposes
                delay = min(300, (2 ** retries) + random.uniform(0, 0.1))  # nosec B311
                time.sleep(delay)
            finally:
                self._update_circuit_state(success, endpoint)

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests"""
        if not self.token:
            self.logger.warning("No token available for request. Please register an agent first.")
            raise ValueError("No token available for request. Please register an agent first.")
        auth_token = self.token.strip()
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        return {
            "Authorization": auth_token,
            "Content-Type": "application/json"
        }

    def register_new_agent(self, agent_symbol: str) -> Dict[str, Any]:
        """Register a new agent and save the token"""
        response = self._make_request(
            "POST",
            "register",
            data={
                "symbol": agent_symbol,
                "faction": "COSMIC"
            }
        )
        
        # Save token to config and .env files
        self.token = response["data"]["token"]
        with open(CONFIG_PATH, 'r+') as f:
            config = json.load(f)
            config["SPACETRADERS_TOKEN"] = self.token
            f.seek(0)
            json.dump(config, f, indent=4)
            f.truncate()
        
        # Update .env file
        with open(ENV_PATH, 'a') as f:
            f.write(f"\nSPACETRADERS_TOKEN={self.token}\n")
        
        return response

    def get_agent(self) -> Dict[str, Any]:
        """Get current agent details"""
        return self._make_request("GET", "my/agent")
        
    def get_contracts(self) -> Dict[str, Any]:
        """Get available contracts"""
        return self._make_request("GET", "my/contracts")
        
    def accept_contract(self, contract_id: str) -> Dict[str, Any]:
        """Accept a contract"""
        return self._make_request("POST", f"my/contracts/{contract_id}/accept")
        
    def get_market(self, system: str, waypoint: str) -> Dict[str, Any]:
        """Get market data at a waypoint"""
        return self._make_request("GET", f"systems/{system}/waypoints/{waypoint}/market")

    def buy_goods(self, ship_symbol: str, symbol: str, units: int) -> Dict[str, Any]:
        """Buy goods at current market"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/purchase", {
            "symbol": symbol,
            "units": units
        })

    def sell_goods(self, ship_symbol: str, symbol: str, units: int) -> Dict[str, Any]:
        """Sell goods at current market"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/sell", {
            "symbol": symbol,
            "units": units
        })

    def get_my_ships(self) -> Dict[str, Any]:
        """Get list of ships owned by the agent"""
        return self._make_request("GET", "my/ships")

    def dock_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Dock ship at current waypoint"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/dock")

    def orbit_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Move ship into orbit"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/orbit")

    def fulfill_contract(self, contract_id: str, ship_symbol: str, trade_symbol: str, units: int) -> Dict[str, Any]:
        """Fulfill a contract delivery"""
        return self._make_request("POST", f"my/contracts/{contract_id}/deliver", {
            "shipSymbol": ship_symbol,
            "tradeSymbol": trade_symbol,
            "units": units
        })

    def extract_resources(self, ship_symbol: str, survey: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract resources from an asteroid or other resource field"""
        payload = {}
        if survey:
            payload["survey"] = survey
        return self._make_request("POST", f"my/ships/{ship_symbol}/extract", payload)

    def scan_ships(self, ship_symbol: str) -> Dict[str, Any]:
        """Scan for nearby ships"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/scan/ships")

    def repair_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Repair ship at a shipyard"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/repair")

    def negotiate_contract(self, ship_symbol: str) -> Dict[str, Any]:
        """Negotiate a new contract"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/negotiate/contract")

    def jump_ship(self, ship_symbol: str, system_symbol: str) -> Dict[str, Any]:
        """Jump ship to another system using a jump gate"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/jump", {
            "systemSymbol": system_symbol
        })

    def survey_location(self, ship_symbol: str) -> Dict[str, Any]:
        """Survey the current location for better extraction spots"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/survey")

    def get_waypoints(self, system: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """Get list of waypoints in a system"""
        return self._make_request("GET", f"systems/{system}/waypoints?page={page}&limit={limit}")

    def get_systems(self, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """Get list of all systems"""
        return self._make_request("GET", f"systems?page={page}&limit={limit}")

    def get_factions(self) -> Dict[str, Any]:
        """Get list of all factions"""
        return self._make_request("GET", "factions")

    def navigate_ship(self, ship_symbol: str, waypoint_symbol: str) -> Dict[str, Any]:
        """Navigate ship to a waypoint."""
        return self._make_request("POST", f"my/ships/{ship_symbol}/navigate", {
            "waypointSymbol": waypoint_symbol
        })

    def transfer_cargo(self, ship_symbol: str, trade_symbol: str, units: int, receiving_ship: str) -> Dict[str, Any]:
        """Transfer cargo between ships"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/transfer", {
            "tradeSymbol": trade_symbol,
            "units": units,
            "shipSymbol": receiving_ship
        })

    def get_system_waypoints(self, system_symbol: str) -> Dict[str, Any]:
        """Get all waypoints in a system"""
        return self._make_request("GET", f"systems/{system_symbol}/waypoints")

    def refuel_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Refuel a ship at a station"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/refuel")

    def get_ship_cooldown(self, ship_symbol: str) -> Dict[str, Any]:
        """Get the ship's cooldown status"""
        return self._make_request("GET", f"my/ships/{ship_symbol}/cooldown")

    def get_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Get details of a specific ship"""
        return self._make_request("GET", f"my/ships/{ship_symbol}")

    def can_ship_mine(self, ship_symbol: str) -> Dict[str, Any]:
        """
        Check if a ship can mine by verifying:
        1. Ship has mining equipment
        2. Ship is at an asteroid field
        3. Ship is in orbit
        4. Ship is not on cooldown
        5. Ship has cargo space available
        
        Returns:
            Dict with keys:
                - can_mine (bool): Whether the ship can mine
                - reason (str): Explanation if can_mine is False
        """
        try:
            # Get ship details
            ship_data = self.get_ship(ship_symbol).get("data", {})
            if not ship_data:
                return {"can_mine": False, "reason": "Could not get ship data"}
                
            # Check if ship has mining equipment
            has_mining_mount = False
            for mount in ship_data.get("mounts", []):
                if "MINING_LASER" in mount.get("symbol", ""):
                    has_mining_mount = True
                    break
                    
            if not has_mining_mount:
                return {"can_mine": False, "reason": "Ship does not have mining equipment"}
                
            # Check ship location and status
            nav = ship_data.get("nav", {})
            if nav.get("status") != "IN_ORBIT":
                return {"can_mine": False, "reason": "Ship must be in orbit to mine"}
                
            # Get waypoint details to check if it's an asteroid field
            system = nav.get("systemSymbol")
            waypoint = nav.get("waypointSymbol")
            if not system or not waypoint:
                return {"can_mine": False, "reason": "Could not determine ship location"}
                
            waypoints = self.get_waypoints(system).get("data", [])
            current_waypoint = next(
                (w for w in waypoints if w.get("symbol") == waypoint),
                None
            )
            
            if not current_waypoint or "ASTEROID" not in current_waypoint.get("type", ""):
                return {"can_mine": False, "reason": "Ship is not at an asteroid field"}
                
            # Check cooldown
            cooldown = self.get_ship_cooldown(ship_symbol).get("data", {})
            if cooldown and cooldown.get("remainingSeconds", 0) > 0:
                return {
                    "can_mine": False, 
                    "reason": f"Ship is on cooldown for {cooldown['remainingSeconds']} seconds"
                }
                
            # Check cargo space
            cargo = ship_data.get("cargo", {})
            if cargo.get("units", 0) >= cargo.get("capacity", 0):
                return {"can_mine": False, "reason": "Cargo hold is full"}
                
            # All checks passed
            return {"can_mine": True}
            
        except Exception as e:
            self.logger.error(f"Error checking mining capability: {str(e)}")
            return {"can_mine": False, "reason": f"Error checking mining capability: {str(e)}"}

    def get_shipyard(self, system: str, waypoint: str) -> Dict[str, Any]:
        """Get shipyard data at a waypoint"""
        return self._make_request("GET", f"systems/{system}/waypoints/{waypoint}/shipyard")

    def purchase_ship(self, ship_type: str, waypoint: str) -> Dict[str, Any]:
        """Purchase a ship at a shipyard"""
        return self._make_request("POST", "my/ships", {
            "shipType": ship_type,
            "waypointSymbol": waypoint
        })

    def purchase_ship_mount(self, ship_symbol: str, mount_symbol: str) -> Dict[str, Any]:
        """Purchase and install a mount on a ship"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/mounts", {"symbol": mount_symbol})

    def get_waypoint(self, system: str, waypoint: str) -> Dict[str, Any]:
        """Get details about a specific waypoint"""
        return self._make_request("GET", f"systems/{system}/waypoints/{waypoint}")

    def make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make a raw HTTP request to the SpaceTraders API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g. '/my/ships')
            params: Optional query parameters
            json_data: Optional JSON request body
            
        Returns:
            Dict containing the API response
        """
        url = f"{self.base_url}/{endpoint}"
        self.logger.debug(f"Making {method} request to {url}")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data
            )
            duration = time.time() - time.time()
            self.response_times.append(duration)
            while len(self.response_times) > 100:  # Keep last 100 response times
                self.response_times.popleft()
                
            self._log_response(response, duration)
            response.raise_for_status()
            return cast(Dict[str, Any], response.json())
        except Exception as e:
            self._handle_error(endpoint, e)
            raise

    def get_ships(self) -> Dict[str, Any]:
        """Get all ships owned by the agent"""
        return self._make_request("GET", "my/ships")

    async def _init_async_session(self) -> None:
        """Initialize async session if not already initialized"""
        if not self.async_session:
            self.async_session = aiohttp.ClientSession(headers=self._get_headers())

    async def _close_async_session(self) -> None:
        """Close async session if it exists"""
        if self.async_session:
            await self.async_session.close()
            self.async_session = None

    async def _async_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make an async GET request"""
        if not self.async_session:
            await self._init_async_session()
            if not self.async_session:
                raise RuntimeError("Failed to initialize async session")

        url = f"{self.base_url}/{endpoint}"
        try:
            start_time = time.time()
            async with self.async_session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                self._log_response(cast(requests.Response, response), time.time() - start_time)
                return cast(Dict[str, Any], data)
        except Exception as e:
            self._log_error(endpoint, e, time.time() - start_time)
            raise

    async def _batch_get(self, endpoints: Sequence[Tuple[str, Optional[Dict[str, Any]]]], chunk_size: int = 10) -> List[Dict[str, Any]]:
        """Batch multiple GET requests with rate limiting"""
        if not self.async_session:
            await self._init_async_session()
            if not self.async_session:
                raise RuntimeError("Failed to initialize async session")

        results: List[Dict[str, Any]] = []
        for i in range(0, len(endpoints), chunk_size):
            chunk = endpoints[i:i + chunk_size]
            tasks = [self._async_get(endpoint, params) for endpoint, params in chunk]
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in chunk_results:
                if isinstance(result, Exception):
                    results.append({"error": str(result)})
                else:
                    results.append(cast(Dict[str, Any], result))
            
            # Rate limiting pause between chunks
            if i + chunk_size < len(endpoints):
                await asyncio.sleep(self.min_request_interval * chunk_size)

        return results

    def batch_get(self, endpoints: Sequence[Tuple[str, Optional[Dict[str, Any]]]], chunk_size: int = 10) -> List[Dict[str, Any]]:
        """Synchronous wrapper for batch GET requests"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._batch_get(endpoints, chunk_size))
        finally:
            loop.close()

    def get_ships_with_info(self, ship_symbols: List[str]) -> List[Dict[str, Any]]:
        """Get detailed information for multiple ships in parallel"""
        endpoints = [(f"my/ships/{symbol}", None) for symbol in ship_symbols]
        return self.batch_get(endpoints)

    def get_markets_info(self, locations: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        """Get market data for multiple locations in parallel
        Args:
            locations: List of (system_symbol, waypoint_symbol) tuples
        """
        endpoints = [(f"systems/{system}/waypoints/{waypoint}/market", None) 
                    for system, waypoint in locations]
        return self.batch_get(endpoints)

    def get_waypoints_in_systems(self, system_symbols: List[str], limit: int = 20) -> List[Dict[str, Any]]:
        """Get waypoints for multiple systems in parallel"""
        endpoints = [(f"systems/{system}/waypoints", {"limit": limit}) 
                    for system in system_symbols]
        return self.batch_get(endpoints)

    def get_shipyards_info(self, locations: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
        """Get shipyard data for multiple locations in parallel
        Args:
            locations: List of (system_symbol, waypoint_symbol) tuples
        """
        endpoints = [(f"systems/{system}/waypoints/{waypoint}/shipyard", None) 
                    for system, waypoint in locations]
        return self.batch_get(endpoints)

    @lru_cache(maxsize=1000)
    def get_system_info(self, system_symbol: str) -> Dict[str, Any]:
        """Get system information with caching"""
        return self._make_request("GET", f"systems/{system_symbol}")

    @lru_cache(maxsize=1000)
    def get_waypoint_info(self, system_symbol: str, waypoint_symbol: str) -> Dict[str, Any]:
        """Get waypoint information with caching"""
        return self._make_request("GET", f"systems/{system_symbol}/waypoints/{waypoint_symbol}")

    def clear_caches(self):
        """Clear all caches"""
        self.cache.clear()
        self.get_system_info.cache_clear()
        self.get_waypoint_info.cache_clear()

    def _log_request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None):
        """Log request details at DEBUG level"""
        self.logger.debug(
            f"API Request: {method} {endpoint}\n"
            f"Params: {params}\n"
            f"Data: {data}\n"
            f"Timestamp: {datetime.now().isoformat()}"
        )

    def _log_response(self, response: requests.Response, duration: float):
        """Log response details at appropriate level based on status code"""
        status = response.status_code
        level = logging.DEBUG if 200 <= status < 300 else logging.WARNING
        
        log_msg = (
            f"API Response: {status} ({response.reason})\n"
            f"Duration: {duration:.2f}s\n"
            f"Timestamp: {datetime.now().isoformat()}\n"
            f"Headers: {dict(response.headers)}"
        )
        
        # Add response body for non-200 responses
        if status >= 300:
            try:
                body = response.json()
            except:
                body = response.text[:1000] + "..." if len(response.text) > 1000 else response.text
            log_msg += f"\nResponse Body: {body}"
            
        self.logger.log(level, log_msg)

    def _log_error(self, endpoint: str, error: Exception, duration: float):
        """Log detailed error information"""
        self.logger.error(
            f"API Error on {endpoint}\n"
            f"Error Type: {type(error).__name__}\n"
            f"Error Message: {str(error)}\n"
            f"Duration: {duration:.2f}s\n"
            f"Timestamp: {datetime.now().isoformat()}"
        )
        if isinstance(error, requests.exceptions.RequestException) and error.response is not None:
            try:
                body = error.response.json()
            except:
                body = error.response.text[:1000] + "..." if len(error.response.text) > 1000 else error.response.text
            self.logger.error(f"Response Body: {body}")

    def _handle_request_error(self, error: Exception, endpoint: str):
        """Handle API errors and track error rate"""
        current_time = time.time()
        
        # Record error
        self.error_count += 1
        self.error_history.append((current_time, endpoint))
        
        # Reset error count if enough time has passed
        if self.last_error_time is not None and current_time - self.last_error_time > self.reset_timeout:
            self.error_count = 1
            self.last_error_reset = current_time
        
        self.last_error_time = current_time
        
        # Log the error with appropriate severity
        if isinstance(error, requests.exceptions.HTTPError):
            if error.response is not None and error.response.status_code >= 500:
                self.logger.error(f"Server error for {endpoint}: {str(error)}")
            else:
                self.logger.warning(f"HTTP error for {endpoint}: {str(error)}")
        else:
            self.logger.error(f"Network error for {endpoint}: {str(error)}")
