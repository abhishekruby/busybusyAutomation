import time
from typing import Dict, Any, Callable, Awaitable
import logging
import asyncio
from functools import wraps

# Simple in-memory cache implementation
class Cache:
    def __init__(self, ttl_seconds: int = 300):  # Default 5 minutes TTL
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl_seconds = ttl_seconds
        
    def get(self, key: str) -> Any:
        """Get value from cache if it exists and is not expired"""
        if key in self._cache:
            cache_entry = self._cache[key]
            if time.time() < cache_entry['expiry']:
                logging.info(f"Cache hit for key: {key}")
                return cache_entry['value']
            else:
                # Clean up expired entry
                logging.info(f"Cache expired for key: {key}")
                del self._cache[key]
        return None
        
    def set(self, key: str, value: Any) -> None:
        """Set value in cache with expiry time"""
        self._cache[key] = {
            'value': value,
            'expiry': time.time() + self._ttl_seconds
        }
        logging.info(f"Cached data for key: {key}, expires in {self._ttl_seconds}s")
        
    def invalidate(self, key: str) -> None:
        """Remove a specific key from cache"""
        if key in self._cache:
            del self._cache[key]
            logging.info(f"Invalidated cache for key: {key}")
            
    def clear(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
        logging.info("Cache cleared")

# Create cache instances
budget_cache = Cache(300)  # 5 minutes TTL
project_cache = Cache(300)  # 5 minutes TTL

# Decorator for caching async functions
def async_cache(cache_instance: Cache):
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            # For API key security, we'll use a hash of the API key rather than the key itself
            safe_args = []
            safe_kwargs = {}
            
            for arg in args:
                if isinstance(arg, str) and len(arg) > 20:  # Likely an API key
                    safe_args.append(f"api_key_hash_{hash(arg) % 10000}")
                else:
                    safe_args.append(str(arg))
                    
            for k, v in kwargs.items():
                if k == 'api_key' and isinstance(v, str) and len(v) > 20:
                    safe_kwargs[k] = f"api_key_hash_{hash(v) % 10000}"
                else:
                    safe_kwargs[k] = str(v)
            
            cache_key = f"{func.__name__}:{str(safe_args)}:{str(safe_kwargs)}"
            
            # Try to get from cache first
            cached_result = cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
                
            # If not in cache, call the function
            result = await func(*args, **kwargs)
            
            # Cache the result
            cache_instance.set(cache_key, result)
            
            return result
        return wrapper
    return decorator 