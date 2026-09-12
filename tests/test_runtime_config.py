"""
Unit tests for AWS Systems Manager (SSM) runtime configuration loader (app.core.runtime_config).
Tests:
1. Local mode (prefix absent/empty) -> returns empty dict, no AWS API calls.
2. AWS mode (prefix set) -> batched single call to ssm.get_parameters with WithDecryption=True.
3. Exact 4 parameter names requested for the configured environment prefix.
4. Correct mapping to Settings keys (MONGO_URI, MONGO_DB_NAME, GOOGLE_API_KEY, CLERK_SECRET_KEY).
5. Fail-closed on missing parameters.
6. Fail-closed on InvalidParameters.
7. Fail-closed on empty/whitespace parameter values.
8. Fail-closed on AWS ClientError / BotoCoreError.
9. No secret values leaked into logs or error messages.
10. Bounded client timeouts and retry configuration.
11. Clean integration with Settings().
"""

import logging
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError, EndpointConnectionError


def test_local_mode_when_prefix_absent(monkeypatch):
    """When VEENOE_SSM_PARAMETER_PREFIX is not set, loader returns empty dict with no SSM calls."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.delenv("VEENOE_SSM_PARAMETER_PREFIX", raising=False)

    with patch("boto3.client") as mock_boto:
        config = load_runtime_config()
        assert config == {}
        mock_boto.assert_not_called()


def test_local_mode_when_prefix_is_empty_or_whitespace(monkeypatch):
    """When VEENOE_SSM_PARAMETER_PREFIX is whitespace or empty, loader returns empty dict."""
    from app.core.runtime_config import load_runtime_config

    for empty_val in ["", "   ", "\t"]:
        monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", empty_val)
        with patch("boto3.client") as mock_boto:
            config = load_runtime_config()
            assert config == {}
            mock_boto.assert_not_called()


def test_aws_mode_requests_exact_parameter_names_with_decryption(monkeypatch):
    """
    In AWS mode, loader makes a single GetParameters call with WithDecryption=True
    for the exact 4 environment-specific parameter names.
    """
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")

    expected_names = [
        "/veenoe/dev/mongo_uri",
        "/veenoe/dev/mongo_db_name",
        "/veenoe/dev/google_api_key",
        "/veenoe/dev/clerk_secret_key",
    ]

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": "mongodb+srv://devuser:devpass@dev.mongodb.net"},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "dev_viva_db"},
            {"Name": "/veenoe/dev/google_api_key", "Value": "real_google_api_key_12345"},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": "sk_test_real_clerk_secret_99999"},
        ],
        "InvalidParameters": [],
    }

    with patch("boto3.client", return_value=mock_ssm) as mock_boto_client:
        config = load_runtime_config()

        # Check client creation
        mock_boto_client.assert_called_once()
        client_args, client_kwargs = mock_boto_client.call_args
        assert client_args[0] == "ssm"
        assert "config" in client_kwargs
        botocore_config = client_kwargs["config"]
        assert botocore_config.connect_timeout == 5
        assert botocore_config.read_timeout == 5
        assert botocore_config.retries == {"max_attempts": 2}

        # Check single get_parameters call
        mock_ssm.get_parameters.assert_called_once()
        call_kwargs = mock_ssm.get_parameters.call_args[1]
        assert set(call_kwargs["Names"]) == set(expected_names)
        assert call_kwargs["WithDecryption"] is True

        # Check mapped dictionary matches Settings contract
        assert config["MONGO_URI"] == "mongodb+srv://devuser:devpass@dev.mongodb.net"
        assert config["MONGO_DB_NAME"] == "dev_viva_db"
        assert config["GOOGLE_API_KEY"] == "real_google_api_key_12345"
        assert config["CLERK_SECRET_KEY"] == "sk_test_real_clerk_secret_99999"


def test_aws_mode_normalizes_trailing_slash_in_prefix(monkeypatch):
    """Loader normalizes trailing slashes in the prefix gracefully."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev/")

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": "mongodb://localhost:27017"},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "dev_db"},
            {"Name": "/veenoe/dev/google_api_key", "Value": "key123"},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": "clerk123"},
        ],
        "InvalidParameters": [],
    }

    with patch("boto3.client", return_value=mock_ssm):
        config = load_runtime_config()
        assert config["MONGO_DB_NAME"] == "dev_db"
        call_names = mock_ssm.get_parameters.call_args[1]["Names"]
        assert all(not name.startswith("/veenoe/dev//") for name in call_names)


def test_aws_mode_fails_closed_on_missing_parameter(monkeypatch):
    """If SSM returns fewer than the 4 required parameters, raises sanitized RuntimeError."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    # Missing clerk_secret_key
    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": "mongodb://localhost:27017"},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "dev_db"},
            {"Name": "/veenoe/dev/google_api_key", "Value": "key123"},
        ],
        "InvalidParameters": [],
    }

    with patch("boto3.client", return_value=mock_ssm):
        with pytest.raises(RuntimeError) as exc_info:
            load_runtime_config()
        assert "missing required parameter" in str(exc_info.value).lower()
        assert "/veenoe/dev/clerk_secret_key" in str(exc_info.value)


def test_aws_mode_fails_closed_on_invalid_parameters(monkeypatch):
    """If SSM returns InvalidParameters, raises sanitized RuntimeError naming the invalid parameter."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "dev_db"},
            {"Name": "/veenoe/dev/google_api_key", "Value": "key123"},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": "clerk123"},
        ],
        "InvalidParameters": ["/veenoe/dev/mongo_uri"],
    }

    with patch("boto3.client", return_value=mock_ssm):
        with pytest.raises(RuntimeError) as exc_info:
            load_runtime_config()
        assert "invalid parameter" in str(exc_info.value).lower()
        assert "/veenoe/dev/mongo_uri" in str(exc_info.value)


def test_aws_mode_fails_closed_on_empty_parameter_value(monkeypatch):
    """If any parameter value is empty or whitespace, raises sanitized RuntimeError."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": "mongodb://localhost:27017"},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "   "},  # whitespace only
            {"Name": "/veenoe/dev/google_api_key", "Value": "key123"},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": "clerk123"},
        ],
        "InvalidParameters": [],
    }

    with patch("boto3.client", return_value=mock_ssm):
        with pytest.raises(RuntimeError) as exc_info:
            load_runtime_config()
        assert "empty value" in str(exc_info.value).lower()
        assert "/veenoe/dev/mongo_db_name" in str(exc_info.value)


def test_aws_mode_fails_closed_on_boto_client_error(monkeypatch):
    """If SSM throws ClientError (e.g. AccessDeniedException), raises sanitized RuntimeError."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "User is not authorized"}},
        "GetParameters",
    )

    with patch("boto3.client", return_value=mock_ssm):
        with pytest.raises(RuntimeError) as exc_info:
            load_runtime_config()
        assert str(exc_info.value) == "Failed to retrieve runtime configuration from AWS SSM: ClientError"
        assert exc_info.value.__cause__ is None


def test_aws_mode_fails_closed_on_endpoint_error(monkeypatch):
    """If network timeout / endpoint connection error occurs, raises sanitized RuntimeError."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.side_effect = EndpointConnectionError(endpoint_url="https://ssm.ap-south-1.amazonaws.com")

    with patch("boto3.client", return_value=mock_ssm):
        with pytest.raises(RuntimeError) as exc_info:
            load_runtime_config()
        assert "failed to retrieve runtime configuration" in str(exc_info.value).lower()


def test_secrets_never_logged(monkeypatch, caplog):
    """Verify that secret values are NEVER present in captured logs at any level."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    secret_mongo = "mongodb+srv://super_secret_user:super_secret_pw@secret.mongodb.net"
    secret_google = "AIzaSySecretGoogleApiKey99999"
    secret_clerk = "sk_test_super_secret_clerk_key_88888"

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": secret_mongo},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "test_db"},
            {"Name": "/veenoe/dev/google_api_key", "Value": secret_google},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": secret_clerk},
        ],
        "InvalidParameters": [],
    }

    with caplog.at_level(logging.DEBUG):
        with patch("boto3.client", return_value=mock_ssm):
            load_runtime_config()

        for record in caplog.records:
            log_text = record.getMessage()
            assert secret_mongo not in log_text, "Mongo URI leaked in log output!"
            assert secret_google not in log_text, "Google API Key leaked in log output!"
            assert secret_clerk not in log_text, "Clerk Secret Key leaked in log output!"
            # Full response object must not be logged
            assert "super_secret" not in log_text


def test_dev_loader_cannot_request_prod_paths(monkeypatch):
    """Loader with /veenoe/dev prefix only requests /veenoe/dev/* parameter paths."""
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": "m"},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "d"},
            {"Name": "/veenoe/dev/google_api_key", "Value": "g"},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": "c"},
        ],
        "InvalidParameters": [],
    }

    with patch("boto3.client", return_value=mock_ssm):
        load_runtime_config()
        call_names = mock_ssm.get_parameters.call_args[1]["Names"]
        assert all("prod" not in name for name in call_names)


def test_settings_integration_local_fallback(monkeypatch):
    """When VEENOE_SSM_PARAMETER_PREFIX is absent, Settings loads from env/.env without AWS call."""
    from app.core.config import Settings

    monkeypatch.delenv("VEENOE_SSM_PARAMETER_PREFIX", raising=False)
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "local_test_db")
    monkeypatch.setenv("GOOGLE_API_KEY", "local_test_google_key")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_local_clerk_key")

    with patch("boto3.client") as mock_boto:
        custom_settings = Settings()
        mock_boto.assert_not_called()
        assert custom_settings.MONGO_URI == "mongodb://localhost:27017"
        assert custom_settings.MONGO_DB_NAME == "local_test_db"
        assert custom_settings.GOOGLE_API_KEY == "local_test_google_key"
        assert custom_settings.CLERK_SECRET_KEY == "sk_test_local_clerk_key"


def test_settings_integration_with_ssm(monkeypatch):
    """When VEENOE_SSM_PARAMETER_PREFIX is set, Settings populates from SSM values."""
    from app.core.config import Settings

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")
    # Delete ambient env vars to prove values come strictly from SSM
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.delenv("MONGO_DB_NAME", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": "mongodb+srv://ssmuser:ssmpw@dev.mongodb.net"},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "ssm_dev_db"},
            {"Name": "/veenoe/dev/google_api_key", "Value": "ssm_google_key_999"},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": "sk_test_ssm_clerk_key_888"},
        ],
        "InvalidParameters": [],
    }

    with patch("boto3.client", return_value=mock_ssm):
        custom_settings = Settings()
        assert custom_settings.MONGO_URI == "mongodb+srv://ssmuser:ssmpw@dev.mongodb.net"
        assert custom_settings.MONGO_DB_NAME == "ssm_dev_db"
        assert custom_settings.GOOGLE_API_KEY == "ssm_google_key_999"
        assert custom_settings.CLERK_SECRET_KEY == "sk_test_ssm_clerk_key_888"


def test_aws_error_sanitization_regression_fake_secret(monkeypatch, caplog):
    """
    Regression test: If AWS exception message contains a sensitive secret value,
    verify that the secret is completely absent from:
    - str(RuntimeError)
    - exception __cause__ / traceback
    - captured logs
    """
    from app.core.runtime_config import load_runtime_config

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")
    leaked_secret = "SUPER_SECRET_MUST_NOT_LEAK"

    mock_ssm = MagicMock()
    mock_ssm.get_parameters.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": f"Sensitive key {leaked_secret} unauthorized"}},
        "GetParameters",
    )

    with caplog.at_level(logging.DEBUG):
        with patch("boto3.client", return_value=mock_ssm):
            with pytest.raises(RuntimeError) as exc_info:
                load_runtime_config()

    # 1. Secret must not appear in str(RuntimeError)
    assert leaked_secret not in str(exc_info.value)
    assert str(exc_info.value) == "Failed to retrieve runtime configuration from AWS SSM: ClientError"

    # 2. Secret must not appear in __cause__ (suppressed via from None)
    assert exc_info.value.__cause__ is None

    # 3. Secret must not appear in captured logs
    for record in caplog.records:
        assert leaked_secret not in record.getMessage()


def test_settings_integration_ssm_overrides_stale_environment(monkeypatch):
    """
    Prove that SSM parameter values take precedence over stale ambient environment
    variables when in AWS mode (VEENOE_SSM_PARAMETER_PREFIX is set).
    """
    from app.core.config import Settings

    monkeypatch.setenv("VEENOE_SSM_PARAMETER_PREFIX", "/veenoe/dev")

    # Set stale environment values
    monkeypatch.setenv("MONGO_URI", "mongodb://stale-host:27017")
    monkeypatch.setenv("MONGO_DB_NAME", "stale_db")
    monkeypatch.setenv("GOOGLE_API_KEY", "stale_google_key_old")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_stale_clerk_key_old")

    # Mock SSM returning FRESH, real values
    mock_ssm = MagicMock()
    mock_ssm.get_parameters.return_value = {
        "Parameters": [
            {"Name": "/veenoe/dev/mongo_uri", "Value": "mongodb+srv://fresh-user:fresh-pw@fresh.mongodb.net"},
            {"Name": "/veenoe/dev/mongo_db_name", "Value": "fresh_viva_db"},
            {"Name": "/veenoe/dev/google_api_key", "Value": "fresh_google_key_active"},
            {"Name": "/veenoe/dev/clerk_secret_key", "Value": "sk_test_fresh_clerk_key_active"},
        ],
        "InvalidParameters": [],
    }

    with patch("boto3.client", return_value=mock_ssm):
        custom_settings = Settings()

        # Assert all four values equal the SSM values, NOT the stale environment values
        assert custom_settings.MONGO_URI == "mongodb+srv://fresh-user:fresh-pw@fresh.mongodb.net"
        assert custom_settings.MONGO_DB_NAME == "fresh_viva_db"
        assert custom_settings.GOOGLE_API_KEY == "fresh_google_key_active"
        assert custom_settings.CLERK_SECRET_KEY == "sk_test_fresh_clerk_key_active"

        assert custom_settings.MONGO_URI != "mongodb://stale-host:27017"
        assert custom_settings.MONGO_DB_NAME != "stale_db"
        assert custom_settings.GOOGLE_API_KEY != "stale_google_key_old"
        assert custom_settings.CLERK_SECRET_KEY != "sk_test_stale_clerk_key_old"
