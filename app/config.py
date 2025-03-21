from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Busy Busy API"
    DEBUG_MODE: bool = True
    BUSYBUSY_GRAPHQL_URL: str = "https://graphql.busybusy.io/"
    BATCH_SIZE: int = 500
    PROCESS_BATCH_SIZE: int = 1000  # For processing large datasets
    MAX_CONCURRENT_REQUESTS: int = 3  # Limit concurrent API calls
    
    class Config:
        env_file = ".env"

settings = Settings()