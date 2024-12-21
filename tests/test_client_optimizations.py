import unittest
from unittest.mock import patch, MagicMock
import time
import requests
from src.api.client import SpaceTradersClient, CacheEntry
import aiohttp

class TestSpaceTradersClientOptimizations(unittest.TestCase):
    def setUp(self):
        self.client = SpaceTradersClient()
        self.client.token = "test_token"
        
    def test_cache_hit(self):
        """Test that caching works for repeated requests"""
        endpoint = "test/endpoint"
        test_data = {"data": "test"}
        
        # Create a mock response
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.url = "http://test/test/endpoint"
        mock_response.json.return_value = test_data
        mock_response.headers = {'ETag': 'test-etag'}
        mock_response.raise_for_status = lambda: None
        
        with patch('requests.request', return_value=mock_response):
            # First request should hit the API
            result1 = self.client._make_request("GET", endpoint)
            self.assertEqual(result1, test_data)
            
            # Second request should hit the cache
            result2 = self.client._make_request("GET", endpoint)
            self.assertEqual(result2, test_data)
            
            # Verify that the API was only called once
            self.assertEqual(mock_response.json.call_count, 1)
            
    def test_etag_handling(self):
        """Test that ETag headers are properly handled"""
        endpoint = "test/endpoint"
        test_data = {"data": "test"}
        
        # First response with ETag
        mock_response1 = MagicMock(spec=requests.Response)
        mock_response1.status_code = 200
        mock_response1.reason = "OK"
        mock_response1.url = "http://test/test/endpoint"
        mock_response1.json.return_value = test_data
        mock_response1.headers = {'ETag': 'test-etag'}
        mock_response1.raise_for_status = lambda: None
        
        # Second response (304 Not Modified)
        mock_response2 = MagicMock(spec=requests.Response)
        mock_response2.status_code = 304
        mock_response2.reason = "Not Modified"
        mock_response2.url = "http://test/test/endpoint"
        mock_response2.headers = {'ETag': 'test-etag'}
        mock_response2.raise_for_status = lambda: None
        
        with patch('requests.request', side_effect=[mock_response1, mock_response2]):
            # First request should store the ETag
            result1 = self.client._make_request("GET", endpoint)
            self.assertEqual(result1, test_data)
            
            # Second request should use If-None-Match header
            result2 = self.client._make_request("GET", endpoint)
            self.assertEqual(result2, test_data)
            
    def test_batch_requests(self):
        """Test that batch requests work correctly"""
        ship_symbols = ["SHIP1", "SHIP2", "SHIP3"]
        test_data = [{"ship": i} for i in range(3)]
        
        # Mock the _async_get method directly
        async def mock_async_get(self, endpoint, params=None):
            ship_symbol = endpoint.split('/')[-1]
            index = ship_symbols.index(ship_symbol)
            return test_data[index]
        
        with patch.object(SpaceTradersClient, '_async_get', new=mock_async_get):
            results = self.client.get_ships_with_info(ship_symbols)
            self.assertEqual(len(results), 3)
            for i, result in enumerate(results):
                self.assertEqual(result, {"ship": i})
            
    def test_lru_cache(self):
        """Test that LRU cache works for system info"""
        system_symbol = "TEST-SYSTEM"
        test_data = {"system": "data"}
        
        # Mock the request
        with patch.object(self.client, '_make_request', return_value=test_data) as mock_request:
            # First call should hit the API
            result1 = self.client.get_system_info(system_symbol)
            self.assertEqual(result1, test_data)
            
            # Second call should use cache
            result2 = self.client.get_system_info(system_symbol)
            self.assertEqual(result2, test_data)
            
            # Verify only one API call was made
            mock_request.assert_called_once_with("GET", f"systems/{system_symbol}")
            
    def test_cache_ttl(self):
        """Test that cache respects TTL"""
        endpoint = "test/endpoint"
        test_data = {"data": "test"}
        
        # Create a mock response
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.url = "http://test/test/endpoint"
        mock_response.json.return_value = test_data
        mock_response.headers = {}
        mock_response.raise_for_status = lambda: None
        
        with patch('requests.request', return_value=mock_response):
            # Set a short TTL for testing
            self.client.cache_ttl = 0.1
            
            # First request should hit the API
            result1 = self.client._make_request("GET", endpoint)
            self.assertEqual(result1, test_data)
            
            # Wait for cache to expire
            time.sleep(0.2)
            
            # Second request should hit the API again
            result2 = self.client._make_request("GET", endpoint)
            self.assertEqual(result2, test_data)
            
            # Verify that the API was called twice
            self.assertEqual(mock_response.json.call_count, 2)

if __name__ == '__main__':
    unittest.main()
