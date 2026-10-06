"""
This module handles the application's configuration management.

It uses pydantic-settings to load configuration variables (like database
URIs and API keys) from environment variables or a .env file.

Design Decisions (First Principles):
1. All sensitive data comes from environment variables, never hardcoded.
2. Reasonable defaults where security permits.
3. Clear documentation for each setting.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Literal, Optional

from app.core.runtime_config import load_runtime_config


class Settings(BaseSettings):
    """
    Defines the application's configuration settings.

    Pydantic-settings will automatically read these variables from
    environment variables or the .env file.
    """

    DYNAMODB_TABLE_NAME: str = Field(..., min_length=3)
    # Set only for DynamoDB Local. Real DEV/PROD use the regional AWS endpoint
    # and their own table names; a local process may target DEV with DEV IAM.
    DYNAMODB_ENDPOINT_URL: str | None = None
    AWS_REGION: str = "ap-south-1"

    # Google AI Studio API Key
    GOOGLE_API_KEY: str = Field(..., description="Google AI Studio API Key")
    GEMINI_LIVE_MODEL: str = Field(
        default="gemini-3.8-live", min_length=1, pattern=r"^\S+$"
    )
    VIVA_SESSION_DURATION_MINUTES: Literal[5, 10, 15] = 5

    # Production Frontend URL (optional, for CORS)
    FRONTEND_URL: Optional[str] = Field(
        default=None, description="Production frontend URL for CORS"
    )

    # Additional CORS origins (comma-separated in env var)
    # Example: CORS_ORIGINS=https://veenoe.com,https://www.veenoe.com
    CORS_ORIGINS: str = Field(
        default="",
        description="Additional CORS origins (comma-separated)",
    )

    # Clerk Authentication (Official SDK)
    # Get from Clerk Dashboard → API Keys (starts with sk_test_ or sk_live_)
    CLERK_SECRET_KEY: str = Field(
        ..., description="Clerk secret key for authentication"
    )

    # Configure the settings to load from a .env file
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def __init__(self, **values):
        """Apply explicit settings overrides after resolving runtime configuration."""
        runtime_config = load_runtime_config()
        merged = {**runtime_config, **values}
        super().__init__(**merged)


# Create a single, reusable instance of the settings
# This instance will be imported by other modules to access config values.
settings = Settings()
