import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from pydantic import ValidationError

from app.core.config import Settings
from app.core.runtime_config import load_runtime_config


@pytest.mark.parametrize("raw, expected", [("5", 5), ("10", 10), ("15", 15)])
@pytest.mark.parametrize("source", ["environment", "dotenv", "override"])
def test_settings_parse_supported_duration_strings(
    monkeypatch, tmp_path, raw, expected, source
):
    """Accept deployment and local configuration strings as supported integer durations."""
    monkeypatch.delenv("VEENOE_SSM_PARAMETER_PREFIX", raising=False)
    monkeypatch.delenv("VIVA_SESSION_DURATION_MINUTES", raising=False)
    values = {"_env_file": None}
    if source == "environment":
        monkeypatch.setenv("VIVA_SESSION_DURATION_MINUTES", raw)
    elif source == "dotenv":
        env_file = tmp_path / ".env"
        env_file.write_text(f"VIVA_SESSION_DURATION_MINUTES={raw}\n", encoding="utf-8")
        values["_env_file"] = env_file
    else:
        values["VIVA_SESSION_DURATION_MINUTES"] = raw
    settings = Settings(**values)
    assert settings.VIVA_SESSION_DURATION_MINUTES == expected
    assert type(settings.VIVA_SESSION_DURATION_MINUTES) is int


@pytest.mark.parametrize("raw", ["", "0", "6", "20", "5.0", "five"])
def test_settings_reject_invalid_environment_durations(monkeypatch, raw):
    """Invalid deployment values must fail rather than silently select a duration."""
    monkeypatch.delenv("VEENOE_SSM_PARAMETER_PREFIX", raising=False)
    monkeypatch.setenv("VIVA_SESSION_DURATION_MINUTES", raw)
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)
    assert any(
        error["loc"] == ("VIVA_SESSION_DURATION_MINUTES",)
        for error in caught.value.errors()
    )


def test_settings_import_with_lambda_environment(tmp_path):
    """Catch cold-start failures when module-level settings read Lambda's string values."""
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "VEENOE_SSM_PARAMETER_PREFIX": "",
        "DYNAMODB_TABLE_NAME": "test-sessions",
        "GOOGLE_API_KEY": "test-key",
        "CLERK_SECRET_KEY": "test-key",
        "VIVA_SESSION_DURATION_MINUTES": "5",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.core.config import settings; print(settings.VIVA_SESSION_DURATION_MINUTES)",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "5"


def ssm_response(prefix="/veenoe/dev"):
    return {
        "Parameters": [
            {"Name": f"{prefix}/google_api_key", "Value": "google-secret"},
            {"Name": f"{prefix}/clerk_secret_key", "Value": "clerk-secret"},
        ]
    }


@pytest.mark.parametrize("prefix", [None, "", "  "])
def test_local_mode_never_calls_ssm(monkeypatch, prefix):
    monkeypatch.delenv("VEENOE_SSM_PARAMETER_PREFIX", raising=False)
    if prefix is not None:
        monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", prefix)
    with patch("boto3.client") as client:
        assert load_runtime_config() == {}
        client.assert_not_called()


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_exact_environment_secrets_and_bounded_timeouts(monkeypatch, environment):
    prefix = f"/veenoe/{environment}"
    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", prefix + "/")
    client = MagicMock()
    client.get_parameters.return_value = ssm_response(prefix)
    with patch("boto3.client", return_value=client) as factory:
        assert load_runtime_config() == {
            "GOOGLE_API_KEY": "google-secret",
            "CLERK_SECRET_KEY": "clerk-secret",
        }
        config = factory.call_args.kwargs["config"]
        assert config.connect_timeout == config.read_timeout == 5
        assert config.retries == {"max_attempts": 2}
    client.get_parameters.assert_called_once_with(
        Names=[f"{prefix}/google_api_key", f"{prefix}/clerk_secret_key"],
        WithDecryption=True,
    )


@pytest.mark.parametrize(
    "response",
    [
        {"Parameters": []},
        {"InvalidParameters": ["/veenoe/dev/clerk_secret_key"]},
        {
            "Parameters": [
                {"Name": "/veenoe/dev/google_api_key", "Value": "  "},
                {"Name": "/veenoe/dev/clerk_secret_key", "Value": "secret"},
            ]
        },
    ],
)
def test_missing_invalid_and_empty_secrets_fail_closed(monkeypatch, response):
    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")
    client = MagicMock()
    client.get_parameters.return_value = response
    with patch("boto3.client", return_value=client), pytest.raises(RuntimeError):
        load_runtime_config()


@pytest.mark.parametrize(
    "error",
    [
        ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "private-secret"}},
            "GetParameters",
        ),
        EndpointConnectionError(endpoint_url="https://private-secret"),
    ],
)
def test_provider_failures_do_not_leak_secrets(monkeypatch, caplog, error):
    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")
    client = MagicMock()
    client.get_parameters.side_effect = error
    with (
        patch("boto3.client", return_value=client),
        caplog.at_level(logging.DEBUG),
        pytest.raises(RuntimeError) as caught,
    ):
        load_runtime_config()
    assert "private-secret" not in str(caught.value) + caplog.text
    assert caught.value.__cause__ is None


def test_settings_need_no_mongodb_configuration(monkeypatch):
    monkeypatch.delenv("VEENOE_SSM_PARAMETER_PREFIX", raising=False)
    with patch("boto3.client") as client:
        settings = Settings(
            _env_file=None,
            DYNAMODB_TABLE_NAME="local-sessions",
            GOOGLE_API_KEY="key",
            CLERK_SECRET_KEY="key",
        )
    client.assert_not_called()
    assert settings.DYNAMODB_TABLE_NAME == "local-sessions"
    assert "MONGO_URI" not in Settings.model_fields
    assert "MONGO_DB_NAME" not in Settings.model_fields


def test_ssm_overrides_stale_environment_without_logging_values(monkeypatch, caplog):
    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")
    monkeypatch.setenv("GOOGLE_API_KEY", "stale")
    monkeypatch.setenv("CLERK_SECRET_KEY", "stale")
    client = MagicMock()
    client.get_parameters.return_value = ssm_response()
    with patch("boto3.client", return_value=client), caplog.at_level(logging.INFO):
        settings = Settings(_env_file=None, DYNAMODB_TABLE_NAME="dev-sessions")
    assert settings.GOOGLE_API_KEY == "google-secret"
    assert settings.CLERK_SECRET_KEY == "clerk-secret"
    assert "google-secret" not in caplog.text
    assert "clerk-secret" not in caplog.text
