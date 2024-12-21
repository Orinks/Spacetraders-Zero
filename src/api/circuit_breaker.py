import time
from enum import Enum
import logging

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    def __init__(self, error_threshold: int = 5, reset_timeout: int = 60, success_threshold: int = 3):
        self.circuit_state: CircuitState = CircuitState.CLOSED
        self.error_threshold = error_threshold
        self.reset_timeout = reset_timeout
        self.last_error_time: float | None = None
        self.error_count: int = 0
        self.success_threshold = success_threshold
        self.success_count: int = 0
        self.logger = logging.getLogger(__name__)

    def allow_request(self) -> bool:
        current_time = time.time()

        if self.circuit_state == CircuitState.OPEN:
            if current_time - (self.last_error_time or 0) > self.reset_timeout:
                self.logger.info("Circuit breaker entering half-open state")
                self.circuit_state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                return False

        return True

    def update_state(self, success: bool, endpoint: str):
        if success:
            if self.circuit_state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.logger.info("Circuit breaker closing - service recovered")
                    self.circuit_state = CircuitState.CLOSED
                    self.error_count = 0
            else:
                self.error_count = max(0, self.error_count - 1)
        else:
            self.error_count += 1
            self.last_error_time = time.time()
            if self.error_count >= self.error_threshold:
                if self.circuit_state != CircuitState.OPEN:
                    self.logger.warning(f"Circuit breaker opening for endpoint pattern: {endpoint}")
                    self.circuit_state = CircuitState.OPEN