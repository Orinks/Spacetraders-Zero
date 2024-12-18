import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import logging
from api.client import SpaceTradersClient
import time
from datetime import datetime, timezone

def test_mining():
    client = SpaceTradersClient()
    ship_symbol = "CDM2766-1"  # Our main ship
    target_waypoint = "X1-TY45-B10"  # Our target asteroid field
    
    def print_ship_status(ship_data):
        print("\nShip Status:")
        print(f"Location: {ship_data['nav']['waypointSymbol']}")
        print(f"Status: {ship_data['nav']['status']}")
        print(f"Flight Mode: {ship_data['nav']['flightMode']}")
        if 'route' in ship_data['nav']:
            route = ship_data['nav']['route']
            print(f"Route: {route['destination']['symbol']}")
            arrival = datetime.fromisoformat(route['arrival'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            time_remaining = (arrival - now).total_seconds()
            if time_remaining > 0:
                print(f"Arrival in: {int(time_remaining)} seconds")
            else:
                print("Arrival: Already passed")
    
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
    
    # Get initial ship details
    try:
        ship = get_ship_safely()
        print_ship_status(ship)
        
        # Wait for any ongoing navigation to complete
        if ship['nav']['status'] == 'IN_TRANSIT':
            print("\nShip is currently in transit...")
            check_interval = 5
            while True:
                ship = get_ship_safely()
                if ship['nav']['status'] != 'IN_TRANSIT':
                    print("Navigation complete!")
                    break
                    
                print(f"Still in transit... checking again in {check_interval} seconds")
                time.sleep(check_interval)
                check_interval = min(30, check_interval * 1.5)
            
            print_ship_status(ship)
        
        # First move to orbit if docked
        if ship['nav']['status'] == 'DOCKED':
            print("\nMoving to orbit...")
            client.orbit_ship(ship_symbol)
            ship['nav']['status'] = 'IN_ORBIT'
            print_ship_status(ship)
        
        # Navigate to asteroid if not already there
        if ship['nav']['waypointSymbol'] != target_waypoint:
            print(f"\nNavigating to asteroid field {target_waypoint}...")
            nav_result = client.navigate_ship(ship_symbol, target_waypoint)
            arrival_time = nav_result['data']['nav']['route']['arrival']
            print(f"Navigation started. Arrival time: {arrival_time}")
            
            # Update local ship state from navigation result
            ship = nav_result['data']
            
            # Wait for navigation with exponential backoff
            print("Waiting for navigation to complete...")
            check_interval = 5
            while True:
                ship = get_ship_safely()
                if ship['nav']['status'] == 'IN_ORBIT':
                    print("Navigation complete!")
                    break
                    
                print(f"Still in transit... checking again in {check_interval} seconds")
                time.sleep(check_interval)
                check_interval = min(30, check_interval * 1.5)
            
            print_ship_status(ship)
        
        # Try mining
        print("\nAttempting to extract resources...")
        try:
            result = client.extract_resources(ship_symbol)
            print("Mining Result:")
            if result and result.get('data'):
                extraction = result['data']['extraction']
                print(f"Extracted: {extraction['yield']['symbol']}")
                print(f"Units: {extraction['yield']['units']}")
                print(f"Cooldown: {extraction.get('cooldown', {}).get('remainingSeconds', 0)} seconds")
            else:
                print("No extraction data in response:", result)
        except Exception as e:
            print(f"Mining failed: {str(e)}")
            ship = get_ship_safely()
            print("\nFinal ship status:")
            print_ship_status(ship)
            
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_mining()
