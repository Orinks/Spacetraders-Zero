# SpaceTraders Zero

An accessible zero-player game powered by [SpaceTraders.io](https://spacetraders.io) API with an accessible [wxPython](https://wxpython.org/) graphical interface.

## Features

- Automated agent activities in SpaceTraders universe
- Accessible UI with screen reader support
- Real-time monitoring of agent actions
- Automated trading and navigation

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
- Windows: `venv\Scripts\activate`
- Unix/MacOS: `source venv/bin/activate`

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. (Optional) Create a `.env` file with your SpaceTraders API key:
```env
SPACETRADERS_TOKEN=your_token_here
```
Note: If you don't have a token yet, you can register a new agent through the UI which will automatically save your token.

5. Run the game:
```bash
python src/main.py
```

## Project Structure

```
spacetraders-zero/
├── src/
│   ├── main.py              # Entry point
│   ├── api/                 # SpaceTraders API integration
│   │   └── client.py        # API client
│   ├── agents/              # Agent logic
│   │   └── trader.py        # Trading agent
│   └── ui/                  # User interface
│       └── main_window.py   # Main UI window
├── tests/                   # Unit tests
├── requirements.txt         # Dependencies
└── README.md               # Documentation
```
