import os
import sys
import time
import logging
import requests
from typing import Dict, Any, Optional, List, Tuple
import json
from config import settings
from collections import deque
import statistics
from datetime import datetime, timedelta
from enum import Enum
import random
from functools import lru_cache
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

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
        self.requests_per_second = 2  # Default to 2 requests per second
        self.request_window = 1.0  # Window in seconds
        self.request_timestamps = deque(maxlen=10)  # Keep track of last 10 requests
        self.burst_limit = 10  # Maximum burst requests
        self.min_request_interval = 1.0 / self.requests_per_second
        
        # Adaptive rate limiting
        self.response_times = deque(maxlen=50)  # Track last 50 response times
        self.rate_adjustment_threshold = 1.0  # Seconds, threshold for rate adjustment
        self.last_rate_adjustment = time.time()
        self.rate_adjustment_interval = 60  # Adjust rates every 60 seconds
        
        # Circuit breaker setup
        self.circuit_state = CircuitState.CLOSED
        self.error_threshold = 5  # Number of errors before opening circuit
        self.reset_timeout = 60  # Seconds to wait before attempting reset
        self.last_error_time = time.time()
        self.error_count = 0
        self.success_threshold = 3  # Successful requests needed to close circuit
        self.success_count = 0
        
        # Cache settings
        self.cache: Dict[str, CacheEntry] = {}
        self.cache_ttl = 60  # Default TTL of 60 seconds
        self.cache_enabled = True
        
        # Async client session
        self.async_session = None
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        
        # Don't auto-register on init, let the UI handle it
        if not self.token:
            self.logger.info("No token found. Please register a new agent through the UI.")
                
        self.error_count = 0
        self.request_count = 0
        self.last_error_time = None
        self.error_history = []  # List of (timestamp, endpoint) tuples
        self.last_error_reset = time.time()
            
    def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits with adaptive adjustment"""
        current_time = time.time()
        
        # Clean up old timestamps
        while self.request_timestamps and current_time - self.request_timestamps[0] > self.request_window:
            self.request_timestamps.popleft()
        
        # Adjust rate limits based on response times
        if (current_time - self.last_rate_adjustment > self.rate_adjustment_interval or self.last_rate_adjustment == 0) and len(self.response_times) > 0:
            avg_response_time = statistics.mean(self.response_times)
            old_rate = self.requests_per_second
            
            if avg_response_time > self.rate_adjustment_threshold:
                # More aggressive rate reduction (30%) when response times are high
                self.requests_per_second = max(1, self.requests_per_second * 0.7)
            elif avg_response_time < self.rate_adjustment_threshold * 0.5:  # If response times are good
                self.requests_per_second = min(10, self.requests_per_second * 1.1)  # Gentle increase
                
            if old_rate != self.requests_per_second:
                self.min_request_interval = 1.0 / self.requests_per_second
                self.last_rate_adjustment = current_time
                self.logger.info(f"Adjusted request rate from {old_rate:.2f} to {self.requests_per_second:.2f} req/s (avg response: {avg_response_time:.2f}s)")
        
        # If we've hit our burst limit, wait for the oldest request to expire
        if len(self.request_timestamps) >= self.burst_limit:
            wait_time = self.request_timestamps[0] + self.request_window - current_time
            if wait_time > 0:
                time.sleep(wait_time)
        
        # Ensure minimum interval between requests
        if self.request_timestamps:
            elapsed = current_time - self.request_timestamps[-1]
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
        
        self.request_timestamps.append(time.time())

    def _check_circuit_breaker(self, endpoint: str) -> bool:
        """Check if circuit breaker allows the request"""
        current_time = time.time()
        
        if self.circuit_state == CircuitState.OPEN:
            if current_time - self.last_error_time > self.reset_timeout:
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
        self.error_count += 1
        self.error_history.append((current_time, endpoint))
        self.last_error_time = current_time
        
        # Clean up old errors (older than 5 minutes)
        self.error_history = [(t, e) for t, e in self.error_history if t > current_time - 300]
        
        # Reset error count if it's been more than 5 minutes since last reset
        if current_time - self.last_error_reset > 300:
            self.error_count = len(self.error_history)
            self.last_error_reset = current_time
            
        if isinstance(error, requests.exceptions.HTTPError):
            self.logger.error(f"HTTP error on {endpoint}: {error}")
        else:
            self.logger.error(f"Error on {endpoint}: {error}")

    def _get_cache_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate a cache key from endpoint and params"""
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            return f"{endpoint}?{param_str}"
        return endpoint

    def _get_cached_response(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Get cached response if available and not expired"""
        cache_key = self._get_cache_key(endpoint, params)
        cached = self.cache.get(cache_key)
        
        if cached and time.time() - cached.timestamp < self.cache_ttl:
            return None  # Let the request proceed with conditional headers
            
        return None

    def _update_cache(self, endpoint: str, data: Dict, response: requests.Response, params: Optional[Dict] = None) -> None:
        """Update cache with response data and validation headers"""
        cache_key = self._get_cache_key(endpoint, params)
        etag = response.headers.get('ETag')
        last_modified = response.headers.get('Last-Modified')
        
        self.cache[cache_key] = CacheEntry(data, etag, last_modified)
        self.logger.debug(f"Updated cache for {cache_key}")

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None, requires_auth: bool = True) -> Dict[str, Any]:
        """Make a request to the SpaceTraders API with caching and rate limiting."""
        if not self._check_circuit_breaker(endpoint):
            self.logger.critical(f"Circuit breaker is open for endpoint pattern: {endpoint}")
            raise RuntimeError(f"Circuit breaker is open for endpoint pattern: {endpoint}")
            
        url = f"{self.base_url}/{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        if requires_auth:
            if not self.token:
                raise ValueError("No token available for request. Please register an agent first.")
            headers["Authorization"] = f"Bearer {self.token}"
        
        # Add conditional GET headers if available
        if method == "GET":
            cache_key = self._get_cache_key(endpoint, params)
            if cache_key in self.cache:
                cached = self.cache[cache_key]
                if cached.etag:
                    headers['If-None-Match'] = cached.etag
                    self.logger.debug(f"Using ETag: {cached.etag}")
                if cached.last_modified:
                    headers['If-Modified-Since'] = cached.last_modified
                    self.logger.debug(f"Using Last-Modified: {cached.last_modified}")
        
        max_retries = 3
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Log request details
                self._log_request(method, endpoint, params, data)
                
                # Wait for rate limiting
                self._wait_for_rate_limit()
                
                start_time = time.time()
                
                if method == "GET":
                    response = requests.get(url, headers=headers, params=params, timeout=10)
                elif method == "POST":
                    response = requests.post(url, headers=headers, json=data, timeout=10)
                elif method == "PATCH":
                    response = requests.patch(url, headers=headers, json=data, timeout=10)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Record response time and log response
                duration = time.time() - start_time
                self._log_response(response, duration)
                self.response_times.append(duration)
                
                if response.status_code == 429:  # Rate limit hit
                    retry_after = int(response.headers.get('Retry-After', base_delay))
                    self.logger.warning(f"Rate limit hit, waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                elif response.status_code == 304:  # Not Modified
                    self.logger.debug(f"Resource not modified for {endpoint}")
                    return self.cache[self._get_cache_key(endpoint, params)].data
                
                response.raise_for_status()
                response_data = response.json()
                
                # Update cache for GET requests
                if method == "GET":
                    self._update_cache(endpoint, response_data, response, params)
                
                self._update_circuit_state(True, endpoint)
                return response_data
                
            except requests.exceptions.RequestException as e:
                duration = time.time() - start_time
                self._log_error(endpoint, e, duration)
                self._update_circuit_state(False, endpoint)
                
                if attempt < max_retries - 1:
                    # Calculate exponential backoff with jitter
                    max_delay = base_delay * (2 ** attempt)
                    jitter = random.uniform(0, 0.1 * max_delay)  # 10% jitter
                    delay = max_delay + jitter
                    
                    self.logger.warning(f"Request failed: {str(e)}")
                    self.logger.warning(f"Retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                else:
                    self.logger.error(f"Maximum retries exceeded for {endpoint}")
                    raise RuntimeError(f"Failed to connect to SpaceTraders API: {str(e)}")
        
        raise RuntimeError("Maximum retries exceeded with no specific error")

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

    def register_new_agent(self, symbol: str, faction: str = "COSMIC") -> Dict[str, Any]:
        """Register a new agent and get access token"""
        self.logger.info(f"Registering new agent {symbol} with faction {faction}")
        
        # Registration doesn't need authentication
        url = f"{self.base_url}/register"
        data = {
            "symbol": symbol,
            "faction": faction,
            "email": "openhands@all-hands.dev"
        }
        
        try:
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            response_data = response.json()
            
            # Extract and store token
            token = response_data.get("data", {}).get("token")
            if not token:
                raise ValueError("No token received in registration response")
            
            # Update token in settings (which also updates .env file)
            settings.update_token(token)
            self.token = token
            self.logger.info("Successfully registered new agent and saved token")
            
            return response_data
            
        except Exception as e:
            self.logger.error(f"Failed to register new agent: {str(e)}")
            raise

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

    def make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, json_data: Dict[str, Any] = None) -> Dict[str, Any]:
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
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self._handle_error(endpoint, e)
            raise

    def get_ships(self):
        """Get all ships owned by the agent"""
        return self._make_request("GET", "my/ships")

    def purchase_ship(self, ship_type, waypoint):
        """Purchase a new ship"""
        return self._make_request("POST", "my/ships", {
            "shipType": ship_type,
            "waypointSymbol": waypoint
        })

    def get_market(self, system_symbol, waypoint_symbol):
        """Get market data for a waypoint"""
        return self._make_request("GET", f"systems/{system_symbol}/waypoints/{waypoint_symbol}/market")

    async def _init_async_session(self):
        """Initialize async session if not already initialized"""
        if self.async_session is None:
            self.async_session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {self.token}"})

    async def _close_async_session(self):
        """Close async session if it exists"""
        if self.async_session:
            await self.async_session.close()
            self.async_session = None

    async def _async_get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an async GET request"""
        await self._init_async_session()
        url = f"{self.base_url}/{endpoint}"
        
        try:
            self._log_request("GET", endpoint, params)
            async with self.async_session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                self._log_response(response, time.time() - datetime.now().timestamp())
                return data
        except Exception as e:
            self._log_error(endpoint, e, time.time() - datetime.now().timestamp())
            return None

    async def _batch_get(self, endpoints: List[Tuple[str, Optional[Dict]]]) -> List[Dict[str, Any]]:
        """Batch multiple GET requests"""
        try:
            await self._init_async_session()
            tasks = []
            for endpoint, params in endpoints:
                task = self._async_get(endpoint, params)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            return [r for r in results if r is not None]  # Filter out failed requests
        finally:
            if self.async_session:
                await self.async_session.close()
                self.async_session = None

    def batch_get(self, endpoints: List[Tuple[str, Optional[Dict]]]) -> List[Dict[str, Any]]:
        """Synchronous wrapper for batch GET requests"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._batch_get(endpoints))
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
