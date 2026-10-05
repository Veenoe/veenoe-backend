import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from moto import mock_aws

from app.db.models import VivaSession, new_session_id, utc_now
from app.db.session_repository import (
    MAX_ITEM_BYTES,
    RepositoryUnavailable,
    SessionConflict,
    SessionNotFound,
    SessionRepository,
    SessionTooLarge,
    session_item,
)
from app.schemas.viva import VivaStartRequest
from app.services.viva_service import VivaService


@pytest.fixture
def repository():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-south-1")
        client.create_table(
            TableName="test-sessions",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )
        yield SessionRepository(client, "test-sessions")
        client.close()


def session(owner="owner", created_at=None, **changes):
    now = created_at or utc_now()
    return VivaSession(
        id=new_session_id(now),
        user_id=owner,
        student_name="Student",
        title="Plants",
        topic="Plants",
        class_level="7",
        started_at=now,
        **changes,
    )


def test_create_read_own_session_and_missing_or_foreign_are_inaccessible(repository):
    async def exercise():
        saved = session()
        await repository.create_session(saved)
        assert await repository.get_session_for_user("owner", saved.id) == saved
        for user, identifier in [
            ("other", saved.id),
            ("owner", new_session_id(utc_now())),
            ("owner", "invalid"),
        ]:
            with pytest.raises(SessionNotFound, match="Session not found"):
                await repository.get_session_for_user(user, identifier)
        with pytest.raises(SessionConflict):
            await repository.create_session(saved)

    asyncio.run(exercise())


def test_update_rename_and_delete_use_revision_conditions(repository):
    async def exercise():
        saved = session()
        await repository.create_session(saved)
        stale = await repository.get_session_for_user("owner", saved.id)
        saved.title = "Renamed"
        await repository.update_session(saved)
        current = await repository.get_session_for_user("owner", saved.id)
        assert current.title == "Renamed"
        assert current.revision == 1
        assert current.updated_at >= saved.started_at
        with pytest.raises(SessionConflict):
            await repository.update_session(stale)
        with pytest.raises(SessionConflict):
            await repository.delete_session(stale)
        await repository.delete_session(current)
        with pytest.raises(SessionNotFound):
            await repository.get_session_for_user("owner", saved.id)
        # UpdateItem must not silently recreate a deleted session.
        with pytest.raises(SessionConflict):
            await repository.update_session(current)

    asyncio.run(exercise())


def test_history_order_pagination_and_owner_scope(repository):
    async def exercise():
        base = utc_now()
        saved = [
            session(created_at=base + datetime.timedelta(seconds=i)) for i in range(5)
        ]
        for value in [
            saved[2],
            saved[0],
            saved[4],
            saved[1],
            saved[3],
            session("other"),
        ]:
            await repository.create_session(value)
        first, cursor = await repository.list_sessions_for_user("owner", limit=2)
        second, cursor2 = await repository.list_sessions_for_user(
            "owner", limit=2, cursor=cursor
        )
        third, cursor3 = await repository.list_sessions_for_user(
            "owner", limit=2, cursor=cursor2
        )
        assert [s.id for s in first + second + third] == [s.id for s in reversed(saved)]
        assert cursor3 is None
        assert all(s.user_id == "owner" for s in first + second + third)
        assert await repository.list_sessions_for_user("empty") == ([], None)

    asyncio.run(exercise())


def test_reads_are_strong_and_history_has_one_bounded_query():
    client = MagicMock()
    saved = session()
    client.get_item.return_value = {"Item": session_item(saved)}
    client.query.return_value = {
        "Items": [],
        "LastEvaluatedKey": {
            "pk": {"S": "USER#owner"},
            "sk": {"S": f"SESSION#{saved.id}"},
        },
    }
    repository = SessionRepository(client, "test-sessions")
    asyncio.run(repository.get_session_for_user("owner", saved.id))
    assert client.get_item.call_args.kwargs["ConsistentRead"] is True
    _, cursor = asyncio.run(repository.list_sessions_for_user("owner", cursor=saved.id))
    params = client.query.call_args.kwargs
    assert params["ConsistentRead"] is True
    assert params["ScanIndexForward"] is False
    assert params["Limit"] == 20
    assert params["ExclusiveStartKey"]["pk"] == {"S": "USER#owner"}
    assert "IndexName" not in params
    assert cursor == saved.id
    client.scan.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "private-secret"}},
            "GetItem",
        ),
        ClientError(
            {
                "Error": {
                    "Code": "ProvisionedThroughputExceededException",
                    "Message": "private-secret",
                }
            },
            "GetItem",
        ),
        EndpointConnectionError(endpoint_url="https://private-secret"),
    ],
)
def test_provider_failure_is_sanitized(error):
    client = MagicMock()
    client.get_item.side_effect = error
    with pytest.raises(RepositoryUnavailable) as caught:
        asyncio.run(
            SessionRepository(client, "table").get_session_for_user(
                "owner", session().id
            )
        )
    assert "private-secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_utf8_transcript_and_whole_item_limits_checked_before_aws():
    client = MagicMock()
    repository = SessionRepository(client, "table")
    for saved in [
        session(transcript="अ" * 22000),
        session().model_copy(update={"topic": "x" * MAX_ITEM_BYTES}),
    ]:
        with pytest.raises(SessionTooLarge):
            asyncio.run(repository.create_session(saved))
    client.put_item.assert_not_called()
    assert session_item(session(transcript="अ" * 20000))


def test_service_create_complete_read_history_and_cross_user_writes(repository):
    async def exercise():
        llm = SimpleNamespace(
            create_ephemeral_token=AsyncMock(
                return_value={
                    "token": "ephemeral-private",
                    "model_name": "model",
                    "voice_name": "Kore",
                    "session_duration_minutes": 5,
                }
            )
        )
        service = VivaService(llm, repository)
        response = await service.start_new_viva_session(
            VivaStartRequest(student_name="Student", topic="Plants", class_level="7"),
            "owner",
        )
        identifier = response["viva_session_id"]
        for operation in [
            service.get_viva_session_details(identifier, "other"),
            service.rename_session(identifier, "Stolen", "other"),
            service.abandon_viva_session(identifier, "other"),
            service.delete_session(identifier, "other"),
            service.conclude_viva_session(identifier, 0, "Stolen", [], [], "other"),
        ]:
            with pytest.raises(SessionNotFound):
                await operation
        await service.rename_session(identifier, "Plant practice", "owner")
        result = await service.conclude_viva_session(
            identifier,
            8,
            "Understood",
            [],
            [],
            "owner",
            transcript="Teacher: Why?\nStudent: Light.",
        )
        assert result["score"] == 8
        detail = await service.get_viva_session_details(identifier, "owner")
        assert detail["transcript"] == "Teacher: Why?\nStudent: Light."
        assert detail["title"] == "Plant practice"
        assert detail["status"] == "completed"
        assert (
            await service.conclude_viva_session(identifier, 1, "Late", [], [], "owner")
            == result
        )
        assert await service.abandon_viva_session(identifier, "owner") == {
            "status": "completed"
        }
        history = await service.get_user_history("owner")
        assert history["sessions"][0]["viva_session_id"] == identifier
        item = await repository.get_session_for_user("owner", identifier)
        assert "ephemeral-private" not in item.model_dump_json()

    asyncio.run(exercise())


def test_expired_session_cannot_complete_and_history_reconciles(repository):
    async def exercise():
        saved = session(expires_at=utc_now() - datetime.timedelta(seconds=1))
        await repository.create_session(saved)
        service = VivaService(SimpleNamespace(), repository)
        with pytest.raises(SessionConflict):
            await service.conclude_viva_session(saved.id, 8, "Late", [], [], "owner")
        history = await service.get_user_history("owner")
        assert history["sessions"][0]["status"] == "abandoned"
        assert (
            await repository.get_session_for_user("owner", saved.id)
        ).feedback is None

    asyncio.run(exercise())
