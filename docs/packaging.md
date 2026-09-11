# AWS Lambda Packaging Guide (VEENOE-6)

This document describes how the `veenoe-backend` FastAPI application is packaged for deployment to AWS Lambda using the AWS Lambda Web Adapter (LWA), the runtime contract, and the configuration expected by VEENOE-7.

---

## 1. Overview & Architectural Decisions

- **Runtime Model**: AWS Lambda managed runtime (`python3.12`) + ZIP deployment package + AWS Lambda Web Adapter layer (`LambdaAdapterLayerX86`).
- **No Docker / No ECR**: Packaging produces a ZIP archive consumable directly by Terraform (`aws_lambda_function`).
- **Zero Code Modification**: The FastAPI application is unmodified and runs with `uvicorn` inside Lambda. Invocations from API Gateway / ALB / Function URLs are translated to HTTP by the Lambda Web Adapter extension.
- **Dependency Platform Targeting**: Several dependencies (`pydantic-core`, `pymongo`, `httptools`, `watchfiles`, `cryptography`, `cffi`, `websockets`) contain native compiled extensions. The packaging script resolves and downloads official `manylinux2014_x86_64` wheels for Python 3.12, producing Linux/x86_64-targeted dependencies suitable for the selected Lambda runtime. Actual runtime compatibility will be proven in the cloud during VEENOE-7.
- **Canonical Production Build Environment**: **Linux is the canonical production build environment** because GitHub Actions CI/CD will eventually build the authoritative deployment artifact on Linux runners. The cross-platform Python build script remains available for local developer convenience on Windows and macOS, but CI/Linux produces the authoritative release artifact.
- **Reproducible vs. Deterministic Packaging**: Because `requirements.txt` currently specifies version floors (e.g. `>=0.115.0`) rather than fully locked dependency hashes, this provides a **consistent and reproducible packaging process** rather than a strictly byte-deterministic build. Dependency-management lockfiles are intentionally not introduced in this ticket.

---

## 2. Selected Runtime & Architecture

- **AWS Lambda Runtime**: `python3.12`
  - Long-term support (scheduled deprecation: October 31, 2028).
  - Built on Amazon Linux 2023.
  - Fully compatible with all current application dependencies (`pydantic` v2, `beanie` 1.30, `motor` 3.6+, `google-genai` 1.0+, `fastapi` 0.115+).
- **Target Architecture**: `x86_64`

---

## 3. How to Build the Lambda ZIP

### From Canonical Production Environment (Linux / CI / WSL)
```bash
./scripts/build_lambda.sh
```

### From Windows / Local Developer Environment (PowerShell / Command Prompt)
```powershell
python scripts/build_lambda.py
```

### Packaging Process:
1. Cleans the build directory (`build/lambda`) and ensures `dist/` exists.
2. Installs Python dependencies directly from `requirements.txt` using:
   ```bash
   pip install --no-compile --platform manylinux2014_x86_64 --only-binary=:all: --target build/lambda --python-version 3.12 --implementation cp --upgrade -r requirements.txt
   ```
3. Copies application code (`app/`) into the package directory, omitting local caches (`__pycache__`, `.pyc`) and environment files.
4. Copies the startup script (`run.sh`) to the root of the package, strictly enforcing Unix LF line endings (`\n`).
5. Purges any lingering Python bytecode caches from dependency extraction.
6. Validates that no forbidden files (`.env*`, `.git`, `.venv`, `*.pyd`, `*.dll`, `.tfstate`) exist and verifies Linux ELF `.so` libraries are present.
7. Assembles the final deployment artifact with explicit POSIX permissions:
   - `0o755` (`-rwxr-xr-x`) for `run.sh` and directories.
   - `0o644` (`-rw-r--r--`) for regular files.
8. Outputs the package to:
   ```
   dist/veenoe-backend.zip
   ```
9. Verifies the artifact size against AWS Lambda constraints:
   - Compressed size: ~15.2 MB (well under the 50 MB direct upload threshold).
   - Uncompressed size: ~52.5 MB (well under the 250 MB Lambda limit).

---

## 4. Lambda Web Adapter Startup & Readiness Contract

### Startup Flow
When AWS Lambda initializes the function:
1. Lambda loads the Lambda Web Adapter layer.
2. Lambda executes `/opt/bootstrap` (configured via `AWS_LAMBDA_EXEC_WRAPPER`).
3. `/opt/bootstrap` invokes the handler script `run.sh`.
4. `run.sh` executes:
   ```bash
   #!/bin/bash
   set -e
   export PATH="${LAMBDA_TASK_ROOT:-/var/task}/bin:$PATH"
   export PYTHONPATH="${LAMBDA_TASK_ROOT:-/var/task}:$PYTHONPATH"
   exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
   ```
5. Incoming invocations from API Gateway / Function URL are reverse-proxied to Uvicorn at `http://127.0.0.1:8080`.

### Readiness Check Path
- AWS Lambda Web Adapter defaults to polling `GET /` (`AWS_LWA_READINESS_CHECK_PATH=/`) every 10ms until a response between status 100–499 is received.
- **The existing root endpoint in `app/main.py` is intentionally sufficient**:
  ```python
  @app.get("/")
  async def root():
      return {
          "message": "AI Viva SaaS Backend is running",
          "version": "1.0.0",
          "status": "healthy",
      }
  ```
  This endpoint returns HTTP 200 immediately without requiring MongoDB connectivity, Gemini API calls, or external network reachability.
- This design is optimal for Lambda Web Adapter readiness because it signals that the Uvicorn web server is ready to accept traffic without gating cold-start initialization on database latency or risking cold-start timeouts. No unnecessary application endpoints are added.

---

## 5. Required Runtime Configuration for VEENOE-7

In the upcoming VEENOE-7 Terraform ticket, the `aws_lambda_function` resource will need the following configuration:

### Function Settings
- **Handler**: `run.sh`
- **Runtime**: `python3.12`
- **Architectures**: `["x86_64"]`
- **Layers**:
  - AWS Lambda Web Adapter layer for `x86_64` (commercial regions):
    `arn:aws:lambda:${AWS_REGION}:753240598075:layer:LambdaAdapterLayerX86:28`

### Environment Variables (Exact Application Contract)
Verified against the `Settings` model in `app/core/config.py`:

| Variable Name | Required | Purpose | Source / Notes |
|---|---|---|---|
| `AWS_LAMBDA_EXEC_WRAPPER` | Yes | Instructs Lambda to run LWA bootstrap | Fixed value: `/opt/bootstrap` |
| `PORT` | Optional | Port Uvicorn listens on | Defaults to `8080` (matches LWA default) |
| `MONGO_URI` | **Yes** | MongoDB connection string | Verified: application uses `MONGO_URI`, **not** `MONGODB_URI` |
| `MONGO_DB_NAME` | **Yes** | MongoDB database name | Verified: application uses `MONGO_DB_NAME`, **not** `MONGODB_DB_NAME` |
| `GOOGLE_API_KEY` | **Yes** | Google AI Studio / Gemini API Key | Required by `Settings` |
| `CLERK_SECRET_KEY` | **Yes** | Clerk authentication backend key | Required by `Settings` |
| `FRONTEND_URL` | No | Production frontend origin for CORS | Optional (`default=None`) |
| `CORS_ORIGINS` | No | Additional CORS origins (comma-separated) | Optional (`default=""`) |

> [!IMPORTANT]
> `app/core/config.py` instantiates `settings = Settings()` at top-level module import time. The four required variables (`MONGO_URI`, `MONGO_DB_NAME`, `GOOGLE_API_KEY`, `CLERK_SECRET_KEY`) must be configured on the Lambda function to prevent a Pydantic `ValidationError` during cold start.

---

## 6. Intentionally Deferred Items (Out of Scope for VEENOE-6)

The following items are explicitly deferred to subsequent tickets:
- **VEENOE-7**: Terraform provisioning of `aws_lambda_function`, API Gateway / Function URL, CloudWatch log groups, and attaching the Lambda Web Adapter layer.
- **Secret Management**: Injecting sensitive secrets from AWS Secrets Manager / Parameter Store into runtime environment variables.
- **CI/CD**: Configuring permanent GitHub Actions deployment workflows using the OIDC role established in VEENOE-5.
- **Database & Auth Migration**: MongoDB Atlas network access / VPC peering and Clerk production webhook wiring.
