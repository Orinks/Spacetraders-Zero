import time
import threading
import json
import sys
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
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
        if self.running:
            logging.warning("Agent already running")
            return
            
        self.running = True
        if self.status_callback:
            self.status_callback({"status": "starting", "message": f"Starting agent with token: {self.client.token[:8]}..."})
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)  # Wait for old thread to finish
            
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True  # Make thread daemon so it exits when main program exits
        self.thread.start()
        logging.info("Agent thread started")
        
    def stop(self):
        """Stop the automated trading"""
        if not self.running:
            logging.warning("Agent already stopped")
            return
            
        self.running = False
        if self.status_callback:
            self.status_callback({"status": "stopping", "message": "Stopping agent..."})
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)  # Give more time for clean shutdown
            if self.thread.is_alive():
                logging.warning("Agent thread did not stop cleanly")
                
        self.save_state()  # Save state on shutdown
        logging.info("Agent stopped")
        
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
        self.start_time = time.time()
        while self.running:
            try:
                if self.status_callback:
                    self.status_callback({"status": "info", "message": "Checking contracts..."})
                print(f"\nAgent cycle starting...", file=sys.stderr)
                result = self.run_cycle()
                print(f"Cycle result: {result}", file=sys.stderr)
                if result and self.status_callback and result["status"] != "idle":  # Only show meaningful status updates
                    self.status_callback(result)
                if not self.running:
                    break
                time.sleep(5)  # Don't overwhelm the API
            except requests.exceptions.HTTPError as e:
                if self.status_callback:
                    self.status_callback({
                        'status': 'error',
                        'error': str(e)
                    })
                if not self.running:
                    break
                time.sleep(30)  # Back off on error
            except Exception as e:
                if self.status_callback:
                    self.status_callback({
                        'status': 'error',
                        'error': str(e)
                    })
                logging.error(f"Error in trader loop: {str(e)}", exc_info=True)
                if not self.running:
                    break
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
            markets = [w for w in waypoints.get("data", []) 
                      if w.get("type") == "MARKETPLACE"]
            asteroids = [w for w in waypoints.get("data", []) 
                        if w.get("type") == "ASTEROID" and 
                        any(t.get("symbol") == "COMMON_METAL_DEPOSITS" for t in w.get("traits", []))]
            
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

    def _ensure_mining_ship(self) -> Dict[str, Any]:
        """
        Ensure we have a mining ship.
        Returns:
            Dict with status and ship data
        """
        try:
            # Check current ships
            ships = self._retry_api_call(self.client.get_my_ships)
            
            # First check if we have any mining ships
            if ships.get("data"):
                mining_ships = [s for s in ships.get("data", []) 
                              if any(m.get("symbol", "").startswith("MOUNT_MINING_LASER") 
                              for m in s.get("mounts", []))]
                if mining_ships:
                    logging.info(f"Found existing mining ship: {mining_ships[0]['symbol']}")
                    return {"status": "success", "ship": mining_ships[0]}

            # No mining ships, try to purchase one
            # Try mining drone first as it's usually cheapest
            result = self._purchase_ship("SHIP_MINING_DRONE")
            if result["status"] == "success":
                return result

            # If mining drone not available/affordable, try other ships that can be equipped for mining
            mining_capable_ships = [
                "SHIP_LIGHT_HAULER",  # Can be equipped with mining laser
                "SHIP_HEAVY_FREIGHTER"  # Can be equipped with mining laser
            ]

            for ship_type in mining_capable_ships:
                result = self._purchase_ship(ship_type)
                if result["status"] == "success":
                    return result

            return {"status": "error", "message": "Could not acquire any mining capable ships"}

        except Exception as e:
            logging.error(f"Error ensuring mining ship: {e}")
            return {"status": "error", "message": str(e)}

    def _prepare_ship_for_mining(self, ship_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare a ship for mining by:
        1. Finding a market that sells mining equipment
        2. Navigating to that market
        3. Purchasing the equipment
        """
        try:
            ship_symbol = ship_data.get("symbol")
            current_system = ship_data.get("nav", {}).get("systemSymbol")
            
            # Check if ship already has mining equipment
            for mount in ship_data.get("mounts", []):
                if "MINING_LASER" in mount.get("symbol", ""):
                    return {"status": "ready"}
                    
            # Find a market that sells mining equipment
            waypoints = self._retry_api_call(self.client.get_waypoints, current_system)
            markets = [w for w in waypoints.get("data", []) if w.get("type") == "MARKETPLACE"]
            
            for market in markets:
                market_data = self._retry_api_call(
                    self.client.get_market,
                    current_system,
                    market.get("symbol")
                )
                
                # Look for mining equipment in the market
                if market_data.get("data", {}).get("tradeGoods"):
                    for good in market_data["data"]["tradeGoods"]:
                        if "MINING_LASER" in good.get("symbol", ""):
                            # Navigate to market if needed
                            if ship_data.get("nav", {}).get("waypointSymbol") != market.get("symbol"):
                                nav_result = self._retry_api_call(
                                    self.client.navigate_ship,
                                    ship_symbol,
                                    market.get("symbol")
                                )
                                logging.info(f"Navigation result: {nav_result}")
                                
                                # Wait for navigation to complete
                                nav_data = nav_result.get("data", {}).get("nav", {})
                                arrival_time = nav_data.get("route", {}).get("arrival")
                                if arrival_time:
                                    wait_time = max(0, (arrival_time - time.time()) + 1)
                                    logging.info(f"Waiting {wait_time} seconds for navigation to complete...")
                                    time.sleep(wait_time)
                                
                                # Dock at the market
                                self._retry_api_call(
                                    self.client.dock_ship,
                                    ship_symbol
                                )
                                
                            # Purchase mining equipment
                            purchase_result = self._retry_api_call(
                                self.client.purchase_ship_mount,
                                ship_symbol,
                                good.get("symbol")
                            )
                            logging.info(f"Mount purchase result: {purchase_result}")
                            return {"status": "ready"}
                            
            return {"status": "error", "message": "No mining equipment available for purchase"}
            
        except Exception as e:
            logging.error(f"Error preparing ship for mining: {str(e)}")
            return {"status": "error", "message": str(e)}
            
    def _handle_mining_contract(self, contract: Dict[str, Any]) -> None:
        """Handle a mining contract by finding an asteroid field and mining resources"""
        try:
            # Get our ships
            ships = self._retry_api_call(self.client.get_my_ships).get("data", [])
            if not ships:
                # No ships, try to buy one
                purchase_result = self._purchase_mining_ship()
                if purchase_result.get("status") != "success":
                    raise Exception(f"Failed to purchase mining ship: {purchase_result.get('message')}")
                ships = self._retry_api_call(self.client.get_my_ships).get("data", [])
                
            # Get ship location and system
            ship = ships[0]  # We should already have a mining ship
            ship_symbol = ship.get("symbol")
            
            # Log ship details
            logging.info(f"Ship details: {json.dumps(ship, indent=2)}")
            
            # Get contract details
            contract_id = contract.get("id")
            terms = contract.get("terms", {})
            deliver = terms.get("deliver", [{}])[0]
            target_good = deliver.get("tradeSymbol")
            target_units = deliver.get("unitsRequired", 0)
            destination = deliver.get("destinationSymbol")
            
            # Get all waypoints in the current system
            waypoints = self._retry_api_call(self.client.get_waypoints, ship.get("nav", {}).get("systemSymbol"))
            if not waypoints or not waypoints.get("data"):
                raise Exception(f"No waypoints found in system {ship.get('nav', {}).get('systemSymbol')}")
                
            # Log available waypoint types for debugging
            waypoint_types = set(w.get("type") for w in waypoints.get("data", []))
            logging.info(f"Available waypoint types in system {ship.get('nav', {}).get('systemSymbol')}: {waypoint_types}")
            
            # Find asteroid fields
            asteroid_fields = [w for w in waypoints.get("data", [])
                             if w.get("type") in ("ASTEROID", "ENGINEERED_ASTEROID")]
            
            if not asteroid_fields:
                raise Exception(f"No asteroid fields found in system {ship.get('nav', {}).get('systemSymbol')}")
                
            # Find asteroid field with required resource
            target_field = None
            for field in asteroid_fields:
                # Get waypoint details to check traits
                field_details = self._retry_api_call(
                    self.client.get_waypoint,
                    ship.get("nav", {}).get("systemSymbol"),
                    field.get("symbol")
                )
                if field_details and field_details.get("data"):
                    traits = field_details.get("data", {}).get("traits", [])
                    if any(t.get("symbol") == "COMMON_METAL_DEPOSITS" for t in traits):
                        target_field = field
                        break
                        
            if not target_field:
                # If no field with COMMON_METAL_DEPOSITS found, just use current field
                current_waypoint = ship.get("nav", {}).get("waypointSymbol")
                if any(f.get("symbol") == current_waypoint for f in asteroid_fields):
                    target_field = next(f for f in asteroid_fields if f.get("symbol") == current_waypoint)
                else:
                    target_field = asteroid_fields[0]
                
            logging.info(f"Selected asteroid field: {target_field}")
            
            while True:
                # Get current ship status
                ship = self._retry_api_call(self.client.get_ship, ship_symbol).get("data", {})
                nav = ship.get("nav", {})
                current_status = nav.get("status")
                current_waypoint = nav.get("waypointSymbol")
                
                # Handle different ship states
                if current_status == "IN_TRANSIT":
                    # Wait for arrival
                    route = nav.get("route", {})
                    arrival_time = route.get("arrival")
                    if arrival_time:
                        # Parse ISO format timestamp to epoch
                        arrival_epoch = time.mktime(time.strptime(arrival_time.split(".")[0], "%Y-%m-%dT%H:%M:%S"))
                        current_epoch = time.time()
                        wait_time = max(0, arrival_epoch - current_epoch + 1)
                        
                        if wait_time > 0:
                            if self.status_callback:
                                self.status_callback({
                                    "status": "waiting",
                                    "message": f"Waiting {wait_time:.0f}s for arrival at {route.get('destination', {}).get('symbol')}"
                                })
                            time.sleep(wait_time)
                            continue  # Get updated ship status
                            
                # Navigate to asteroid field if needed
                if current_waypoint != target_field.get("symbol"):
                    # First orbit if we're docked
                    if current_status == "DOCKED":
                        logging.info("Orbiting before navigation")
                        self._retry_api_call(self.client.orbit_ship, ship_symbol)
                        continue  # Get updated ship status
                        
                    # Then navigate if we're in orbit
                    if current_status == "IN_ORBIT":
                        # Get destination waypoint details
                        dest_waypoint = self._retry_api_call(
                            self.client.get_waypoint,
                            ship.get("nav", {}).get("systemSymbol"),
                            target_field.get("symbol")
                        ).get("data", {})
                        
                        can_navigate, fuel_needed = self._can_navigate_to(ship, dest_waypoint)
                        
                        if not can_navigate:
                            logging.info(f"Need {fuel_needed} fuel for navigation but only have {ship.get('fuel', {}).get('current', 0)}")
                            # Find nearest fuel station
                            waypoints = self._retry_api_call(
                                self.client.get_waypoints,
                                ship.get("nav", {}).get("systemSymbol")
                            ).get("data", [])
                            fuel_stations = [w for w in waypoints if any(t.get("symbol") == "MARKETPLACE" for t in w.get("traits", []))]
                            
                            if fuel_stations:
                                nearest_station = min(
                                    fuel_stations,
                                    key=lambda w: ((w.get("x", 0) - ship.get("nav", {}).get("route", {}).get("destination", {}).get("x", 0))**2 + 
                                                 (w.get("y", 0) - ship.get("nav", {}).get("route", {}).get("destination", {}).get("y", 0))**2)**0.5
                                )
                                can_reach_station, station_fuel = self._can_navigate_to(ship, nearest_station)
                                
                                if can_reach_station:
                                    logging.info(f"Found reachable fuel station at {nearest_station.get('symbol')}")
                                    # Navigate to fuel station
                                    nav_result = self._retry_api_call(
                                        self.client.navigate_ship,
                                        ship_symbol,
                                        nearest_station.get("symbol")
                                    )
                                    if self.status_callback:
                                        self.status_callback({
                                            "status": "navigating",
                                            "destination": nearest_station.get("symbol"),
                                            "reason": "refueling"
                                        })
                                    continue  # Get updated ship status
                                else:
                                    logging.error(f"Cannot reach any fuel stations. Need {station_fuel} fuel but only have {ship.get('fuel', {}).get('current', 0)}")
                                    raise Exception("Ship stranded without fuel")
                            else:
                                logging.error("No fuel stations found in system")
                                raise Exception("No fuel stations available")
                        
                        # Try to navigate to target field
                        nav_result = self._retry_api_call(
                            self.client.navigate_ship,
                            ship_symbol,
                            target_field.get("symbol")
                        )
                        if self.status_callback:
                            self.status_callback({
                                "status": "navigating",
                                "destination": target_field.get("symbol")
                            })
                        continue  # Get updated ship status
                    
                # Enter orbit if needed
                if current_status != "IN_ORBIT":
                    logging.info("Entering orbit")
                    self._retry_api_call(self.client.orbit_ship, ship_symbol)
                    continue  # Get updated ship status
                    
                # Check if we can mine
                mining_check = self._retry_api_call(self.client.can_ship_mine, ship_symbol)
                if not mining_check.get("can_mine"):
                    if "cooldown" in mining_check.get("reason", "").lower():
                        # Get cooldown details
                        cooldown = self._retry_api_call(self.client.get_ship_cooldown, ship_symbol).get("data", {})
                        if cooldown:
                            wait_time = cooldown.get("remainingSeconds", 0)
                            if wait_time > 0:
                                if self.status_callback:
                                    self.status_callback({
                                        "status": "cooling_down",
                                        "message": f"Waiting {wait_time}s for cooldown"
                                    })
                                time.sleep(wait_time)
                                continue
                    else:
                        raise Exception(f"Cannot mine: {mining_check.get('reason')}")
                
                # Extract resources
                extract_result = self._retry_api_call(self.client.extract_resources, ship_symbol)
                if extract_result.get("data"):
                    if self.status_callback:
                        self.status_callback({
                            "status": "mining",
                            "result": extract_result.get("data")
                        })
                    
                    # Check if we have enough of the target resource
                    cargo = extract_result.get("data", {}).get("cargo", {})
                    inventory = cargo.get("inventory", [])
                    target_resource = next(
                        (item for item in inventory if item.get("symbol") == target_good),
                        None
                    )
                    
                    if target_resource and target_resource.get("units", 0) >= target_units:
                        # We have enough, deliver to destination
                        if current_waypoint != destination:
                            # First orbit if we're docked
                            if current_status == "DOCKED":
                                logging.info("Orbiting before navigation")
                                self._retry_api_call(self.client.orbit_ship, ship_symbol)
                                continue  # Get updated ship status
                                
                            # Then navigate if we're in orbit
                            if current_status == "IN_ORBIT":
                                # Get destination waypoint details
                                dest_waypoint = self._retry_api_call(
                                    self.client.get_waypoint,
                                    ship.get("nav", {}).get("systemSymbol"),
                                    destination
                                ).get("data", {})
                                
                                can_navigate, fuel_needed = self._can_navigate_to(ship, dest_waypoint)
                                
                                if not can_navigate:
                                    logging.info(f"Need {fuel_needed} fuel for navigation but only have {ship.get('fuel', {}).get('current', 0)}")
                                    # Find nearest fuel station
                                    waypoints = self._retry_api_call(
                                        self.client.get_waypoints,
                                        ship.get("nav", {}).get("systemSymbol")
                                    ).get("data", [])
                                    fuel_stations = [w for w in waypoints if any(t.get("symbol") == "MARKETPLACE" for t in w.get("traits", []))]
                                    
                                    if fuel_stations:
                                        nearest_station = min(
                                            fuel_stations,
                                            key=lambda w: ((w.get("x", 0) - ship.get("nav", {}).get("route", {}).get("destination", {}).get("x", 0))**2 + 
                                                         (w.get("y", 0) - ship.get("nav", {}).get("route", {}).get("destination", {}).get("y", 0))**2)**0.5
                                        )
                                        can_reach_station, station_fuel = self._can_navigate_to(ship, nearest_station)
                                        
                                        if can_reach_station:
                                            logging.info(f"Found reachable fuel station at {nearest_station.get('symbol')}")
                                            # Navigate to fuel station
                                            nav_result = self._retry_api_call(
                                                self.client.navigate_ship,
                                                ship_symbol,
                                                nearest_station.get("symbol")
                                            )
                                            if self.status_callback:
                                                self.status_callback({
                                                    "status": "navigating",
                                                    "destination": nearest_station.get("symbol"),
                                                    "reason": "refueling"
                                                })
                                            continue  # Get updated ship status
                                        else:
                                            logging.error(f"Cannot reach any fuel stations. Need {station_fuel} fuel but only have {ship.get('fuel', {}).get('current', 0)}")
                                            raise Exception("Ship stranded without fuel")
                                    else:
                                        logging.error("No fuel stations found in system")
                                        raise Exception("No fuel stations available")
                                
                                # Try to navigate to destination
                                nav_result = self._retry_api_call(
                                    self.client.navigate_ship,
                                    ship_symbol,
                                    destination
                                )
                                if self.status_callback:
                                    self.status_callback({
                                        "status": "navigating",
                                        "destination": destination
                                    })
                                continue  # Get updated ship status
                        
                        # Dock at destination if needed
                        if current_status != "DOCKED":
                            self._retry_api_call(self.client.dock_ship, ship_symbol)
                        
                        # Deliver goods
                        deliver_result = self._retry_api_call(
                            self.client.fulfill_contract,
                            contract_id,
                            ship_symbol,
                            target_good,
                            target_units
                        )
                        if deliver_result.get("data"):
                            if self.status_callback:
                                self.status_callback({
                                    "status": "delivered_contract",
                                    "contract": contract_id,
                                    "good": target_good,
                                    "units": target_units
                                })
                            return
                
                # Handle mining cooldown
                cooldown = extract_result.get("data", {}).get("cooldown", {})
                if cooldown:
                    wait_time = cooldown.get("remainingSeconds", 0)
                    if wait_time > 0:
                        if self.status_callback:
                            self.status_callback({
                                "status": "cooling_down",
                                "message": f"Waiting {wait_time}s for cooldown"
                            })
                        time.sleep(wait_time)
                        
        except Exception as e:
            if self.status_callback:
                self.status_callback({
                    "status": "error",
                    "error": f"Mining error: {str(e)}"
                })
            logging.error(f"Error in mining contract: {str(e)}", exc_info=True)

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
            markets = [w for w in waypoints.get("data", []) 
                      if any(t.get("symbol") == "MARKETPLACE" for t in w.get("traits", []))]
            return markets[0] if markets else None
        except Exception as e:
            print(f"Error finding nearest market: {e}")
            return None

    def _refuel_ship(self, ship_symbol: str, current_waypoint: str) -> None:
        """Refuel ship at current waypoint if possible"""
        try:
            # First dock if needed
            ship = self._retry_api_call(self.client.get_ship, ship_symbol).get("data", {})
            if ship.get("nav", {}).get("status") != "DOCKED":
                self._retry_api_call(self.client.dock_ship, ship_symbol)
                
            # Then refuel
            refuel_result = self._retry_api_call(self.client.refuel_ship, ship_symbol)
            if refuel_result:
                logging.info(f"Refueled ship at {current_waypoint}")
                return True
        except Exception as e:
            logging.error(f"Error refueling: {str(e)}")
        return False

    def _can_navigate_to(self, ship_data: Dict[str, Any], destination: Dict[str, Any]) -> Tuple[bool, int]:
        """
        Check if ship has enough fuel to navigate to destination.
        Returns (can_navigate, fuel_required)
        """
        current_x = ship_data.get("nav", {}).get("route", {}).get("destination", {}).get("x", 0)
        current_y = ship_data.get("nav", {}).get("route", {}).get("destination", {}).get("y", 0)
        dest_x = destination.get("x", 0)
        dest_y = destination.get("y", 0)
        
        # Calculate distance
        distance = ((dest_x - current_x) ** 2 + (dest_y - current_y) ** 2) ** 0.5
        
        # Estimate fuel required (this is a rough estimate)
        fuel_required = int(distance)
        fuel_available = ship_data.get("fuel", {}).get("current", 0)
        
        return fuel_available >= fuel_required, fuel_required

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

            # First check for contracts
            try:
                contracts = self._retry_api_call(self.client.get_contracts)
                if not contracts or "data" not in contracts:
                    logging.error("Failed to get contracts data")
                    return {"status": "error", "error": "Failed to get contracts data"}
                    
                active_contracts = [c for c in contracts.get("data", []) 
                                  if c.get("accepted") and not c.get("fulfilled")]

                # Accept a new contract if we don't have any
                if not active_contracts:
                    available_contracts = [c for c in contracts.get("data", []) 
                                        if not c.get("accepted")]
                    if available_contracts:
                        contract = available_contracts[0]
                        accept_result = self._retry_api_call(self.client.accept_contract, contract["id"])
                        if accept_result and accept_result.get("data"):
                            active_contracts = [contract]
                            logging.info(f"Accepted new contract: {contract['id']}")
                        else:
                            logging.error("Failed to accept contract")
                            return {"status": "error", "error": "Failed to accept contract"}
                    else:
                        logging.info("No contracts available")
                        return {"status": "idle", "message": "No contracts available"}
                        
            except Exception as e:
                logging.error(f"Error getting contracts: {str(e)}")
                return {"status": "error", "error": f"Error getting contracts: {str(e)}"}

            # Then ensure we have a mining ship
            mining_ship_result = self._ensure_mining_ship()
            if mining_ship_result["status"] == "error":
                logging.error(f"Mining ship error: {mining_ship_result['message']}")
                return mining_ship_result
            elif mining_ship_result["status"] == "success":
                logging.info("Mining ship ready")

            # If we have both a contract and a mining ship, start mining
            if active_contracts and mining_ship_result["status"] == "success":
                ship = mining_ship_result["ship"]
                contract = active_contracts[0]
                return self._handle_mining_contract(contract)

            return {"status": "idle"}

        except Exception as e:
            logging.error(f"Error in agent cycle: {str(e)}")
            if self.status_callback:
                self.status_callback({"status": "error", "error": str(e)})
            return {"status": "error", "error": str(e)}

    def _purchase_ship(self, ship_type: str, system: str = None) -> Dict[str, Any]:
        """
        Purchase a specific type of ship.
        Args:
            ship_type: The type of ship to purchase (e.g. 'SHIP_MINING_DRONE')
            system: Optional system to purchase in. If None, uses current system or HQ
        Returns:
            Dict with status and ship data if successful
        """
        try:
            # Get agent details to check credits
            agent = self._retry_api_call(self.client.get_agent)
            credits = agent.get("data", {}).get("credits", 0)
            logging.info(f"Agent has {credits} credits available")

            # Get system to search in
            if not system:
                headquarters = agent.get("data", {}).get("headquarters", "")
                system = headquarters.split("-")[0:2]  # Get X1-FY5 instead of just X1
                system = "-".join(system) if system else None
            if not system:
                return {"status": "error", "message": "Could not determine system"}

            logging.info(f"Searching for ships in system {system}")

            # Find shipyards in the system
            waypoints = self._retry_api_call(self.client.get_waypoints, system)
            shipyards = [w for w in waypoints.get("data", []) 
                       if any(t.get("symbol") == "SHIPYARD" for t in w.get("traits", []))]

            if not shipyards:
                return {"status": "error", "message": f"No shipyards found in system {system}"}

            # Try each shipyard until we find one with our desired ship
            for shipyard in shipyards:
                shipyard_data = self._retry_api_call(
                    self.client.get_shipyard, 
                    system, 
                    shipyard["symbol"]
                )

                ships_for_sale = shipyard_data.get("data", {}).get("ships", [])
                available_ships = [s for s in ships_for_sale 
                                if s.get("type") == ship_type and 
                                s.get("purchasePrice", float('inf')) <= credits]

                if available_ships:
                    # Found a ship we can afford, purchase it
                    result = self._retry_api_call(
                        self.client.purchase_ship,
                        ship_type,
                        shipyard["symbol"]
                    )

                    if result:
                        ship_data = result.get("data", {})
                        logging.info(f"Successfully purchased {ship_type}: {ship_data.get('symbol')}")
                        return {"status": "success", "ship": ship_data}

            return {"status": "error", "message": f"No affordable {ship_type} ships found in system {system}"}

        except Exception as e:
            logging.error(f"Error purchasing ship: {e}")
            return {"status": "error", "message": str(e)}

    def run(self):
        """Run the automated trader"""
        try:
            # Check if we have any active contracts
            contracts = self._retry_api_call(self.client.get_contracts)
            if not contracts or not contracts.get("data"):
                # No contracts, try to get a new one
                self._get_new_contract()
                return
            
            # Handle the first contract
            contract = contracts["data"][0]
            if contract["type"] == "MINING":
                try:
                    self._handle_mining_contract(contract)
                except Exception as e:
                    logging.error(f"Error in mining contract: {str(e)}")
                    # Stop running to prevent excessive API calls
                    raise Exception("Stopping agent due to error") from e
            else:
                logging.info(f"Unsupported contract type: {contract['type']}")
                
        except Exception as e:
            logging.error(f"Error in trader run: {str(e)}")
            # Stop running to prevent excessive API calls
            raise
