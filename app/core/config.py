# /app/core/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Manages application configuration using environment variables.
    - Per Phase 3 guide, this handles the DATABASE_URL.
    - It loads from a .env file for local development.
    """
    DATABASE_URL: str = "postgresql://user:password@host:port/database"
    MODEL_NAME: str = "bkai-foundation-models/vietnamese-bi-encoder"
    KAFKA_BROKER_URL: str = "kafka:9092"
    KAFKA_SEARCH_EVENTS_TOPIC: str = "search_events"

    class Config:
        # This tells pydantic-settings to look for a .env file
        env_file = ".env"
        env_file_encoding = 'utf-8'

# Create a single, reusable instance of the settings
settings = Settings()