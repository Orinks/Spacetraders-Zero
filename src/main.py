import wx
import os
import logging
from dotenv import load_dotenv
from ui.main_window import MainWindow

def main():
    """Main entry point for SpaceTraders Zero"""
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/spacetraders.log')
        ]
    )
    logger = logging.getLogger(__name__)
    
    logger.info("Starting SpaceTraders Zero")
    
    # Load environment variables
    load_dotenv()
    logger.info("Environment variables loaded")
    
    # Initialize WX App
    logger.info("Initializing WX App")
    app = wx.App()
    frame = MainWindow(None, title="SpaceTraders Zero")
    frame.Show()
    logger.info("Main window created and shown")
    app.MainLoop()

if __name__ == "__main__":
    main()
