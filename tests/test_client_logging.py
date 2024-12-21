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
        
        # Mock settings for testing
        self.settings_patcher = patch('src.api.client.settings')
        self.mock_settings = self.settings_patcher.start()
        self.mock_settings.api_url = "http://test"
        self.mock_settings.spacetraders_token = "test_token"
        
        # Create formatter that matches the client's format
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', 
                                   datefmt='%Y-%m-%d %H:%M:%S')
        self.handler.setFormatter(formatter)
        
        # Get logger and add handler
        # Use the same logger name as the client
        self.logger = logging.getLogger('src.api.client')
        # Remove any existing handlers and reset level
        self.logger.handlers = []
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        
        # Also set the root logger to DEBUG to catch all messages
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        # Clear any existing handlers from root logger
        root_logger.handlers = []
        
        # Create client
        self.client = SpaceTradersClient()
        self.client.token = "test_token"
        
    def tearDown(self):
        # Clean up handlers
        self.logger.removeHandler(self.handler)
        self.handler.close()
        self.log_output.close()
        
        # Stop settings patcher
        self.settings_patcher.stop()
        
    def test_successful_request_logging(self):
        """Test that successful requests are logged properly"""
        # Mock successful response
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.headers = {"X-Test": "test"}
        mock_response.json.return_value = {"data": "test"}
        mock_response.url = "http://test/test/endpoint"
        mock_response.raise_for_status = lambda: None  # No error for 200 response
        
        with patch('requests.request', return_value=mock_response):
            self.client._make_request("GET", "test/endpoint")
            
        log_output = self.log_output.getvalue()
        
        # Check response logging
        self.assertIn("API Response: 200 (OK)", log_output)
        self.assertIn("Duration:", log_output)
        self.assertIn("Timestamp:", log_output)
        self.assertIn("Headers:", log_output)
        
    def test_error_request_logging(self):
        """Test that failed requests are logged properly with response body"""
        # Mock error response
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 400
        mock_response.reason = "Bad Request"
        mock_response.url = "http://test/test/endpoint"
        mock_response.headers = {}
        mock_response.json.return_value = {"error": "Bad Request"}
        mock_response.text = json.dumps({"error": "Bad Request"})
        
        def mock_request(*args, **kwargs):
            mock_response.raise_for_status = lambda: requests.HTTPError("400 Client Error: Bad Request", response=mock_response)
            raise mock_response.raise_for_status()
        
        with patch('requests.request', side_effect=mock_request):
            with self.assertRaises(requests.exceptions.HTTPError):
                self.client._make_request("GET", "test/endpoint")
            
        log_output = self.log_output.getvalue()
        
        # Check error logging
        self.assertIn("HTTP error for test/endpoint: 400 Client Error: Bad Request", log_output)
        
    def test_rate_limit_logging(self):
        """Test that rate limit responses are logged properly"""
        # Mock rate limit response
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 429
        mock_response.reason = "Too Many Requests"
        mock_response.url = "http://test/test/endpoint"
        mock_response.headers = {"Retry-After": "5"}
        mock_response.json.return_value = {"error": "Rate limit exceeded"}
        mock_response.text = json.dumps({"error": "Rate limit exceeded"})
        
        def mock_request(*args, **kwargs):
            mock_response.raise_for_status = lambda: requests.HTTPError("429 Client Error: Too Many Requests", response=mock_response)
            raise mock_response.raise_for_status()
        
        with patch('requests.request', side_effect=mock_request), \
             patch('time.sleep'):  # Mock sleep to speed up test
            with self.assertRaises(requests.exceptions.HTTPError):
                self.client._make_request("GET", "test/endpoint")
            
        log_output = self.log_output.getvalue()
        
        # Check rate limit logging
        self.assertIn("HTTP error for test/endpoint: 429 Client Error: Too Many Requests", log_output)
        
    def test_response_header_logging(self):
        """Test that response headers are properly logged"""
        # Mock response with cache-related headers
        mock_response = MagicMock(spec=requests.Response)
        mock_response.status_code = 200
        mock_response.reason = "OK"
        mock_response.url = "http://test/test/endpoint"
        mock_response.headers = {
            "ETag": "test-etag",
            "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT",
            "Cache-Control": "max-age=3600"
        }
        mock_response.json.return_value = {"data": "test"}
        mock_response.text = json.dumps({"data": "test"})
        mock_response.raise_for_status = lambda: None
        
        with patch('requests.request', return_value=mock_response):
            # Make request and check response logging
            self.client._make_request("GET", "test/endpoint")
            log_output = self.log_output.getvalue()
            
            # Verify response headers are logged
            self.assertIn("API Response: 200 (OK)", log_output)
            self.assertIn("ETag", log_output)
            self.assertIn("Last-Modified", log_output)
            self.assertIn("Cache-Control", log_output)
            self.assertIn("max-age=3600", log_output)
        
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
