import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import logging
from api.client import SpaceTradersClient
import time
from datetime import datetime, timezone

def test_selling():
    client = SpaceTradersClient()
    ship_symbol = "CDM2766-1"
    
    def print_ship_status(ship_data):
        print("\nShip Status:")
        print(f"Location: {ship_data['nav']['waypointSymbol']}")
        print(f"Status: {ship_data['nav']['status']}")
        print(f"Flight Mode: {ship_data['nav']['flightMode']}")
        print("\nCargo:")
        for item in ship_data['cargo']['inventory']:
            print(f"  - {item['symbol']}: {item['units']} units")
        print(f"Space: {ship_data['cargo']['units']}/{ship_data['cargo']['capacity']}")
    
    def get_ship_safely():
        """Get ship details with error handling"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                response = client.get_ship(ship_symbol)
                if response and 'data' in response:
                    return response['data']
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Error getting ship details: {str(e)}")
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
        raise ValueError("Failed to get ship details after multiple attempts")
    
    try:
        # Get current ship status
        ship = get_ship_safely()
        print_ship_status(ship)
        
        # Try to sell at current location first
        current_waypoint = ship['nav']['waypointSymbol']
        try:
            print(f"\nChecking if current location has a marketplace...")
            waypoint_data = client.get_waypoint(ship['nav']['systemSymbol'], current_waypoint)
            if any(trait['symbol'] == 'MARKETPLACE' for trait in waypoint_data.get('data', {}).get('traits', [])):
                print("Current location has a marketplace!")
                market_waypoint = current_waypoint
            else:
                print("No marketplace here, searching nearby...")
                # Get system waypoints to find a market
                current_system = ship['nav']['systemSymbol']
                waypoints = client.get_waypoints(current_system)
                
                # Find the nearest marketplace
                market_waypoint = None
                for waypoint in waypoints.get('data', []):
                    waypoint_data = client.get_waypoint(current_system, waypoint['symbol'])
                    if any(trait['symbol'] == 'MARKETPLACE' for trait in waypoint_data.get('data', {}).get('traits', [])):
                        market_waypoint = waypoint['symbol']
                        print(f"\nFound marketplace at: {market_waypoint}")
                        break
                    time.sleep(1)  # Add delay between waypoint checks
                
                if not market_waypoint:
                    print("No marketplace found in the system!")
                    return
        except Exception as e:
            print(f"Error checking waypoint: {str(e)}")
            return
        
        # Navigate to market if not already there
        if ship['nav']['waypointSymbol'] != market_waypoint:
            # Make sure we're in orbit before navigating
            if ship['nav']['status'] != 'IN_ORBIT':
                print("\nMoving to orbit before navigation...")
                client.orbit_ship(ship_symbol)
                time.sleep(1)  # Brief pause after changing status
            
            print(f"\nNavigating to marketplace {market_waypoint}...")
            nav_result = client.navigate_ship(ship_symbol, market_waypoint)
            arrival_time = nav_result['data']['nav']['route']['arrival']
            arrival = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            wait_time = (arrival - now).total_seconds()
            
            if wait_time > 0:
                print(f"Waiting {int(wait_time)} seconds for arrival...")
                time.sleep(wait_time + 1)  # Add 1 second buffer
            
            ship = get_ship_safely()
            print_ship_status(ship)
        
        # Dock at the market
        print("\nDocking at market...")
        client.dock_ship(ship_symbol)
        time.sleep(1)
        
        # Get market data
        market_data = client.get_market(ship['nav']['systemSymbol'], market_waypoint)
        print("\nMarket Prices:")
        for trade_good in market_data.get('data', {}).get('tradeGoods', []):
            print(f"  - {trade_good['symbol']}: {trade_good['sellPrice']} credits")
        
        # Sell each cargo item
        ship = get_ship_safely()
        for item in ship['cargo']['inventory']:
            try:
                print(f"\nSelling {item['units']} units of {item['symbol']}...")
                result = client.sell_goods(ship_symbol, item['symbol'], item['units'])
                if result and result.get('data'):
                    transaction = result['data']['transaction']
                    print(f"Sold for {transaction['totalPrice']} credits")
                    print(f"Price per unit: {transaction['pricePerUnit']} credits")
                else:
                    print("Sale failed:", result)
            except Exception as e:
                print(f"Error selling {item['symbol']}: {str(e)}")
        
        # Show final status
        ship = get_ship_safely()
        print("\nFinal Status:")
        print_ship_status(ship)
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_selling()
