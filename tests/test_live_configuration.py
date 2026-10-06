import asyncio
import datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import gemini_service
from app.services.gemini_service import GeminiService, GeminiTokenCreationError
from app.schemas.viva import VivaStartRequest
from app.services.viva_service import VivaService


@pytest.mark.parametrize("duration", [5, 10, 15])
def test_duration_controls_prompt_token_and_response(monkeypatch, duration):
    """Keep prompt, compression, credential lifetime, and response metadata on one policy."""
    monkeypatch.setattr(
        gemini_service.settings, "VIVA_SESSION_DURATION_MINUTES", duration
    )
    monkeypatch.setattr(
        gemini_service.settings, "GEMINI_LIVE_MODEL", "configured-live-model"
    )
    create = AsyncMock(return_value=SimpleNamespace(name="auth_tokens/private"))
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
    result = asyncio.run(
        GeminiService().create_ephemeral_token(
            VivaStartRequest(student_name="Student", topic="Plants", class_level="7")
        )
    )
    config = create.await_args.kwargs["config"]
    live = config["live_connect_constraints"]["config"]
    assert (
        config["live_connect_constraints"]["model"]
        == result["model_name"]
        == "configured-live-model"
    )
    context = json.loads(live["system_instruction"].split("\n")[-1])
    assert (
        context["session_duration_minutes"]
        == result["session_duration_minutes"]
        == duration
    )
    assert (
        "Stay within the configured session_duration_minutes"
        in live["system_instruction"]
    )
    assert ("context_window_compression" in live) == (duration == 15)
    assert result["google_api_version"] == "v1beta"
    assert result["session_resumption_enabled"] is True
    assert result["token_expires_at"] == config["expire_time"]
    assert result["new_session_expires_at"] == config["new_session_expire_time"]
    assert config["expire_time"] - config[
        "new_session_expire_time"
    ] == datetime.timedelta(minutes=duration + 2)
    assert "sessionResumption" not in config["lock_additional_fields"]
    assert {
        "model",
        "generationConfig",
        "systemInstruction",
        "tools",
        "realtimeInputConfig",
    } <= set(config["lock_additional_fields"])
    close.assert_awaited_once()


@pytest.mark.parametrize("duration", [0, 6, 20])
def test_settings_reject_unsupported_duration(duration):
    """Reject durations that have no supported viva policy."""
    with pytest.raises(ValidationError):
        Settings(VIVA_SESSION_DURATION_MINUTES=duration)


@pytest.mark.parametrize("name", [None, "", " "])
def test_empty_provider_token_is_rejected_and_client_closed(monkeypatch, name):
    """An unusable credential must fail without leaking a provider client."""
    close = AsyncMock()
    monkeypatch.setattr(
        gemini_service.genai,
        "Client",
        lambda **_: SimpleNamespace(
            aio=SimpleNamespace(
                auth_tokens=SimpleNamespace(
                    create=AsyncMock(return_value=SimpleNamespace(name=name))
                ),
                aclose=close,
            )
        ),
    )
    with pytest.raises(GeminiTokenCreationError):
        asyncio.run(
            GeminiService().create_ephemeral_token(
                VivaStartRequest(
                    student_name="Student", topic="Plants", class_level="7"
                )
            )
        )
    close.assert_awaited_once()


def test_start_returns_metadata_and_deadline_without_persisting_credentials():
    """Persist the viva deadline while keeping ephemeral credentials out of storage."""
    now = datetime.datetime.now(datetime.timezone.utc)
    metadata = {
        "google_api_version": "v1beta",
        "token_expires_at": now + datetime.timedelta(minutes=13),
        "new_session_expires_at": now + datetime.timedelta(minutes=1),
        "session_resumption_enabled": True,
    }
    repository = SimpleNamespace(create_session=AsyncMock())
    service = VivaService(
        SimpleNamespace(
            create_ephemeral_token=AsyncMock(
                return_value={
                    "token": "auth_tokens/private",
                    "model_name": "configured-live-model",
                    "voice_name": "Kore",
                    "session_duration_minutes": 10,
                    **metadata,
                }
            )
        ),
        repository,
    )
    result = asyncio.run(
        service.start_new_viva_session(
            VivaStartRequest(student_name="Student", topic="Plants", class_level="7"),
            "owner",
        )
    )
    session = repository.create_session.await_args.args[0]
    assert result["session_deadline_at"] == session.started_at + datetime.timedelta(
        minutes=10
    )
    assert session.expires_at == result["session_deadline_at"] + datetime.timedelta(
        minutes=2
    )
    assert all(result[key] == value for key, value in metadata.items())
    assert "auth_tokens/private" not in session.model_dump_json()
