import logging
from src.api.client import SpaceTradersClient
import time
from datetime import datetime

import responses

@responses.activate
def test_gameplay():
    # Initialize client
    client = SpaceTradersClient()
    client.token = "test-token"  # Set test token
    
    # Mock agent info response
    mock_agent = {
        "data": {
            "symbol": "TEST_AGENT",
            "credits": 150000,
            "startingFaction": "COSMIC",
            "headquarters": "X1-TEST"
        }
    }
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/my/agent",
        json=mock_agent,
        status=200
    )
    
    # Get agent info
    agent_info = client.get_agent()
    print("\nAgent Info:")
    print(f"Symbol: {agent_info['data']['symbol']}")
    print(f"Credits: {agent_info['data']['credits']}")
    print(f"Starting Faction: {agent_info['data']['startingFaction']}")
    print(f"Headquarters: {agent_info['data']['headquarters']}")
    
    # Mock ships response
    mock_ships = {
        "data": [{
            "symbol": "TEST_SHIP",
            "nav": {
                "status": "DOCKED",
                "waypointSymbol": "X1-TEST-STATION",
                "systemSymbol": "X1-TEST"
            },
            "fuel": {
                "current": 100,
                "capacity": 100
            },
            "cargo": {
                "units": 0,
                "capacity": 100
            }
        }]
    }
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/my/ships",
        json=mock_ships,
        status=200
    )
    
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
        
        # Mock waypoints response
        mock_waypoints = {
            "data": [
                {
                    "symbol": "X1-TEST-1",
                    "type": "PLANET"
                },
                {
                    "symbol": "X1-TEST-2",
                    "type": "ASTEROID_FIELD"
                },
                {
                    "symbol": "X1-TEST-3",
                    "type": "STATION"
                }
            ]
        }
        responses.add(
            responses.GET,
            f"https://api.spacetraders.io/v2/systems/{current_system}/waypoints",
            json=mock_waypoints,
            status=200
        )
        
        waypoints = client.get_waypoints(current_system)
        print(f"\nWaypoints in system {current_system}:")
        for waypoint in waypoints.get('data', [])[:5]:  # Show first 5 waypoints
            print(f"  - {waypoint['symbol']}: {waypoint['type']}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_gameplay()
