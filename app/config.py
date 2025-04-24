from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_NAME: str = "Busy Busy API"
    DEBUG_MODE: bool = True
    BUSYBUSY_GRAPHQL_URL: str = "https://graphql.busybusy.io/"
    ALLOWED_ORIGINS: str = "*"  # For production, set to your Apps Script domain
    APP_URL: str = "https://your-fastapi-server.com"  # Replace with your deployed API URL
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    class Config:
        env_file = ".env"

settings = Settings()