import pytest
from src.api.client import SpaceTradersClient
import os
import responses

@pytest.fixture
def client():
    return SpaceTradersClient()

@responses.activate
def test_register_sets_token():
    """Test that registration properly sets the token for future requests"""
    client = SpaceTradersClient()
    
    # Mock registration response
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/register",
        json={"data": {"token": "test-token"}},
        status=200
    )
    
    # Register new agent
    client.register_new_agent("TEST_AGENT")
    
    assert client.token == "test-token"
    
    # Check that token was saved to .env
    with open('.env', 'r') as f:
        content = f.read()
        assert 'SPACETRADERS_TOKEN=test-token' in content
    
    # Check that token was saved to .env
    with open('.env', 'r') as f:
        content = f.read()
        assert 'SPACETRADERS_TOKEN=test-token' in content

@responses.activate 
def test_auth_header_present():
    """Test that authenticated requests include the token"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    # Mock contracts endpoint
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/my/contracts",
        json={"data": []},
        status=200
    )
    
    # Make request
    client.get_contracts()
    
    # Check that last request had auth header
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-token"

@responses.activate
def test_get_contracts():
    """Test getting contracts"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    mock_contracts = {
        "data": [
            {
                "id": "test-contract",
                "type": "PROCUREMENT",
                "terms": {
                    "deadline": "2024-03-20",
                    "payment": {"onAccepted": 100000}
                }
            }
        ]
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

@responses.activate
def test_accept_contract():
    """Test accepting a contract"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    contract_id = "test-contract"
    mock_response = {
        "data": {
            "id": contract_id,
            "accepted": True
        }
    }
    
    responses.add(
        responses.POST,
        f"https://api.spacetraders.io/v2/my/contracts/{contract_id}/accept",
        json=mock_response,
        status=200
    )
    
    result = client.accept_contract(contract_id)
    assert result == mock_response
    assert result["data"]["accepted"] is True

@responses.activate
def test_market_operations():
    """Test market operations (buy/sell)"""
    client = SpaceTradersClient()
    client.token = "test-token"
    
    # Mock market data
    responses.add(
        responses.GET,
        "https://api.spacetraders.io/v2/systems/X1-TEST/waypoints/X1-TEST-MARKET/market",
        json={"data": {"symbol": "X1-TEST-MARKET", "tradeGoods": []}},
        status=200
    )
    
    # Mock buy operation
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/SHIP-1/purchase",
        json={"data": {"transaction": {"units": 10, "pricePerUnit": 100}}},
        status=200
    )
    
    # Mock sell operation
    responses.add(
        responses.POST,
        "https://api.spacetraders.io/v2/my/ships/SHIP-1/sell",
        json={"data": {"transaction": {"units": 10, "pricePerUnit": 150}}},
        status=200
    )
    
    # Test market data
    market_data = client.get_market("X1-TEST", "X1-TEST-MARKET")
    assert "data" in market_data
    
    # Test buy
    buy_result = client.buy_goods("SHIP-1", "IRON_ORE", 10)
    assert "data" in buy_result
    assert buy_result["data"]["transaction"]["units"] == 10
    
    # Test sell
    sell_result = client.sell_goods("SHIP-1", "IRON_ORE", 10)
    assert "data" in sell_result
    assert sell_result["data"]["transaction"]["units"] == 10
