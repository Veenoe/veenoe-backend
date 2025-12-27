"""
This module contains the logic for initializing the database connection.

It sets up the asynchronous MongoDB client and configures Beanie ODM with
the application's document models. This initialization is typically executed
once during application startup to ensure all database dependencies are ready
before handling incoming requests.

Design Decisions (First Principles):
1. Singleton Pattern: Database client is expensive to create - reuse it.
2. Explicit Lifecycle: init_db() / close_db() for clear resource management.
3. Accessor Function: get_client() ensures initialized state before use.
4. Health Check Support: verify_connection() for production health endpoints.
"""

import logging
import motor.motor_asyncio
from beanie import init_beanie
from app.core.config import settings
from app.db.models import VivaSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-Level Singleton
# ---------------------------------------------------------------------------
# The client is stored at module level for process-wide reuse.
# This is thread-safe in Python due to the GIL.
_client: motor.motor_asyncio.AsyncIOMotorClient | None = None


def get_client() -> motor.motor_asyncio.AsyncIOMotorClient:
    """
    Get the singleton database client.

    Raises:
        RuntimeError: If database has not been initialized.

    Returns:
        The AsyncIOMotorClient instance.
    """
    if _client is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )
    return _client


async def init_db() -> None:
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
        - This method should be invoked during application startup.
        - The database connection is maintained by Motor and reused throughout the app lifecycle.
        - Any models added to the application must also be registered here in `document_models`.

    Raises:
        Any exception originating from Motor or Beanie will propagate up, ensuring
        that the application does not start in an invalid or partially-initialized
        database state.
    """
    global _client

    # Create the async MongoDB client using the application's configured URI.
    _client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)

    # Retrieve a reference to the configured database.
    db_instance = _client[settings.MONGO_DB_NAME]

    # Initialize Beanie with the database instance and registered document models.
    await init_beanie(database=db_instance, document_models=[VivaSession])

    logger.info("Database '%s' initialized successfully", settings.MONGO_DB_NAME)


async def close_db() -> None:
    """
    Close the database connection gracefully.

    Should be called during application shutdown to release resources cleanly.
    Safe to call multiple times or if database was never initialized.
    """
    global _client

    if _client is not None:
        _client.close()
        _client = None
        logger.info("Database connection closed")


async def verify_connection() -> bool:
    """
    Verify that the database connection is healthy.

    Performs a lightweight ping command to check connectivity.
    Used by health check endpoints.

    Returns:
        True if connection is healthy, False otherwise.
    """
    if _client is None:
        return False

    try:
        # The 'ping' command is the lightest way to verify connectivity
        await _client.admin.command("ping")
        return True
    except Exception as e:
        logger.warning("Database health check failed: %s", str(e))
        return False
