import time
import threading
import json
import sys
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
from src.api.client import SpaceTradersClient

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
        
    def _get_current_state(self) -> dict:
        """Get the current state as a dictionary."""
        return {
            'trade_history': self.trade_history[-100:],  # Keep last 100 trades
            'known_markets': self.known_markets,
            'visited_waypoints': list(self.visited_waypoints),
            'market_trends': self.market_trends,
            'total_profits': self.total_profits,
            'trades_completed': self.trades_completed,
            'failed_trades': self.failed_trades,
            'mining_attempts': self.mining_attempts,
            'mining_successes': self.mining_successes,
            'cycle_count': self.cycle_count,
            'last_update': time.time()
        }

    def save_state(self):
        """Save agent state to database"""
        try:
            if not hasattr(self, 'state_manager'):
                from persistence import StateManager
                self.state_manager = StateManager()
            
            state = self._get_current_state()
            self.state_manager.save_state(state)
            logging.debug("State saved successfully")
        except Exception as e:
            logging.error(f"Failed to save state: {e}")
            
    def load_state(self):
        """Load agent state from database"""
        try:
            if not hasattr(self, 'state_manager'):
                from persistence import StateManager
                self.state_manager = StateManager()
            
            state = self.state_manager.get_latest_state()
            if state:
                self.trade_history = state.get('trade_history', [])
                self.known_markets = state.get('known_markets', {})
                self.visited_waypoints = set(state.get('visited_waypoints', []))
                self.market_trends = state.get('market_trends', {})
                self.total_profits = state.get('total_profits', 0)
                self.trades_completed = state.get('trades_completed', 0)
                self.failed_trades = state.get('failed_trades', 0)
                self.mining_attempts = state.get('mining_attempts', 0)
                self.mining_successes = state.get('mining_successes', 0)
                self.cycle_count = state.get('cycle_count', 0)
                logging.info("State loaded successfully")
        except Exception as e:
            logging.error(f"Failed to load state: {e}")
        
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
        
        # Final state save and cleanup
        self.save_state()
        if hasattr(self, 'state_manager'):
            self.state_manager.stop()  # Stop periodic saves
            self.state_manager.cleanup_old_states()  # Clean up old states
        
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
            system = nav.get("systemSymbol")  # Use system from nav data instead of parsing
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
                      if w.get("type") == "MARKETPLACE"]
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
        self.cycle_count += 1
        
        # Save state every 10 cycles
        if self.cycle_count % 10 == 0:
            self.save_state()

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
            if not mining_ship_result["success"]:
                logging.error(f"Mining ship error: {mining_ship_result.get('error')}")
                return {"status": "error", "error": mining_ship_result.get('error')}
            else:
                logging.info("Mining ship ready")

            # If we have both a contract and a mining ship, start mining
            if active_contracts and mining_ship_result["success"]:
                ship = mining_ship_result["ship"]
                contract = active_contracts[0]
                return self._handle_mining_contract(contract)

            return {"status": "idle"}

        except Exception as e:
            logging.error(f"Error in agent cycle: {str(e)}")
            if self.status_callback:
                self.status_callback({"status": "error", "error": str(e)})
            return {"status": "error", "error": str(e)}

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

    def _extract_resources(self, ship_symbol: str, survey: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract resources from an asteroid or other resource field
        Args:
            ship_symbol: The symbol of the ship to extract with
            survey: Optional survey data to target specific deposits
        Returns:
            Dict with extraction results
        """
        try:
            result = self._retry_api_call(self.client.extract_resources, ship_symbol, survey)
            if result.get("data"):
                self.mining_attempts += 1
                self.mining_successes += 1
                extraction = result["data"].get("extraction", {})
                logging.info(f"Successfully extracted {extraction.get('yield', {}).get('units')} units of {extraction.get('yield', {}).get('symbol')}")
            return result
        except Exception as e:
            self.mining_attempts += 1
            logging.error(f"Failed to extract resources: {e}")
            return {"error": str(e)}

    def _scan_for_threats(self, ship_symbol: str) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Scan the area for potential threats
        Args:
            ship_symbol: The symbol of the ship to scan with
        Returns:
            Tuple of (is_safe, detected_ships)
        """
        try:
            result = self._retry_api_call(self.client.scan_ships, ship_symbol)
            if result.get("data", {}).get("ships"):
                ships = result["data"]["ships"]
                # Check for hostile ships (pirates, etc)
                threats = [s for s in ships if s.get("registration", {}).get("factionSymbol") == "PIRATES"]
                return (len(threats) == 0, ships)
            return (True, [])
        except Exception as e:
            logging.error(f"Failed to scan for threats: {e}")
            return (False, [])

    def _negotiate_new_contract(self, ship_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Negotiate a new contract at the current location
        Args:
            ship_symbol: The symbol of the ship to negotiate with
        Returns:
            Contract data if successful, None otherwise
        """
        try:
            result = self._retry_api_call(self.client.negotiate_contract, ship_symbol)
            if result.get("data", {}).get("contract"):
                contract = result["data"]["contract"]
                logging.info(f"Negotiated new contract: {contract.get('id')} - {contract.get('type')}")
                return contract
            return None
        except Exception as e:
            logging.error(f"Failed to negotiate contract: {e}")
            return None

    def _maintain_ship(self, ship_symbol: str) -> bool:
        """
        Perform maintenance on a ship if needed
        Args:
            ship_symbol: The symbol of the ship to maintain
        Returns:
            True if maintenance was successful or not needed
        """
        try:
            ship = self._retry_api_call(self.client.get_ship, ship_symbol).get("data", {})
            frame = ship.get("frame", {})
            
            # Check if repair is needed (condition below 90%)
            if frame.get("condition", 100) < 90:
                result = self._retry_api_call(self.client.repair_ship, ship_symbol)
                if result.get("data"):
                    cost = result["data"].get("transaction", {}).get("totalPrice", 0)
                    logging.info(f"Repaired ship {ship_symbol} for {cost} credits")
                    return True
            return True
        except Exception as e:
            logging.error(f"Failed to maintain ship: {e}")
            return False

    def _jump_to_system(self, ship_symbol: str, destination_system: str) -> bool:
        """
        Jump to another system using a jump gate
        Args:
            ship_symbol: The symbol of the ship to jump
            destination_system: The symbol of the destination system
        Returns:
            True if jump was successful
        """
        try:
            result = self._retry_api_call(self.client.jump_ship, ship_symbol, destination_system)
            if result.get("data"):
                nav = result["data"].get("nav", {})
                cooldown = result["data"].get("cooldown", {})
                logging.info(f"Jumped to system {nav.get('systemSymbol')}. Cooldown: {cooldown.get('remainingSeconds')}s")
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to jump to system: {e}")
            return False

    def _find_nearest_shipyard(self, current_system: str) -> Optional[Dict[str, Any]]:
        """Find the nearest system with a shipyard"""
        try:
            # Get first page of systems
            page = 1
            limit = 20
            systems = []
            
            while True:
                response = self._retry_api_call(self.client.get_systems, page, limit)
                data = response.get("data", [])
                if not data:
                    break
                systems.extend(data)
                
                # Check if we have more pages
                meta = response.get("meta", {})
                total_pages = meta.get("total", 1) // limit + 1
                if page >= total_pages:
                    break
                page += 1
                
            if not systems:
                logging.error("No systems data available")
                return None
                
            # Find current system data
            current_system_data = next((s for s in systems if s["symbol"] == current_system), None)
            if not current_system_data:
                logging.error(f"Could not find data for system {current_system}")
                return None
                
            current_x = current_system_data["x"]
            current_y = current_system_data["y"]
            
            # Sort systems by distance
            systems.sort(key=lambda s: ((s["x"] - current_x) ** 2 + (s["y"] - current_y) ** 2) ** 0.5)
            
            # Check each system for shipyards
            for system in systems[:10]:  # Check closest 10 systems
                logging.info(f"Checking system {system['symbol']} for shipyards")
                # Get all waypoints with pagination
                waypoints = []
                waypoint_page = 1
                while True:
                    waypoint_response = self._retry_api_call(self.client.get_waypoints, system["symbol"], waypoint_page, limit)
                    waypoint_data = waypoint_response.get("data", [])
                    if not waypoint_data:
                        break
                    waypoints.extend(waypoint_data)
                    
                    # Check if we have more pages
                    waypoint_meta = waypoint_response.get("meta", {})
                    total_waypoint_pages = waypoint_meta.get("total", 1) // limit + 1
                    if waypoint_page >= total_waypoint_pages:
                        break
                    waypoint_page += 1
                
                # Find shipyards
                shipyards = [w for w in waypoints if any(t.get("symbol") == "SHIPYARD" for t in w.get("traits", []))]\
                    if waypoints else []
                
                if shipyards:
                    logging.info(f"Found shipyard in system {system['symbol']}")
                    return {"system": system["symbol"], "waypoint": shipyards[0]}
                
            logging.error("No shipyards found in nearby systems")
            return None
            
        except Exception as e:
            logging.error(f"Error finding shipyard: {str(e)}")
            return None

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
            # Get available ships
            if not system:
                agent = self._retry_api_call(self.client.get_agent).get("data", {})
                # Use the full headquarters system symbol
                system = "-".join(agent.get("headquarters", "").split("-")[:2])
                
            # Find shipyard
            shipyard = self._find_nearest_shipyard(system)
            if not shipyard:
                return {"status": "error", "message": "No shipyard found"}
                
            # Get available ships
            ships = self._retry_api_call(self.client.get_shipyard, shipyard["system"], shipyard["waypoint"]["symbol"]).get("data", {}).get("ships", [])
            if not ships:
                return {"status": "error", "message": "No ships available at shipyard"}
                
            # Find the requested ship type
            ship_data = next((s for s in ships if s.get("type") == ship_type), None)
            if not ship_data:
                return {"status": "error", "message": f"Ship type {ship_type} not available"}
                
            # Check if we can afford it
            agent = self._retry_api_call(self.client.get_agent).get("data", {})
            credits = agent.get("credits", 0)
            if credits < ship_data.get("purchasePrice", float("inf")):
                return {"status": "error", "message": f"Not enough credits to purchase {ship_type}"}
                
            # Purchase the ship
            result = self._retry_api_call(self.client.purchase_ship, ship_type, shipyard["waypoint"]["symbol"])
            if result and "data" in result:
                ship = result["data"]["ship"]
                return {"status": "success", "ship": ship}
            else:
                return {"status": "error", "message": "Failed to purchase ship"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _ensure_mining_ship(self) -> Dict[str, Any]:
        """
        Ensure we have a mining ship.
        Returns:
            Dict with status and ship data
        """
        try:
            # Get our ships
            ships = self._retry_api_call(self.client.get_my_ships).get("data", [])
            logging.info(f"Current ships: {[ship.get('symbol') for ship in ships]}")
            
            # Check if we have a mining ship
            mining_ships = [s for s in ships if any(m.get("symbol", "").startswith("MINING") 
                                                  for m in s.get("modules", []))]
            
            if mining_ships:
                ship = mining_ships[0]
                logging.info(f"Found existing mining ship: {ship.get('symbol')}")
                return {"success": True, "ship": ship}
            
            # No mining ship found, try to buy one
            logging.info("No mining ship found, attempting to purchase one")
            purchase_result = self._purchase_ship("SHIP_MINING_DRONE")
            
            if purchase_result.get("status") == "success":
                ship = purchase_result.get("ship")
                logging.info(f"Successfully purchased mining ship: {ship.get('symbol')}")
                return {"success": True, "ship": ship}
            else:
                error_msg = purchase_result.get("message", "Unknown error purchasing ship")
                logging.error(f"Failed to purchase mining ship: {error_msg}")
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error ensuring mining ship: {error_msg}")
            return {"success": False, "error": error_msg}

    def _prepare_ship_for_mining(self, ship_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare a ship for mining by:
        1. Finding a market that sells mining equipment
        2. Navigating to that market
        3. Purchasing the equipment
        """
        try:
            ship_symbol = ship_data.get("symbol")
            if not ship_symbol:
                return {"success": False, "error": "Invalid ship data"}

            # Check if ship already has mining equipment
            modules = ship_data.get("modules", [])
            mining_modules = [m for m in modules if m.get("symbol", "").startswith("MINING")]
            if mining_modules:
                logging.info(f"Ship {ship_symbol} already has mining equipment")
                return {"success": True}

            # Get current system
            nav = ship_data.get("nav", {})
            current_system = nav.get("systemSymbol")
            if not current_system:
                return {"success": False, "error": "Could not determine current system"}
                
            logging.info(f"Preparing ship {ship_symbol} for mining")
            
            # Find markets in current system first
            waypoints = self._retry_api_call(self.client.get_waypoints, current_system)
            markets = [w for w in waypoints.get("data", []) 
                      if any(t.get("symbol") == "MARKETPLACE" for t in w.get("traits", []))]
            
            for market in markets:
                market_data = self._retry_api_call(
                    self.client.get_market,
                    current_system,
                    market["symbol"]
                ).get("data", {})
                
                # Check if market sells mining equipment
                trade_goods = market_data.get("tradeGoods", [])
                mining_equipment = [g for g in trade_goods 
                                  if g.get("symbol", "").startswith("MOUNT_MINING")]
                
                if not mining_equipment:
                    continue
                    
                # Navigate to market
                nav_result = self._retry_api_call(
                    self.client.navigate_ship,
                    ship_symbol,
                    market["symbol"]
                )
                
                if "error" in nav_result:
                    logging.error(f"Navigation to market failed: {nav_result.get('error')}")
                    continue
                    
                # Wait for arrival
                while True:
                    ship = self._retry_api_call(self.client.get_ship, ship_symbol).get("data", {})
                    if ship.get("nav", {}).get("status") == "IN_ORBIT":
                        break
                    time.sleep(2)
                    
                # Purchase mining equipment
                for equipment in mining_equipment:
                    purchase_result = self._retry_api_call(
                        self.client.purchase_ship_module,
                        ship_symbol,
                        equipment["symbol"]
                    )
                    
                    if purchase_result.get("data"):
                        logging.info(f"Successfully purchased {equipment['symbol']}")
                        return {"success": True}
                        
            return {"success": False, "error": "Could not find or purchase mining equipment"}
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error preparing ship for mining: {error_msg}")
            return {"success": False, "error": error_msg}

    def _handle_mining_contract(self, contract: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a mining contract by finding an asteroid field and mining resources"""
        try:
            logging.info(f"Handling mining contract {contract.get('id')}")
            
            # Get ship data
            mining_ship_result = self._ensure_mining_ship()
            if not mining_ship_result["success"]:
                return {"status": "error", "error": mining_ship_result["error"]}
                
            ship_data = mining_ship_result["ship"]
            ship_symbol = ship_data.get("symbol")
            
            # Ensure ship has mining equipment
            prep_result = self._prepare_ship_for_mining(ship_data)
            if not prep_result["success"]:
                return {"status": "error", "error": f"Failed to prepare ship: {prep_result['error']}"}
            
            # Get contract details
            terms = contract.get("terms", {})
            deliver_items = terms.get("deliver", [])
            if not deliver_items:
                return {"status": "error", "error": "No delivery terms in contract"}
                
            # Find system with asteroid fields
            current_system = ship_data.get("nav", {}).get("systemSymbol")
            if not current_system:
                return {"status": "error", "error": "Could not determine current system"}
                
            mining_system = self._find_mining_system(current_system)
            if not mining_system:
                return {"status": "error", "error": "No suitable mining location found"}
                
            asteroid_field = mining_system["asteroids"][0]
            target_system = mining_system["system"]
            
            # Navigate to asteroid field
            if target_system != current_system:
                jump_result = self._jump_to_system(ship_symbol, target_system)
                if not jump_result["success"]:
                    return {"status": "error", "error": f"Failed to jump to system: {jump_result['error']}"}
            
            nav_result = self._retry_api_call(
                self.client.navigate_ship,
                ship_symbol,
                asteroid_field["symbol"]
            )
            
            if "error" in nav_result:
                return {"status": "error", "error": f"Failed to navigate to asteroid field: {nav_result['error']}"}
            
            # Wait for arrival
            while True:
                ship = self._retry_api_call(self.client.get_ship, ship_symbol).get("data", {})
                if ship.get("nav", {}).get("status") == "IN_ORBIT":
                    break
                logging.info(f"Ship status: {ship.get('nav', {}).get('status')}")
                time.sleep(2)
            
            # Start mining
            extract_result = self._extract_resources(ship_symbol)
            if "error" in extract_result:
                return {"status": "error", "error": f"Mining failed: {extract_result['error']}"}
                
            return {"status": "success", "message": "Successfully mined resources"}
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error handling mining contract: {error_msg}")
            return {"status": "error", "error": error_msg}

    def _find_mining_system(self, current_system: str) -> Dict[str, Any]:
        """Find a system with asteroid fields"""
        try:
            # First check current system
            waypoints = self._retry_api_call(self.client.get_waypoints, current_system)
            asteroid_fields = [w for w in waypoints.get("data", []) if "ASTEROID" in w.get("type", "")]
            if asteroid_fields:
                return {"success": True, "system": current_system, "asteroids": asteroid_fields}
                
            # If no asteroids in current system, check nearby systems
            systems = self._retry_api_call(self.client.get_systems).get("data", [])
            if not systems:
                return {"success": False, "error": "Could not get systems data"}
                
            # Filter to systems in same sector
            sector = current_system.split("-")[0]
            sector_systems = [s for s in systems if s["symbol"].startswith(sector)]
            
            for system in sector_systems:
                waypoints = self._retry_api_call(self.client.get_waypoints, system["symbol"])
                asteroid_fields = [w for w in waypoints.get("data", []) if "ASTEROID" in w.get("type", "")]
                if asteroid_fields:
                    return {"success": True, "system": system["symbol"], "asteroids": asteroid_fields}
                    
            return {"success": False, "error": "No asteroid fields found in sector"}
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error finding mining system: {error_msg}")
            return {"success": False, "error": error_msg}
