from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DB_URL: str = Field(..., description="MongoDB connection URL")
    DB_NAME: str = Field(..., description="MongoDB database name")

    # API
    BE_API_URL: str = Field(..., description="Backend API base URL")

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

    # JWT Configuration
    JWT_SECRET: str = Field(..., description="Secret key for JWT token generation")
    JWT_ALGORITHM: str = Field(default="HS256", description="Algorithm for JWT encoding")

    # Mail Configuration
    MAIL_USERNAME: str = Field(default="", description="SMTP username")
    MAIL_PASSWORD: str = Field(default="", description="SMTP password")
    MAIL_FROM: str = Field(default="noreply@example.com", description="Default sender email")
    MAIL_PORT: int = Field(default=587, description="SMTP port")
    MAIL_SERVER: str = Field(default="smtp.gmail.com", description="SMTP server")
    MAIL_FROM_NAME: str = Field(default="App", description="Default sender name")
    MAIL_STARTTLS: bool = Field(default=True, description="Use STARTTLS")
    MAIL_SSL_TLS: bool = Field(default=False, description="Use SSL/TLS")
    USE_CREDENTIALS: bool = Field(default=True, description="Use SMTP credentials")
    VALIDATE_CERTS: bool = Field(default=True, description="Validate SSL certificates")

    # Cloudinary Configuration
    CLDY_CLOUD_NAME: str = Field(default="", description="Cloudinary cloud name")
    CLDY_API_KEY: str = Field(default="", description="Cloudinary API key")
    CLDY_API_SECRET: str = Field(default="", description="Cloudinary API secret")

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create a global settings instance
settings = Settings()
