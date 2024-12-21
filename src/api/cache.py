import time
from typing import Dict, Any, Optional

class CacheEntry:
    def __init__(self, data: Dict[str, Any], etag: Optional[str] = None, last_modified: Optional[str] = None):
        self.data = data
        self.etag = etag
        self.last_modified = last_modified
        self.timestamp = time.time()

class Cache:
    def __init__(self, ttl: int = 60, enabled: bool = True):
        self.cache: Dict[str, CacheEntry] = {}
        self.ttl = ttl
        self.enabled = enabled

    def get_cache_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            return f"{endpoint}?{param_str}"
        return endpoint

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        cache_key = self.get_cache_key(endpoint, params)
        if cache_key not in self.cache:
            return None

        cached = self.cache[cache_key]
        if time.time() - cached.timestamp > self.ttl:
            del self.cache[cache_key]
            return None

        return cached.data

    def update(self, endpoint: str, data: Dict, etag: Optional[str] = None, last_modified: Optional[str] = None, params: Optional[Dict] = None):
        cache_key = self.get_cache_key(endpoint, params)
        self.cache[cache_key] = CacheEntry(data, etag, last_modified)