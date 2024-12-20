import os
import sys
import time
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple, Callable, Set, cast, TypedDict, Literal
from threading import Thread

# Add src directory to Python path
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if src_dir not in sys.path:
    sys.path.append(src_dir)

from api.client import SpaceTradersClient
from persistence import StateManager

class ShipMount(TypedDict):
    symbol: str
    name: str
    description: str
    strength: Optional[int]
    deposits: Optional[List[str]]
    requirements: Dict[str, Any]

class Contract(TypedDict):
    id: str
    factionSymbol: str
    type: str
    terms: Dict[str, Any]
    accepted: bool
    fulfilled: bool
    expiration: str
    deadlineToAccept: str

class ShipRegistration(TypedDict):
    name: str
    factionSymbol: str
    role: str

class ShipNav(TypedDict):
    systemSymbol: str
    waypointSymbol: str
    route: Dict[str, Any]
    status: Literal["IN_TRANSIT", "IN_ORBIT", "DOCKED"]
    flightMode: Literal["DRIFT", "STEALTH", "CRUISE", "BURN"]

class Ship(TypedDict):
    symbol: str
    registration: ShipRegistration
    nav: ShipNav
    crew: Dict[str, Any]
    frame: Dict[str, Any]
    reactor: Dict[str, Any]
    engine: Dict[str, Any]
    modules: List[Dict[str, Any]]
    mounts: List[Dict[str, Any]]
    cargo: Dict[str, Any]
    fuel: Dict[str, Any]

class AutomatedTrader:
    """Automated trading agent for Space Traders"""
    
    def __init__(self, client: SpaceTradersClient, status_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """Initialize the trader with a client instance"""
        self.client = client
        self.status_callback = status_callback
        self.running = False
        self.thread: Optional[Thread] = None
        self.start_time = 0.0
        self.error_count = 0
        self.max_errors = 5
        self.mining_attempts = 0
        self.mining_successes = 0
        self.market_trends: Dict[str, Dict[str, Dict[str, List[Any]]]] = {}
        self.state_manager = StateManager("trader_state.json")
        self.state = self.state_manager.get_latest_state() or {}
        
        # Trading history and market data
        self.trade_history: List[Dict[str, Any]] = []
        self.known_markets: Dict[str, Dict[str, Any]] = {}
        self.visited_waypoints: Set[str] = set()
        
        # Performance metrics
        self.cycle_count: int = 0
        self.total_profits: int = 0
        self.trades_completed: int = 0
        self.failed_trades: int = 0
        
        # Initialize persistence
        self.load_state()

        logging.info("Automated trader initialized")
        
    def _get_current_state(self) -> Dict[str, Any]:
        """Get the current state as a dictionary."""
        return {
            'trade_history': self.trade_history[-100:],  # Keep last 100 trades
            'known_markets': self.known_markets,
            'visited_waypoints': list(self.visited_waypoints),
            'market_trends': self.market_trends,
            'total_profits': 0,
            'trades_completed': 0,
            'failed_trades': 0,
            'mining_attempts': self.mining_attempts,
            'mining_successes': self.mining_successes,
            'cycle_count': self.cycle_count,
            'last_update': time.time()
        }

    def save_state(self) -> None:
        """Save agent state to database"""
        try:
            state = self._get_current_state()
            self.state_manager.save_state(state)
            logging.debug("State saved successfully")
        except Exception as e:
            logging.error(f"Failed to save state: {e}")
            
    def load_state(self) -> None:
        """Load agent state from database"""
        try:
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
        
    def start(self) -> None:
        """Start the automated trading"""
        if self.running:
            logging.warning("Agent already running")
            return
        
        self.running = True
        if self.status_callback:
            token_prefix = self.client.token[:8] if self.client.token else "No token"
            self.status_callback({"status": "starting", "message": f"Starting agent with token: {token_prefix}..."})
            
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)  # Wait for old thread to finish
            
        self.thread = Thread(target=self._run_loop)
        self.thread.daemon = True  # Make thread daemon so it exits when main program exits
        self.thread.start()
        logging.info("Agent thread started")
        
    def stop(self) -> None:
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
        
    def _retry_api_call(self, func: Callable[..., Any], *args: Any, max_attempts: int = 3) -> Any:
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
                
    def _run_loop(self) -> None:
        """Main automation loop"""
        self.start_time = time.time()
        while self.running:
            try:
                # Negotiate new contracts if needed
                contracts = self._get_current_contracts()
                if not contracts:
                    ships = self._get_ships()
                    if ships:
                        self._negotiate_new_contract(ships[0]["symbol"])
                
                # Run mining operations
                if ships:  # Check ships is defined and not empty
                    self._mine_resources(ships[0]["symbol"])
                
                # Save state periodically
                self.save_state()
                
                # Sleep between cycles
                time.sleep(30)
                
            except Exception as e:
                logging.error(f"Error in automation loop: {e}")
                self.error_count += 1
                if self.error_count >= self.max_errors:
                    logging.error("Maximum errors reached, stopping automation")
                    self.running = False
                time.sleep(30)  # Back off on error

    def _mine_resources(self, ship_symbol: str) -> Dict[str, Any]:
        """Mine resources at current location"""
        try:
            # First check cooldown
            cooldown = self.client.get_ship_cooldown(ship_symbol)
            if cooldown and isinstance(cooldown, dict) and "data" in cooldown and cooldown["data"].get("remainingSeconds", 0) > 0:
                return {"status": "cooldown", "seconds": cooldown["data"]["remainingSeconds"]}
            
            # Attempt mining
            self.mining_attempts += 1
            result = self.client.extract_resources(ship_symbol)
            
            if isinstance(result, dict) and result.get("data", {}).get("extraction", {}).get("yield"):
                self.mining_successes += 1
                return {"status": "success", "data": result["data"]}
            
            return {"status": "error", "error": "No resources extracted"}
            
        except Exception as e:
            logging.error(f"Mining error: {e}")
            return {"status": "error", "error": str(e)}

    def _get_ship_upgrades(self, ship_symbol: str) -> List[Dict[str, Any]]:
        """Get available ship upgrades at current waypoint"""
        try:
            nav = self._retry_api_call(self.client.get_ship, ship_symbol).get("data", {}).get("nav", {})
            if not nav:
                return []
            
            waypoint = nav.get("waypointSymbol")
            if not waypoint:
                return []
            
            system = waypoint.split("-")[0]
            result = self._retry_api_call(self.client.get_ship_mounts, system, waypoint)
            if result and "data" in result:
                return cast(List[Dict[str, Any]], result["data"])
            return []
            
        except Exception as e:
            logging.error(f"Failed to get ship upgrades: {e}")
            return []

    def find_best_trade_route(self, ship_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                                        trend_data = self.market_trends.get(market2["symbol"], {}).get(good["symbol"], {})
                                        if trend_data:
                                            # Only consider trades where sell price has been stable or increasing
                                            recent_prices = trend_data.get("prices", [])[-5:]  # Last 5 price points
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
                                                        "total_potential_profit": profit * min(10, supply_level)
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

    def _refuel_ship(self, ship_symbol: str, current_waypoint: str) -> bool:
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
        """Run a single cycle of the automated trader"""
        try:
            # Check if we have any active contracts
            contracts = self._get_current_contracts()
            if not contracts:
                # No contracts, try to get a new one
                ships = self._get_ships()
                if ships:
                    result = self._negotiate_new_contract(ships[0]["symbol"])
                    if result:
                        return {"status": "success", "message": "New contract negotiated"}
                    else:
                        return {"status": "error", "error": "Failed to negotiate contract"}
                else:
                    return {"status": "error", "error": "No ships available"}

            # Run mining operations with first ship
            ships = self._get_ships()
            if ships and len(ships) > 0:
                result = self._mine_resources(ships[0]["symbol"])
                if isinstance(result, dict):
                    return result
            return {"status": "idle", "message": "No actions needed"}

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error in agent cycle: {error_msg}")
            return {"status": "error", "error": error_msg}

    def run(self) -> None:
        """Run the automated trader"""
        try:
            # Check if we have any active contracts
            contracts = self._get_current_contracts()
            if not contracts:
                # No contracts, try to get a new one
                ships = self._get_ships()
                if ships and len(ships) > 0:
                    self._negotiate_new_contract(ships[0]["symbol"])
                else:
                    logging.error("No ships available")
                    return

            # Run mining operations with first ship
            if ships and len(ships) > 0:
                self._mine_resources(ships[0]["symbol"])

            # Save state periodically
            self.save_state()

        except Exception as e:
            logging.error(f"Error in agent run: {str(e)}")
            self.error_count += 1
            if self.error_count >= self.max_errors:
                logging.error("Maximum errors reached, stopping automation")
                self.running = False

    def _negotiate_new_contract(self, ship_symbol: str) -> Dict[str, Any]:
        """Negotiate a new contract"""
        try:
            result = self.client.negotiate_contract(ship_symbol)
            if result and "data" in result and "contract" in result["data"]:
                return cast(Dict[str, Any], result["data"]["contract"])
            return {"status": "error", "error": "Failed to get contract data"}
        except Exception as e:
            logging.error(f"Failed to negotiate contract: {e}")
            return {"status": "error", "error": str(e)}

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

    def _purchase_ship(self, ship_type: str, system: Optional[str] = None) -> Dict[str, Any]:
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
                if not jump_result:
                    return {"status": "error", "error": f"Failed to jump to system: {jump_result}"}
            
            nav_result = self._retry_api_call(
                self.client.navigate_ship,
                ship_symbol,
                asteroid_field["symbol"]
            )
            
            if "error" in nav_result:
                return {"status": "error", "error": f"Failed to navigate to asteroid field: {nav_result.get('error')}"}
            
            # Wait for arrival
            while True:
                ship = self._retry_api_call(self.client.get_ship, ship_symbol).get("data", {})
                if ship.get("nav", {}).get("status") == "IN_ORBIT":
                    break
                logging.info(f"Ship status: {ship.get('nav', {}).get('status')}")
                time.sleep(2)
            
            # Start mining
            extract_result = self._mine_resources(ship_symbol)
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

    def _update_market_trends(self, market_symbol: str, good_symbol: str, price: int) -> None:
        """Track price history for market analysis"""
        if market_symbol not in self.market_trends:
            self.market_trends[market_symbol] = {}
        
        if good_symbol not in self.market_trends[market_symbol]:
            self.market_trends[market_symbol][good_symbol] = {"prices": [], "timestamps": []}
        
        trend_data = self.market_trends[market_symbol][good_symbol]
        trend_data["prices"].append(price)
        trend_data["timestamps"].append(time.time())
        
        # Keep only last 24 hours of data
        cutoff = time.time() - 86400
        prices_and_times = list(zip(trend_data["prices"], trend_data["timestamps"]))
        filtered_data = [(p, t) for p, t in prices_and_times if t > cutoff]
        
        if filtered_data:
            prices, timestamps = zip(*filtered_data)
            trend_data["prices"] = list(prices)
            trend_data["timestamps"] = list(timestamps)
        else:
            trend_data["prices"] = []
            trend_data["timestamps"] = []

    def _get_current_contracts(self) -> List[Dict[str, Any]]:
        """Get current contracts"""
        try:
            result = self._retry_api_call(self.client.get_contracts)
            if result and "data" in result:
                return cast(List[Dict[str, Any]], result["data"])
            return []
        except Exception as e:
            logging.error(f"Failed to get contracts: {e}")
            return []

    def _get_ships(self) -> List[Dict[str, Any]]:
        """Get all ships owned by the agent"""
        try:
            result = self._retry_api_call(self.client.get_my_ships)
            if result and "data" in result:
                return cast(List[Dict[str, Any]], result["data"])
            return []
        except Exception as e:
            logging.error(f"Failed to get ships: {e}")
            return []
