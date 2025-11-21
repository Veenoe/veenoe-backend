"""
This module contains the logic for initializing the database connection.

It uses Beanie (an async ODM for MongoDB) and Motor to connect to the
database specified in the application's configuration.
"""

import motor.motor_asyncio
from beanie import init_beanie
from app.core.config import settings  # Import the centralized settings
from app.db.models import VivaSession, QuestionBank  # Import all Beanie models


async def init_db():
    """
    Initializes the asynchronous database connection using Beanie.

    This function creates a Motor client, points to the correct database,
    and then initializes Beanie with all the defined document models.
    """
    # Create an async MongoDB client
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)

    # Get the target database instance from the client
    db_instance = client[settings.MONGO_DB_NAME]

    # Initialize Beanie with the database instance and all document models
    # This allows Beanie to manage the models and database operations.
    await init_beanie(database=db_instance, document_models=[VivaSession, QuestionBank])
    print(f"Database '{settings.MONGO_DB_NAME}' initialized...")
