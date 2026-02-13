from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DB_URL: str = Field(default="", description="MongoDB connection URL")
    DB_NAME: str = Field(default="bishl_dev", description="MongoDB database name")

    # API
    BE_API_URL: str = Field(default="", description="Backend API base URL")

    # Application Settings
    DEBUG_LEVEL: int = Field(default=0, description="Debug verbosity level (0-2)")
    ENVIRONMENT: str = Field(
        default="development", description="Environment: development, staging, production"
    )
    RESULTS_PER_PAGE: int = Field(
        default=20, description="Default number of results per page for pagination"
    )

    # CORS Configuration
    CORS_ORIGINS: str = Field(
        default="*", description="Comma-separated list of allowed CORS origins"
    )

    # Security
    SECRET_KEY: str = Field(
        default="", description="General application secret key for encryption/signing"
    )

    # JWT Configuration
    JWT_SECRET: str = Field(default="", description="Secret key for JWT token generation")
    JWT_ALGORITHM: str = Field(default="HS256", description="Algorithm for JWT encoding")

    # Mail Configuration
    MAIL_ENABLED: bool = Field(
        default=True, description="Enable/disable email sending (useful for dev)"
    )
    MAIL_USERNAME: str = Field(default="", description="SMTP username")
    MAIL_PASSWORD: str = Field(default="", description="SMTP password")
    MAIL_FROM: str = Field(default="noreply@example.com", description="Default sender email")
    MAIL_PORT: int = Field(default=465, description="SMTP port (465 for SSL/TLS, 587 for STARTTLS)")
    MAIL_SERVER: str = Field(default="smtp.strato.de", description="SMTP server")
    MAIL_FROM_NAME: str = Field(default="App", description="Default sender name")
    MAIL_STARTTLS: bool = Field(
        default=False, description="Use STARTTLS (port 587, upgrades to TLS)"
    )
    MAIL_SSL_TLS: bool = Field(
        default=True, description="Use implicit SSL/TLS (port 465, Strato default)"
    )
    USE_CREDENTIALS: bool = Field(default=True, description="Use SMTP credentials")
    VALIDATE_CERTS: bool = Field(default=True, description="Validate SSL certificates")

    # Cloudinary Configuration
    CLDY_CLOUD_NAME: str = Field(default="", description="Cloudinary cloud name")
    CLDY_API_KEY: str = Field(default="", description="Cloudinary API key")
    CLDY_API_SECRET: str = Field(default="", description="Cloudinary API secret")

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


# Create a global settings instance
settings = Settings()
