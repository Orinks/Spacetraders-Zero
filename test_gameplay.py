import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import logging
from api.client import SpaceTradersClient
import time
from datetime import datetime

def test_gameplay():
    # Initialize client
    client = SpaceTradersClient()
    
    # Get agent info
    agent_info = client.get_agent()
    print("\nAgent Info:")
    print(f"Symbol: {agent_info['data']['symbol']}")
    print(f"Credits: {agent_info['data']['credits']}")
    print(f"Starting Faction: {agent_info['data']['startingFaction']}")
    print(f"Headquarters: {agent_info['data']['headquarters']}")
    
    # List available ships
    ships = client.get_ships()
    print("\nAvailable Ships:")
    for ship in ships.get('data', []):
        print(f"Ship {ship['symbol']}:")
        print(f"  - Nav Status: {ship['nav']['status']}")
        print(f"  - Location: {ship['nav']['waypointSymbol']}")
        print(f"  - Fuel: {ship['fuel']['current']}/{ship['fuel']['capacity']}")
        print(f"  - Cargo: {ship['cargo']['units']}/{ship['cargo']['capacity']}")

    # Get current system info
    if ships.get('data'):
        current_system = ships['data'][0]['nav']['systemSymbol']
        waypoints = client.get_waypoints(current_system)
        print(f"\nWaypoints in system {current_system}:")
        for waypoint in waypoints.get('data', [])[:5]:  # Show first 5 waypoints
            print(f"  - {waypoint['symbol']}: {waypoint['type']}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_gameplay()
