import os
import requests
from typing import Dict, Any

class SpaceTradersClient:
    """Client for interacting with SpaceTraders API"""
    
    def __init__(self):
        self.base_url = "https://api.spacetraders.io/v2"
        self.token = os.getenv("SPACETRADERS_TOKEN")
            
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
    def register_new_agent(self, symbol: str, faction: str = "COSMIC") -> Dict[str, Any]:
        """Register a new agent and get access token"""
        response = requests.post(
            f"{self.base_url}/register",
            json={"symbol": symbol, "faction": faction}
        )
        response.raise_for_status()
        result = response.json()
        self.token = result.get("token")  # Store token for future requests
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
        response = requests.get(
            f"{self.base_url}/my/contracts",
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

    def navigate_ship(self, ship_symbol: str, waypoint: str) -> Dict[str, Any]:
        """Navigate ship to waypoint"""
        response = requests.post(
            f"{self.base_url}/my/ships/{ship_symbol}/navigate",
            headers=self._get_headers(),
            json={"waypointSymbol": waypoint}
        )
        response.raise_for_status()
        return response.json()
