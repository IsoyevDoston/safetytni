"""In-memory LRU cache for driver ID to name mapping."""
from typing import Optional
from cachetools import LRUCache
import asyncio


class AsyncLRUCache:
    """Thread-safe async LRU cache wrapper."""
    
    def __init__(self, maxsize: int = 100):
        """Initialize the cache with a maximum size."""
        self._cache: LRUCache[int, str] = LRUCache(maxsize=maxsize)
        self._lock = asyncio.Lock()
    
    async def get(self, key: int) -> Optional[str]:
        """Get a value from the cache."""
        async with self._lock:
            return self._cache.get(key)
    
    async def set(self, key: int, value: str) -> None:
        """Set a value in the cache."""
        async with self._lock:
            self._cache[key] = value
    
    async def clear(self) -> None:
        """Clear all entries from the cache."""
        async with self._lock:
            self._cache.clear()


# Global cache instance
driver_cache = AsyncLRUCache(maxsize=100)
