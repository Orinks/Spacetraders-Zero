import wx
import wx.adv
import requests
import logging
from typing import Dict, Any
from api.client import SpaceTradersClient
from agents.trader import AutomatedTrader

class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        try:
            super().__init__(parent, title=title, size=(800, 600))
            logging.info("MainWindow: Base window initialized")
            
            self.client = SpaceTradersClient()
            logging.info("MainWindow: API client created")
            
            self.agent = AutomatedTrader(self.client, self.on_agent_update)
            logging.info("MainWindow: Trader agent initialized")
            
            self.refresh_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.on_refresh_timer, self.refresh_timer)
            logging.info("MainWindow: Timer initialized")
            
            self.init_ui()
            logging.info("MainWindow: UI initialized")
            
            self.init_tray()
            logging.info("MainWindow: Tray initialized")
        except Exception as e:
            logging.error(f"MainWindow initialization failed: {str(e)}", exc_info=True)
            raise
        
    def init_tray(self):
        """Initialize system tray icon and menu"""
        self.tray_icon = wx.adv.TaskBarIcon()
        self.tray_icon.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, size=(16, 16))), "SpaceTraders Zero")
        
        self.Bind(wx.EVT_ICONIZE, self.on_minimize)
        self.tray_icon.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.on_tray_double_click)
        self.tray_icon.Bind(wx.adv.EVT_TASKBAR_RIGHT_UP, self.on_tray_right_click)
        
    def on_minimize(self, event):
        """Handle window minimize"""
        if event.Iconized():
            self.Hide()
            
    def on_tray_double_click(self, event):
        """Show window on tray icon double click"""
        self.Show()
        self.Restore()
        
    def on_tray_right_click(self, event):
        """Show context menu on tray icon right click"""
        menu = wx.Menu()
        
        show = menu.Append(wx.ID_ANY, "Show Window")
        self.tray_icon.Bind(wx.EVT_MENU, self.on_tray_double_click, show)
        
        menu.AppendSeparator()
        
        exit = menu.Append(wx.ID_ANY, "Exit")
        self.tray_icon.Bind(wx.EVT_MENU, self.on_exit, exit)
        
        self.tray_icon.PopupMenu(menu)
        
    def on_exit(self, event):
        """Handle exit from tray menu"""
        self.tray_icon.RemoveIcon()
        self.tray_icon.Destroy()
        self.Close()
        
    def init_ui(self):
        """Initialize the user interface"""
        # Create main panel
        panel = wx.Panel(self)
        
        # Create main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Create notebook for tabbed interface (screen reader accessible)
        self.notebook = wx.Notebook(panel)
        
        # Status panel
        status_panel = wx.Panel(self.notebook)
        status_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Add status text (screen reader accessible)
        self.status_text = wx.TextCtrl(
            status_panel, 
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
            name="Status Messages"  # Accessible name
        )
        status_sizer.Add(self.status_text, 1, wx.EXPAND | wx.ALL, 5)
        status_panel.SetSizer(status_sizer)
        
        # Contracts tab
        contracts_panel = wx.Panel(self.notebook)
        contracts_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.contracts_list = wx.ListCtrl(
            contracts_panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN,
            name="Available Contracts"  # Accessible name
        )
        self.contracts_list.InsertColumn(0, "Type", width=100)
        self.contracts_list.InsertColumn(1, "Payment", width=100)
        self.contracts_list.InsertColumn(2, "Status", width=100)
        
        # Add contract control buttons
        contract_buttons = wx.BoxSizer(wx.HORIZONTAL)
        
        refresh_contracts = wx.Button(contracts_panel, label="Refresh")
        refresh_contracts.Bind(wx.EVT_BUTTON, self.on_refresh_contracts)
        contract_buttons.Add(refresh_contracts, 0, wx.ALL, 5)
        
        accept_contract = wx.Button(contracts_panel, label="Accept Selected")
        accept_contract.Bind(wx.EVT_BUTTON, self.on_accept_contract)
        contract_buttons.Add(accept_contract, 0, wx.ALL, 5)
        
        contracts_sizer.Add(self.contracts_list, 1, wx.EXPAND | wx.ALL, 5)
        contracts_sizer.Add(contract_buttons, 0, wx.CENTER | wx.ALL, 5)
        contracts_panel.SetSizer(contracts_sizer)
        
        # Market tab
        market_panel = wx.Panel(self.notebook)
        market_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.market_list = wx.ListCtrl(
            market_panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN,
            name="Market Goods"  # Accessible name
        )
        self.market_list.InsertColumn(0, "Symbol", width=100)
        self.market_list.InsertColumn(1, "Supply", width=100)
        self.market_list.InsertColumn(2, "Purchase", width=100)
        self.market_list.InsertColumn(3, "Sell", width=100)
        
        market_sizer.Add(self.market_list, 1, wx.EXPAND | wx.ALL, 5)
        
        # Market control buttons
        market_buttons = wx.BoxSizer(wx.HORIZONTAL)
        
        refresh_market = wx.Button(market_panel, label="Refresh Market")
        refresh_market.Bind(wx.EVT_BUTTON, self.on_refresh_market)
        market_buttons.Add(refresh_market, 0, wx.ALL, 5)
        
        buy_button = wx.Button(market_panel, label="Buy Selected")
        buy_button.Bind(wx.EVT_BUTTON, self.on_buy)
        market_buttons.Add(buy_button, 0, wx.ALL, 5)
        
        sell_button = wx.Button(market_panel, label="Sell Selected")
        sell_button.Bind(wx.EVT_BUTTON, self.on_sell)
        market_buttons.Add(sell_button, 0, wx.ALL, 5)
        
        market_sizer.Add(market_buttons, 0, wx.CENTER | wx.ALL, 5)
        
        market_panel.SetSizer(market_sizer)
        
        # Ship status tab
        ship_panel = wx.Panel(self.notebook)
        ship_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.ship_list = wx.ListCtrl(
            ship_panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN,
            name="Your Ships"  # Accessible name
        )
        self.ship_list.InsertColumn(0, "Symbol", width=100)
        self.ship_list.InsertColumn(1, "Location", width=100)
        self.ship_list.InsertColumn(2, "Status", width=100)
        self.ship_list.InsertColumn(3, "Fuel", width=100)
        
        ship_sizer.Add(self.ship_list, 1, wx.EXPAND | wx.ALL, 5)
        
        # Ship control buttons
        ship_buttons = wx.BoxSizer(wx.HORIZONTAL)
        
        refresh_ships = wx.Button(ship_panel, label="Refresh Ships")
        refresh_ships.Bind(wx.EVT_BUTTON, self.on_refresh_ships)
        ship_buttons.Add(refresh_ships, 0, wx.ALL, 5)
        
        dock_button = wx.Button(ship_panel, label="Dock")
        dock_button.Bind(wx.EVT_BUTTON, self.on_dock)
        ship_buttons.Add(dock_button, 0, wx.ALL, 5)
        
        orbit_button = wx.Button(ship_panel, label="Orbit")
        orbit_button.Bind(wx.EVT_BUTTON, self.on_orbit)
        ship_buttons.Add(orbit_button, 0, wx.ALL, 5)
        
        ship_sizer.Add(ship_buttons, 0, wx.CENTER | wx.ALL, 5)
        
        ship_panel.SetSizer(ship_sizer)
        
        # Navigation tab
        nav_panel = wx.Panel(self.notebook)
        nav_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.waypoint_list = wx.ListCtrl(
            nav_panel,
            style=wx.LC_REPORT | wx.BORDER_SUNKEN,
            name="Navigation Waypoints"  # Accessible name
        )
        self.waypoint_list.InsertColumn(0, "Symbol", width=100)
        self.waypoint_list.InsertColumn(1, "Type", width=100)
        self.waypoint_list.InsertColumn(2, "Distance", width=100)
        
        nav_sizer.Add(self.waypoint_list, 1, wx.EXPAND | wx.ALL, 5)
        
        nav_buttons = wx.BoxSizer(wx.HORIZONTAL)
        
        refresh_waypoints = wx.Button(nav_panel, label="Refresh Waypoints")
        refresh_waypoints.Bind(wx.EVT_BUTTON, self.on_refresh_waypoints)
        nav_buttons.Add(refresh_waypoints, 0, wx.ALL, 5)
        
        navigate_button = wx.Button(nav_panel, label="Navigate To")
        navigate_button.Bind(wx.EVT_BUTTON, self.on_navigate)
        nav_buttons.Add(navigate_button, 0, wx.ALL, 5)
        
        nav_sizer.Add(nav_buttons, 0, wx.CENTER | wx.ALL, 5)
        nav_panel.SetSizer(nav_sizer)
        
        # Add tabs to notebook
        self.notebook.AddPage(status_panel, "Status")
        self.notebook.AddPage(contracts_panel, "Contracts")
        self.notebook.AddPage(market_panel, "Market")
        self.notebook.AddPage(ship_panel, "Ships")
        self.notebook.AddPage(nav_panel, "Navigation")
        
        # Agent info panel (screen reader accessible)
        info_panel = wx.Panel(status_panel)
        info_sizer = wx.GridBagSizer(5, 5)
        
        self.agent_name = wx.StaticText(info_panel, label="Agent: Not registered")
        self.credits = wx.StaticText(info_panel, label="Credits: 0")
        self.location = wx.StaticText(info_panel, label="Location: Unknown")
        self.profit_info = wx.StaticText(info_panel, label="Total Profit: 0")
        self.trades_info = wx.StaticText(info_panel, label="Trades: 0 completed, 0 failed")
        self.api_health = wx.StaticText(info_panel, label="API Health: No errors")
        self.mining_info = wx.StaticText(info_panel, label="Mining: 0/0 successful")
        
        info_sizer.Add(self.agent_name, pos=(0, 0), flag=wx.ALL, border=5)
        info_sizer.Add(self.credits, pos=(1, 0), flag=wx.ALL, border=5)
        info_sizer.Add(self.location, pos=(2, 0), flag=wx.ALL, border=5)
        info_sizer.Add(self.profit_info, pos=(3, 0), flag=wx.ALL, border=5)
        info_sizer.Add(self.trades_info, pos=(4, 0), flag=wx.ALL, border=5)
        info_sizer.Add(self.api_health, pos=(5, 0), flag=wx.ALL, border=5)
        info_sizer.Add(self.mining_info, pos=(6, 0), flag=wx.ALL, border=5)
        
        info_panel.SetSizer(info_sizer)
        status_sizer.Add(info_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # Add control buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        register_button = wx.Button(panel, label="Register New Agent")
        register_button.Bind(wx.EVT_BUTTON, self.on_register)
        button_sizer.Add(register_button, 0, wx.ALL, 5)
        
        start_button = wx.Button(panel, label="Start Agent")
        start_button.Bind(wx.EVT_BUTTON, self.on_start)
        button_sizer.Add(start_button, 0, wx.ALL, 5)
        
        stop_button = wx.Button(panel, label="Stop Agent")
        stop_button.Bind(wx.EVT_BUTTON, self.on_stop)
        button_sizer.Add(stop_button, 0, wx.ALL, 5)
        
        exit_button = wx.Button(panel, label="Exit")
        exit_button.Bind(wx.EVT_BUTTON, self.on_exit)
        button_sizer.Add(exit_button, 0, wx.ALL, 5)
        
        main_sizer.Add(button_sizer, 0, wx.CENTER)
        
        # Set sizer
        panel.SetSizer(main_sizer)
        
        # Add menu bar
        menubar = wx.MenuBar()
        window_menu = wx.Menu()
        minimize_item = window_menu.Append(wx.ID_ANY, "Minimize to Tray", "Minimize window to system tray")
        self.Bind(wx.EVT_MENU, self.on_minimize, minimize_item)
        menubar.Append(window_menu, "Window")
        self.SetMenuBar(menubar)
        
        # Center window
        self.Centre()
        
    def on_agent_update(self, status: Dict[str, Any]):
        """Handle agent status updates"""
        try:
            if status["status"] == "error":
                error_msg = status.get('error', 'Unknown error')
                self.status_text.AppendText(f"Error: {error_msg}\n")
                self.tray_icon.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_ERROR, size=(16, 16))), 
                                     f"SpaceTraders Zero - Error: {status['error']}")
            elif status["status"] == "accepted_contract":
                self.status_text.AppendText(f"Accepted contract: {status['contract']}\n")
                self.tray_icon.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, size=(16, 16))), 
                                     f"SpaceTraders Zero - Contract accepted: {status['contract']}")
                self.on_refresh_contracts(None)  # Refresh contracts list
                self.on_refresh_contracts(None)  # Refresh contracts list
            elif status["status"] == "bought_goods":
                self.status_text.AppendText(f"Bought goods: {status['good']}\n")
                self.tray_icon.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, size=(16, 16))), 
                                     f"SpaceTraders Zero - Bought: {status['good']}")
                self.on_refresh_market(None)  # Refresh market data
            elif status["status"] == "sold_goods":
                self.status_text.AppendText(f"Sold goods: {status['good']}\n")
                self.tray_icon.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, size=(16, 16))), 
                                     f"SpaceTraders Zero - Sold: {status['good']}")
                self.on_refresh_market(None)  # Refresh market data
            elif status["status"] == "navigating":
                self.status_text.AppendText(f"Navigating to: {status['destination']}\n")
                self.tray_icon.SetIcon(wx.Icon(wx.ArtProvider.GetBitmap(wx.ART_INFORMATION, size=(16, 16))), 
                                     f"SpaceTraders Zero - Navigating to: {status['destination']}")
                self.on_refresh_ships(None)  # Refresh ship status
            elif status["status"] == "starting":
                self.status_text.AppendText(f"{status['message']}\n")
            elif status["status"] == "mining":
                self.status_text.AppendText(f"Mining resources at {status.get('result', {}).get('extraction', {}).get('shipSymbol', 'unknown location')}\n")
            elif status["status"] == "navigating":
                self.status_text.AppendText(f"Navigating to: {status['destination']}\n")
        except RuntimeError:
            # UI has been destroyed, stop the agent
            if hasattr(self, 'agent'):
                self.agent.stop()
            
    def on_start(self, event):
        """Handle start button click"""
        self.status_text.AppendText("Starting agent...\n")
        self.agent.start()
        self.refresh_timer.Start(30000)  # Refresh every 30 seconds
        
    def on_stop(self, event):
        """Handle stop button click"""
        self.status_text.AppendText("Stopping agent...\n")
        self.agent.stop()
        self.refresh_timer.Stop()
        
    def on_refresh_timer(self, event):
        """Handle periodic refresh"""
        self.on_refresh_ships(None)
        self.on_refresh_contracts(None)
        self.on_refresh_market(None)
        
        # Update performance metrics
        if hasattr(self, 'agent'):
            self.profit_info.SetLabel(f"Total Profit: {self.agent.total_profits}")
            self.trades_info.SetLabel(f"Trades: {self.agent.trades_completed} completed, {self.agent.failed_trades} failed")
            
            # Update API health info
            error_rate = (self.client.error_count / self.client.request_count * 100) if self.client.request_count > 0 else 0
            status = "PAUSED" if error_rate > 20 else "OK"
            
            # Calculate recent error rate from history
            recent_errors = len([t for t, _ in self.client.error_history if t > time.time() - 300])  # Last 5 minutes
            recent_rate = f"Recent: {recent_errors} in 5m"
            
            self.api_health.SetLabel(f"API Health: {error_rate:.1f}% errors ({self.client.error_count}/{self.client.request_count}) - {status} - {recent_rate}")
            
            # Update color based on status
            if error_rate > 20:
                self.api_health.SetForegroundColour(wx.RED)
            elif error_rate > 10:
                self.api_health.SetForegroundColour(wx.Colour(255, 140, 0))  # Orange
            else:
                self.api_health.SetForegroundColour(wx.Colour(0, 128, 0))  # Dark Green
            
            # Update mining metrics
            mining_success_rate = (self.agent.mining_successes / self.agent.mining_attempts * 100) if self.agent.mining_attempts > 0 else 0
            self.mining_info.SetLabel(f"Mining: {self.agent.mining_successes}/{self.agent.mining_attempts} successful ({mining_success_rate:.1f}%)")
        
    def on_refresh_contracts(self, event):
        """Refresh the contracts list"""
        try:
            contracts = self.client.get_contracts()
            self.contracts_list.DeleteAllItems()
            for contract in contracts.get("data", []):
                index = self.contracts_list.GetItemCount()
                self.contracts_list.InsertItem(index, contract.get("type", "Unknown"))
                self.contracts_list.SetItem(index, 1, str(contract.get("payment", {}).get("onAccepted", 0)))
                self.contracts_list.SetItem(index, 2, contract.get("status", "Unknown"))
        except Exception as e:
            self.status_text.AppendText(f"Failed to refresh contracts: {str(e)}\n")

    def on_buy(self, event):
        """Handle buy button click"""
        selected = self.market_list.GetFirstSelected()
        if selected == -1:
            self.status_text.AppendText("Please select an item to buy\n")
            return
        try:
            symbol = self.market_list.GetItem(selected, 0).GetText()
            dialog = wx.TextEntryDialog(self, "Enter quantity to buy:", "Buy Goods")
            if dialog.ShowModal() == wx.ID_OK:
                units = int(dialog.GetValue())
                ships = self.client.get_my_ships()
                if not ships.get("data"):
                    self.status_text.AppendText("No ships available\n")
                    return
                ship_symbol = ships["data"][0]["symbol"]  # Use first ship
                result = self.client.buy_goods(ship_symbol, symbol, units)
                self.status_text.AppendText(f"Purchased {units} units of {symbol}\n")
                self.on_refresh_market(None)  # Refresh market data
        except Exception as e:
            self.status_text.AppendText(f"Failed to buy goods: {str(e)}\n")
        dialog.Destroy()
        
    def on_dock(self, event):
        """Handle dock button click"""
        selected = self.ship_list.GetFirstSelected()
        if selected == -1:
            self.status_text.AppendText("Please select a ship first\n")
            return
        try:
            ship_symbol = self.ship_list.GetItem(selected, 0).GetText()
            result = self.client.dock_ship(ship_symbol)
            self.status_text.AppendText(f"Ship {ship_symbol} docked\n")
            self.on_refresh_ships(None)  # Refresh ship status
        except Exception as e:
            self.status_text.AppendText(f"Failed to dock ship: {str(e)}\n")
        
    def on_refresh_waypoints(self, event):
        """Refresh the waypoints list"""
        try:
            # Get current system from ship data
            ships = self.client.get_my_ships()
            if not ships.get("data"):
                self.status_text.AppendText("No ships available to check waypoints\n")
                return
            ship = ships["data"][0]  # Use first ship's location
            nav = ship.get("nav", {})
            current_waypoint = nav.get("waypointSymbol")
            if not current_waypoint:
                return
            system = '-'.join(current_waypoint.split('-')[:2])  # Extract system from waypoint
            waypoints = self.client.get_waypoints(system)
            self.waypoint_list.DeleteAllItems()
            for waypoint in waypoints.get("data", []):
                index = self.waypoint_list.GetItemCount()
                self.waypoint_list.InsertItem(index, waypoint.get("symbol", ""))
                self.waypoint_list.SetItem(index, 1, waypoint.get("type", ""))
                self.waypoint_list.SetItem(index, 2, str(waypoint.get("distance", 0)))
        except Exception as e:
            self.status_text.AppendText(f"Failed to refresh waypoints: {str(e)}\n")
            
    def on_navigate(self, event):
        """Handle navigation button click"""
        selected_ship = self.ship_list.GetFirstSelected()
        selected_waypoint = self.waypoint_list.GetFirstSelected()
        if selected_ship == -1:
            self.status_text.AppendText("Please select a ship first\n")
            return
        if selected_waypoint == -1:
            self.status_text.AppendText("Please select a destination waypoint\n")
            return
        try:
            ship_symbol = self.ship_list.GetItem(selected_ship, 0).GetText()
            waypoint = self.waypoint_list.GetItem(selected_waypoint, 0).GetText()
            result = self.client.navigate_ship(ship_symbol, waypoint)
            self.status_text.AppendText(f"Ship {ship_symbol} navigating to {waypoint}\n")
            self.on_refresh_ships(None)  # Refresh ship status
        except Exception as e:
            self.status_text.AppendText(f"Failed to navigate: {str(e)}\n")
            
    def on_orbit(self, event):
        """Handle orbit button click"""
        selected = self.ship_list.GetFirstSelected()
        if selected == -1:
            self.status_text.AppendText("Please select a ship first\n")
            return
        try:
            ship_symbol = self.ship_list.GetItem(selected, 0).GetText()
            result = self.client.orbit_ship(ship_symbol)
            self.status_text.AppendText(f"Ship {ship_symbol} entered orbit\n")
            self.on_refresh_ships(None)  # Refresh ship status
        except Exception as e:
            self.status_text.AppendText(f"Failed to orbit ship: {str(e)}\n")
        
    def on_refresh_ships(self, event):
        """Refresh the ships list"""
        try:
            ships = self.client.get_my_ships()
            self.ship_list.DeleteAllItems()
            for ship in ships.get("data", []):
                index = self.ship_list.GetItemCount()
                self.ship_list.InsertItem(index, ship.get("symbol", ""))
                nav = ship.get("nav", {})
                self.ship_list.SetItem(index, 1, nav.get("waypointSymbol", ""))
                self.ship_list.SetItem(index, 2, nav.get("status", ""))
                self.ship_list.SetItem(index, 3, str(ship.get("fuel", {}).get("current", 0)))
        except Exception as e:
            self.status_text.AppendText(f"Failed to refresh ships: {str(e)}\n")
            
    def on_sell(self, event):
        """Handle sell button click"""
        selected = self.market_list.GetFirstSelected()
        if selected == -1:
            self.status_text.AppendText("Please select an item to sell\n")
            return
        try:
            symbol = self.market_list.GetItem(selected, 0).GetText()
            dialog = wx.TextEntryDialog(self, "Enter quantity to sell:", "Sell Goods")
            if dialog.ShowModal() == wx.ID_OK:
                units = int(dialog.GetValue())
                ships = self.client.get_my_ships()
                if not ships.get("data"):
                    self.status_text.AppendText("No ships available\n")
                    return
                ship_symbol = ships["data"][0]["symbol"]  # Use first ship
                result = self.client.sell_goods(ship_symbol, symbol, units)
                self.status_text.AppendText(f"Sold {units} units of {symbol}\n")
                self.on_refresh_market(None)  # Refresh market data
        except Exception as e:
            self.status_text.AppendText(f"Failed to sell goods: {str(e)}\n")
        dialog.Destroy()
        
    def on_refresh_market(self, event):
        """Refresh the market data"""
        try:
            # Get current system/waypoint from ship data
            ships = self.client.get_my_ships()
            if not ships.get("data"):
                self.status_text.AppendText("No ships available to check market\n")
                return
            ship = ships["data"][0]  # Use first ship's location
            nav = ship.get("nav", {})
            current_waypoint = nav.get("waypointSymbol")
            if not current_waypoint:
                return
            system = '-'.join(current_waypoint.split('-')[:2])  # Extract system from waypoint
            market_data = self.client.get_market(system, current_waypoint)
            
            self.market_list.DeleteAllItems()
            for item in market_data.get("data", {}).get("tradeGoods", []):
                index = self.market_list.GetItemCount()
                self.market_list.InsertItem(index, item.get("symbol", ""))
                self.market_list.SetItem(index, 1, item.get("supply", ""))
                self.market_list.SetItem(index, 2, str(item.get("purchasePrice", 0)))
                self.market_list.SetItem(index, 3, str(item.get("sellPrice", 0)))
        except Exception as e:
            self.status_text.AppendText(f"Failed to refresh market: {str(e)}\n")
            
    def on_accept_contract(self, event):
        """Accept the selected contract"""
        selected = self.contracts_list.GetFirstSelected()
        if selected == -1:
            self.status_text.AppendText("Please select a contract first\n")
            return
        try:
            contract_id = self.contracts_list.GetItem(selected, 0).GetText()
            result = self.client.accept_contract(contract_id)
            self.status_text.AppendText(f"Contract accepted: {contract_id}\n")
            self.on_refresh_contracts(None)  # Refresh the list
        except Exception as e:
            self.status_text.AppendText(f"Failed to accept contract: {str(e)}\n")

    def on_register(self, event):
        """Handle register button click"""
        dialog = wx.TextEntryDialog(self, "Enter agent name:", "Register New Agent")
        if dialog.ShowModal() == wx.ID_OK:
            try:
                agent_name = dialog.GetValue()
                # Get factions from API
                factions = ["COSMIC"]  # Default to COSMIC if can't get factions
                try:
                    faction_response = self.client.get_factions()
                    if faction_response.get("data"):
                        factions = [f["symbol"] for f in faction_response["data"]]
                except Exception as e:
                    self.status_text.AppendText(f"Failed to get factions: {str(e)}\n")
                
                faction_dialog = wx.SingleChoiceDialog(self, 
                    "Choose your faction:", 
                    "Select Faction",
                    choices=factions)
                
                if faction_dialog.ShowModal() == wx.ID_OK:
                    faction = faction_dialog.GetStringSelection()
                    self.status_text.AppendText(f"Registering new agent {agent_name} with faction {faction}...\n")
                    try:
                        result = self.client.register_new_agent(agent_name, faction)
                        self.status_text.AppendText("Registration successful! Token received.\n")
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 409:
                            self.status_text.AppendText("Registration failed: Agent name already taken. Please try another name.\n")
                        else:
                            self.status_text.AppendText(f"Registration failed: {str(e)}\n")
                faction_dialog.Destroy()
            except Exception as e:
                self.status_text.AppendText(f"Registration failed: {str(e)}\n")
        dialog.Destroy()
