import os
import sys
import time
import logging
import requests
from typing import Dict, Any, Optional
import json
from dotenv import load_dotenv
from collections import deque
from datetime import datetime, timedelta

class SpaceTradersClient:
    """Client for interacting with SpaceTraders API"""
    
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        load_dotenv()  # Load environment variables from .env file
        self.base_url = os.getenv("SPACETRADERS_API_URL", "https://api.spacetraders.io/v2")
        self.token = os.getenv("SPACETRADERS_TOKEN")
        
        # Rate limiting setup
        self.requests_per_second = 2  # Default to 2 requests per second
        self.request_window = 1.0  # Window in seconds
        self.request_timestamps = deque(maxlen=10)  # Keep track of last 10 requests
        self.burst_limit = 10  # Maximum burst requests
        self.min_request_interval = 1.0 / self.requests_per_second
        
        # If no token is found, try to register a new agent
        if not self.token:
            logging.info("No token found, attempting to register new agent...")
            try:
                # Use a short name to avoid length issues
                agent_name = f"CODEIUM{len(os.listdir('.'))}"
                result = self.register_new_agent(agent_name, "COSMIC")
                if result and result.get("data", {}).get("token"):
                    self.token = result["data"]["token"]
                    logging.info("Successfully registered new agent and saved token")
                else:
                    logging.error("Failed to register new agent: No token received.")
                    sys.exit(1)
            except Exception as e:
                logging.error(f"Failed to register new agent: {str(e)}")
                sys.exit(1)
                
        self.error_count = 0
        self.request_count = 0
        self.last_error_time = None
        self.error_history = []  # List of (timestamp, endpoint) tuples
        self.last_error_reset = time.time()
            
    def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limits"""
        current_time = time.time()
        
        # Clean up old timestamps
        while self.request_timestamps and current_time - self.request_timestamps[0] > self.request_window:
            self.request_timestamps.popleft()
        
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

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests"""
        if not self.token:
            logging.warning("No token available for request. Please register an agent first.")
            raise ValueError("No token available for request. Please register an agent first.")
        auth_token = self.token.strip()
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        return {
            "Authorization": auth_token,
            "Content-Type": "application/json"
        }

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
            logging.error(f"HTTP error on {endpoint}: {error}")
        else:
            logging.error(f"Error on {endpoint}: {error}")

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make a request to the SpaceTraders API with rate limiting and retries."""
        url = f"{self.base_url}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                if method == "GET":
                    response = requests.get(url, headers=headers, timeout=10)
                elif method == "POST":
                    response = requests.post(url, headers=headers, json=data, timeout=10)
                elif method == "PATCH":
                    response = requests.patch(url, headers=headers, json=data, timeout=10)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                if response.status_code == 429:  # Rate limit hit
                    retry_after = int(response.headers.get('Retry-After', retry_delay))
                    logging.warning(f"Rate limit hit, waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logging.warning(f"Request failed: {str(e)}")
                    logging.warning(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logging.error(f"HTTP error on {endpoint}: {str(e)}")
                    raise RuntimeError(f"Failed to connect to SpaceTraders API: {str(e)}")
        
        raise RuntimeError("Maximum retries exceeded with no specific error")

    def register_new_agent(self, symbol: str, faction: str = "COSMIC") -> Dict[str, Any]:
        """Register a new agent and get access token"""
        logging.info(f"Registering new agent {symbol} with faction {faction}")
        response = self._make_request("POST", "register", {
            "symbol": symbol,
            "faction": faction,
            "email": "codeium@example.com"
        })
        # Extract token from data field and store it
        self.token = response.get("data", {}).get("token")
        if not self.token:
            raise ValueError("No token received in registration response")
            
        # Update config.json with the new agent symbol
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            config['agent_symbol'] = symbol
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to update config.json: {str(e)}")
            
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
            logging.error(f"Error checking mining capability: {str(e)}")
            return {"can_mine": False, "reason": f"Error checking mining capability: {str(e)}"}

    def get_shipyard(self, system: str, waypoint: str) -> Dict[str, Any]:
        """Get shipyard data at a waypoint"""
        return self._make_request("GET", f"systems/{system}/waypoints/{waypoint}/shipyard")

    def purchase_ship(self, ship_type: str, waypoint: str) -> Dict[str, Any]:
        """Purchase a ship at a shipyard"""
        return self._make_request("POST", f"my/ships", {
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
        logging.debug(f"Making {method} request to {url}")
        
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
