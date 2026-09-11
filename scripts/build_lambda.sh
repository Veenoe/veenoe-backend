#!/usr/bin/env bash
# ==============================================================================
# build_lambda.sh
# Reproducible packaging script for veenoe-backend on AWS Lambda.
# Invokes scripts/build_lambda.py with python3/python.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# Detect Python 3 command
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Python is not installed or not in PATH." >&2
    exit 1
fi

echo "Running Lambda packaging via ${PYTHON_CMD}..."
"${PYTHON_CMD}" "${SCRIPT_DIR}/build_lambda.py"
