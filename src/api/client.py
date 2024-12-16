import os
import sys
import time
import logging
import requests
from typing import Dict, Any
from dotenv import load_dotenv

class SpaceTradersClient:
    """Client for interacting with SpaceTraders API"""
    
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        load_dotenv()  # Load environment variables from .env file
        self.base_url = os.getenv("SPACETRADERS_API_URL", "https://api.spacetraders.io/v2")
        self.token = os.getenv("SPACETRADERS_TOKEN")
        
        # If no token is found, try to register a new agent
        if not self.token:
            logging.info("No token found, attempting to register new agent...")
            try:
                # Use a short name to avoid length issues
                agent_name = f"CODEIUM{len(os.listdir('.'))}"
                result = self.register_new_agent(agent_name, "COSMIC")
                if result and result.get("data", {}).get("token"):
                    self.token = result["data"]["token"]
                    # Save token to .env file
                    with open(".env", "w") as f:
                        f.write(f"SPACETRADERS_TOKEN={self.token}\n")
                    logging.info("Successfully registered new agent and saved token")
            except Exception as e:
                logging.error(f"Failed to register new agent: {str(e)}")
                
        self.error_count = 0
        self.request_count = 0
        self.last_error_time = None
        self.error_history = []  # List of (timestamp, endpoint) tuples
            
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests"""
        if not self.token:
            logging.warning("No token available for request. Please register an agent first.")
            raise ValueError("No token available for request. Please register an agent first.")
        # Ensure token has Bearer prefix and strip any whitespace
        auth_token = self.token.strip()
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        logging.debug(f"Using auth token: {auth_token[:15]}...")
        return {
            "Authorization": auth_token,
            "Content-Type": "application/json"
        }
        
    def register_new_agent(self, symbol: str, faction: str = "COSMIC") -> Dict[str, Any]:
        """Register a new agent and get access token"""
        logging.info(f"Registering new agent {symbol} with faction {faction}")
        response = requests.post(
            f"{self.base_url}/register",
            json={
                "symbol": symbol,
                "faction": faction,
                "email": "codeium@example.com"
            },
            headers={
                "Content-Type": "application/json",
                "Version": "v2.2.0",
                "ResetDate": "2024-10-27"
            }
        )
        logging.debug(f"Registration response: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        # Extract token from data field and store it
        self.token = result.get("data", {}).get("token")
        if not self.token:
            raise ValueError("No token received in registration response")
            
        # Save token to .env file
        with open('.env', 'w') as f:
            f.write(f"SPACETRADERS_TOKEN={self.token}\n")
            
        return result

    def get_agent(self) -> Dict[str, Any]:
        """Get current agent details"""
        response = requests.get(
            f"{self.base_url}/my/agent",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
        
    def get_contracts(self) -> Dict[str, Any]:
        """Get available contracts"""
        url = f"{self.base_url}/my/contracts"
        print(f"\nCalling API: GET {url}", file=sys.stderr)
        response = requests.get(
            url,
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
        
    def accept_contract(self, contract_id: str) -> Dict[str, Any]:
        """Accept a contract"""
        response = requests.post(
            f"{self.base_url}/my/contracts/{contract_id}/accept",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
        
    def get_market(self, system: str, waypoint: str) -> Dict[str, Any]:
        """Get market data at a waypoint"""
        response = requests.get(
            f"{self.base_url}/systems/{system}/waypoints/{waypoint}/market",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def buy_goods(self, ship_symbol: str, symbol: str, units: int) -> Dict[str, Any]:
        """Buy goods at current market"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/purchase",
            headers=self._get_headers(),
            json={"symbol": symbol, "units": units}
        )
        response.raise_for_status()
        return response.json()

    def sell_goods(self, ship_symbol: str, symbol: str, units: int) -> Dict[str, Any]:
        """Sell goods at current market"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/sell",
            headers=self._get_headers(),
            json={"symbol": symbol, "units": units}
        )
        response.raise_for_status()
        return response.json()

    def get_my_ships(self) -> Dict[str, Any]:
        """Get list of ships owned by the agent"""
        response = requests.get(
            f"{self.base_url}/my/ships",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def dock_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Dock ship at current waypoint"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/dock",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def orbit_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Move ship into orbit"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/orbit",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def fulfill_contract(self, contract_id: str, ship_symbol: str, trade_symbol: str, units: int) -> Dict[str, Any]:
        """Fulfill a contract delivery"""
        response = requests.post(
            f"{self.base_url}/my/contracts/{contract_id}/deliver",
            headers=self._get_headers(),
            json={
                "shipSymbol": ship_symbol,
                "tradeSymbol": trade_symbol,
                "units": units
            }
        )
        response.raise_for_status()
        return response.json()

    def _retry_api_call(self, func, *args, max_attempts=3):
        """Retry an API call with exponential backoff"""
        last_error = None
        self.request_count += 1
        endpoint = func.__name__ if hasattr(func, '__name__') else 'unknown'
        
        # Check recent error rate for this endpoint
        endpoint_errors = len([t for t, e in self.error_history if e == endpoint and t > time.time() - 300])
        if endpoint_errors > 5:  # If more than 5 errors in last 5 minutes for this endpoint
            logging.warning(f"High error rate for endpoint {endpoint}, increasing backoff")
            time.sleep(10)  # Additional backoff for problematic endpoints
        for attempt in range(max_attempts):
            try:
                logging.debug(f"API call attempt {attempt + 1}/{max_attempts}")
                result = func(*args)
                logging.debug("API call successful")
                return result
            except requests.exceptions.RequestException as e:
                last_error = e
                self.error_count += 1
                self.last_error_time = time.time()
                self.error_history.append((time.time(), endpoint))
                # Keep only last hour of errors
                cutoff = time.time() - 3600
                self.error_history = [(t, e) for t, e in self.error_history if t > cutoff]
                if attempt < max_attempts - 1:
                    # Base exponential backoff modified by error rate
                    base_wait = 2 ** attempt
                    error_rate = (self.error_count / self.request_count * 100) if self.request_count > 0 else 0
                    wait_time = base_wait * (1 + (error_rate / 100))  # Increase wait time as error rate increases
                    logging.warning(f"API call failed, retrying in {wait_time:.1f}s: {str(e)}")
                    time.sleep(wait_time)
                else:
                    logging.error(f"API call failed after {max_attempts} attempts: {str(e)}")
                    raise last_error

    def extract_resources(self, ship_symbol: str, survey: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extract resources from the current location"""
        json_data = {"survey": survey} if survey else {}
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/extract",
            headers=self._get_headers(),
            json=json_data
        )
        response.raise_for_status()
        return response.json()

    def survey_location(self, ship_symbol: str) -> Dict[str, Any]:
        """Survey the current location for better extraction spots"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/survey",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def get_waypoints(self, system: str) -> Dict[str, Any]:
        """Get list of waypoints in a system"""
        response = requests.get(
            f"{self.base_url}/systems/{system}/waypoints",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
        
    def get_systems(self) -> Dict[str, Any]:
        """Get list of all systems"""
        response = requests.get(
            f"{self.base_url}/systems",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
        
    def get_factions(self) -> Dict[str, Any]:
        """Get list of all factions"""
        response = requests.get(
            f"{self.base_url}/factions",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def navigate_ship(self, ship_symbol: str, waypoint: str) -> Dict[str, Any]:
        """Navigate ship to waypoint"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/navigate",
            headers=self._get_headers(),
            json={"waypointSymbol": waypoint}
        )
        if response.status_code != 200:
            logging.error(f"Navigation error: {response.text}")
        response.raise_for_status()
        return response.json()

    def get_ship_cooldown(self, ship_symbol: str) -> Dict[str, Any]:
        """Get the ship's cooldown status"""
        response = requests.get(
            f"{self.base_url}/my/ships/{ship_symbol}/cooldown",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def get_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Get details of a specific ship"""
        response = requests.get(
            f"{self.base_url}/my/ships/{ship_symbol}",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

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
        response = requests.get(
            f"{self.base_url}/systems/{system}/waypoints/{waypoint}/shipyard",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()

    def purchase_ship(self, ship_type: str, waypoint: str) -> Dict[str, Any]:
        """Purchase a new ship at the specified waypoint"""
        response = requests.post(
            f"{self.base_url}/my/ships",
            headers=self._get_headers(),
            json={
                "shipType": ship_type,
                "waypointSymbol": waypoint
            }
        )
        response.raise_for_status()
        return response.json()

    def purchase_ship_mount(self, ship_symbol: str, mount_symbol: str) -> Dict[str, Any]:
        """Purchase and install a mount on a ship"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/mounts",
            headers=self._get_headers(),
            json={"symbol": mount_symbol}
        )
        response.raise_for_status()
        return response.json()

    def get_waypoint(self, system: str, waypoint: str) -> Dict[str, Any]:
        """Get details about a specific waypoint"""
        response = requests.get(
            f"{self.base_url}/systems/{system}/waypoints/{waypoint}",
            headers=self._get_headers()
        )
        if response.status_code != 200:
            logging.error(f"Waypoint error: {response.text}")
        response.raise_for_status()
        return response.json()

    def refuel_ship(self, ship_symbol: str) -> Dict[str, Any]:
        """Refuel ship at current waypoint"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/refuel",
            headers=self._get_headers()
        )
        if response.status_code != 200:
            logging.error(f"Refuel error: {response.text}")
        response.raise_for_status()
        return response.json()

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
        url = f"{self.base_url}{endpoint}"
        logging.debug(f"Making {method} request to {url}")
        
        response = requests.request(
            method=method,
            url=url,
            headers=self._get_headers(),
            params=params,
            json=json_data
        )
        response.raise_for_status()
        return response.json()
