# Veenoe Terraform Bootstrap & GitHub Actions OIDC

This module provisions the foundational AWS infrastructure required for managing Veenoe via Terraform and deploying via GitHub Actions with short-lived OIDC credentials.

## Overview

This bootstrap stack owns:
1. **S3 Remote State Bucket**: Durable, encrypted, versioned storage for Terraform state with native S3 state locking (`use_lockfile = true`).
2. **GitHub OIDC Identity Provider**: An account-level OpenID Connect provider for `https://token.actions.githubusercontent.com`.
3. **Deployment Roles**: Dedicated IAM roles for development and production deployments with strict trust conditions matching the `Veenoe/veenoe-backend` repository and respective GitHub environments.
4. **Scoped Deployment Policies**: Least-privilege permissions preventing unrestricted account access and separating state paths between environments.

---

## State & Environment Layout

A single state bucket is used with isolated prefixes:

```
s3://<state-bucket-name>/
├── bootstrap/terraform.tfstate          # State for this bootstrap module
├── backend/dev/terraform.tfstate        # State for the dev application stack (infra/app)
└── backend/prod/terraform.tfstate       # State for the prod application stack (infra/app)
```

### Native S3 State Locking
This architecture uses HashiCorp's S3 native locking (`use_lockfile = true`) introduced in Terraform 1.10. It stores `.tflock` files directly in S3 alongside the state files and does **not** use a DynamoDB lock table (which HashiCorp has deprecated).

---

## Step-by-Step Bootstrap Runbook

### Step 1: Initial Local State Provisioning
The S3 backend cannot be used before the bucket exists. Run initial creation with local state:

```bash
cd infra/bootstrap

# 1. Initialize Terraform plugins without remote backend
terraform init -backend=false

# 2. Review the execution plan
terraform plan -out=tfplan

# 3. Apply to create the S3 bucket, OIDC provider, and IAM roles
terraform apply tfplan
```

### Step 2: Migrate State to S3
Once the S3 bucket is created, migrate the local state file into the remote S3 bucket:

```bash
# 1. Extract the created bucket name
STATE_BUCKET=$(terraform output -raw state_bucket_name)
AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-south-1")

# 2. Run terraform init with migration flag and backend configuration
terraform init -migrate-state \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="key=bootstrap/terraform.tfstate" \
  -backend-config="region=${AWS_REGION}"

# 3. Type 'yes' when prompted to copy existing state to the new backend.

# 4. Verify the remote state exists in S3
aws s3 ls "s3://${STATE_BUCKET}/bootstrap/terraform.tfstate"

# 5. Clean up the local state file (now safe to delete)
rm -f terraform.tfstate terraform.tfstate.backup tfplan
```

---

## GitHub Actions CI/CD Configuration

Workflows authenticate to AWS using short-lived credentials via `aws-actions/configure-aws-credentials@v4` with zero permanent access keys stored in GitHub Secrets.

### Required Permissions
The GitHub workflow job **must** specify:
```yaml
permissions:
  id-token: write   # Required for requesting the JWT
  contents: read    # Required for actions/checkout
```

### Example Development Deployment Step
```yaml
jobs:
  deploy-dev:
    runs-on: ubuntu-latest
    environment: development
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/veenoe-github-actions-dev-deploy
          aws-region: ap-south-1
          audience: sts.amazonaws.com

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.13.4

      - name: Terraform Init Dev
        working-directory: infra/app
        run: |
          terraform init \
            -backend-config="bucket=veenoe-terraform-state-<ACCOUNT_ID>" \
            -backend-config="key=backend/dev/terraform.tfstate" \
            -backend-config="region=ap-south-1"
```

### Example Production Deployment Step
```yaml
jobs:
  deploy-prod:
    runs-on: ubuntu-latest
    environment: Production
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/veenoe-github-actions-prod-deploy
          aws-region: ap-south-1
          audience: sts.amazonaws.com

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.13.4

      - name: Terraform Init Prod
        working-directory: infra/app
        run: |
          terraform init \
            -backend-config="bucket=veenoe-terraform-state-<ACCOUNT_ID>" \
            -backend-config="key=backend/prod/terraform.tfstate" \
            -backend-config="region=ap-south-1"
```

---

## Security & Verification Tests

### Positive Test: Verify Role Assumption from Intended Context
Within a workflow running in GitHub Actions under the `development` environment:
```bash
# Verify the assumed identity
aws sts get-caller-identity
```
**Expected Output:**
```json
{
  "UserId": "AROA...:bot",
  "Account": "<ACCOUNT_ID>",
  "Arn": "arn:aws:sts::<ACCOUNT_ID>:assumed-role/veenoe-github-actions-dev-deploy/..."
}
```

### Negative Test: Verify Cross-Repository or Unauthorized Environment Denial
Attempting to assume the role outside the designated repository or environment will result in an STS authorization failure:
```bash
# Attempting to assume prod role from a branch without the production environment
aws sts assume-role-with-web-identity \
  --role-arn arn:aws:iam::<ACCOUNT_ID>:role/veenoe-github-actions-prod-deploy \
  --role-session-name test-session \
  --web-identity-token "<UNTRUSTED_OIDC_TOKEN>"
```
**Expected Outcome:**
`An error occurred (AccessDenied) when calling the AssumeRoleWithWebIdentity operation: Not authorized to perform sts:AssumeRoleWithWebIdentity` because the `token.actions.githubusercontent.com:sub` claim does not match `repo:Veenoe/veenoe-backend:environment:Production`.

---

## Disaster Recovery & Troubleshooting

### State Lock Stuck
If a pipeline job crashes while holding the S3 lock, HashiCorp's S3 native locking mechanism stores the lock at:
`s3://<state-bucket-name>/<state-key>.tflock`

To inspect or force-unlock:
```bash
# Using standard Terraform force-unlock (recommended):
terraform force-unlock <LOCK_ID>

# Manual inspection (if needed):
aws s3 ls s3://<state-bucket-name>/backend/dev/
```

### State Recovery via S3 Versioning
If a bad state is written, object versioning is enabled on the S3 bucket:
```bash
# List state versions
aws s3api list-object-versions \
  --bucket "<state-bucket-name>" \
  --prefix "backend/dev/terraform.tfstate"

# Restore a prior version if necessary
aws s3api get-object \
  --bucket "<state-bucket-name>" \
  --key "backend/dev/terraform.tfstate" \
  --version-id "<VERSION_ID>" \
  restored-state.json
```
