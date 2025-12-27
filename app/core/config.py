"""
This module handles the application's configuration management.

It uses pydantic-settings to load configuration variables (like database
URIs and API keys) from environment variables or a .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Defines the application's configuration settings.

    Pydantic-settings will automatically read these variables from
    environment variables or the .env file.
    """

    # MongoDB connection string
    MONGO_URI: str

    # Google AI Studio API Key
    GOOGLE_API_KEY: str

    # The name of the MongoDB database to use
    MONGO_DB_NAME: str

    # Production Frontend URL (optional, for CORS)
    FRONTEND_URL: str | None = None

    # Configure the settings to load from a .env file
    model_config = SettingsConfigDict(env_file=".env")


# Create a single, reusable instance of the settings
# This instance will be imported by other modules to access config values.
settings = Settings()
