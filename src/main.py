import wx
import os
from dotenv import load_dotenv
from ui.main_window import MainWindow

def main():
    """Main entry point for SpaceTraders Zero"""
    # Load environment variables
    load_dotenv()
    
    # Initialize WX App
    app = wx.App()
    frame = MainWindow(None, title="SpaceTraders Zero")
    frame.Show()
    app.MainLoop()

if __name__ == "__main__":
    main()
