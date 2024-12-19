import pytest
import sys
from unittest.mock import MagicMock

# Mock wxPython for tests
class MockWx:
    def __init__(self):
        self.Frame = MagicMock
        self.App = MagicMock
        self.BoxSizer = MagicMock
        self.TextCtrl = MagicMock
        self.Button = MagicMock
        self.VERTICAL = 'vertical'
        self.HORIZONTAL = 'horizontal'
        self.ID_ANY = -1
        self.EXPAND = 1
        self.ALL = 2
        self.DefaultPosition = (0, 0)
        self.DefaultSize = (0, 0)

@pytest.fixture(autouse=True)
def mock_wx(monkeypatch):
    """Mock wx module for all tests"""
    mock_wx = MockWx()
    monkeypatch.setitem(sys.modules, 'wx', mock_wx)
    return mock_wx