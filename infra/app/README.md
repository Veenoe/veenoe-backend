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
- **DEV-Only Prototype Strategy**: Parameter resources are provisioned strictly for DEV (`count = var.environment == "dev" ? 1 : 0`) in `infra/app/secrets.tf`. No PROD parameters are created or managed by Terraform under this prototype mechanism.
- **Harmless Configuration Placeholders**: Terraform configuration files (`secrets.tf`), variables, and commits contain only harmless fixed placeholder strings (`VEENOE_REPLACE_ME`). Real credentials never exist in Git, `.tfvars`, or deployment inputs.
- **Manual Out-of-Band Population**: After initial deployment, the operator manually writes real credential values directly into AWS Systems Manager Parameter Store via the AWS Management Console or AWS CLI.
- **Drift Protection via `ignore_changes`**: Each `aws_ssm_parameter` resource declares `lifecycle { ignore_changes = [value] }`. This prevents Terraform from planning to overwrite or revert externally updated parameter values during subsequent runs.
- **Terraform State Exposure Caveat**: Declaring `lifecycle { ignore_changes = [value] }` prevents Terraform from planning to overwrite an externally changed value, but it does **NOT** guarantee that real secret values can never appear in remote Terraform state. Terraform refresh operations observe remote resource attributes, meaning real parameter values may become represented in remote Terraform state (`.tfstate`) after subsequent Terraform operations.
- **S3 State Backend Sensitivity**: Because remote state may capture refreshed parameter attributes, the S3 remote state bucket (`veenoe-terraform-state-165835313361`) and state files must be treated as sensitive, protected by strict least-privilege IAM policies, encryption at rest, and access auditing.
- **Production Migration Path**: Before production release, this prototype strategy must be migrated to a state-safe approach—such as Terraform 1.11+ write-only attribute support (`value_wo`) or dedicated out-of-band secret management—after separately validating Terraform CLI and AWS provider compatibility.
- **Runtime Pointer**: Terraform sets a non-sensitive environment variable pointer on the Lambda function: `VEENOE_SSM_PARAMETER_PREFIX = "/veenoe/${var.environment}"`.

### 2. AWS SSM Parameter Store Parameters
All parameters reside in **AWS Systems Manager Parameter Store** under the **Standard Tier** using the default AWS-managed KMS key (`alias/aws/ssm`):

| Parameter Name | SSM Type | Initial Value | Sensitivity | Destination Field |
| :--- | :--- | :--- | :--- | :--- |
| `/veenoe/dev/mongo_uri` | `SecureString` | `VEENOE_REPLACE_ME` | Secret (post-replace) | `MONGO_URI` |
| `/veenoe/dev/mongo_db_name` | `String` | `VEENOE_REPLACE_ME` | Non-Secret | `MONGO_DB_NAME` |
| `/veenoe/dev/google_api_key` | `SecureString` | `VEENOE_REPLACE_ME` | Secret (post-replace) | `GOOGLE_API_KEY` |
| `/veenoe/dev/clerk_secret_key` | `SecureString` | `VEENOE_REPLACE_ME` | Secret (post-replace) | `CLERK_SECRET_KEY` |

*(Note: PROD parameters are not created by Terraform and will be addressed in a future ticket).*

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

## Workflow & Deployment Model

### 1. Local / Operator Inspection Flow (Plan Only)
Local execution is strictly for verification, artifact generation, and plan inspection:

1. **Build the Lambda Package**:
   ```bash
   python scripts/build_lambda.py
   ```
2. **Initialize Terraform**:
   ```bash
   terraform -chdir=infra/app init -backend-config=dev.backend.hcl
   ```
3. **Generate & Inspect Plan**:
   ```bash
   terraform -chdir=infra/app plan -var-file=dev.tfvars -out=dev.tfplan
   ```
4. **STOP**:
   > [!WARNING]
   > **Do not use local `terraform apply` for `infra/app` as a normal deployment path.**
   > All application runtime deployments must execute exclusively through the GitHub Actions CI/CD pipeline using OIDC and temporary credentials.

---

### 2. CI/CD Deployment Flow
Application deployments to `dev` are manual-only and executed via GitHub Actions:

1. Trigger the **Deploy Development** (`deploy-dev.yml`) workflow manually (`workflow_dispatch`).
   *(Do not reintroduce automatic deployment triggers on push or PR).*
2. The pipeline builds and verifies the Lambda package, running the full test suite.
3. GitHub Actions authenticates to AWS using **GitHub OIDC** assuming `veenoe-github-actions-dev-deploy` (no long-lived credentials).
4. Terraform initializes the remote backend and generates a saved execution plan (`dev.tfplan`).
5. A destructive-change safety guard verifies that 0 deletions or replacements exist in the plan.
6. GitHub Actions applies the exact saved plan.
7. Automated post-deploy smoke tests verify:
   - Root liveness: `GET /` $\rightarrow$ 200 (healthy)
   - Database connectivity: `GET /health` $\rightarrow$ 200 (connected)
   - Auth rejection: `POST /api/v1/viva/start` without Authorization $\rightarrow$ 401
   - Route boundary: `GET /api/v1/viva/start` $\rightarrow$ 404
8. A post-apply zero-diff plan check ensures remote state perfectly matches configuration.

*(Note: `infra/bootstrap` infrastructure remains manually managed out-of-band by the operator).*

---

## Rollback Plan

To completely tear down the DEV application stack without touching the bootstrap infrastructure (state bucket, OIDC provider, IAM deployment roles):
```bash
terraform -chdir=infra/app destroy -var-file=dev.tfvars
```
Never destroy `infra/bootstrap` during an application rollback.
