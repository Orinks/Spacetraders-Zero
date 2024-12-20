import os
import sys
import logging
import time
from typing import Dict, Any

# Add src directory to Python path
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, src_dir)

from src.api.client import SpaceTradersClient
from src.agents.trader import AutomatedTrader
def on_agent_update(status: Dict[str, Any]) -> None:
    """Handle agent status updates"""
    if status.get("status") == "error":
        logging.error(f"Agent error: {status.get('error')}")
    else:
        logging.info(f"Agent status: {status}")

def main() -> None:
    """Main entry point for running the automated trader"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    try:
        # Initialize client and trader
        client = SpaceTradersClient()
        trader = AutomatedTrader(client, on_agent_update)
        
        # Start trading
        logging.info("Starting automated trader...")
        trader.start()
        
        # Keep running until interrupted
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Stopping automated trader...")
            trader.stop()
            
    except Exception as e:
        logging.error(f"Error in main: {e}", exc_info=True)

if __name__ == "__main__":
    main()
