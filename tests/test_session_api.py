from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_viva_service
from app.core.auth import get_current_user
from app.db.session_repository import (
    RepositoryUnavailable,
    SessionConflict,
    SessionNotFound,
    SessionTooLarge,
)
from app.main import app

SESSION_ID = "20261005120000000000-" + "a" * 32


def test_details_require_authentication_before_resolving_storage():
    client = TestClient(app)
    assert client.get(f"/api/v1/viva/{SESSION_ID}").status_code == 401


@pytest.mark.parametrize(
    "error,code",
    [
        (SessionNotFound("private-data"), 404),
        (SessionConflict("private-data"), 409),
        (RepositoryUnavailable("private-data"), 503),
        (SessionTooLarge("private-data"), 413),
        (RuntimeError("private-data"), 500),
    ],
)
def test_owner_scoped_details_and_sanitized_error_mapping(error, code, caplog):
    read = AsyncMock(side_effect=error)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="owner"
    )
    app.dependency_overrides[get_viva_service] = lambda: SimpleNamespace(
        get_viva_session_details=read
    )
    try:
        response = TestClient(app).get(f"/api/v1/viva/{SESSION_ID}")
        assert response.status_code == code
        read.assert_awaited_once_with(SESSION_ID, "owner")
        assert "private-data" not in response.text + caplog.text
    finally:
        app.dependency_overrides.clear()


def test_history_validates_limit_and_cursor_and_forwards_owner():
    history = AsyncMock(return_value={"sessions": [], "next_cursor": None})
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="owner"
    )
    app.dependency_overrides[get_viva_service] = lambda: SimpleNamespace(
        get_user_history=history
    )
    try:
        client = TestClient(app)
        assert (
            client.get(
                "/api/v1/viva/history", params={"cursor": SESSION_ID, "limit": 5}
            ).status_code
            == 200
        )
        history.assert_awaited_once_with("owner", 5, SESSION_ID)
        for params in [{"limit": 0}, {"limit": 51}, {"cursor": "USER#other"}]:
            assert client.get("/api/v1/viva/history", params=params).status_code == 422
        assert history.await_count == 1
    finally:
        app.dependency_overrides.clear()


def test_oversized_unicode_transcript_rejected_before_service():
    conclude = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="owner"
    )
    app.dependency_overrides[get_viva_service] = lambda: SimpleNamespace(
        conclude_viva_session=conclude
    )
    try:
        response = TestClient(app).post(
            "/api/v1/viva/conclude-viva",
            json={
                "viva_session_id": SESSION_ID,
                "score": 8,
                "summary": "Good",
                "strong_points": [],
                "areas_of_improvement": [],
                "transcript": "अ" * 22000,
            },
        )
        assert response.status_code == 422
        conclude.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


def test_repository_initialization_failure_returns_503():
    async def fail():
        raise RepositoryUnavailable("private-data")

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="owner"
    )
    app.dependency_overrides[get_viva_service] = fail
    try:
        response = TestClient(app).get(f"/api/v1/viva/{SESSION_ID}")
        assert response.status_code == 503
        assert "private-data" not in response.text
    finally:
        app.dependency_overrides.clear()
