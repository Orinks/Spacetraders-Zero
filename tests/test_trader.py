import logging
from src.api.client import SpaceTradersClient
from src.agents.trader import AutomatedTrader
from dotenv import load_dotenv

def main():
    """Test the automated trader"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load environment variables
    load_dotenv()
    token = os.getenv('SPACETRADERS_TOKEN')
    
    if not token:
        logging.error("No token found in .env file")
        return
        
    # Create client and trader
    client = SpaceTradersClient()
    client.token = token
    
    # Create and start trader
    trader = AutomatedTrader(client)
    trader.start()
    
    try:
        # Keep the script running
        while True:
            pass
    except KeyboardInterrupt:
        logging.info("Stopping trader")
        trader.stop()

if __name__ == "__main__":
    main()
