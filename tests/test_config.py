
"""Test configuration settings"""
import os
from config import Settings


class TestSettings(Settings):
    """Override settings for testing environment"""
    
    DB_NAME: str = "bishl_test"
    JWT_SECRET_KEY: str = "test-secret-key-do-not-use-in-production"
    JWT_REFRESH_SECRET_KEY: str = "test-refresh-secret-do-not-use-in-production"
    DEBUG_LEVEL: int = 0  # Suppress debug output in tests
    ENVIRONMENT: str = "test"
    
    class Config:
        env_file = ".env.test"
        case_sensitive = True
