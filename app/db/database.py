"""
This module contains the logic for initializing the database connection.
"""

import motor.motor_asyncio
from beanie import init_beanie
from app.core.config import settings
from app.db.models import VivaSession


async def init_db():
    """
    Initializes the asynchronous database connection using Beanie.
    """
    client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)
    db_instance = client[settings.MONGO_DB_NAME]

    await init_beanie(database=db_instance, document_models=[VivaSession])
    print(f"Database '{settings.MONGO_DB_NAME}' initialized...")
