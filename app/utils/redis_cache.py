import redis
import json
import logging
from datetime import datetime
from ..config import settings

class RedisCache:
    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True
            )
        except Exception as e:
            logging.error(f"Redis connection failed: {str(e)}")
            self.redis_client = None

    async def get_cached_data(self, key: str) -> dict:
        """Get data from Redis cache"""
        if not self.redis_client:
            return None

        try:
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logging.error(f"Redis get error: {str(e)}")
            return None

    async def set_cached_data(self, key: str, data: dict, expiry_minutes: int) -> bool:
        """Set data in Redis cache with expiry"""
        if not self.redis_client:
            return False

        try:
            json_data = json.dumps(data)
            self.redis_client.setex(
                key,
                expiry_minutes * 60,  # Convert minutes to seconds
                json_data
            )
            return True
        except Exception as e:
            logging.error(f"Redis set error: {str(e)}")
            return False
