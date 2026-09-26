import asyncio
import datetime
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_viva_service
from app.core.auth import get_current_user
from app.main import app
from app.schemas.viva import VivaStartRequest
from app.services import gemini_service
from app.services.gemini_service import (
    GeminiService,
    GeminiTokenCreationError,
    GEMINI_LIVE_CONFIG,
)


def request(**overrides):
    values = {
        "student_name": "Private Student",
        "topic": "Private Topic",
        "class_level": "12",
    }
    values.update(overrides)
    return VivaStartRequest(**values)


def test_token_uses_current_live_contract_and_requested_voice(monkeypatch, caplog):
    token = SimpleNamespace(name="ephemeral-secret-token")
    create = AsyncMock(return_value=token)
    client = SimpleNamespace(
        aio=SimpleNamespace(auth_tokens=SimpleNamespace(create=create))
    )
    client_args = {}

    def fake_client(**kwargs):
        client_args.update(kwargs)
        return client

    monkeypatch.setattr(gemini_service.genai, "Client", fake_client)
    caplog.set_level(logging.INFO, logger=gemini_service.__name__)

    response = asyncio.run(
        GeminiService().create_ephemeral_token(request(voice_name="Aoede"))
    )

    config = create.await_args.kwargs["config"]
    live = config["live_connect_constraints"]["config"]
    assert config["live_connect_constraints"]["model"] == "gemini-3.8-live"
    assert client_args["http_options"]["api_version"] == "v1beta"
    assert "http_options" not in config
    assert config["uses"] == 1
    remaining = config["expire_time"] - datetime.datetime.now(datetime.timezone.utc)
    assert (
        datetime.timedelta(minutes=14, seconds=55)
        < remaining
        <= datetime.timedelta(minutes=15)
    )
    assert live["response_modalities"] == ["AUDIO"]
    assert live["session_resumption"] == {}
    assert live["input_audio_transcription"] == {}
    assert live["output_audio_transcription"] == {}
    assert live["tools"][0]["function_declarations"][0]["name"] == "conclude_viva"
    assert live["tools"][0]["function_declarations"][0]["behavior"] == "BLOCKING"
    assert (
        live["speech_config"]["voice_config"]["prebuilt_voice_config"]["voice_name"]
        == "Aoede"
    )
    assert response["voice_name"] == "Aoede"
    assert response["token"] == "ephemeral-secret-token"
    assert response["model_name"] == GEMINI_LIVE_CONFIG.model
    assert "event=gemini_ephemeral_token_attempt" in caplog.text
    assert "event=gemini_ephemeral_token_created" in caplog.text
    assert "duration_ms=" in caplog.text
    for private_value in (
        "test_google_api_key",
        "ephemeral-secret-token",
        "Private Student",
        "Private Topic",
        "**Student Name:**",
        "sk_test_mock_clerk_secret_key",
        "mongodb://localhost:27017",
    ):
        assert private_value not in caplog.text


def test_default_voice_and_failure_logs_only_safe_metadata(monkeypatch, caplog):
    failure = RuntimeError("test_google_api_key ephemeral-secret prompt content")
    create = AsyncMock(side_effect=failure)
    client = SimpleNamespace(
        aio=SimpleNamespace(auth_tokens=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(gemini_service.genai, "Client", lambda **_: client)
    caplog.set_level(logging.INFO, logger=gemini_service.__name__)

    assert (
        GeminiService().generate_system_instruction(request()).find("Private Topic")
        >= 0
    )
    with pytest.raises(GeminiTokenCreationError) as raised:
        asyncio.run(GeminiService().create_ephemeral_token(request()))

    assert raised.value.__cause__ is None
    assert "event=gemini_ephemeral_token_failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "duration_ms=" in caplog.text
    for private_value in (
        "test_google_api_key",
        "ephemeral-secret",
        "Private Student",
        "Private Topic",
        "prompt content",
        "**Student Name:**",
    ):
        assert private_value not in caplog.text

    success_create = AsyncMock(return_value=SimpleNamespace(name="another-token"))
    client.aio.auth_tokens.create = success_create
    response = asyncio.run(
        GeminiService().create_ephemeral_token(request(voice_name=None))
    )
    live = success_create.await_args.kwargs["config"]["live_connect_constraints"][
        "config"
    ]
    assert "speech_config" not in live
    assert response["voice_name"] == "Kore"


def test_start_endpoint_never_logs_upstream_exception_content(monkeypatch, caplog):
    from app.services import gemini_service as gemini_module

    upstream_failure = RuntimeError(
        "test_google_api_key auth_tokens/example-secret system prompt content"
    )

    create = AsyncMock(side_effect=upstream_failure)
    client = SimpleNamespace(
        aio=SimpleNamespace(auth_tokens=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(gemini_module.genai, "Client", lambda **_: client)
    from app.services import viva_service as viva_service_module

    class FakeVivaSession:
        id = "507f1f77bcf86cd799439011"

        def __init__(self, **_):
            pass

        async def insert(self):
            pass

    monkeypatch.setattr(viva_service_module, "VivaSession", FakeVivaSession)

    async def service_dependency():
        from app.services.viva_service import VivaService

        return VivaService(llm_client=GeminiService())

    async def user_dependency():
        return SimpleNamespace(user_id="user_test_safe")

    app.dependency_overrides[get_viva_service] = service_dependency
    app.dependency_overrides[get_current_user] = user_dependency
    caplog.set_level(logging.INFO)
    try:
        response = TestClient(app).post(
            "/api/v1/viva/start",
            json={
                "student_name": "Private Student",
                "topic": "Private Topic",
                "class_level": "12",
            },
        )
    finally:
        app.dependency_overrides.clear()

    create.assert_awaited_once()
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Failed to start session. Please try again."
    }
    for private_value in (
        "test_google_api_key",
        "auth_tokens/example-secret",
        "system prompt content",
        "Private Student",
        "Private Topic",
        "Traceback",
    ):
        assert private_value not in caplog.text
    assert "event=viva_start_failed" in caplog.text


def test_start_endpoint_handles_domain_token_error_without_logging_details(
    monkeypatch, caplog
):
    failure = GeminiTokenCreationError(
        "test_google_api_key auth_tokens/example-secret private prompt data"
    )

    class FailingVivaService:
        async def start_new_viva_session(self, viva_request, user_id):
            raise failure

    async def service_dependency():
        return FailingVivaService()

    async def user_dependency():
        return SimpleNamespace(user_id="user_test_safe")

    app.dependency_overrides[get_viva_service] = service_dependency
    app.dependency_overrides[get_current_user] = user_dependency
    caplog.set_level(logging.INFO)
    try:
        response = TestClient(app).post(
            "/api/v1/viva/start",
            json={
                "student_name": "Private Student",
                "topic": "Private Topic",
                "class_level": "12",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {
        "detail": "Failed to start session. Please try again."
    }
    assert "event=viva_start_failed" in caplog.text
    assert "error_type=GeminiTokenCreationError" in caplog.text
    for private_value in (
        "test_google_api_key",
        "auth_tokens/example-secret",
        "private prompt data",
        "Private Student",
        "Private Topic",
        "Traceback",
    ):
        assert private_value not in caplog.text
