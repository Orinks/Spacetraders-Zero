from src.api.client import SpaceTradersClient
from src.api.client import logging
import time

logging.basicConfig(level=logging.INFO)

# Create client and register new agent
client = SpaceTradersClient()
agent_name = f"CDM{int(time.time())%10000}"  # Use last 4 digits of timestamp
result = client.register_new_agent(agent_name, "COSMIC")

if result and result.get("data", {}).get("token"):
    token = result["data"]["token"]
    # Save token to .env file
    with open(".env", "w") as f:
        f.write(f"SPACETRADERS_TOKEN={token}\n")
        f.write(f"SPACETRADERS_API_URL=https://api.spacetraders.io/v2\n")
    logging.info("Successfully registered new agent and saved token")
    
    # Print agent details
    agent_data = result.get("data", {}).get("agent", {})
    logging.info(f"Agent Details:")
    logging.info(f"  Symbol: {agent_data.get('symbol')}")
    logging.info(f"  Headquarters: {agent_data.get('headquarters')}")
    logging.info(f"  Credits: {agent_data.get('credits')}")
    
    # Print ship details
    ship_data = result.get("data", {}).get("ship", {})
    logging.info(f"\nStarting Ship:")
    logging.info(f"  Symbol: {ship_data.get('symbol')}")
    logging.info(f"  Frame: {ship_data.get('frame', {}).get('name')}")
    logging.info(f"  Fuel: {ship_data.get('fuel', {}).get('current')}/{ship_data.get('fuel', {}).get('capacity')}")
else:
    logging.error("Failed to register agent")
