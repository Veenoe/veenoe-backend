"""Owner-scoped session access using a single table, without scans or indexes."""

import asyncio
import re
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from app.db.models import SESSION_ID_PATTERN, VivaSession, utc_now

MAX_ITEM_BYTES = 256 * 1024
# Bound both write capacity and payload growth; large archives belong in a
# separate storage design rather than silently increasing this session limit.
MAX_TRANSCRIPT_BYTES = 64 * 1024


class SessionNotFound(ValueError):
    """Missing and inaccessible sessions deliberately share the same response."""


class SessionConflict(Exception):
    """A conditional write lost to another update or deletion."""


class RepositoryUnavailable(Exception):
    """Sanitized storage failure safe to translate into a retryable HTTP 503."""


class SessionTooLarge(ValueError):
    """Serialized content exceeds the application limit before an AWS write."""


def validate_session_id(session_id: str) -> str:
    if not re.fullmatch(SESSION_ID_PATTERN, session_id):
        raise SessionNotFound("Session not found")
    return session_id


def item_size_bytes(item: dict[str, Any]) -> int:
    """Conservatively size this repository's flat string/number item format.

    This is not a general DynamoDB size calculator. UTF-8 attribute names and
    values count toward size; numeric text plus overhead deliberately overcounts
    our nonnegative revision counter.
    """
    return sum(
        len(name.encode("utf-8"))
        + len(next(iter(value.values())).encode("utf-8"))
        + (2 if "N" in value else 0)
        for name, value in item.items()
    )


def session_item(session: VivaSession) -> dict[str, Any]:
    """Serialize one bounded aggregate; revision stays outside the JSON payload.

    Only owner and session ID are queried, so nested domain fields need no AWS
    attribute mapping. Keeping revision separate permits atomic stale-write checks.
    """
    if (
        session.transcript
        and len(session.transcript.encode("utf-8")) > MAX_TRANSCRIPT_BYTES
    ):
        raise SessionTooLarge("Transcript exceeds 64 KiB")
    item = {
        "pk": {"S": f"USER#{session.user_id}"},
        "sk": {"S": f"SESSION#{validate_session_id(session.id)}"},
        "data": {"S": session.model_dump_json(exclude={"revision"})},
        "revision": {"N": str(session.revision)},
    }
    # Overestimating numeric size keeps the guard conservative and leaves
    # headroom below AWS's 400 KiB item limit.
    size = item_size_bytes(item)
    if size > MAX_ITEM_BYTES:
        raise SessionTooLarge("Session exceeds 256 KiB")
    return item


class SessionRepository:
    """Execute owner-scoped operations with callers' verified authentication IDs.

    The partition is always supplied by server-side authentication, never by a
    client cursor or request body. Every mutation checks its precondition in AWS.
    """

    def __init__(self, client: Any, table_name: str):
        self.client = client
        self.table_name = table_name

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _key(user_id: str, session_id: str) -> dict[str, Any]:
        return {
            "pk": {"S": f"USER#{user_id}"},
            "sk": {"S": f"SESSION#{validate_session_id(session_id)}"},
        }

    @staticmethod
    def _decode(item: dict[str, Any]) -> VivaSession:
        session = VivaSession.model_validate_json(item["data"]["S"])
        session.revision = int(item["revision"]["N"])
        return session

    async def _call(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        """Keep synchronous SDK calls off the event loop and hide provider details."""
        try:
            return await asyncio.to_thread(
                getattr(self.client, operation), TableName=self.table_name, **kwargs
            )
        except ClientError as error:
            if (
                error.response.get("Error", {}).get("Code")
                == "ConditionalCheckFailedException"
            ):
                raise SessionConflict("Session changed; retry the operation") from None
            raise RepositoryUnavailable("Session storage is unavailable") from None
        except BotoCoreError:
            raise RepositoryUnavailable("Session storage is unavailable") from None

    async def create_session(self, session: VivaSession) -> None:
        await self._call(
            "put_item",
            Item=session_item(session),
            ConditionExpression="attribute_not_exists(pk)",
        )

    async def get_session_for_user(self, user_id: str, session_id: str) -> VivaSession:
        """Read the latest saved state without revealing whether a foreign ID exists."""
        response = await self._call(
            "get_item", Key=self._key(user_id, session_id), ConsistentRead=True
        )
        if "Item" not in response:
            raise SessionNotFound("Session not found")
        return self._decode(response["Item"])

    async def list_sessions_for_user(
        self, user_id: str, limit: int = 20, cursor: str | None = None
    ) -> tuple[list[VivaSession], str | None]:
        """Return one newest-first Query page, including AWS's continuation cursor.

        AWS may stop at its byte boundary before reaching limit. Do not drain all
        pages here: request cost and latency must remain bounded. Strong reads
        give current items, but pagination is not a snapshot across requests.
        """
        if not 1 <= limit <= 50:
            raise ValueError("History limit must be between 1 and 50")
        params: dict[str, Any] = {
            "KeyConditionExpression": "pk = :owner AND begins_with(sk, :sessions)",
            "ExpressionAttributeValues": {
                ":owner": {"S": f"USER#{user_id}"},
                ":sessions": {"S": "SESSION#"},
            },
            "ConsistentRead": True,
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if cursor:
            # The client cannot inject another owner's partition into pagination.
            params["ExclusiveStartKey"] = self._key(user_id, cursor)
        response = await self._call("query", **params)
        sessions = [self._decode(item) for item in response.get("Items", [])]
        last_key = response.get("LastEvaluatedKey")
        next_cursor = last_key["sk"]["S"].removeprefix("SESSION#") if last_key else None
        return sessions, next_cursor

    async def update_session(self, session: VivaSession) -> None:
        """Replace the aggregate only if its read revision still exists.

        A stale rename must not erase feedback, and an update must not recreate a
        deleted session. Advance the caller's revision only after AWS succeeds.
        """
        updated = session.model_copy(
            update={"revision": session.revision + 1, "updated_at": utc_now()}
        )
        item = session_item(updated)
        await self._call(
            "update_item",
            Key=self._key(session.user_id, session.id),
            UpdateExpression="SET #data = :data, revision = :next",
            ConditionExpression="attribute_exists(pk) AND revision = :previous",
            ExpressionAttributeNames={"#data": "data"},
            ExpressionAttributeValues={
                ":data": item["data"],
                ":next": item["revision"],
                ":previous": {"N": str(session.revision)},
            },
        )
        session.revision = updated.revision
        session.updated_at = updated.updated_at

    async def delete_session(self, session: VivaSession) -> None:
        """Reject deletion of a session changed since the caller read it."""
        await self._call(
            "delete_item",
            Key=self._key(session.user_id, session.id),
            ConditionExpression="attribute_exists(pk) AND revision = :previous",
            ExpressionAttributeValues={":previous": {"N": str(session.revision)}},
        )

    async def check_connection(self) -> None:
        # A nonexistent reserved key exercises the same data-plane IAM as reads.
        await self._call(
            "get_item",
            Key={"pk": {"S": "HEALTH"}, "sk": {"S": "HEALTH"}},
            ConsistentRead=True,
        )
