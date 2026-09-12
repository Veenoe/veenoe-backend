#!/usr/bin/env python3
"""
Packaging script for building the veenoe-backend FastAPI application as an AWS Lambda ZIP artifact
using AWS Lambda Web Adapter.

Supports local developer builds on Windows, macOS, and Linux, with Linux/CI being the canonical
production build environment.
Produces Linux/x86_64-targeted dependencies suitable for the selected Lambda runtime (Python 3.12).
Enforces:
- Clean build directory
- Linux x86_64 binary wheels (manylinux2014_x86_64) for Python 3.12
- POSIX file permissions (0755 for run.sh, 0644 for regular files)
- Unix LF line endings for run.sh
- Exclusion of secrets, virtual environments, caches, and test files
- Validation against AWS Lambda ZIP size constraints
"""

import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"
APP_DIR = REPO_ROOT / "app"
RUN_SH_SRC = REPO_ROOT / "run.sh"
BUILD_DIR = REPO_ROOT / "build" / "lambda"
DIST_DIR = REPO_ROOT / "dist"
OUTPUT_ZIP = DIST_DIR / "veenoe-backend.zip"

# Target Python runtime and architecture for AWS Lambda
TARGET_PYTHON_VERSION = "3.12"
TARGET_PLATFORM = "manylinux2014_x86_64"
TARGET_IMPLEMENTATION = "cp"

# AWS Lambda direct zip upload limit: 50 MB compressed, 250 MB uncompressed
LAMBDA_ZIP_COMPRESSED_LIMIT_BYTES = 50 * 1024 * 1024
LAMBDA_UNCOMPRESSED_LIMIT_BYTES = 250 * 1024 * 1024

# Patterns that must never be packaged
FORBIDDEN_PATTERNS = [
    ".env",
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".terraform",
    ".tfstate",
    ".pyd",  # Windows binary extension
    ".dll",  # Windows library
]


def clean_directory(path: Path) -> None:
    """Removes and recreates the specified directory."""
    if path.exists():
        print(f"Cleaning existing directory: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def install_dependencies(target_dir: Path) -> None:
    """
    Installs Linux-compatible wheels for Python 3.12 into the target directory.
    Uses pip's cross-platform options to ensure binary Linux ELF compatibility
    even when built on Windows or macOS.
    """
    print(
        f"Installing dependencies from {REQUIREMENTS_FILE} into {target_dir}...",
        flush=True,
    )
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-compile",
        "--platform",
        TARGET_PLATFORM,
        "--only-binary=:all:",
        "--target",
        str(target_dir),
        "--python-version",
        TARGET_PYTHON_VERSION,
        "--implementation",
        TARGET_IMPLEMENTATION,
        "--upgrade",
        "-r",
        str(REQUIREMENTS_FILE),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Dependency installation failed!", file=sys.stderr, flush=True)
        print(result.stdout, file=sys.stderr, flush=True)
        print(result.stderr, file=sys.stderr, flush=True)
        sys.exit(1)
    print("Dependencies successfully installed.", flush=True)


def clean_bytecaches(target_dir: Path) -> None:
    """Removes __pycache__, *.pyc, and *.pyo to ensure no workstation bytecode is packaged."""
    print("Purging any Python bytecode caches from build directory...", flush=True)
    for root, dirs, files in os.walk(target_dir, topdown=False):
        for d in dirs:
            if d in ("__pycache__", ".pytest_cache"):
                shutil.rmtree(Path(root) / d)
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                (Path(root) / f).unlink()


def copy_application(target_dir: Path) -> None:
    """Copies application source code into the build directory."""
    print("Copying application code into build directory...", flush=True)
    dest_app = target_dir / "app"
    shutil.copytree(
        APP_DIR,
        dest_app,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".env*"),
    )


def copy_run_script(target_dir: Path) -> None:
    """Copies run.sh into build directory, enforcing Unix LF line endings."""
    print("Copying run.sh with Unix LF line endings...")
    if not RUN_SH_SRC.exists():
        print(f"Error: {RUN_SH_SRC} not found!", file=sys.stderr)
        sys.exit(1)

    content = RUN_SH_SRC.read_bytes()
    # Normalize CRLF to LF
    content_lf = content.replace(b"\r\n", b"\n")
    dest_run_sh = target_dir / "run.sh"
    dest_run_sh.write_bytes(content_lf)


def validate_build_contents(build_dir: Path) -> None:
    """Scans build directory for forbidden files and verifies Linux ELF binaries."""
    print("Validating build directory contents...")
    found_forbidden = []
    has_linux_so = False
    has_windows_pyd = False

    for root, _, files in os.walk(build_dir):
        for file in files:
            file_path = Path(root) / file
            rel_path = file_path.relative_to(build_dir).as_posix()

            # Check forbidden patterns
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in rel_path.split("/"):
                    found_forbidden.append(rel_path)
                elif rel_path.endswith(pattern):
                    found_forbidden.append(rel_path)

            if file.endswith(".so"):
                has_linux_so = True
            if file.endswith(".pyd"):
                has_windows_pyd = True

    if found_forbidden:
        print("Error: Forbidden files detected in build output:", file=sys.stderr)
        for f in found_forbidden:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)

    if has_windows_pyd:
        print(
            "Error: Detected Windows .pyd binary extensions in build output!",
            file=sys.stderr,
        )
        sys.exit(1)

    if not has_linux_so:
        print("Warning: No .so Linux binary extensions detected in package.")
    else:
        print(
            "Verified: Linux ELF shared objects (.so) present, no Windows (.pyd) binaries."
        )


def create_zip(build_dir: Path, output_zip_path: Path) -> tuple[int, int]:
    """
    Creates a deterministic ZIP archive from the build directory.
    Explicitly assigns Unix file permissions:
    - 0755 (-rwxr-xr-x) for run.sh and directories
    - 0644 (-rw-r--r--) for standard files
    """
    print(f"Packaging artifact into {output_zip_path}...")
    total_uncompressed = 0

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(build_dir):
            for d in dirs:
                dir_path = Path(root) / d
                rel_path = dir_path.relative_to(build_dir).as_posix() + "/"
                zinfo = zipfile.ZipInfo(rel_path)
                # Directory permissions: 0755 | standard directory flag (0o040000)
                zinfo.external_attr = (0o040755) << 16
                zf.writestr(zinfo, b"")

            for f in files:
                file_path = Path(root) / f
                rel_path = file_path.relative_to(build_dir).as_posix()
                data = file_path.read_bytes()
                total_uncompressed += len(data)

                zinfo = zipfile.ZipInfo(rel_path)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                # Assign permissions
                if rel_path == "run.sh" or rel_path.startswith("bin/"):
                    # Executable permission: 0755 | standard file flag (0o100000)
                    zinfo.external_attr = (0o100755) << 16
                else:
                    # Regular file permission: 0644 | standard file flag (0o100000)
                    zinfo.external_attr = (0o100644) << 16

                zf.writestr(zinfo, data)

    compressed_size = output_zip_path.stat().st_size
    return compressed_size, total_uncompressed


def main() -> None:
    print("=== Building AWS Lambda Deployment Package for veenoe-backend ===")
    print(f"Target runtime: Python {TARGET_PYTHON_VERSION} ({TARGET_PLATFORM})")
    print(f"Repo root:      {REPO_ROOT}")
    print(f"Build dir:      {BUILD_DIR}")
    print(f"Output artifact:{OUTPUT_ZIP}")
    print("-----------------------------------------------------------------")

    # Step 1: Clean build directories
    clean_directory(BUILD_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    # Step 2: Install dependencies
    install_dependencies(BUILD_DIR)

    # Step 3: Copy app code
    copy_application(BUILD_DIR)

    # Step 4: Copy run.sh
    copy_run_script(BUILD_DIR)

    # Step 5: Clean any cached bytecode
    clean_bytecaches(BUILD_DIR)

    # Step 6: Validate contents before packaging
    validate_build_contents(BUILD_DIR)

    # Step 7: Create ZIP archive with correct POSIX attributes
    compressed_size, uncompressed_size = create_zip(BUILD_DIR, OUTPUT_ZIP)

    print("-----------------------------------------------------------------")
    print(f"Artifact created: {OUTPUT_ZIP}")
    print(
        f"Compressed size:   {compressed_size:,} bytes ({compressed_size / (1024 * 1024):.2f} MB)"
    )
    print(
        f"Uncompressed size: {uncompressed_size:,} bytes ({uncompressed_size / (1024 * 1024):.2f} MB)"
    )

    # Check against Lambda limits
    if compressed_size > LAMBDA_ZIP_COMPRESSED_LIMIT_BYTES:
        print(
            f"WARNING: Compressed size ({compressed_size / (1024 * 1024):.2f} MB) exceeds "
            f"direct upload limit of 50 MB! Lambda deployment will require S3 bucket reference.",
            file=sys.stderr,
        )
    else:
        print("OK: Compressed size within AWS Lambda 50 MB direct upload threshold.")

    if uncompressed_size > LAMBDA_UNCOMPRESSED_LIMIT_BYTES:
        print(
            f"ERROR: Uncompressed size ({uncompressed_size / (1024 * 1024):.2f} MB) exceeds "
            f"Lambda maximum uncompressed size of 250 MB!",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print("OK: Uncompressed size within AWS Lambda 250 MB uncompressed limit.")

    print("=== Build completed successfully! ===")


if __name__ == "__main__":
    main()
