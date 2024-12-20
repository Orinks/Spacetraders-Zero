import wx
import os

import sys

import logging

from dotenv import load_dotenv



# Add the project root directory to Python path when running directly

if __name__ == "__main__":

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    sys.path.insert(0, project_root)



try:

    from src.ui.main_window import MainWindow

except ImportError:

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

