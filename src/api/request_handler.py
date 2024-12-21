import requests
import time
import logging
import random
import statistics
from typing import Dict, Any, Optional
from collections import deque

class RequestHandler:
    def __init__(self, base_url: str, token: str, rate_limiter, circuit_breaker):
        self.base_url = base_url
        self.token = token
        self.logger = logging.getLogger(__name__)
        self.rate_limiter = rate_limiter
        self.circuit_breaker = circuit_breaker
        self.response_times: deque[float] = deque(maxlen=50)
        self.rate_adjustment_threshold: float = 1.0
        self.min_request_interval = 1.0 / self.rate_limiter.requests_per_second
        self.error_history = []
        self.last_error_reset = time.time()

    def _log_response(self, response: requests.Response, duration: float):
        self.logger.debug(f"Response: {response.status_code} - {response.request.method} {response.url} - {duration:.4f}s")

    def _handle_request_error(self, error: Exception, endpoint: str) -> None:
        current_time = time.time()
        self.error_history.append((current_time, endpoint))
        if isinstance(error, requests.exceptions.HTTPError):
            if error.response is not None and error.response.status_code >= 500:
                self.logger.error(f"Server error for {endpoint}: {str(error)}")
            else:
                self.logger.warning(f"HTTP error for {endpoint}: {str(error)}")
        else:
            self.logger.error(f"Network error for {endpoint}: {str(error)}")

    def make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        if not self.circuit_breaker.allow_request():
            raise RuntimeError(f"Circuit breaker is open for {endpoint}")

        retries = 0
        max_retries = 2
        success = False

        while retries <= max_retries:
            try:
                self.rate_limiter.wait_if_needed()
                start_time = time.time()

                url = f"{self.base_url}/{endpoint}"
                headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

                if data is not None:
                    kwargs["json"] = data

                response = requests.request(method, url, headers=headers, **kwargs)

                duration = time.time() - start_time
                self.response_times.append(duration)
                while len(self.response_times) > 100:
                    self.response_times.popleft()

                self._log_response(response, duration)

                if len(self.response_times) > 0:
                    avg_response_time = statistics.mean(self.response_times)
                    if avg_response_time > self.rate_adjustment_threshold:
                        new_rate = max(0.1, self.rate_limiter.requests_per_second * 0.5)
                        self.rate_limiter.update_rate(new_rate)
                        self.logger.info(f"Reduced rate limit to {new_rate:.1f} requests/second due to high response times")

                response.raise_for_status()
                success = True
                return response.json()

            except Exception as e:
                retries += 1
                if retries > max_retries:
                    self._handle_request_error(e, endpoint)
                    raise

                delay = min(300, (2 ** retries) + random.uniform(0, 0.1))
                time.sleep(delay)
            finally:
                self.circuit_breaker.update_state(success, endpoint)

    def get_headers(self) -> Dict[str, str]:
        if not self.token:
            self.logger.warning("No token available for request. Please register an agent first.")
            raise ValueError("No token available for request. Please register an agent first.")
        auth_token = self.token.strip()
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        return {
            "Authorization": auth_token,
            "Content-Type": "application/json"
        }