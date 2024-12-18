import os
import sys

# Add src directory to Python path
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, src_dir)

from api.client import SpaceTradersClient
from agents.trader import AutomatedTrader
import time
import signal
import sys

def signal_handler(signum, frame):
    print("\nStopping agent...")
    if 'trader' in globals():
        trader.stop()
    sys.exit(0)

def main():
    # Set up signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    client = SpaceTradersClient()
    global trader
    trader = AutomatedTrader(client)
    trader.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping agent...")
        trader.stop()

if __name__ == "__main__":
    main()
