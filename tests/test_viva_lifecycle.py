import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import viva_service as module
from app.services.viva_service import VivaService


SESSION_ID = "507f1f77bcf86cd799439011"


def test_token_failure_never_creates_in_progress_record(monkeypatch):
    insert = AsyncMock()
    monkeypatch.setattr(module, "VivaSession", lambda **_: SimpleNamespace(insert=insert))
    service = VivaService(
        SimpleNamespace(
            create_ephemeral_token=AsyncMock(side_effect=RuntimeError("failed"))
        )
    )
    with pytest.raises(RuntimeError):
        asyncio.run(
            service.start_new_viva_session(
                SimpleNamespace(
                    student_name="a", topic="b", class_level="1", session_type="viva"
                ),
                "owner",
            )
        )
    insert.assert_not_awaited()


def test_abandon_is_owner_scoped_and_preserves_completed_result(monkeypatch):
    session = SimpleNamespace(id=SESSION_ID, status="completed")
    update = AsyncMock(return_value=SimpleNamespace(modified_count=0))
    get = AsyncMock(return_value=session)
    monkeypatch.setattr(
        module,
        "VivaSession",
        SimpleNamespace(
            get_motor_collection=lambda: SimpleNamespace(update_one=update),
            get=get,
        ),
    )
    service = VivaService(SimpleNamespace())
    service._get_session_with_ownership_check = AsyncMock(return_value=session)
    assert asyncio.run(service.abandon_viva_session(SESSION_ID, "owner")) == {
        "status": "completed"
    }
    assert update.await_args.args[0] == {
        "_id": SESSION_ID,
        "user_id": "owner",
        "status": "in_progress",
    }


def test_abandon_marks_active_session_without_feedback(monkeypatch):
    session = SimpleNamespace(id=SESSION_ID, status="in_progress", feedback=None)

    async def update_one(criteria, change):
        assert criteria["status"] == "in_progress"
        assert change["$set"]["status"] == "abandoned"
        assert "feedback" not in change["$set"]
        session.status = "abandoned"

    monkeypatch.setattr(
        module,
        "VivaSession",
        SimpleNamespace(
            get_motor_collection=lambda: SimpleNamespace(update_one=update_one),
            get=AsyncMock(return_value=session),
        ),
    )
    service = VivaService(SimpleNamespace())
    service._get_session_with_ownership_check = AsyncMock(return_value=session)
    assert asyncio.run(service.abandon_viva_session(SESSION_ID, "owner")) == {
        "status": "abandoned"
    }
    assert session.feedback is None


def test_expiry_only_targets_in_progress_records(monkeypatch):
    update_many = AsyncMock()
    monkeypatch.setattr(
        module,
        "VivaSession",
        SimpleNamespace(
            get_motor_collection=lambda: SimpleNamespace(update_many=update_many)
        ),
    )
    service = VivaService(SimpleNamespace())
    asyncio.run(service._reconcile_expired_sessions(user_id="owner"))
    criteria = update_many.await_args.args[0]
    assert criteria["status"] == "in_progress"
    assert criteria["user_id"] == "owner"
    assert criteria["$or"][0]["expires_at"]["$lte"] <= datetime.datetime.now(
        datetime.timezone.utc
    )
