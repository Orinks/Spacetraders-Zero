import time
import threading
import json
import sys
from typing import Dict, Any, List, Optional
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
        self.market_trends = {}  # Track price history per good
        self.ship_cargo = {}  # Track cargo per ship
        self.ship_states = {}  # Track ship states
        self.visited_waypoints = set()  # Track explored locations
        self.cycle_count = 0  # Track number of cycles
        
        # Mining metrics
        self.mining_attempts = 0
        self.mining_successes = 0
        
        # Performance metrics
        self.total_profits = 0
        self.trades_completed = 0
        self.failed_trades = 0
        self.start_time = None
        
        self.load_state()
        logging.info("Automated trader initialized")
        
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
        if self.status_callback:
            self.status_callback({"status": "starting", "message": f"Starting agent with token: {self.client.token[:8]}..."})
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self):
        """Stop the automated trading"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)  # Add timeout to prevent hanging
        self.save_state()  # Save state on shutdown
            
    def _retry_api_call(self, func, *args, max_attempts=3):
        """Retry an API call with exponential backoff"""
        for attempt in range(max_attempts):
            try:
                return func(*args)
            except Exception as e:
                if attempt == max_attempts - 1:
                    # If we've hit max retries, back off for longer
                    if self.client.error_count > 10:  # High error rate
                        time.sleep(30)  # Longer backoff when errors are high
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
                
    def _run_loop(self):
        """Main automation loop"""
        while self.running:
            try:
                if self.status_callback:
                    self.status_callback({"status": "info", "message": "Checking contracts..."})
                print(f"\nAgent cycle starting...", file=sys.stderr)
                result = self.run_cycle()
                print(f"Cycle result: {result}", file=sys.stderr)
                if result and self.status_callback:  # Only callback if we have a result
                    self.status_callback(result)
                time.sleep(5)  # Don't overwhelm the API
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    if self.status_callback:
                        self.status_callback({"status": "error", "error": "Authentication failed. Please register or check your token."})
                    self.stop()  # Stop the agent on auth failure
                    break
                if self.status_callback:
                    self.status_callback({"status": "error", "error": str(e)})
                time.sleep(30)  # Back off on error
            except Exception as e:
                if self.status_callback:
                    self.status_callback({"status": "error", "error": str(e)})
                time.sleep(30)  # Back off on error
                
    def _update_market_trends(self, market_symbol: str, good_symbol: str, price: int):
        """Track price history for market analysis"""
        if market_symbol not in self.market_trends:
            self.market_trends[market_symbol] = {}
        if good_symbol not in self.market_trends[market_symbol]:
            self.market_trends[market_symbol][good_symbol] = []
        self.market_trends[market_symbol][good_symbol].append((time.time(), price))
        # Keep only last 24 hours of data
        cutoff = time.time() - (24 * 60 * 60)
        self.market_trends[market_symbol][good_symbol] = [
            (t, p) for t, p in self.market_trends[market_symbol][good_symbol] 
            if t > cutoff
        ]

    def find_best_trade_route(self, ship_data: Dict[str, Any]) -> Dict[str, Any]:
        """Find most profitable trade route from current location"""
        try:
            nav = ship_data.get("nav", {})
            current_waypoint = nav.get("waypointSymbol")
            if not current_waypoint:
                logging.debug("No current waypoint found for ship")
                return None
            system = nav.get("systemSymbol")  # Use system from nav data
            if not system:
                return None
            
            # Get all waypoints in system
            waypoints = self._retry_api_call(self.client.get_waypoints, system)
            print(f"Available waypoints: {waypoints}", file=sys.stderr)
            markets = [w for w in waypoints.get("data", []) if w.get("type") == "MARKETPLACE"]
            asteroids = [w for w in waypoints.get("data", []) 
                        if w.get("type") == "ASTEROID" and 
                        any(t.get("symbol") == "COMMON_METAL_DEPOSITS" for t in w.get("traits", []))]
            print(f"Found {len(asteroids)} asteroid fields with metal deposits", file=sys.stderr)
            
            best_profit = 0
            best_route = None
            
            # Find most profitable good between any two markets
            for market1 in markets:
                # Get market data for all markets
                market1_data = self._retry_api_call(self.client.get_market, system, market1["symbol"])
                logging.debug(f"Analyzing market at {market1['symbol']}")
                for good in market1_data.get("data", {}).get("tradeGoods", []):
                    # Check supply levels for potential profit
                    supply_level = good.get("supply")
                    buy_price = good.get("purchasePrice", 0)
                    self._update_market_trends(market1["symbol"], good["symbol"], buy_price)
                    # Look for best sell price at other markets
                    for market2 in markets:
                        if market2["symbol"] != market1["symbol"]:
                            market2_data = self._retry_api_call(self.client.get_market, system, market2["symbol"])
                            for sell_good in market2_data.get("data", {}).get("tradeGoods", []):
                                if sell_good["symbol"] == good["symbol"]:
                                        profit = sell_good.get("sellPrice", 0) - buy_price
                                        
                                        # Check price trends for stability
                                        trend_data = self.market_trends.get(market2["symbol"], {}).get(good["symbol"], [])
                                        if trend_data:
                                            # Only consider trades where sell price has been stable or increasing
                                            recent_prices = [p for t, p in trend_data[-5:]]  # Last 5 price points
                                            if len(recent_prices) >= 2:
                                                price_stable = all(p2 >= p1 for p1, p2 in zip(recent_prices, recent_prices[1:]))
                                                if price_stable and profit > best_profit:
                                                    best_profit = profit
                                                    best_route = {
                                                        "buy_market": market1["symbol"],
                                                        "sell_market": market2["symbol"],
                                                        "good": good["symbol"],
                                                        "profit_per_unit": profit,
                                                        "supply_level": supply_level,
                                                        "total_potential_profit": profit * min(space_available, 10)
                                                    }
                                            logging.info(f"Found better trade route: {best_route}")
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

    def _find_nearest_market(self, ship_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find the nearest market to trade at"""
        try:
            nav = ship_data.get("nav", {})
            current_waypoint = nav.get("waypointSymbol")
            if not current_waypoint:
                return None
            system = nav.get("systemSymbol")  # Use system from nav data instead of parsing
            if not system:
                return None
            
            # Get all waypoints in system
            waypoints = self._retry_api_call(self.client.get_waypoints, system)
            return next((w for w in waypoints.get("data", []) if w.get("type") == "MARKETPLACE"), None)
        except Exception as e:
            print(f"Error finding nearest market: {e}")
            return None

    def run_cycle(self) -> Dict[str, Any]:
        """Run one cycle of automated trading"""
        if not self.running:
            logging.debug("Agent cycle skipped - agent not running")
            return {"status": "stopped"}
        
        # Check error rate before proceeding
        error_rate = (self.client.error_count / self.client.request_count * 100) if self.client.request_count > 0 else 0
        if error_rate > 20:  # Pause if error rate exceeds 20%
            logging.warning(f"Pausing agent due to high error rate: {error_rate:.1f}%")
            return {"status": "paused_high_errors"}
            
        logging.debug("Starting agent cycle")
            
        try:
            # Get current status once at start of cycle
            if self.status_callback:
                self.status_callback({"status": "info", "message": "Checking status..."})

            # Check for mining opportunities
            ships = self._retry_api_call(self.client.get_my_ships)
            if ships.get("data"):
                for ship in ships["data"]:
                    nav = ship.get("nav", {})
                    if nav.get("status") == "IN_ORBIT":
                        # Check if we're at an asteroid
                        current_waypoint = nav.get("waypointSymbol")
                        if current_waypoint:
                            waypoints = self._retry_api_call(self.client.get_waypoints, nav.get("systemSymbol"))
                            current_wp_data = next((w for w in waypoints.get("data", []) 
                                                  if w.get("symbol") == current_waypoint 
                                                  and w.get("type") == "ASTEROID"), None)
                            if current_wp_data:
                                try:
                                    self.mining_attempts += 1
                                    result = self._retry_api_call(self.client.extract_resources, ship["symbol"])
                                    if result:
                                        self.mining_successes += 1
                                        return {"status": "mining", "ship": ship["symbol"], "result": result}
                                except Exception as e:
                                    if "cooldown" not in str(e).lower():  # Ignore cooldown errors
                                        print(f"Mining error: {e}", file=sys.stderr)
                
            # Only check contracts if we have cargo to potentially fulfill them
            if any(self.ship_cargo.values()):
                contracts = self._retry_api_call(self.client.get_contracts)
                print(f"Contracts response: {contracts}", file=sys.stderr)
                
                if contracts.get("data"):
                    for contract in contracts["data"]:
                        # Accept open contracts
                        if not contract["accepted"]:  # Changed from status to accepted
                            self._retry_api_call(self.client.accept_contract, contract["id"])
                            return {"status": "accepted_contract", "contract": contract["id"]}
                        # Fulfill accepted contracts
                        elif contract["accepted"] and not contract["fulfilled"]:
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
            
            # For each ship, try to find mining or trading opportunities 
            for ship in ships.get("data", []):
                try:
                    # Check mining success rate to decide strategy
                    mining_success_rate = (self.mining_successes / self.mining_attempts * 100) if self.mining_attempts > 0 else 0
                    
                    # Prioritize mining if success rate is good (>50%)
                    if mining_success_rate > 50:
                        nav = ship.get("nav", {})
                        nav_status = nav.get("status")
                        system = nav.get("systemSymbol")
                        if system and nav_status not in ("IN_TRANSIT", "IN_ORBIT"):
                            waypoints = self._retry_api_call(self.client.get_waypoints, system)
                            asteroids = [w for w in waypoints.get("data", []) 
                                       if w.get("type") == "ASTEROID"]
                            if asteroids:
                                # Navigate to first asteroid found
                                result = self._retry_api_call(
                                    self.client.navigate_ship,
                                    ship["symbol"],
                                    asteroids[0]["symbol"]
                                )
                                if result:
                                    return {"status": "navigating", "destination": asteroids[0]["symbol"]}
                    
                    # Try trading if mining not viable or no asteroids found
                    route = self.find_best_trade_route(ship)
                    if route:
                        nav = ship.get("nav", {})
                        current_waypoint = nav.get("waypointSymbol")
                        
                        if current_waypoint == route["buy_market"]:
                            # Buy goods if we have space
                            cargo = ship.get("cargo", {})
                            space_available = cargo.get("capacity", 0) - cargo.get("units", 0)
                            if space_available >= 10:
                                result = self._retry_api_call(
                                    self.client.buy_goods, 
                                    ship["symbol"], 
                                    route["good"], 
                                    10
                                )
                                if result:
                                    self.trades_completed += 1
                                    continue  # Move to next ship
                                else:
                                    self.failed_trades += 1
                        elif current_waypoint == route["sell_market"]:
                            # Sell goods if we have them
                            cargo = ship.get("cargo", {})
                            if cargo.get("units", 0) > 0:
                                result = self._retry_api_call(
                                    self.client.sell_goods,
                                    ship["symbol"],
                                    route["good"],
                                    cargo.get("units", 0)
                                )
                                if result:
                                    profit = result.get("data", {}).get("transaction", {}).get("totalPrice", 0)
                                    self.total_profits += profit
                                    self.trades_completed += 1
                                    continue  # Move to next ship
                                else:
                                    self.failed_trades += 1
                        else:
                            # Navigate to buy location if not already there
                            result = self._retry_api_call(
                                self.client.navigate_ship,
                                ship["symbol"],
                                route["buy_market"]
                            )
                            if result:
                                continue  # Move to next ship
                except Exception as e:
                    print(f"Error executing trade for ship {ship['symbol']}: {e}", file=sys.stderr)
                    continue
            
            # Get ship status
            if self.status_callback:
                self.status_callback({"status": "info", "message": "Checking ship status..."})
            print(f"Checking ships...", file=sys.stderr)
            ships = self._retry_api_call(self.client.get_my_ships)
            print(f"Ships response: {ships}", file=sys.stderr)
            if not ships.get("data"):
                return {"status": "no_ships"}
                
            # Update ship states
            self._update_ship_states(ships.get("data", []))
                
            # For each ship
            for ship in ships["data"]:
                nav = ship.get("nav", {})
                nav_status = nav.get("status")  # API uses 'status' for navigation state
                print(f"Ship {ship['symbol']} status: {nav_status}", file=sys.stderr)
                
                # If docked, first try to orbit to prepare for actions
                if nav_status == "DOCKED":
                    try:
                        print(f"Attempting to orbit ship {ship['symbol']}", file=sys.stderr)
                        self._retry_api_call(self.client.orbit_ship, ship["symbol"])
                        continue  # Move to next ship or let it take actions on next cycle
                        # Otherwise look for trade routes
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
                
                # If in orbit, look for trade opportunities first
                elif nav_status == "IN_ORBIT":
                    try:
                        route = self.find_best_trade_route(ship)
                        print(f"Found route: {route}", file=sys.stderr)  # Debug print
                        if route:
                            nav = ship.get("nav", {})
                            current_waypoint = nav.get("waypointSymbol")
                            if current_waypoint != route["buy_market"]:
                                print(f"Navigating to buy market {route['buy_market']}", file=sys.stderr)  # Debug print
                                result = self._retry_api_call(
                                    self.client.navigate_ship,
                                    ship["symbol"],
                                    route["buy_market"]
                                )
                                if result:
                                    return {"status": "navigating", "destination": route["buy_market"]}
                            elif current_waypoint != route["sell_market"]:
                                print(f"Navigating to sell market {route['sell_market']}", file=sys.stderr)  # Debug print
                                result = self._retry_api_call(
                                    self.client.navigate_ship,
                                    ship["symbol"],
                                    route["sell_market"]
                                )
                                if result:
                                    return {"status": "navigating", "destination": route["sell_market"]}
                    except Exception as e:
                        print(f"Navigation error: {str(e)}")
            
            self.cycle_count += 1
            return {"status": "idle"}
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
