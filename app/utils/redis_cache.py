import json
import logging
from typing import Dict, Any, Callable, Awaitable, Optional, List, Type
from functools import wraps
import redis
from redis.exceptions import RedisError
import asyncio
from ..config import settings

# Redis connection pool
try:
    redis_pool = redis.ConnectionPool(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True
    )
    redis_client = redis.Redis(connection_pool=redis_pool)
    # Test connection
    redis_client.ping()
    logging.info("Redis connection pool initialized successfully")
except RedisError as e:
    logging.error(f"Redis connection failed: {str(e)}")
    redis_client = None
except Exception as e:
    logging.error(f"Unexpected error during Redis initialization: {str(e)}")
    redis_client = None

class RedisCache:
    def __init__(self, prefix: str, ttl_seconds: int = 300):  # Default 5 minutes TTL
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds
        
    def _get_full_key(self, key: str) -> str:
        """Create a prefixed key to avoid collisions"""
        # Make sure we don't double-prefix
        if key.startswith(f"{self.prefix}_") or key.startswith(f"{self.prefix}:"):
            return key
        return f"{self.prefix}:{key}"
        
    def get(self, key: str) -> Any:
        """Get value from Redis cache"""
        if not redis_client:
            logging.warning("Redis client not available")
            return None
            
        try:
            full_key = self._get_full_key(key)
            logging.debug(f"Attempting to retrieve cache for key: {full_key}")
            data = redis_client.get(full_key)
            if data:
                logging.info(f"Cache hit for key: {full_key}")
                return json.loads(data)
            logging.info(f"Cache miss for key: {full_key}")
            return None
        except RedisError as e:
            logging.error(f"Redis error in get: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error for key {full_key}: {str(e)}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in cache get: {str(e)}")
            return None
        
    def set(self, key: str, value: Any) -> bool:
        """Set value in Redis cache with expiry time"""
        if not redis_client:
            logging.warning("Redis client not available")
            return False
            
        try:
            full_key = self._get_full_key(key)
            logging.debug(f"Attempting to cache data for key: {full_key}")
            try:
                # Try serializing first to catch errors
                serialized = json.dumps(value)
                logging.info(f"Serialized data size: {len(serialized)} bytes")
                
                # Check if data is too large (Redis typically has a 512MB limit)
                if len(serialized) > 100_000_000:  # 100MB limit as safety
                    logging.warning(f"Data too large for Redis: {len(serialized)} bytes")
                    return False
                    
                result = redis_client.setex(full_key, self.ttl_seconds, serialized)
                logging.info(f"Cached data for key: {full_key}, expires in {self.ttl_seconds}s")
                return result
            except TypeError as e:
                logging.error(f"JSON serialization error for key {full_key}: {str(e)}")
                return False
        except RedisError as e:
            logging.error(f"Redis error in set: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error in cache set: {str(e)}")
            return False
            
    def invalidate(self, key: str) -> bool:
        """Remove a specific key from cache"""
        if not redis_client:
            logging.warning("Redis client not available")
            return False
            
        try:
            full_key = self._get_full_key(key)
            result = redis_client.delete(full_key)
            logging.info(f"Invalidated cache for key: {full_key}")
            return bool(result)
        except RedisError as e:
            logging.error(f"Redis error in invalidate: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error in cache invalidate: {str(e)}")
            return False
            
    def clear(self) -> int:
        """Clear all cache entries with this prefix"""
        if not redis_client:
            logging.warning("Redis client not available")
            return 0
            
        try:
            pattern = f"{self.prefix}:*"
            keys = redis_client.keys(pattern)
            if keys:
                count = redis_client.delete(*keys)
                logging.info(f"Cleared {count} keys with pattern {pattern}")
                return count
            return 0
        except RedisError as e:
            logging.error(f"Redis error in clear: {str(e)}")
            return 0
        except Exception as e:
            logging.error(f"Unexpected error in cache clear: {str(e)}")
            return 0

# Create cache instances
budget_cache = RedisCache("budget", 300)  # 5 minutes TTL
project_cache = RedisCache("project", 300)  # 5 minutes TTL

# Decorator for caching async functions
def redis_cache(cache_instance: RedisCache):
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract key information for a more readable cache key
            service_name = func.__module__.split('.')[-1].replace('_service', '')
            
            # Debug logging to see what's happening
            logging.debug(f"Cache args: {args}")
            logging.debug(f"Cache kwargs: {kwargs}")
            
            # Handle common patterns for our API
            is_archived = None
            
            # Check kwargs first
            if 'is_archived' in kwargs:
                is_archived = kwargs['is_archived']
                logging.debug(f"Found is_archived in kwargs: {is_archived}")
            
            # If not in kwargs, check positional args (typically args[1] for class methods)
            elif len(args) > 2:  # self, api_key, is_archived
                # For methods like fetch_all_budgets(self, api_key, is_archived)
                is_archived = args[2]
                logging.debug(f"Found is_archived in args[2]: {is_archived}")
            
            # Create a human-readable cache key with explicit status
            if is_archived is not None:
                status = "archived" if is_archived else "active"
                cache_key = f"{service_name}_{status}_data"
            else:
                # Fallback with a warning
                cache_key = f"{service_name}_unknownStatusData"
                logging.warning(f"Could not determine is_archived status for {func.__name__}")
            
            logging.info(f"Using cache key: {cache_key}")
            
            try:
                # Try to get from cache first
                cached_result = cache_instance.get(cache_key)
                if cached_result is not None:
                    logging.info(f"Cache hit for {cache_key}")
                    return cached_result
            except Exception as e:
                logging.error(f"Cache retrieval failed: {str(e)}")
                # Continue execution without cache
            
            # If not in cache or cache failed, call the function
            result = await func(*args, **kwargs)
            
            try:
                # Try to cache the result
                logging.debug(f"Attempting to cache result for {cache_key}: {result}")
                success = cache_instance.set(cache_key, result)
                if success:
                    logging.info(f"Successfully cached result for {cache_key}")
                else:
                    logging.warning(f"Failed to cache result for {cache_key}")
            except Exception as e:
                logging.error(f"Cache storage failed: {str(e)}")
                # Continue without caching
            
            return result
        return wrapper
    return decorator