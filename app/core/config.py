# /app/core/config.py
import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict # <-- Thêm dòng này

class Settings(BaseSettings):
    """
    Manages application configuration using environment variables.
    """
    # --- THAY ĐỔI: Sử dụng ConfigDict thay vì class Config ---
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore' # Bỏ qua các biến môi trường không cần thiết
    )

    # --- Các biến môi trường của bạn giữ nguyên ---
    DATABASE_URL: str = "postgresql://postgres:123456@host.docker.internal:5431/HomeLandFinest"
    MODEL_NAME: str = "bkai-foundation-models/vietnamese-bi-encoder"
    KAFKA_BROKER_URL: str = "154.26.130.248:9092"
    SEARCH_REQUESTS_TOPIC: str = "search_requests"
    SEARCH_RESULTS_TOPIC: str = "search_results"
    SEARCH_LOGGING_TOPIC: str = "search_logging_events"
    SUGGESTION_REQUESTS_TOPIC: str = "suggestion_requests"
    SUGGESTION_RESULTS_TOPIC: str = "suggestion_results"
    MODEL_READY_TOPIC: str = "model_ready_signal"


# Create a single, reusable instance of the settings
settings = Settings()