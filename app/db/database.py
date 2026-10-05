"""Reuse a thread-safe DynamoDB client across requests and Lambda invocations."""

import asyncio
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError

from app.core.config import settings
from app.db.session_repository import SessionRepository, RepositoryUnavailable


@lru_cache
def get_repository() -> SessionRepository:
    """Cache the SDK client; real AWS uses the default IAM credential chain.

    Fixed timeouts and bounded retries prevent a storage outage or throttling
    from occupying a request indefinitely. A local endpoint opts into dummy
    credentials and must never be configured for an AWS deployment.
    """
    try:
        client = boto3.client(
            "dynamodb",
            region_name=settings.AWS_REGION,
            endpoint_url=settings.DYNAMODB_ENDPOINT_URL,
            # DynamoDB Local needs signed requests but no real AWS credentials.
            aws_access_key_id="local" if settings.DYNAMODB_ENDPOINT_URL else None,
            aws_secret_access_key="local" if settings.DYNAMODB_ENDPOINT_URL else None,
            config=Config(
                connect_timeout=2,
                read_timeout=3,
                retries={"mode": "standard", "total_max_attempts": 3},
            ),
        )
    except BotoCoreError:
        raise RepositoryUnavailable("Session storage is unavailable") from None
    return SessionRepository(client, settings.DYNAMODB_TABLE_NAME)


async def init_db() -> None:
    await asyncio.to_thread(get_repository)


async def close_db() -> None:
    if get_repository.cache_info().currsize:
        get_repository().close()
        get_repository.cache_clear()


async def verify_connection() -> bool:
    try:
        await get_repository().check_connection()
        return True
    except RepositoryUnavailable:
        return False
