"""
Centralized Configuration Management

All environment variables are defined here using Pydantic Settings.
This provides validation, type safety, and documentation in one place.

Replit Secrets are accessed via environment variables and validated here.
"""

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables (Replit Secrets).

    To use in your code:
        from config import settings
        db_url = settings.get_db_url()
    """

    # Database Configuration
    DB_URL: str = Field(..., description="MongoDB connection string for dev")
    DB_URL_PROD: str = Field(..., description="MongoDB connection string for production")
    DB_NAME: str = Field(default="bishl_dev", description="Database name")

    # API Configuration
    BE_API_URL: str = Field(default="http://localhost:8080", description="Backend API URL")

    # Security
    SECRET_KEY: str = Field(..., description="JWT signing secret key")
    API_TIMEOUT_MIN: int = Field(default=60, description="JWT token expiration in minutes")

    # Cloudinary (for image uploads)
    CLDY_CLOUD_NAME: str = Field(..., description="Cloudinary cloud name")
    CLDY_API_KEY: str = Field(..., description="Cloudinary API key")
    CLDY_API_SECRET: str = Field(..., description="Cloudinary API secret")

    # Application Settings
    DEBUG_LEVEL: int = Field(default=0, description="Debug verbosity level (0-3)")
    ENVIRONMENT: str = Field(
        default="development", description="Environment: development, staging, production"
    )

    # CORS Configuration
    CORS_ORIGINS: str = Field(
        default="*", description="Comma-separated list of allowed CORS origins"
    )

    @validator("DEBUG_LEVEL")
    def validate_debug_level(cls, v):
        if v not in [0, 1, 2, 3]:
            raise ValueError("DEBUG_LEVEL must be 0, 1, 2, or 3")
        return v

    @validator("CORS_ORIGINS")
    def parse_cors_origins(cls, v):
        """Parse comma-separated CORS origins into a list"""
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",")]

    def get_db_url(self, use_prod: bool = False) -> str:
        """Get database URL based on environment"""
        return self.DB_URL_PROD if use_prod else self.DB_URL

    def get_db_name(self, use_prod: bool = False) -> str:
        """Get database name based on environment"""
        return "bishl" if use_prod else self.DB_NAME

    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Singleton instance - import this throughout your application
settings = Settings()
