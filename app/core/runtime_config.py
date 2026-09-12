"""
Runtime configuration loader for AWS Systems Manager (SSM) Parameter Store.

Responsibilities:
1. Detect whether AWS SSM runtime configuration is enabled via VEENOE_SSM_PARAMETER_PREFIX.
2. In local development (prefix absent), return an empty dict so Pydantic-settings
   falls back to .env or local environment variables.
3. In AWS Lambda mode (prefix present), retrieve the exact expected parameters
   using a single batched GetParameters call with WithDecryption=True.
4. Validate that all required parameters are present and non-empty (fail-closed).
5. Map parameters to the existing application Settings contract keys:
   - MONGO_URI
   - MONGO_DB_NAME
   - GOOGLE_API_KEY
   - CLERK_SECRET_KEY
6. Never log or leak secret values, connection strings, or full AWS API responses.
7. Use bounded connection/read timeouts and bounded retry attempts.
"""

import os
import logging
from typing import Dict

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# Exact parameter suffixes expected under VEENOE_SSM_PARAMETER_PREFIX
PARAM_MONGO_URI = "mongo_uri"
PARAM_MONGO_DB_NAME = "mongo_db_name"
PARAM_GOOGLE_API_KEY = "google_api_key"
PARAM_CLERK_SECRET_KEY = "clerk_secret_key"

REQUIRED_PARAM_SUFFIXES = [
    PARAM_MONGO_URI,
    PARAM_MONGO_DB_NAME,
    PARAM_GOOGLE_API_KEY,
    PARAM_CLERK_SECRET_KEY,
]

# Mapping from SSM parameter suffix to Settings field name
SUFFIX_TO_SETTINGS_KEY = {
    PARAM_MONGO_URI: "MONGO_URI",
    PARAM_MONGO_DB_NAME: "MONGO_DB_NAME",
    PARAM_GOOGLE_API_KEY: "GOOGLE_API_KEY",
    PARAM_CLERK_SECRET_KEY: "CLERK_SECRET_KEY",
}


def load_runtime_config() -> Dict[str, str]:
    """
    Load runtime configuration parameters from AWS SSM Parameter Store if enabled.

    Returns:
        Dict[str, str]: Dictionary of configuration key-values matching Settings fields
                        if SSM prefix is configured; empty dict if local mode.

    Raises:
        RuntimeError: If AWS mode is enabled and parameter fetch, validation, or
                      decryption fails (fail-closed).
    """
    raw_prefix = os.environ.get("VEENOE_SSM_PARAMETER_PREFIX")
    if not raw_prefix or not raw_prefix.strip():
        logger.debug(
            "VEENOE_SSM_PARAMETER_PREFIX not set. Using local environment/.env configuration."
        )
        return {}

    # Normalize prefix (e.g. "/veenoe/dev/" -> "/veenoe/dev")
    prefix = raw_prefix.strip().rstrip("/")
    if not prefix.startswith("/"):
        prefix = f"/{prefix}"

    # Build exact parameter names
    expected_names = [f"{prefix}/{suffix}" for suffix in REQUIRED_PARAM_SUFFIXES]
    name_to_suffix = {f"{prefix}/{suffix}": suffix for suffix in REQUIRED_PARAM_SUFFIXES}

    logger.info(
        "Loading runtime configuration from AWS SSM Parameter Store under prefix: %s",
        prefix,
    )

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-south-1"

    # Bounded timeouts and retries so SSM delays do not exhaust Lambda execution timeout
    sdk_config = Config(
        connect_timeout=5,
        read_timeout=5,
        retries={"max_attempts": 2},
    )

    try:
        ssm_client = boto3.client("ssm", region_name=region, config=sdk_config)
        response = ssm_client.get_parameters(
            Names=expected_names,
            WithDecryption=True,
        )
    except (ClientError, BotoCoreError) as e:
        logger.error(
            "Failed to retrieve runtime configuration from AWS SSM: %s",
            type(e).__name__,
        )
        raise RuntimeError(
            f"Failed to retrieve runtime configuration from AWS SSM: {type(e).__name__}: {str(e)}"
        ) from e
    except Exception as e:
        logger.error(
            "Unexpected error during AWS SSM configuration load: %s",
            type(e).__name__,
        )
        raise RuntimeError(
            f"Failed to retrieve runtime configuration from AWS SSM: {type(e).__name__}"
        ) from e

    # Check for invalid parameters reported by SSM
    invalid_params = response.get("InvalidParameters", [])
    if invalid_params:
        logger.error(
            "AWS SSM returned invalid parameter(s): %s",
            ", ".join(invalid_params),
        )
        raise RuntimeError(
            f"AWS SSM returned invalid parameter(s): {', '.join(invalid_params)}"
        )

    # Process returned parameters
    returned_params: Dict[str, str] = {}
    for param in response.get("Parameters", []):
        param_name = param.get("Name")
        param_value = param.get("Value")
        if param_name:
            returned_params[param_name] = param_value or ""

    # Validate all required parameters are present (fail-closed)
    missing_params = [name for name in expected_names if name not in returned_params]
    if missing_params:
        logger.error(
            "AWS SSM response missing required parameter(s): %s",
            ", ".join(missing_params),
        )
        raise RuntimeError(
            f"AWS SSM response missing required parameter(s): {', '.join(missing_params)}"
        )

    # Validate that no parameter value is empty or whitespace-only (fail-closed)
    config_dict: Dict[str, str] = {}
    for name in expected_names:
        val = returned_params[name]
        if not val or not val.strip():
            logger.error("AWS SSM parameter '%s' contains an empty value", name)
            raise RuntimeError(f"AWS SSM parameter '{name}' contains an empty value")

        suffix = name_to_suffix[name]
        settings_key = SUFFIX_TO_SETTINGS_KEY[suffix]
        config_dict[settings_key] = val

    logger.info("Successfully loaded runtime configuration from AWS SSM (%d parameters)", len(config_dict))
    return config_dict
