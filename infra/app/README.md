# Veenoe Backend Application Infrastructure (`infra/app`)

This Terraform root module provisions the AWS serverless application runtime for `veenoe-backend` in development (`dev`).

---

## Architecture Overview

```
[Client / Browser]
       │
       ▼ (HTTPS GET /)
[API Gateway HTTP API] (veenoe-dev-api)
       │
       ▼ (AWS_PROXY payload 2.0)
[AWS Lambda Function] (veenoe-dev-backend)
  ├── Lambda Web Adapter Layer (LambdaAdapterLayerX86:29)
  │     └─ /opt/bootstrap
  └── Application Container (python3.12, x86_64)
        └─ run.sh
             └─ uvicorn app.main:app --port 8080
                   └─ FastAPI (GET / -> 200 OK)
```

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
