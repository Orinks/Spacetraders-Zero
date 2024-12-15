import time
import threading
from typing import Dict, Any, List
from api.client import SpaceTradersClient

class AutomatedTrader:
    """Basic automated trading agent"""
    
    def __init__(self, client: SpaceTradersClient, status_callback=None):
        self.client = client
        self.running = False
        self.thread = None
        self.status_callback = status_callback
        self.trade_history = []  # Track successful trades
        self.known_markets = {}  # Cache market data
        self.ship_cargo = {}  # Track cargo per ship
        self.ship_states = {}  # Track ship states
        self.visited_waypoints = set()  # Track explored locations
        self.load_state()
        
    def save_state(self):
        """Save agent state to disk"""
        try:
            state = {
                'trade_history': self.trade_history[-100:],  # Keep last 100 trades
                'known_markets': self.known_markets,
                'visited_waypoints': list(self.visited_waypoints)
            }
            with open('agent_state.json', 'w') as f:
                json.dump(state, f)
        except Exception as e:
            print(f"Failed to save state: {e}")
            
    def load_state(self):
        """Load agent state from disk"""
        try:
            with open('agent_state.json', 'r') as f:
                state = json.load(f)
                self.trade_history = state.get('trade_history', [])
                self.known_markets = state.get('known_markets', {})
                self.visited_waypoints = set(state.get('visited_waypoints', []))
        except FileNotFoundError:
            pass  # No state file yet
        except Exception as e:
            print(f"Failed to load state: {e}")
        
    def start(self):
        """Start the automated trading"""
        self.running = True
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self):
        """Stop the automated trading"""
        self.running = False
        if self.thread:
            self.thread.join()
        self.save_state()  # Save state on shutdown
            
    def _run_loop(self):
        """Main automation loop"""
        while self.running:
            try:
                result = self.run_cycle()
                if self.status_callback:
                    self.status_callback(result)
                time.sleep(5)  # Don't overwhelm the API
            except Exception as e:
                if self.status_callback:
                    self.status_callback({"status": "error", "error": str(e)})
                time.sleep(30)  # Back off on error
        
    def _retry_api_call(self, func, *args, max_attempts=3):
        """Retry an API call with exponential backoff"""
        for attempt in range(max_attempts):
            try:
                return func(*args)
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
                
    def _run_loop(self):
        """Main automation loop"""
        while self.running:
            try:
                result = self.run_cycle()
                if self.status_callback:
                    self.status_callback(result)
                time.sleep(5)  # Don't overwhelm the API
            except Exception as e:
                if self.status_callback:
                    self.status_callback({"status": "error", "error": str(e)})
                time.sleep(30)  # Back off on error
                
    def find_best_trade_route(self, ship_data: Dict[str, Any]) -> Dict[str, Any]:
        """Find most profitable trade route from current location"""
        try:
            current_waypoint = ship_data.get("nav", {}).get("waypointSymbol")
            system = current_waypoint.split('-')[0]
            
            # Get all waypoints in system
            waypoints = self._retry_api_call(self.client.get_waypoints, system)
            markets = [w for w in waypoints.get("data", []) if w.get("type") == "MARKETPLACE"]
            
            best_profit = 0
            best_route = None
            
            # Find most profitable good between any two markets
            for market1 in markets:
                market1_data = self._retry_api_call(self.client.get_market, system, market1["symbol"])
                for good in market1_data.get("data", {}).get("tradeGoods", []):
                    if good.get("supply") == "ABUNDANT":
                        buy_price = good.get("purchasePrice", 0)
                        # Look for best sell price at other markets
                        for market2 in markets:
                            if market2["symbol"] != market1["symbol"]:
                                market2_data = self._retry_api_call(self.client.get_market, system, market2["symbol"])
                                for sell_good in market2_data.get("data", {}).get("tradeGoods", []):
                                    if sell_good["symbol"] == good["symbol"] and sell_good.get("supply") == "SCARCE":
                                        profit = sell_good.get("sellPrice", 0) - buy_price
                                        if profit > best_profit:
                                            best_profit = profit
                                            best_route = {
                                                "buy_market": market1["symbol"],
                                                "sell_market": market2["symbol"],
                                                "good": good["symbol"],
                                                "profit_per_unit": profit
                                            }
            return best_route
        except Exception as e:
            if self.status_callback:
                self.status_callback({"status": "error", "error": f"Route planning error: {str(e)}"})
            return None

    def _update_ship_states(self, ships_data: List[Dict[str, Any]]):
        """Update tracked ship states"""
        for ship in ships_data:
            symbol = ship.get("symbol")
            if symbol:
                self.ship_states[symbol] = {
                    "nav": ship.get("nav", {}),
                    "cargo": ship.get("cargo", {}),
                    "fuel": ship.get("fuel", {})
                }

    def run_cycle(self) -> Dict[str, Any]:
        """Run one cycle of automated trading"""
        if not self.running:
            return {"status": "stopped"}
            
        try:
            # Handle contracts
            contracts = self._retry_api_call(self.client.get_contracts)
            if contracts.get("data"):
                for contract in contracts["data"]:
                    # Accept open contracts
                    if contract["status"] == "OPEN":
                        self._retry_api_call(self.client.accept_contract, contract["id"])
                        return {"status": "accepted_contract", "contract": contract["id"]}
                    # Fulfill accepted contracts
                    elif contract["status"] == "ACTIVE":
                        # Check if we have the required goods
                        for term in contract.get("terms", {}).get("deliver", []):
                            if term["unitsFulfilled"] < term["unitsRequired"]:
                                # Try to fulfill this term
                                for ship_symbol, cargo in self.ship_cargo.items():
                                    if cargo.get("good") == term["tradeSymbol"]:
                                        try:
                                            self._retry_api_call(
                                                self.client.fulfill_contract,
                                                contract["id"],
                                                ship_symbol,
                                                term["tradeSymbol"],
                                                min(cargo.get("units", 0), term["unitsRequired"] - term["unitsFulfilled"])
                                            )
                                            return {"status": "fulfilled_contract", "contract": contract["id"]}
                                        except Exception as e:
                                            print(f"Failed to fulfill contract: {e}")
            
            # Get ship status
            ships = self._retry_api_call(self.client.get_my_ships)
            if not ships.get("data"):
                return {"status": "no_ships"}
                
            # Update ship states
            self._update_ship_states(ships.get("data", []))
                
            # For each ship
            for ship in ships["data"]:
                nav = ship.get("nav", {})
                status = nav.get("status")
                
                # If docked, check for trade opportunities
                if status == "DOCKED":
                    try:
                        # Find best trade route from current location
                        route = self.find_best_trade_route(ship)
                        if route:
                            if nav.get("waypointSymbol") == route["buy_market"]:
                                # Check cargo capacity before buying
                                cargo = ship.get("cargo", {})
                                capacity = cargo.get("capacity", 0)
                                units = cargo.get("units", 0)
                                space_available = capacity - units
                                
                                if space_available >= 10:
                                    # Buy goods at current market
                                    self._retry_api_call(self.client.buy_goods, ship["symbol"], route["good"], 10)
                                    self.ship_cargo[ship["symbol"]] = cargo  # Update cargo tracking
                                    return {"status": "bought_goods", "good": route["good"], "profit_potential": route["profit_per_unit"] * 10}
                                else:
                                    return {"status": "cargo_full"}
                            elif nav.get("waypointSymbol") == route["sell_market"]:
                                # Sell goods at current market
                                self._retry_api_call(self.client.sell_goods, ship["symbol"], route["good"], 10)
                                return {"status": "sold_goods", "good": route["good"]}
                    except Exception as e:
                        print(f"Trading error: {str(e)}")
                
                # If in orbit, look for opportunities
                elif status == "IN_ORBIT":
                    try:
                        # Get current system/waypoint from ship data
                        current_waypoint = nav.get("waypointSymbol")
                        system = current_waypoint.split('-')[0]  # Extract system from waypoint
                        
                        # Check if at an asteroid field
                        waypoint = self._retry_api_call(
                            self.client.get_waypoints, 
                            system, 
                            current_waypoint
                        )
                        if "ASTEROID" in waypoint.get("traits", []):
                            # Try to extract resources
                            try:
                                survey = self._retry_api_call(
                                    self.client.survey_location,
                                    ship["symbol"]
                                )
                                result = self._retry_api_call(
                                    self.client.extract_resources,
                                    ship["symbol"],
                                    survey
                                )
                                return {"status": "extracted_resources"}
                            except Exception as e:
                                # If extraction fails, look for trade opportunities
                                route = self.find_best_trade_route(ship)
                                if route:
                                    if current_waypoint != route["buy_market"]:
                                        self._retry_api_call(self.client.navigate_ship, ship["symbol"], route["buy_market"])
                                        return {"status": "navigating", "destination": route["buy_market"]}
                                    elif current_waypoint != route["sell_market"]:
                                        self._retry_api_call(self.client.navigate_ship, ship["symbol"], route["sell_market"])
                                        return {"status": "navigating", "destination": route["sell_market"]}
                    except Exception as e:
                        print(f"Navigation error: {str(e)}")
            
            return {"status": "idle"}
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
