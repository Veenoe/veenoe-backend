"""Exercise the actual Actions deletion filter without contacting AWS."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "address,name,actions,blocked",
    [
        ("aws_ssm_parameter.mongo_uri[0]", "/veenoe/dev/mongo_uri", ["delete"], False),
        (
            "aws_ssm_parameter.mongo_db_name[0]",
            "/veenoe/dev/mongo_db_name",
            ["delete"],
            False,
        ),
        (
            "aws_ssm_parameter.mongo_uri[0]",
            "/veenoe/dev/mongo_uri",
            ["delete", "create"],
            True,
        ),
        (
            "aws_ssm_parameter.mongo_uri[0]",
            "/veenoe/dev/mongo_uri",
            ["create", "delete"],
            True,
        ),
        ("aws_ssm_parameter.mongo_uri[0]", "/veenoe/prod/mongo_uri", ["delete"], True),
        (
            "aws_ssm_parameter.mongo_uri[0]",
            "/veenoe/dev/google_api_key",
            ["delete"],
            True,
        ),
        ("aws_dynamodb_table.sessions", "veenoe-dev-sessions", ["delete"], True),
        ("aws_lambda_function.backend", "veenoe-dev-backend", ["update"], False),
    ],
)
def test_dev_deletion_allowlist(address, name, actions, blocked):
    jq = shutil.which("jq")
    if not jq:
        pytest.skip("jq is required; it is installed on the GitHub Actions runner")
    workflow = (
        Path(__file__).resolve().parents[1] / ".github/workflows/deploy-dev.yml"
    ).read_text()
    match = re.search(r"BLOCKED_DELETIONS=.*?jq -c '(.*?)'\)", workflow, re.DOTALL)
    assert match, "Test must exercise the workflow's actual deletion filter"
    changes = [
        {"address": address, "change": {"actions": actions, "before": {"name": name}}}
    ]
    result = subprocess.run(
        [jq, "-c", match.group(1)],
        input=json.dumps(changes),
        capture_output=True,
        text=True,
        check=True,
    )
    assert bool(json.loads(result.stdout)) is blocked
