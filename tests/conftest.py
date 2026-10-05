"""
Pytest configuration and fixtures for veenoe-backend.
Sets dummy environment variables for required settings so application
can be imported and initialized cleanly in test environments.
Ensures repository root is in sys.path.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set test environment variables immediately so module-level Settings() initialization succeeds
os.environ.setdefault("DYNAMODB_TABLE_NAME", "veenoe-test-sessions")
os.environ.setdefault("GOOGLE_API_KEY", "test_google_api_key")
os.environ.setdefault("CLERK_SECRET_KEY", "sk_test_mock_clerk_secret_key")
