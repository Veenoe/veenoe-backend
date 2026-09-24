import asyncio
import datetime
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.viva import VivaStartRequest
from app.services import gemini_service
from app.services.gemini_service import GeminiService, GEMINI_LIVE_CONFIG


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
    monkeypatch.setattr(gemini_service.genai, "Client", lambda **_: client)
    caplog.set_level(logging.INFO, logger=gemini_service.__name__)

    response = asyncio.run(
        GeminiService().create_ephemeral_token(request(voice_name="Aoede"))
    )

    config = create.await_args.kwargs["config"]
    live = config["live_connect_constraints"]["config"]
    assert (
        config["live_connect_constraints"]["model"]
        == "gemini-2.5-flash-native-audio-preview-09-2025"
    )
    assert config["http_options"]["api_version"] == "v1alpha"
    assert config["uses"] == 1
    remaining = config["expire_time"] - datetime.datetime.now(datetime.timezone.utc)
    assert (
        datetime.timedelta(minutes=14, seconds=59)
        < remaining
        <= datetime.timedelta(minutes=15)
    )
    assert live["response_modalities"] == ["AUDIO"]
    assert live["session_resumption"] == {}
    assert live["input_audio_transcription"] == {}
    assert live["output_audio_transcription"] == {}
    assert live["tools"][0]["function_declarations"][0]["name"] == "conclude_viva"
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
    with pytest.raises(RuntimeError) as raised:
        asyncio.run(GeminiService().create_ephemeral_token(request()))

    assert raised.value is failure
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
