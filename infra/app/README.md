# Veenoe Backend Application Infrastructure (`infra/app`)

This Terraform root module provisions the AWS serverless application runtime for `veenoe-backend` in development (`dev`).

---

## Architecture Overview

```
[Client / Browser]
       │
       ▼ (HTTPS: GET /, GET /health, POST /api/v1/viva/start)
[API Gateway HTTP API] (veenoe-dev-api)
       │
       ▼ (AWS_PROXY payload 2.0)
[AWS Lambda Function] (veenoe-dev-backend)
  ├── Environment: VEENOE_SSM_PARAMETER_PREFIX=/veenoe/dev
  ├── Lambda Web Adapter Layer (LambdaAdapterLayerX86:29)
  │     └─ /opt/bootstrap
  └── Application Container (python3.12, x86_64)
        └─ run.sh
             └─ uvicorn app.main:app --port 8080
                   ├── app.core.runtime_config: Retrieves exact parameters from AWS SSM
                   └── FastAPI Application
```

---

## Runtime Configuration & Secrets Architecture (VEENOE-9)

### 1. Separation of Concerns & State Security
- **Real secrets never enter Terraform**: No secret values exist in `.tf`, `.tfvars`, Terraform state (`.tfstate`), Git, or CI logs.
- **Out-of-Band Population**: Parameters in AWS Systems Manager (SSM) Parameter Store are populated manually by the operator.
- **Terraform Scope**: Terraform provisions only the non-sensitive Lambda pointer (`VEENOE_SSM_PARAMETER_PREFIX = "/veenoe/${var.environment}"`) and the least-privilege IAM policy.

### 2. AWS SSM Parameter Store Parameters
All parameters reside in **AWS Systems Manager Parameter Store** under the **Standard Tier** using the default AWS-managed KMS key (`alias/aws/ssm`):

| Parameter Name | SSM Type | Sensitivity | Destination Field |
| :--- | :--- | :--- | :--- |
| `/veenoe/dev/mongo_uri` | `SecureString` | Secret | `MONGO_URI` |
| `/veenoe/dev/mongo_db_name` | `String` | Non-Secret | `MONGO_DB_NAME` |
| `/veenoe/dev/google_api_key` | `SecureString` | Secret | `GOOGLE_API_KEY` |
| `/veenoe/dev/clerk_secret_key` | `SecureString` | Secret | `CLERK_SECRET_KEY` |

*(Equivalent naming `/veenoe/prod/...` is anticipated in Terraform for production, but PROD parameters are not created or deployed).*

### 3. Local Development vs. AWS Lambda Mode
- **Local Development**: When `VEENOE_SSM_PARAMETER_PREFIX` is absent or unset, the application automatically reads configuration from `.env` or local environment variables via `pydantic-settings`. No AWS API calls are made.
- **AWS Lambda Runtime**: When `VEENOE_SSM_PARAMETER_PREFIX=/veenoe/dev` is present, `app.core.runtime_config` issues a single batched `ssm:GetParameters` call with `WithDecryption=True` for the 4 exact parameter paths during application bootstrap (cold start).

### 4. Cold-Start Caching & Secret Rotation
- **Cached in Memory**: Configuration is instantiated once at module import during cold start and held in memory across warm invocations. No SSM calls occur during warm requests.
- **Rotation Requirement**: If an operator updates a parameter in SSM Parameter Store, existing warm Lambda execution environments will retain the previous secret until recycled. To force an immediate rotation, trigger a new deployment or update an environment variable (e.g. via `aws lambda update-function-configuration`).

### 5. IAM Runtime Boundaries
- **Action**: `ssm:GetParameters` only.
- **Resource ARNs**: Constrained strictly to the four exact parameter ARNs for the environment. No wildcards (`*`).
- **No KMS Policy**: Per AWS SSM guidance, the default AWS-managed `alias/aws/ssm` key decryption is granted implicitly via account membership and SSM parameter read access. No custom KMS key policy or `kms:Decrypt` statements are added.
- **Cross-Environment Isolation**: The `dev` runtime role cannot access `/veenoe/prod/...` parameters, and vice versa.

---

## State & Locking

- **S3 Remote State Bucket**: `veenoe-terraform-state-165835313361` (created by VEENOE-5 bootstrap)
- **State Key**: `backend/dev/terraform.tfstate`
- **Locking**: Native S3 lockfile (`use_lockfile = true`)
- **Backend Configuration**: Partial backend in `backend.tf`, initialized via `dev.backend.hcl`

---

## Commands

### 1. Build the Lambda Package
```bash
python scripts/build_lambda.py
```

### 2. Initialize Terraform
```bash
terraform -chdir=infra/app init -backend-config=dev.backend.hcl
```

### 3. Plan Deployment
```bash
terraform -chdir=infra/app plan -var-file=dev.tfvars -out=dev.tfplan
```

### 4. Apply (Only after approval)
```bash
terraform -chdir=infra/app apply dev.tfplan
```

---

## Rollback Plan

To completely tear down the DEV application stack without touching the bootstrap infrastructure (state bucket, OIDC provider, IAM deployment roles):
```bash
terraform -chdir=infra/app destroy -var-file=dev.tfvars
```
Never destroy `infra/bootstrap` during an application rollback.
