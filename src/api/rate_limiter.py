from collections import deque
import time

class RateLimiter:
    def __init__(self, requests_per_second: float = 2.0, request_window: float = 1.0, burst_limit: int = 10):
        self.requests_per_second = requests_per_second
        self.request_window = request_window
        self.request_timestamps: deque[float] = deque(maxlen=10)
        self.burst_limit = burst_limit
        self.min_request_interval = 1.0 / self.requests_per_second

    def wait_if_needed(self):
        current_time = time.time()

        while self.request_timestamps and current_time - self.request_timestamps[0] > self.request_window:
            self.request_timestamps.popleft()

        if len(self.request_timestamps) >= self.burst_limit:
            oldest_timestamp = self.request_timestamps[0]
            time_passed = current_time - oldest_timestamp
            if time_passed < self.request_window:
                sleep_time = self.request_window - time_passed
                time.sleep(sleep_time)

        if self.request_timestamps:
            time_since_last = current_time - self.request_timestamps[-1]
            if time_since_last < self.min_request_interval:
                time.sleep(self.min_request_interval - time_since_last)

        self.request_timestamps.append(current_time)

    def update_rate(self, new_rate: float):
        self.requests_per_second = new_rate
        self.min_request_interval = 1.0 / self.requests_per_second