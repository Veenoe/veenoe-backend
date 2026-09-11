#!/bin/bash
set -e

# Ensure Lambda task root and installed binaries/modules are in PATH and PYTHONPATH
export PATH="${LAMBDA_TASK_ROOT:-/var/task}/bin:$PATH"
export PYTHONPATH="${LAMBDA_TASK_ROOT:-/var/task}:$PYTHONPATH"

# Run uvicorn on the port expected by AWS Lambda Web Adapter (default: 8080)
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
