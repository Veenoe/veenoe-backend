"""
Tests for AWS Lambda packaging and FastAPI application health.
Verifies:
1. Application imports and initializes with correct configuration
2. Root endpoint / returns expected healthy response
3. Lambda deployment ZIP exists and satisfies structure, permissions, and platform requirements
4. No sensitive, local, or platform-incompatible files are present in the ZIP
"""

import os
import stat
import zipfile
from pathlib import Path
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_ZIP = REPO_ROOT / "dist" / "veenoe-backend.zip"


def test_application_import_and_metadata():
    """Verify app.main imports cleanly and has expected metadata."""
    from app.main import app

    assert app is not None
    assert app.title == "AI Viva SaaS Backend"
    assert app.version == "1.0.0"


def test_settings_environment_variable_contract():
    """
    Verify that Settings fields exactly match the documented Lambda environment variable contract.
    Confirms MONGO_URI and MONGO_DB_NAME (NOT MONGODB_URI or MONGODB_DB_NAME) are enforced.
    """
    from app.core.config import Settings

    fields = set(Settings.model_fields.keys())
    assert "MONGO_URI" in fields, "Settings must have MONGO_URI"
    assert "MONGO_DB_NAME" in fields, "Settings must have MONGO_DB_NAME"
    assert "GOOGLE_API_KEY" in fields, "Settings must have GOOGLE_API_KEY"
    assert "CLERK_SECRET_KEY" in fields, "Settings must have CLERK_SECRET_KEY"
    assert "FRONTEND_URL" in fields, "Settings must have FRONTEND_URL"
    assert "CORS_ORIGINS" in fields, "Settings must have CORS_ORIGINS"

    assert "MONGODB_URI" not in fields, "MONGODB_URI is not part of Settings contract"
    assert (
        "MONGODB_DB_NAME" not in fields
    ), "MONGODB_DB_NAME is not part of Settings contract"


def test_root_health_endpoint():
    """Verify root endpoint returns 200 OK for Lambda Web Adapter readiness check."""
    from app.main import app

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "message" in data


def test_cors_preflight_production_frontend():
    """Verify CORS preflight returns 200 with Access-Control-Allow-Origin for production frontend."""
    from app.main import app

    client = TestClient(app)
    response = client.options(
        "/api/v1/viva/start",
        headers={
            "Origin": "https://app.veenoe.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.veenoe.com"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_vercel_preview():
    """Verify CORS preflight returns 200 with Access-Control-Allow-Origin for Vercel preview domains."""
    from app.main import app

    client = TestClient(app)
    response = client.options(
        "/api/v1/viva/history",
        headers={
            "Origin": "https://veenoe-web-preview-123.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://veenoe-web-preview-123.vercel.app"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_lambda_zip_exists_and_size_limits():
    """Verify Lambda ZIP artifact exists and is within AWS Lambda size limits."""
    assert (
        DIST_ZIP.exists()
    ), f"Deployment artifact {DIST_ZIP} not found. Run scripts/build_lambda.py first."

    compressed_size = DIST_ZIP.stat().st_size
    # Lambda direct upload limit is 50 MB
    assert (
        compressed_size < 50 * 1024 * 1024
    ), f"ZIP compressed size ({compressed_size} bytes) exceeds 50MB"

    # Lambda uncompressed limit is 250 MB
    with zipfile.ZipFile(DIST_ZIP, "r") as zf:
        uncompressed_size = sum(zinfo.file_size for zinfo in zf.infolist())
        assert (
            uncompressed_size < 250 * 1024 * 1024
        ), f"ZIP uncompressed size ({uncompressed_size} bytes) exceeds 250MB"


def test_lambda_zip_run_script():
    """Verify run.sh is at the ZIP root with executable permissions and LF line endings."""
    with zipfile.ZipFile(DIST_ZIP, "r") as zf:
        names = zf.namelist()
        assert "run.sh" in names, "run.sh is missing from ZIP root"

        run_info = zf.getinfo("run.sh")
        mode = run_info.external_attr >> 16
        # Must have Unix executable bit set (0o755 or 0o100755)
        assert bool(
            mode & stat.S_IXUSR
        ), f"run.sh lacks user execute permission: {stat.filemode(mode)}"

        content = zf.read("run.sh")
        assert b"\r\n" not in content, "run.sh contains Windows CRLF line endings"
        assert b"\n" in content, "run.sh must contain Unix LF line endings"
        assert (
            b"uvicorn app.main:app" in content
        ), "run.sh does not start uvicorn app.main:app"


def test_lambda_zip_application_code_present():
    """Verify application source code modules are present in the ZIP."""
    with zipfile.ZipFile(DIST_ZIP, "r") as zf:
        names = set(zf.namelist())
        assert "app/main.py" in names
        assert "app/core/config.py" in names
        assert "app/core/runtime_config.py" in names
        assert "app/api/api.py" in names
        assert "app/db/database.py" in names


def test_lambda_zip_boto3_present():
    """Verify pinned boto3 and botocore packages are packaged in the ZIP."""
    with zipfile.ZipFile(DIST_ZIP, "r") as zf:
        names = zf.namelist()
        boto3_entries = [n for n in names if n.startswith("boto3/")]
        botocore_entries = [n for n in names if n.startswith("botocore/")]
        assert len(boto3_entries) > 0, "boto3 package not found in ZIP"
        assert len(botocore_entries) > 0, "botocore package not found in ZIP"


def test_lambda_zip_contains_linux_binaries():
    """Verify that compiled extensions inside the ZIP are Linux ELF (.so) and not Windows (.pyd)."""
    with zipfile.ZipFile(DIST_ZIP, "r") as zf:
        names = zf.namelist()
        so_files = [n for n in names if n.endswith(".so")]
        pyd_files = [n for n in names if n.endswith(".pyd")]
        dll_files = [n for n in names if n.endswith(".dll")]

        assert (
            len(pyd_files) == 0
        ), f"Found Windows .pyd binary extensions in ZIP: {pyd_files}"
        assert len(dll_files) == 0, f"Found Windows .dll libraries in ZIP: {dll_files}"
        assert (
            len(so_files) > 0
        ), "No Linux .so binary extensions found; manylinux wheels were not installed"


def test_lambda_zip_excludes_forbidden_files():
    """Verify no secrets, workstation caches, virtualenvs, or git files are included in the ZIP."""
    with zipfile.ZipFile(DIST_ZIP, "r") as zf:
        names = zf.namelist()
        forbidden_substrings = [
            ".env",
            ".git",
            "venv",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            ".terraform",
            ".tfstate",
        ]
        for name in names:
            for pattern in forbidden_substrings:
                assert pattern not in name.split(
                    "/"
                ), f"Forbidden pattern '{pattern}' found in ZIP entry: {name}"
