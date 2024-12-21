import os
import sys
import logging
import json
from typing import Dict, Any, Optional, List, Tuple, TypeVar
from src.config import settings, CONFIG_PATH, ENV_PATH
from concurrent.futures import ThreadPoolExecutor
import asyncio
import aiohttp
from src.api.rate_limiter import RateLimiter
from src.api.circuit_breaker import CircuitBreaker
from src.api.cache import Cache
from src.api.request_handler import RequestHandler

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
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter()
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker()
        
        # Initialize cache
        self.cache = Cache()
        
        # Initialize request handler
        self.request_handler = RequestHandler(self.base_url, self.token, self.rate_limiter, self.circuit_breaker)
        
        # Async client session
        self.async_session: Optional[aiohttp.ClientSession] = None
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        
        # Don't auto-register on init, let the UI handle it
        if not self.token:
            self.logger.info("No token found. Please register a new agent through the UI.")

    

    

    

    

    

    

    

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Make a request to the SpaceTraders API using the request handler."""
        cache_key = self.cache.get_cache_key(endpoint, kwargs.get("params"))
            cached_response = self.cache.get(endpoint, kwargs.get("params"))

        if cached_response:
            self.logger.debug(f"Cache hit for {cache_key}")
            return cached_response
        
        response = self.request_handler.make_request(method, endpoint, data, **kwargs)
        
        if response:
            self.cache.update(endpoint, response, params=kwargs.get("params"))
        
        return response

    

    def register_new_agent(self, agent_symbol: str) -> Dict[str, Any]:
        """Register a new agent and save the token"""
        response = self.request_handler.make_request(
            "POST",
            "register",
            data={
                "symbol": agent_symbol,
                "faction": "COSMIC"
            },
            headers=self.request_handler.get_headers()
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
        return self._make_request("GET", "my/agent", headers=self.request_handler.get_headers())
        
    def get_contracts(self) -> Dict[str, Any]:
        """Get available contracts"""
        return self._make_request("GET", "my/contracts", headers=self.request_handler.get_headers())
        
    def accept_contract(self, contract_id: str) -> Dict[str, Any]:
        """Accept a contract"""
        return self._make_request("POST", f"my/contracts/{contract_id}/accept", headers=self.request_handler.get_headers())
        
    def get_market(self, system: str, waypoint: str) -> Dict[str, Any]:
        """Get market data at a waypoint"""
        return self._make_request("GET", f"systems/{system}/waypoints/{waypoint}/market", headers=self.request_handler.get_headers())

    def buy_goods(self, ship_symbol: str, symbol: str, units: int) -> Dict[str, Any]:
        """Buy goods at current market"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/purchase", {
            "symbol": symbol,
            "units": units
        }, headers=self.request_handler.get_headers())

    def sell_goods(self, ship_symbol: str, symbol: str, units: int) -> Dict[str, Any]:
        """Sell goods at current market"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/sell", {
            "symbol": symbol,
            "units": units
        }, headers=self.request_handler.get_headers())

    def get_my_ships(self) -> Dict[str, Any]:
        """Get list of ships owned by the agent"""
        return self._make_request("GET", "my/ships", headers=self.request_handler.get_headers())

    def dock_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Dock ship at current waypoint"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/dock", headers=self.request_handler.get_headers())

    def orbit_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Move ship into orbit"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/orbit", headers=self.request_handler.get_headers())

    def fulfill_contract(self, contract_id: str, ship_symbol: str, trade_symbol: str, units: int) -> Dict[str, Any]:
        """Fulfill a contract delivery"""
        return self._make_request("POST", f"my/contracts/{contract_id}/deliver", {
            "shipSymbol": ship_symbol,
            "tradeSymbol": trade_symbol,
            "units": units
        }, headers=self.request_handler.get_headers())

    def extract_resources(self, ship_symbol: str, survey: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract resources from an asteroid or other resource field"""
        payload = {}
        if survey:
            payload["survey"] = survey
        return self._make_request("POST", f"my/ships/{ship_symbol}/extract", payload, headers=self.request_handler.get_headers())

    def scan_ships(self, ship_symbol: str) -> Dict[str, Any]:
        """Scan for nearby ships"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/scan/ships", headers=self.request_handler.get_headers())

    def repair_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Repair ship at a shipyard"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/repair", headers=self.request_handler.get_headers())

    def negotiate_contract(self, ship_symbol: str) -> Dict[str, Any]:
        """Negotiate a new contract"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/negotiate/contract", headers=self.request_handler.get_headers())

    def jump_ship(self, ship_symbol: str, system_symbol: str) -> Dict[str, Any]:
        """Jump ship to another system using a jump gate"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/jump", {
            "systemSymbol": system_symbol
        }, headers=self.request_handler.get_headers())

    def survey_location(self, ship_symbol: str) -> Dict[str, Any]:
        """Survey the current location for better extraction spots"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/survey", headers=self.request_handler.get_headers())

    def get_waypoints(self, system: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """Get list of waypoints in a system"""
        return self._make_request("GET", f"systems/{system}/waypoints?page={page}&limit={limit}", headers=self.request_handler.get_headers())

    def get_systems(self, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """Get list of all systems"""
        return self._make_request("GET", f"systems?page={page}&limit={limit}", headers=self.request_handler.get_headers())

    def get_factions(self) -> Dict[str, Any]:
        """Get list of all factions"""
        return self._make_request("GET", "factions", headers=self.request_handler.get_headers())

    def navigate_ship(self, ship_symbol: str, waypoint_symbol: str) -> Dict[str, Any]:
        """Navigate ship to a waypoint."""
        return self._make_request("POST", f"my/ships/{ship_symbol}/navigate", {
            "waypointSymbol": waypoint_symbol
        }, headers=self.request_handler.get_headers())

    def transfer_cargo(self, ship_symbol: str, trade_symbol: str, units: int, receiving_ship: str) -> Dict[str, Any]:
        """Transfer cargo between ships"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/transfer", {
            "tradeSymbol": trade_symbol,
            "units": units,
            "shipSymbol": receiving_ship
        }, headers=self.request_handler.get_headers())

    def get_system_waypoints(self, system_symbol: str) -> Dict[str, Any]:
        """Get all waypoints in a system"""
        return self._make_request("GET", f"systems/{system_symbol}/waypoints", headers=self.request_handler.get_headers())

    def refuel_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Refuel a ship at a station"""
        return self._make_request("POST", f"my/ships/{ship_symbol}/refuel", headers=self.request_handler.get_headers())

    def get_ship_cooldown(self, ship_symbol: str) -> Dict[str, Any]:
        """Get the ship's cooldown status"""
        return self._make_request("GET", f"my/ships/{ship_symbol}/cooldown", headers=self.request_handler.get_headers())

    def get_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Get details of a specific ship"""
        return self._make_request("GET", f"my/ships/{ship_symbol}", headers=self.request_handler.get_headers())

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
