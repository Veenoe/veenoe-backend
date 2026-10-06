"""Exercise provisioning failures at the real SDK HTTP boundary, without network calls."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai

from app.api.deps import get_viva_service
from app.core.auth import get_current_user
from app.main import app
from app.schemas.viva import VivaStartRequest
from app.services import gemini_service
from app.services.gemini_service import (
    GeminiService,
    GeminiTokenCreationError,
    GeminiTokenUnavailable,
)
from app.services.viva_service import VivaService


def request():
    """Build synthetic session metadata without student or credential data."""
    return VivaStartRequest(
        student_name="Synthetic Student", topic="Plants", class_level="7"
    )


def sdk_transport(monkeypatch, outcomes):
    """Replace only HTTP I/O so token conversion and transport errors stay real."""
    real_client = genai.Client
    requests = []
    clients = []

    def respond(http_request):
        requests.append(json.loads(http_request.content))
        outcome = outcomes[min(len(requests) - 1, len(outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(
            outcome,
            json=(
                {"name": "auth_tokens/synthetic"}
                if outcome == 200
                else {
                    "error": {
                        "code": outcome,
                        "message": "private provider details",
                        "status": "UNAVAILABLE",
                    }
                }
            ),
        )

    def factory(**kwargs):
        options = dict(kwargs["http_options"])
        options["async_client_args"] = {"transport": httpx.MockTransport(respond)}
        client = real_client(api_key="synthetic-key", http_options=options)
        clients.append(client)
        return client

    monkeypatch.setattr(gemini_service.genai, "Client", factory)
    return requests, clients


@pytest.mark.parametrize(
    "failure",
    [
        httpx.RemoteProtocolError("private transport details"),
        httpx.ReadTimeout("private timeout"),
        503,
        429,
    ],
)
def test_transient_failure_retries_without_creating_an_extra_viva(monkeypatch, failure):
    requests, clients = sdk_transport(monkeypatch, [failure, 200])
    repository = SimpleNamespace(create_session=AsyncMock())
    result = asyncio.run(
        VivaService(GeminiService(), repository).start_new_viva_session(
            request(), "synthetic-owner"
        )
    )
    assert result["ephemeral_token"] == "auth_tokens/synthetic"
    assert len(requests) == 2
    repository.create_session.assert_awaited_once()
    assert all(client._api_client._async_httpx_client.is_closed for client in clients)
    assert requests[1]["newSessionExpireTime"] >= requests[0]["newSessionExpireTime"]


@pytest.mark.parametrize("status", [400, 401, 403])
def test_permanent_provider_errors_do_not_retry(monkeypatch, status):
    requests, _ = sdk_transport(monkeypatch, [status])
    with pytest.raises(GeminiTokenCreationError):
        asyncio.run(GeminiService().create_ephemeral_token(request()))
    assert len(requests) == 1


def test_exhausted_transport_failure_is_503_and_never_persists_or_leaks(
    monkeypatch, caplog
):
    requests, _ = sdk_transport(
        monkeypatch, [httpx.RemoteProtocolError("private transport details")]
    )
    repository = SimpleNamespace(create_session=AsyncMock())
    app.dependency_overrides[get_viva_service] = lambda: VivaService(
        GeminiService(), repository
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        user_id="synthetic-owner"
    )
    try:
        response = TestClient(app).post(
            "/api/v1/viva/start", json=request().model_dump()
        )
        assert response.status_code == 503
        assert len(requests) == 2
        repository.create_session.assert_not_awaited()
        for private in [
            "private transport details",
            "Synthetic Student",
            "synthetic-key",
            "auth_tokens/synthetic",
        ]:
            assert private not in response.text + caplog.text
    finally:
        app.dependency_overrides.clear()


def test_overall_provisioning_budget_cancels_a_hung_provider_and_closes_client(
    monkeypatch,
):
    async def hang(**_):
        await asyncio.Event().wait()

    close = AsyncMock()
    monkeypatch.setattr(
        gemini_service, "TOKEN_PROVISIONING_BUDGET_SECONDS", 0.02, raising=False
    )
    monkeypatch.setattr(
        gemini_service.genai,
        "Client",
        lambda **_: SimpleNamespace(
            aio=SimpleNamespace(auth_tokens=SimpleNamespace(create=hang), aclose=close)
        ),
    )
    with pytest.raises(GeminiTokenUnavailable):
        asyncio.run(GeminiService().create_ephemeral_token(request()))
    close.assert_awaited_once()


def test_request_cancellation_closes_client_without_retrying(monkeypatch):
    """Cancellation belongs to the caller and must not start another mint."""
    create = AsyncMock(side_effect=asyncio.CancelledError)
    close = AsyncMock()
    monkeypatch.setattr(
        gemini_service.genai,
        "Client",
        lambda **_: SimpleNamespace(
            aio=SimpleNamespace(
                auth_tokens=SimpleNamespace(create=create), aclose=close
            )
        ),
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(GeminiService().create_ephemeral_token(request()))
    create.assert_awaited_once()
    close.assert_awaited_once()
