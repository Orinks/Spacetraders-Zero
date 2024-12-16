import os
import sys
import time
import logging
import requests
from typing import Dict, Any

class SpaceTradersClient:
    """Client for interacting with SpaceTraders API"""
    
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.base_url = os.getenv("SPACETRADERS_API_URL", "https://api.spacetraders.io/v2")
        self.token = os.getenv("SPACETRADERS_TOKEN")
        self.error_count = 0
        self.request_count = 0
        self.last_error_time = None
        self.error_history = []  # List of (timestamp, endpoint) tuples
            
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests"""
        if not self.token:
            logging.warning("No token available for request. Please register an agent first.")
            raise ValueError("No token available for request. Please register an agent first.")
        # Ensure token has Bearer prefix
        auth_token = self.token if self.token.startswith("Bearer ") else f"Bearer {self.token}"
        logging.debug(f"Using auth token: {auth_token[:8]}...")
        return {
            "Authorization": auth_token,
            "Content-Type": "application/json"
        }
        
    def register_new_agent(self, symbol: str, faction: str = "COSMIC") -> Dict[str, Any]:
        """Register a new agent and get access token"""
        logging.info(f"Registering new agent {symbol} with faction {faction}")
        response = requests.post(
            f"{self.base_url}/register",
            json={"symbol": symbol, "faction": faction}
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
        response.raise_for_status()
        return response.json()

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
