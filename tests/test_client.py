import pytest
from src.api.client import SpaceTradersClient
import os
import responses
import json
from jsonschema import validate, validators
from unittest.mock import patch
from src.config import Settings

OPENAPI_SCHEMA_PATH = "openapi.json"

def load_openapi_schema(path):
    with open(path, 'r') as f:
        schema = json.load(f)
        # Create a validator that includes the full schema
        validator = validators.Draft202012Validator(schema)
        return schema, validator

@pytest.fixture
def client():
    # Clean up any existing config files
    if os.path.exists('config/config.json'):
        os.remove('config/config.json')
    if os.path.exists('config/.env'):
        os.remove('config/.env')
    return SpaceTradersClient()

@responses.activate
def test_register_sets_token(tmp_path):
    """Test that registration properly sets the token and updates config.json"""
    # Create a subdirectory for the config file
    config_dir = tmp_path / "config"
    os.makedirs(config_dir, exist_ok=True)
    
    config_path = config_dir / "config.json"
    env_path = config_dir / ".env"
    
    # Create empty config file
    with open(config_path, 'w') as f:
        json.dump({}, f)
    
    # Create empty .env file
    with open(env_path, 'w') as f:
        pass
    
    # Create a test settings instance with patched paths
    with patch('src.config.CONFIG_PATH', str(config_path)), \
         patch('src.config.ENV_PATH', str(env_path)), \
         patch('src.api.client.CONFIG_PATH', str(config_path)), \
         patch('src.api.client.ENV_PATH', str(env_path)), \
         patch.dict('os.environ', {'PWD': str(config_dir)}):
        
        # Create a new settings instance
        test_settings = Settings(
            _env_file=str(env_path),  # Enable .env file loading for this test
            spacetraders_token=None,
            api_url='https://api.spacetraders.io/v2'
        )
        
        # Mock get_settings to always return our test instance
        def mock_get_settings():
            return test_settings
        
        # Patch the settings instance and paths
        with patch('src.config.settings', test_settings), \
             patch('src.config.get_settings', mock_get_settings), \
             patch('src.api.client.settings', test_settings):
            
            client = SpaceTradersClient()

            # Mock registration response
            mock_response = {
                "data": {
                    "token": "test-token",
                    "agent": {
                        "accountId": "test-account",
                        "symbol": "TEST_AGENT",
                        "headquarters": "X1-TEST",
                        "credits": 150000,
                        "startingFaction": "COSMIC",
                        "shipCount": 2
                    }
                }
            }

            responses.add(
                responses.POST,
                "https://api.spacetraders.io/v2/register",
                json=mock_response,
                status=201
            )

            # Register new agent
            client.register_new_agent("TEST_AGENT")
            
            assert client.token == "test-token"
            
            # Print out actual paths and content for debugging
            print(f"Config path: {config_path}")
            print(f"Env path: {env_path}")
            print(f"Config exists: {os.path.exists(config_path)}")
            print(f"Env exists: {os.path.exists(env_path)}")
            
            if os.path.exists(config_path):
                with open(config_path) as f:
                    print(f"Config content: {f.read()}")
            
            if os.path.exists(env_path):
                with open(env_path) as f:
                    print(f"Env content: {f.read()}")
            
            # Check that token was saved to config.json
            with open(config_path) as f:
                config = json.load(f)
                assert config.get('SPACETRADERS_TOKEN') == "test-token"
            
            # Check that token was saved to .env
            with open(env_path) as f:
                content = f.read()
                assert 'SPACETRADERS_TOKEN=test-token\n' in content
            
            # Create a new settings instance to verify token is loaded from files
            new_settings = Settings(
                _env_file=str(env_path),  # Enable .env file loading
                api_url='https://api.spacetraders.io/v2'
            )
            assert new_settings.spacetraders_token == "test-token"

@responses.activate
def test_get_contracts():
    """Test getting contracts"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_contracts = {
        "data": [
            {
                "id": "test-contract",
                "factionSymbol": "COSMIC",
                "type": "PROCUREMENT",
                "terms": {
                    "deadline": "2024-03-20T00:00:00.000Z",
                    "payment": {
                        "onAccepted": 100000,
                        "onFulfilled": 200000
                    },
                    "deliver": []
                },
                "accepted": False,
                "fulfilled": False,
                "expiration": "2024-03-20T00:00:00.000Z",
                "deadlineToAccept": "2024-03-20T00:00:00.000Z"
            }
        ],
        "meta": {
            "total": 1,
            "page": 1,
            "limit": 10
        }
    }
    
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/my/contracts",
        json=mock_contracts,
        status=200
    )
    
    result = client.get_contracts()
    assert result == mock_contracts
    assert len(result["data"]) == 1
    assert result["data"][0]["id"] == "test-contract"
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    contracts_schema = schema["paths"]["/my/contracts"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_contracts)

@responses.activate
def test_get_agent():
    """Test getting agent details"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_agent = {
        "data": {
            "accountId": "test-account",
            "symbol": "TEST_AGENT",
            "headquarters": "X1-TEST",
            "credits": 150000,
            "startingFaction": "COSMIC",
            "shipCount": 2
        }
    }
    
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/my/agent",
        json=mock_agent,
        status=200
    )
    
    result = client.get_agent()
    assert result == mock_agent
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    agent_schema = schema["paths"]["/my/agent"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_agent)

@responses.activate
def test_api_error_response():
    """Test API error response schema"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    error_response = {
        "error": {
            "code": 4000,
            "message": "Token is invalid."
        }
    }
    
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/my/ships",
        json=error_response,
        status=401
    )
    
    with pytest.raises(Exception) as exc_info:
        client.get_ships()
    
    # Validate error schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    error_schema = {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "integer"
                    },
                    "message": {
                        "type": "string"
                    }
                },
                "required": ["code", "message"]
            }
        },
        "required": ["error"]
    }
    validator.validate(error_response)

@responses.activate
def test_list_ships():
    """Test getting ships list"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_ships = {
        "data": [
            {
                "symbol": "TEST_SHIP",
                "registration": {
                    "name": "Test Ship",
                    "factionSymbol": "COSMIC",
                    "role": "COMMAND"
                },
                "nav": {
                    "systemSymbol": "X1-TEST",
                    "waypointSymbol": "X1-TEST-STATION",
                    "route": {
                        "departure": {
                            "symbol": "X1-TEST-STATION",
                            "type": "ORBITAL_STATION",
                            "systemSymbol": "X1-TEST",
                            "x": 0,
                            "y": 0
                        },
                        "destination": {
                            "symbol": "X1-TEST-STATION",
                            "type": "ORBITAL_STATION",
                            "systemSymbol": "X1-TEST",
                            "x": 0,
                            "y": 0
                        },
                        "departureTime": "2024-12-18T01:08:06-05:00",
                        "arrival": "2024-12-18T01:08:06-05:00"
                    },
                    "status": "DOCKED",
                    "flightMode": "CRUISE"
                },
                "crew": {
                    "current": 0,
                    "required": 0,
                    "capacity": 0,
                    "rotation": "STRICT",
                    "morale": 100,
                    "wages": 0
                },
                "frame": {
                    "symbol": "FRAME_PROBE",
                    "name": "Probe",
                    "description": "A small, unmanned spacecraft used for exploration, reconnaissance, and scientific research.",
                    "condition": 100,
                    "moduleSlots": 0,
                    "mountingPoints": 0,
                    "fuelCapacity": 0,
                    "requirements": {
                        "power": 0,
                        "crew": 0
                    }
                },
                "reactor": {
                    "symbol": "REACTOR_SOLAR_I",
                    "name": "Solar Reactor I",
                    "description": "A basic solar power reactor, converting solar energy into electrical power.",
                    "condition": 100,
                    "powerOutput": 3,
                    "requirements": {
                        "crew": 0
                    }
                },
                "engine": {
                    "symbol": "ENGINE_IMPULSE_DRIVE_I",
                    "name": "Impulse Drive I",
                    "description": "A basic low-energy propulsion system that generates thrust for interplanetary travel.",
                    "condition": 100,
                    "speed": 2,
                    "requirements": {
                        "power": 1,
                        "crew": 0
                    }
                },
                "modules": [],
                "mounts": [],
                "cargo": {
                    "capacity": 0,
                    "units": 0,
                    "inventory": []
                },
                "fuel": {
                    "current": 100,
                    "capacity": 100,
                    "consumed": {
                        "amount": 0,
                        "timestamp": "2024-12-18T01:08:06-05:00"
                    }
                }
            }
        ],
        "meta": {
            "total": 1,
            "page": 1,
            "limit": 10
        }
    }
    
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/my/ships",
        json=mock_ships,
        status=200
    )
    
    result = client.get_ships()
    assert result == mock_ships
    assert len(result["data"]) == 1
    assert result["data"][0]["symbol"] == "TEST_SHIP"
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    ships_schema = schema["paths"]["/my/ships"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_ships)

@responses.activate
def test_purchase_ship():
    """Test purchasing a ship"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_purchase = {
        "data": {
            "agent": {
                "accountId": "test-account",
                "symbol": "TEST_AGENT",
                "headquarters": "X1-TEST",
                "credits": 150000,
                "startingFaction": "COSMIC",
                "shipCount": 2
            },
            "ship": {
                "symbol": "TEST_SHIP_2",
                "registration": {
                    "name": "Test Ship 2",
                    "factionSymbol": "COSMIC",
                    "role": "COMMAND"
                },
                "nav": {
                    "systemSymbol": "X1-TEST",
                    "waypointSymbol": "X1-TEST-STATION",
                    "route": {
                        "departure": {
                            "symbol": "X1-TEST-STATION",
                            "type": "ORBITAL_STATION",
                            "systemSymbol": "X1-TEST",
                            "x": 0,
                            "y": 0
                        },
                        "destination": {
                            "symbol": "X1-TEST-STATION",
                            "type": "ORBITAL_STATION",
                            "systemSymbol": "X1-TEST",
                            "x": 0,
                            "y": 0
                        },
                        "departureTime": "2024-12-18T01:08:06-05:00",
                        "arrival": "2024-12-18T01:08:06-05:00"
                    },
                    "status": "DOCKED",
                    "flightMode": "CRUISE"
                },
                "crew": {
                    "current": 0,
                    "required": 0,
                    "capacity": 0,
                    "rotation": "STRICT",
                    "morale": 100,
                    "wages": 0
                },
                "frame": {
                    "symbol": "FRAME_PROBE",
                    "name": "Probe",
                    "description": "A small, unmanned spacecraft used for exploration, reconnaissance, and scientific research.",
                    "condition": 100,
                    "moduleSlots": 0,
                    "mountingPoints": 0,
                    "fuelCapacity": 0,
                    "requirements": {
                        "power": 0,
                        "crew": 0
                    }
                },
                "reactor": {
                    "symbol": "REACTOR_SOLAR_I",
                    "name": "Solar Reactor I",
                    "description": "A basic solar power reactor, converting solar energy into electrical power.",
                    "condition": 100,
                    "powerOutput": 3,
                    "requirements": {
                        "crew": 0
                    }
                },
                "engine": {
                    "symbol": "ENGINE_IMPULSE_DRIVE_I",
                    "name": "Impulse Drive I",
                    "description": "A basic low-energy propulsion system that generates thrust for interplanetary travel.",
                    "condition": 100,
                    "speed": 2,
                    "requirements": {
                        "power": 1,
                        "crew": 0
                    }
                },
                "modules": [],
                "mounts": [],
                "cargo": {
                    "capacity": 0,
                    "units": 0,
                    "inventory": []
                },
                "fuel": {
                    "current": 100,
                    "capacity": 100,
                    "consumed": {
                        "amount": 0,
                        "timestamp": "2024-12-18T01:08:06-05:00"
                    }
                }
            },
            "transaction": {
                "waypointSymbol": "X1-TEST-STATION",
                "shipSymbol": "TEST_SHIP_2",
                "price": 50000,
                "agentSymbol": "TEST_AGENT",
                "timestamp": "2024-12-18T01:08:06-05:00"
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships",
        json=mock_purchase,
        status=201
    )
    
    result = client.purchase_ship("SHIP_PROBE", "X1-TEST-STATION")
    assert result == mock_purchase
    assert result["data"]["ship"]["symbol"] == "TEST_SHIP_2"
    assert result["data"]["transaction"]["price"] == 50000
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    purchase_schema = schema["paths"]["/my/ships"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    validator.validate(mock_purchase)

@responses.activate
def test_get_market():
    """Test getting market data"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_market = {
        "data": {
            "symbol": "X1-TEST-MARKET",
            "exports": [
                {
                    "symbol": "PRECIOUS_STONES",
                    "name": "Precious Stones",
                    "description": "Rare and valuable gems and minerals used for both industrial and decorative purposes."
                }
            ],
            "imports": [
                {
                    "symbol": "ADVANCED_MACHINERY",
                    "name": "Advanced Machinery",
                    "description": "Complex mechanical and electronic systems used in manufacturing."
                }
            ],
            "exchange": [
                {
                    "symbol": "FUEL",
                    "name": "Fuel",
                    "description": "High-energy fuel used in spacecraft propulsion systems."
                }
            ],
            "transactions": [],
            "tradeGoods": [
                {
                    "symbol": "PRECIOUS_STONES",
                    "type": "EXPORT",
                    "tradeVolume": 100,
                    "supply": "ABUNDANT",
                    "purchasePrice": 5000,
                    "sellPrice": 4500
                }
            ]
        }
    }
    
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/systems/X1-TEST/waypoints/X1-TEST-MARKET/market",
        json=mock_market,
        status=200
    )
    
    result = client.get_market("X1-TEST", "X1-TEST-MARKET")
    assert result == mock_market
    assert result["data"]["symbol"] == "X1-TEST-MARKET"
    assert len(result["data"]["tradeGoods"]) == 1
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    market_schema = schema["paths"]["/systems/{systemSymbol}/waypoints/{waypointSymbol}/market"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_market)

@responses.activate
def test_ship_navigation():
    """Test ship navigation capabilities"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_nav = {
        "data": {
            "nav": {
                "systemSymbol": "X1-TEST",
                "waypointSymbol": "X1-TEST-STATION",
                "route": {
                    "departure": {
                        "symbol": "X1-TEST-STATION",
                        "type": "ORBITAL_STATION",
                        "systemSymbol": "X1-TEST",
                        "x": 0,
                        "y": 0
                    },
                    "destination": {
                        "symbol": "X1-TEST-PLANET",
                        "type": "PLANET",
                        "systemSymbol": "X1-TEST",
                        "x": 10,
                        "y": 10
                    },
                    "departureTime": "2024-12-18T01:11:08-05:00",
                    "arrival": "2024-12-18T02:11:08-05:00"
                },
                "status": "IN_TRANSIT",
                "flightMode": "CRUISE"
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/navigate",
        json=mock_nav,
        status=200
    )
    
    result = client.navigate_ship("TEST_SHIP", "X1-TEST-PLANET")
    assert result == mock_nav
    assert result["data"]["nav"]["status"] == "IN_TRANSIT"
    assert result["data"]["nav"]["route"]["destination"]["symbol"] == "X1-TEST-PLANET"
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    nav_schema = schema["paths"]["/my/ships/{shipSymbol}/navigate"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_nav)

@responses.activate
def test_ship_cargo():
    """Test ship cargo operations"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_transfer = {
        "data": {
            "cargo": {
                "capacity": 100,
                "units": 40,
                "inventory": [
                    {
                        "symbol": "PRECIOUS_STONES",
                        "name": "Precious Stones",
                        "description": "Rare and valuable gems and minerals.",
                        "units": 40
                    }
                ]
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/transfer",
        json=mock_transfer,
        status=200
    )
    
    result = client.transfer_cargo(
        "TEST_SHIP",
        "PRECIOUS_STONES",
        10,
        "TEST_SHIP_2"
    )
    assert result == mock_transfer
    assert result["data"]["cargo"]["units"] == 40
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    transfer_schema = schema["paths"]["/my/ships/{shipSymbol}/transfer"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_transfer)

@responses.activate
def test_system_waypoints():
    """Test getting system waypoints"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_waypoints = {
        "data": [
            {
                "symbol": "X1-TEST-STATION",
                "type": "ORBITAL_STATION",
                "systemSymbol": "X1-TEST",
                "x": 0,
                "y": 0,
                "orbitals": [],
                "traits": [
                    {
                        "symbol": "MARKETPLACE",
                        "name": "Marketplace",
                        "description": "A bustling marketplace where goods are traded."
                    },
                    {
                        "symbol": "SHIPYARD",
                        "name": "Shipyard",
                        "description": "A shipyard for constructing and repairing ships."
                    }
                ],
                "chart": {
                    "submittedBy": "TEST_AGENT",
                    "submittedOn": "2024-12-18T01:11:08-05:00"
                }
            }
        ],
        "meta": {
            "total": 1,
            "page": 1,
            "limit": 10
        }
    }
    
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/systems/X1-TEST/waypoints",
        json=mock_waypoints,
        status=200
    )
    
    result = client.get_system_waypoints("X1-TEST")
    assert result == mock_waypoints
    assert len(result["data"]) == 1
    assert "MARKETPLACE" in [t["symbol"] for t in result["data"][0]["traits"]]
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    waypoints_schema = schema["paths"]["/systems/{systemSymbol}/waypoints"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_waypoints)

@responses.activate
def test_ship_fuel():
    """Test ship refueling"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_refuel = {
        "data": {
            "agent": {
                "accountId": "test-account",
                "symbol": "TEST_AGENT",
                "credits": 148730,
                "startingFaction": "COSMIC",
                "shipCount": 1
            },
            "fuel": {
                "current": 1000,
                "capacity": 1000,
                "consumed": {
                    "amount": 0,
                    "timestamp": "2024-12-18T01:11:08-05:00"
                }
            },
            "transaction": {
                "waypointSymbol": "X1-TEST-STATION",
                "shipSymbol": "TEST_SHIP",
                "tradeSymbol": "FUEL",
                "totalPrice": 1270,
                "units": 100,
                "timestamp": "2024-12-18T01:11:08-05:00"
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/refuel",
        json=mock_refuel,
        status=200
    )
    
    result = client.refuel_ship("TEST_SHIP")
    assert result == mock_refuel
    assert result["data"]["fuel"]["current"] == 1000
    assert result["data"]["transaction"]["tradeSymbol"] == "FUEL"
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    refuel_schema = schema["paths"]["/my/ships/{shipSymbol}/refuel"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_refuel)

@responses.activate
def test_ship_extraction():
    """Test ship mining and extraction operations"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_extract = {
        "data": {
            "cooldown": {
                "shipSymbol": "TEST_SHIP",
                "totalSeconds": 60,
                "remainingSeconds": 60,
                "expiration": "2024-12-18T01:14:39-05:00"
            },
            "extraction": {
                "shipSymbol": "TEST_SHIP",
                "yield": {
                    "symbol": "IRON_ORE",
                    "units": 10
                }
            },
            "cargo": {
                "capacity": 100,
                "units": 10,
                "inventory": [
                    {
                        "symbol": "IRON_ORE",
                        "name": "Iron Ore",
                        "description": "A common ore used in construction and manufacturing.",
                        "units": 10
                    }
                ]
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/extract",
        json=mock_extract,
        status=201
    )
    
    result = client.extract_resources("TEST_SHIP")
    assert result == mock_extract
    assert result["data"]["extraction"]["yield"]["symbol"] == "IRON_ORE"
    assert result["data"]["cargo"]["units"] == 10
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    extract_schema = schema["paths"]["/my/ships/{shipSymbol}/extract"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    validator.validate(mock_extract)

@responses.activate
def test_ship_combat_scanning():
    """Test ship combat and scanning capabilities"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_scan = {
        "data": {
            "cooldown": {
                "shipSymbol": "TEST_SHIP",
                "totalSeconds": 60,
                "remainingSeconds": 60,
                "expiration": "2024-12-18T01:14:39-05:00"
            },
            "ships": [
                {
                    "symbol": "ENEMY_SHIP",
                    "registration": {
                        "name": "Enemy Ship",
                        "factionSymbol": "PIRATES",
                        "role": "HUNTER"
                    },
                    "nav": {
                        "systemSymbol": "X1-TEST",
                        "waypointSymbol": "X1-TEST-ASTEROID",
                        "status": "IN_ORBIT"
                    },
                    "frame": {
                        "symbol": "FRAME_FIGHTER"
                    }
                }
            ]
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/scan/ships",
        json=mock_scan,
        status=201
    )
    
    result = client.scan_ships("TEST_SHIP")
    assert result == mock_scan
    assert len(result["data"]["ships"]) == 1
    assert result["data"]["ships"][0]["registration"]["role"] == "HUNTER"
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    scan_schema = schema["paths"]["/my/ships/{shipSymbol}/scan/ships"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    validator.validate(mock_scan)

@responses.activate
def test_contract_negotiation():
    """Test contract negotiation and management"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_contract = {
        "data": {
            "contract": {
                "id": "test-contract",
                "factionSymbol": "COSMIC",
                "type": "PROCUREMENT",
                "terms": {
                    "deadline": "2024-12-25T01:13:39-05:00",
                    "payment": {
                        "onAccepted": 10000,
                        "onFulfilled": 50000
                    },
                    "deliver": [
                        {
                            "tradeSymbol": "IRON_ORE",
                            "destinationSymbol": "X1-TEST-STATION",
                            "unitsRequired": 100,
                            "unitsFulfilled": 0
                        }
                    ]
                },
                "accepted": False,
                "fulfilled": False,
                "expiration": "2024-12-19T01:13:39-05:00",
                "deadlineToAccept": "2024-12-19T01:13:39-05:00"
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/negotiate/contract",
        json=mock_contract,
        status=201
    )
    
    result = client.negotiate_contract("TEST_SHIP")
    assert result == mock_contract
    assert result["data"]["contract"]["type"] == "PROCUREMENT"
    assert not result["data"]["contract"]["accepted"]
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    contract_schema = schema["paths"]["/my/ships/{shipSymbol}/negotiate/contract"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    validator.validate(mock_contract)

@responses.activate
def test_ship_repair():
    """Test ship repair functionality"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_repair = {
        "data": {
            "agent": {
                "accountId": "test-account",
                "symbol": "TEST_AGENT",
                "credits": 148730,
                "startingFaction": "COSMIC",
                "shipCount": 1
            },
            "ship": {
                "symbol": "TEST_SHIP",
                "registration": {
                    "name": "Test Ship",
                    "factionSymbol": "COSMIC",
                    "role": "COMMAND"
                },
                "frame": {
                    "symbol": "FRAME_FRIGATE",
                    "condition": 100
                },
                "reactor": {
                    "symbol": "REACTOR_SOLAR_I",
                    "condition": 100
                },
                "engine": {
                    "symbol": "ENGINE_ION_I",
                    "condition": 100
                }
            },
            "transaction": {
                "waypointSymbol": "X1-TEST-STATION",
                "shipSymbol": "TEST_SHIP",
                "totalPrice": 1000,
                "timestamp": "2024-12-18T01:13:39-05:00"
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/repair",
        json=mock_repair,
        status=200
    )
    
    result = client.repair_ship("TEST_SHIP")
    assert result == mock_repair
    assert result["data"]["ship"]["frame"]["condition"] == 100
    assert result["data"]["transaction"]["totalPrice"] == 1000
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    repair_schema = schema["paths"]["/my/ships/{shipSymbol}/repair"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_repair)

@responses.activate
def test_jump_gate_travel():
    """Test jump gate travel between systems"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_jump = {
        "data": {
            "cooldown": {
                "shipSymbol": "TEST_SHIP",
                "totalSeconds": 60,
                "remainingSeconds": 60,
                "expiration": "2024-12-18T01:14:39-05:00"
            },
            "nav": {
                "systemSymbol": "X1-TEST-2",
                "waypointSymbol": "X1-TEST-2-JUMP_GATE",
                "route": {
                    "departure": {
                        "symbol": "X1-TEST-JUMP_GATE",
                        "type": "JUMP_GATE",
                        "systemSymbol": "X1-TEST",
                        "x": 0,
                        "y": 0
                    },
                    "destination": {
                        "symbol": "X1-TEST-2-JUMP_GATE",
                        "type": "JUMP_GATE",
                        "systemSymbol": "X1-TEST-2",
                        "x": 100,
                        "y": 100
                    },
                    "departureTime": "2024-12-18T01:13:39-05:00",
                    "arrival": "2024-12-18T01:14:39-05:00"
                },
                "status": "IN_TRANSIT",
                "flightMode": "CRUISE"
            }
        }
    }
    
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/TEST_SHIP/jump",
        json=mock_jump,
        status=200
    )
    
    result = client.jump_ship("TEST_SHIP", "X1-TEST-2")
    assert result == mock_jump
    assert result["data"]["nav"]["systemSymbol"] == "X1-TEST-2"
    assert result["data"]["nav"]["status"] == "IN_TRANSIT"
    
    # Validate response schema
    schema, validator = load_openapi_schema(OPENAPI_SCHEMA_PATH)
    jump_schema = schema["paths"]["/my/ships/{shipSymbol}/jump"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    validator.validate(mock_jump)

import unittest
from unittest.mock import patch, MagicMock
import time
import requests
import logging
from src.api.client import SpaceTradersClient, CircuitState

# Configure logging to be less noisy during tests
logging.getLogger().setLevel(logging.INFO)

class TestSpaceTradersClient(unittest.TestCase):
    def setUp(self):
        self.client = SpaceTradersClient()
        # Mock the token to avoid actual registration
        self.client.token = "test_token"
        logging.info("\n=== Starting new test ===")
        
    def test_circuit_breaker_opens_after_errors(self):
        """Test that circuit breaker opens after threshold errors"""
        logging.info("[TEST] Simulating multiple failures to trigger circuit breaker")
        endpoint = "test/endpoint"
        
        # Simulate multiple failures
        for _ in range(self.client.error_threshold):
            self.client._update_circuit_state(False, endpoint)
            
        self.assertEqual(self.client.circuit_state, CircuitState.OPEN)
        
    def test_circuit_breaker_half_open_after_timeout(self):
        """Test that circuit breaker moves to half-open state after timeout"""
        logging.info("[TEST] Simulating circuit breaker recovery after timeout")
        endpoint = "test/endpoint"
        
        # Open the circuit
        for _ in range(self.client.error_threshold):
            self.client._update_circuit_state(False, endpoint)
            
        # Set last error time to be older than reset timeout
        self.client.last_error_time = time.time() - (self.client.reset_timeout + 1)
        
        # Check circuit breaker state
        self.assertTrue(self.client._check_circuit_breaker(endpoint))
        self.assertEqual(self.client.circuit_state, CircuitState.HALF_OPEN)
        
    def test_circuit_breaker_closes_after_success(self):
        """Test that circuit breaker closes after success threshold"""
        logging.info("[TEST] Simulating successful requests to close circuit breaker")
        endpoint = "test/endpoint"
        
        # Set to half-open state
        self.client.circuit_state = CircuitState.HALF_OPEN
        
        # Simulate successful requests
        for _ in range(self.client.success_threshold):
            self.client._update_circuit_state(True, endpoint)
            
        self.assertEqual(self.client.circuit_state, CircuitState.CLOSED)
        
    @patch('time.time')
    @patch('requests.get')
    def test_adaptive_rate_limiting(self, mock_get, mock_time):
        """Test that rate limiting adapts based on response times"""
        logging.info("[TEST] Testing adaptive rate limiting with simulated slow responses")
        # Set up time mock to advance by 0.1 seconds each call
        mock_time.side_effect = [x * 0.1 for x in range(100)]
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response
        
        # Set initial rate higher for testing
        self.client.requests_per_second = 5.0
        self.client.min_request_interval = 1.0 / self.client.requests_per_second
        initial_rate = self.client.requests_per_second
        
        # Fill response times with slow responses
        self.client.response_times.extend([2.0] * 50)  # 50 slow responses
        
        # Set last adjustment time to trigger immediate adjustment
        self.client.last_rate_adjustment = 0
        
        # Trigger rate adjustment
        self.client._wait_for_rate_limit()
        
        # Check that rate was reduced
        self.assertLess(self.client.requests_per_second, initial_rate)
        
    @patch('time.time')
    @patch('requests.get')
    def test_exponential_backoff(self, mock_get, mock_time):
        """Test exponential backoff with jitter on failures"""
        logging.info("[TEST] Testing exponential backoff with simulated failures")
        # Set up time mock
        current_time = 0
        def time_side_effect():
            nonlocal current_time
            current_time += 0.1
            return current_time
        mock_time.side_effect = time_side_effect
        
        # Mock failed response
        mock_get.side_effect = requests.exceptions.RequestException("[TEST] Simulated API error for testing")
        
        with self.assertRaises(RuntimeError):
            self.client._make_request("GET", "test/endpoint")
        
        # Verify number of retries
        self.assertEqual(mock_get.call_count, 3)  # Initial attempt + 2 retries

if __name__ == '__main__':
    unittest.main()
