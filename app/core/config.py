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
from typing import List, Optional


class Settings(BaseSettings):
    """
    Defines the application's configuration settings.

    Pydantic-settings will automatically read these variables from
    environment variables or the .env file.
    """

    # MongoDB connection string
    MONGO_URI: str = Field(..., description="MongoDB connection string")

    # Google AI Studio API Key
    GOOGLE_API_KEY: str = Field(..., description="Google AI Studio API Key")

    # The name of the MongoDB database to use
    MONGO_DB_NAME: str = Field(..., description="MongoDB database name")

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
    model_config = SettingsConfigDict(env_file=".env")


# Create a single, reusable instance of the settings
# This instance will be imported by other modules to access config values.
settings = Settings()
