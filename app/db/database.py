"""
This module contains the logic for initializing the database connection.

It sets up the asynchronous MongoDB client and configures Beanie ODM with
the application's document models. This initialization is typically executed
once during application startup to ensure all database dependencies are ready
before handling incoming requests.
"""

import motor.motor_asyncio
from beanie import init_beanie
from app.core.config import settings
from app.db.models import VivaSession


async def init_db():
    """
    Initialize the application's asynchronous database connection.

    This function:
        1. Creates an AsyncIOMotorClient instance using the configured Mongo URI.
        2. Retrieves the database instance referenced by the configured DB name.
        3. Initializes Beanie (the ODM) with the database and registered document models.

    Beanie's initialization step is required before any CRUD operations can be
    performed, as it sets up internal indexes, schema metadata, and document
    mappings.

    Notes:
        - This method should be invoked during application startup (e.g., FastAPI startup event).
        - The database connection is maintained by Motor and reused throughout the app lifecycle.
        - Any models added to the application must also be registered here in `document_models`.

    Raises:
        Any exception originating from Motor or Beanie will propagate up, ensuring
        that the application does not start in an invalid or partially-initialized
        database state.

    Returns:
        None
            The function is executed for its side effects—initializing the DB client
            and configuring Beanie.
    """
    # Create the async MongoDB client using the application's configured URI.
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)

    # Retrieve a reference to the configured database.
    db_instance = client[settings.MONGO_DB_NAME]

    # Initialize Beanie with the database instance and registered document models.
    # This step loads indexes, schema metadata, and prepares ODM operations.
    await init_beanie(database=db_instance, document_models=[VivaSession])

    # Log or print a simple confirmation for successful initialization.
    print(f"Database '{settings.MONGO_DB_NAME}' initialized...")
