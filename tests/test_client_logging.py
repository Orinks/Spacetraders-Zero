import unittest
from unittest.mock import patch, MagicMock
import logging
import io
import json
from src.api.client import SpaceTradersClient
import requests

class TestSpaceTradersClientLogging(unittest.TestCase):
    def setUp(self):
        # Create a new handler for each test
        self.log_output = io.StringIO()
        self.handler = logging.StreamHandler(self.log_output)
        self.handler.setLevel(logging.DEBUG)
        
        # Create formatter that matches the client's format
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', 
                                   datefmt='%Y-%m-%d %H:%M:%S')
        self.handler.setFormatter(formatter)
        
        # Get logger and add handler
        self.logger = logging.getLogger('src.api.client')
        # Remove any existing handlers
        self.logger.handlers = []
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        # Create client
        self.client = SpaceTradersClient()
        self.client.token = "test_token"
        
    def tearDown(self):
        # Clean up handlers
        self.logger.removeHandler(self.handler)
        self.handler.close()
        self.log_output.close()
        
    def test_successful_request_logging(self):
        """Test that successful requests are logged properly"""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.headers = {"X-Test": "test"}
        mock_response.json.return_value = {"data": "test"}
        
        with patch('requests.get', return_value=mock_response):
            self.client._make_request("GET", "test/endpoint")
            
        log_output = self.log_output.getvalue()
        
        # Check request logging
        self.assertIn("[DEBUG] API Request: GET test/endpoint", log_output)
        self.assertIn("Timestamp:", log_output)
        
        # Check response logging
        self.assertIn("[DEBUG] API Response: 200 (OK)", log_output)
        self.assertIn("Duration:", log_output)
        self.assertIn("Headers:", log_output)
        
    def test_error_request_logging(self):
        """Test that failed requests are logged properly with response body"""
        # Mock error response
        error_response = requests.Response()
        error_response.status_code = 400
        error_response._content = json.dumps({"error": "Bad Request"}).encode()
        
        mock_error = requests.exceptions.HTTPError("Bad Request")
        mock_error.response = error_response
        
        with patch('requests.get', side_effect=mock_error):
            with self.assertRaises(RuntimeError):
                self.client._make_request("GET", "test/endpoint")
            
        log_output = self.log_output.getvalue()
        
        # Check error logging
        self.assertIn("[ERROR] API Error on test/endpoint", log_output)
        self.assertIn("Error Type: HTTPError", log_output)
        self.assertIn("Error Message: Bad Request", log_output)
        self.assertIn("Response Body:", log_output)
        self.assertIn("Bad Request", log_output)
        
    def test_rate_limit_logging(self):
        """Test that rate limit responses are logged properly"""
        # Mock rate limit response
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "5"}
        mock_response.json.return_value = {"error": "Rate limit exceeded"}
        
        with patch('requests.get', return_value=mock_response), \
             patch('time.sleep'):  # Mock sleep to speed up test
            with self.assertRaises(RuntimeError):
                self.client._make_request("GET", "test/endpoint")
            
        log_output = self.log_output.getvalue()
        
        # Check rate limit logging
        self.assertIn("[WARNING] Rate limit hit, waiting 5 seconds", log_output)
        self.assertIn("[WARNING] API Response: 429", log_output)
        
    def test_cache_logging(self):
        """Test that cache operations are logged properly"""
        # Mock successful response with cache headers
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "ETag": "test-etag",
            "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"
        }
        mock_response.json.return_value = {"data": "test"}
        
        def mock_get(*args, **kwargs):
            # Check if the request includes cache headers
            if 'headers' in kwargs and 'If-None-Match' in kwargs['headers']:
                mock_response.status_code = 304  # Not Modified
            return mock_response
        
        with patch('requests.get', side_effect=mock_get):
            # First request should cache
            self.client._make_request("GET", "test/endpoint")
            # Clear the log to only capture the second request
            self.log_output.truncate(0)
            self.log_output.seek(0)
            # Second request should use cache headers
            self.client._make_request("GET", "test/endpoint")
            
        log_output = self.log_output.getvalue()
        
        # Check cache logging with the correct format
        # We now only expect the cache hit message since we return cached data directly
        self.assertIn("[DEBUG] Cache hit for test/endpoint", log_output)
        
    def test_circuit_breaker_logging(self):
        """Test that circuit breaker state changes are logged properly"""
        endpoint = "test/endpoint"
        
        # Simulate multiple failures to trigger circuit breaker
        for _ in range(self.client.error_threshold):
            self.client._update_circuit_state(False, endpoint)
            
        log_output = self.log_output.getvalue()
        
        # Check circuit breaker logging
        self.assertIn("[WARNING] Circuit breaker opening for endpoint pattern: test/endpoint", log_output)

if __name__ == '__main__':
    unittest.main()
