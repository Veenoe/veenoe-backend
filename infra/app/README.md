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

## Gemini Live token control plane and logs

The backend owns the Gemini model, Live API version, one-use ephemeral-token
policy (15-minute lifetime), AUDIO modality, session resumption, audio
transcription settings, `conclude_viva` declaration, and the response fallback
voice name (`Kore`). The fallback is response metadata when no voice is
requested; the backend does not add a voice constraint to that token, preserving
current client-side voice behavior.
These settings live in `app/services/gemini_service.py`. The browser receives
only the ephemeral token and connects directly to Gemini Live; the permanent
Google API key stays in backend runtime configuration. The tested SDK
dependency is pinned to `google-genai==2.23.0`.

Token issuance writes one attempt event and one success or failure event through
Python logging to Lambda stdout/stderr and the existing `/aws/lambda/<function>`
CloudWatch log group. Events include duration and model/API metadata. They never
include the API key, ephemeral token, student name, topic, prompt, transcript,
audio, or SDK exception message. Find the function log group in CloudWatch Logs;
DEV retention is 14 days and PROD retention is 30 days. No log group, metric,
alarm, dashboard, or IAM permission is added for this behavior. Terraform in
`infra/app` remains the source of truth for persistent AWS configuration, and
deployments continue through GitHub Actions OIDC and Terraform.

## Runtime Configuration & Secrets Architecture (VEENOE-9)

### 1. Separation of Concerns & State Security
- **DEV-Only Prototype Strategy**: Parameter resources are provisioned strictly for DEV (`count = var.environment == "dev" ? 1 : 0`) in `infra/app/secrets.tf`. No PROD parameters are created or managed by Terraform under this prototype mechanism.
- **Harmless Configuration Placeholders**: Terraform configuration files (`secrets.tf`), variables, and commits contain only harmless fixed placeholder strings (`VEENOE_REPLACE_ME`). Real credentials never exist in Git, `.tfvars`, or deployment inputs.
- **Manual Out-of-Band Population**: After initial deployment, the operator manually writes real credential values directly into AWS Systems Manager Parameter Store via the AWS Management Console or AWS CLI.
- **Write-only secret placeholders**: Google and Clerk SecureString resources use Terraform 1.11 `value_wo` and ignore changes to `value_wo` / `value_wo_version`. Operator-populated secret values are not reverted and are not read into state by these write-only attributes.
- **State security**: Existing state history still needs encryption and least-privilege access. PROD secrets are populated separately under `/veenoe/prod` before deploying PROD.
- **Runtime Pointer**: Terraform sets a non-sensitive environment variable pointer on the Lambda function: `VEENOE_SSM_PARAMETER_PREFIX = "/veenoe/${var.environment}"`.

### 2. AWS SSM Parameter Store Parameters
All parameters reside in **AWS Systems Manager Parameter Store** under the **Standard Tier** using the default AWS-managed KMS key (`alias/aws/ssm`):

| Parameter Name | SSM Type | Initial Value | Sensitivity | Destination Field |
| :--- | :--- | :--- | :--- | :--- |
| `/veenoe/dev/google_api_key` | `SecureString` | `VEENOE_REPLACE_ME` | Secret (post-replace) | `GOOGLE_API_KEY` |
| `/veenoe/dev/clerk_secret_key` | `SecureString` | `VEENOE_REPLACE_ME` | Secret (post-replace) | `CLERK_SECRET_KEY` |

*(Note: PROD parameters are not created by Terraform and will be addressed in a future ticket).*

### 3. Local Development vs. AWS Lambda Mode
- **Local Development**: When `VEENOE_SSM_PARAMETER_PREFIX` is absent or unset, the application automatically reads configuration from `.env` or local environment variables via `pydantic-settings`. No AWS API calls are made.
- **AWS Lambda Runtime**: The environment prefix selects the two exact Google and Clerk secret paths, retrieved in one decrypted `ssm:GetParameters` call during cold start. The table name is supplied directly by Terraform as a Lambda environment variable.

### 4. Cold-Start Caching & Secret Rotation
- **Cached in Memory**: Configuration is instantiated once at module import during cold start and held in memory across warm invocations. No SSM calls occur during warm requests.
- **Rotation Requirement**: If an operator updates a parameter in SSM Parameter Store, existing warm Lambda execution environments will retain the previous secret until recycled. To force an immediate rotation, trigger a new deployment or update an environment variable (e.g. via `aws lambda update-function-configuration`).

### 5. IAM Runtime Boundaries
- **Action**: `ssm:GetParameters` only.
- **Resource ARNs**: Constrained strictly to the two exact secret parameter ARNs for the environment. No wildcards (`*`).
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

## DynamoDB sessions (VEENOE-10)

`dynamodb.tf` creates the environment-specific session table and exact-table runtime IAM policy. Terraform passes `DYNAMODB_TABLE_NAME` to Lambda. MongoDB SSM containers are retired from state without deleting operator-owned secrets. The runtime fetches only Google and Clerk secrets. See [the persistence and deployment runbook](../../docs/dynamodb-sessions.md), including bootstrap IAM prerequisites.
