"""Test configuration settings"""
import os
from pydantic import ConfigDict
from pydantic_settings import BaseSettings
from config import Settings


class TestSettings(Settings):
    """Override settings for testing environment"""

    DB_URL: str = "mongodb://localhost:27017"  # Default test DB URL
    DB_NAME: str = "bishl_test"
    JWT_SECRET_KEY: str = "test-secret-key-do-not-use-in-production"
    JWT_REFRESH_SECRET_KEY: str = "test-refresh-secret-do-not-use-in-production"
    DEBUG_LEVEL: int = 0  # Suppress debug output in tests
    ENVIRONMENT: str = "test"

    model_config = ConfigDict(
        # Don't load .env.test here - conftest.py sets environment variables
        # This prevents accidentally loading .env instead
        case_sensitive=True
    )