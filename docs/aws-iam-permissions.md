# AWS IAM Permissions & Security Boundaries

Terraform IAM definitions are authoritative. This document is an operator-readable summary and must be updated whenever Terraform IAM policies or trust relationships change.

---

## 1. Architectural Ownership & Security Boundary

The Veenoe AWS infrastructure enforces a strict privilege separation between repository management roots:

```
┌─────────────────────────────────────────────────────────────┐
│                      infra/bootstrap                         │
│  (Managed by Account Operator via bootstrap state/profile)  │
└──────────────────────────────┬──────────────────────────────┘
                               │ provisions
                               ▼
┌─────────────────────────────────────────────────────────────┐
│          GitHub Actions OIDC Deployment Identity            │
│       Role: veenoe-github-actions-dev-deploy                │
│       Role: veenoe-github-actions-prod-deploy               │
└──────────────────────────────┬──────────────────────────────┘
                               │ manages (via CI/CD only)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         infra/app                           │
│  - Backend Lambda Function                                  │
│  - API Gateway HTTP API & Routes                            │
│  - Runtime IAM Role (veenoe-dev-lambda-runtime)             │
│  - DEV SSM Parameter Store Resources                        │
└─────────────────────────────────────────────────────────────┘
```

### Boundary Rules
- **`infra/bootstrap`**:
  - Owns the S3 remote state bucket, GitHub Actions OIDC identity provider, GitHub Actions deployment roles, and all deployment-role IAM policies/trust configurations.
  - Changes to deployment roles or trust policies require direct operator authorization in `infra/bootstrap`.
- **`infra/app`**:
  - Owns the application runtime Lambda, API Gateway HTTP API, CloudWatch log groups, Lambda runtime execution role/policy, and environment SSM Parameter Store resources.
- **Least-Privilege Invariant**:
  - The GitHub Actions OIDC deploy role manages application infrastructure in `infra/app`.
  - The deploy role **must not** have permission to modify its own bootstrap IAM policies, trust relationships, or state bucket policies.

---

## 2. GitHub Actions OIDC Identity Provider

Configured in [`infra/bootstrap/main.tf`](file:///d:/Veenoe/veenoe-backend/infra/bootstrap/main.tf):

- **Issuer URL**: `https://token.actions.githubusercontent.com`
- **Audience (Client IDs)**: `["sts.amazonaws.com"]`
- **Target Repository**: `Veenoe/veenoe-backend`
- **Trust Model**: Cryptographic authentication via short-lived OIDC JSON Web Tokens (JWT) issued by GitHub Actions. Long-lived AWS access keys are prohibited for deployment workflows.

---

## 3. Development Deployment Role: `veenoe-github-actions-dev-deploy`

Role ARN: `arn:aws:iam::165835313361:role/veenoe-github-actions-dev-deploy`

### A. Trust Policy (`sts:AssumeRoleWithWebIdentity`)
Constrained strictly to workflow runs executed in the GitHub `development` environment on repository `Veenoe/veenoe-backend`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubActionsDevAssumeRoleWithWebIdentity",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::165835313361:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:Veenoe/veenoe-backend:environment:development"
        }
      }
    }
  ]
}
```

### B. Attached Inline Policies

#### 1. Terraform S3 State Access (`veenoe-dev-terraform-state-access`)
- **Bucket List**: `s3:ListBucket` on `arn:aws:s3:::veenoe-terraform-state-165835313361` with prefix conditions `backend/dev/*` and `backend/dev`.
- **State Objects**: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` restricted to `arn:aws:s3:::veenoe-terraform-state-165835313361/backend/dev/*`.

#### 2. Application Deployment Scope (`veenoe-dev-application-deploy-scope`)
Permissions are grouped by resource type and strictly scoped to `dev` resources:

- **Lambda Management**:
  - Actions: `lambda:CreateFunction`, `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`, `lambda:DeleteFunction`, `lambda:GetFunction`, `lambda:GetFunctionConfiguration`, `lambda:GetFunctionCodeSigningConfig`, `lambda:GetFunctionEventInvokeConfig`, `lambda:ListVersionsByFunction`, `lambda:PublishVersion`, `lambda:TagResource`, `lambda:UntagResource`, `lambda:ListTags`, `lambda:AddPermission`, `lambda:RemovePermission`, `lambda:GetPolicy`
  - Resource: `arn:aws:lambda:ap-south-1:165835313361:function:veenoe-dev-*`
- **API Gateway Management**:
  - Actions: `apigateway:GET`, `apigateway:POST`, `apigateway:PUT`, `apigateway:PATCH`, `apigateway:DELETE`
  - Resources: `arn:aws:apigateway:ap-south-1::/apis`, `arn:aws:apigateway:ap-south-1::/apis/*`, `arn:aws:apigateway:ap-south-1::/tags/*`
- **DynamoDB Management**:
  - Actions: `dynamodb:CreateTable`, `dynamodb:UpdateTable`, `dynamodb:DeleteTable`, `dynamodb:DescribeTable`, `dynamodb:TagResource`, `dynamodb:UntagResource`, `dynamodb:ListTagsOfResource`
  - Resource: `arn:aws:dynamodb:ap-south-1:165835313361:table/veenoe-dev-*`
- **Lambda Layer Read**:
  - Actions: `lambda:GetLayerVersion`
  - Resource: `arn:aws:lambda:ap-south-1:753240598075:layer:LambdaAdapterLayerX86:*`
- **CloudWatch Logs Management**:
  - Actions: `logs:DescribeLogGroups` (resource: `*`), `logs:CreateLogGroup`, `logs:DeleteLogGroup`, `logs:PutRetentionPolicy`, `logs:DeleteRetentionPolicy`, `logs:ListTagsForResource`, `logs:TagResource`, `logs:UntagResource`
  - Resources: `arn:aws:logs:ap-south-1:165835313361:log-group:/aws/lambda/veenoe-dev-*`
- **Runtime IAM Role Management**:
  - Actions: `iam:CreateRole`, `iam:DeleteRole`, `iam:GetRole`, `iam:GetRolePolicy`, `iam:PutRolePolicy`, `iam:DeleteRolePolicy`, `iam:AttachRolePolicy`, `iam:DetachRolePolicy`, `iam:ListAttachedRolePolicies`, `iam:ListRolePolicies`, `iam:TagRole`, `iam:UntagRole`
  - Resource: `arn:aws:iam::165835313361:role/veenoe-dev-*`
- **IAM PassRole**:
  - Action: `iam:PassRole`
  - Resource: `arn:aws:iam::165835313361:role/veenoe-dev-*`
  - Condition: `iam:PassedToService = lambda.amazonaws.com`
- **SSM Parameter Store Management (VEENOE-9 Bootstrap Update)**:
  - Statement ID: `SSMManageParametersDev`
  - Actions:
    - `ssm:GetParameter`
    - `ssm:GetParameters`
    - `ssm:PutParameter`
    - `ssm:DeleteParameter`
    - `ssm:AddTagsToResource`
    - `ssm:RemoveTagsFromResource`
    - `ssm:ListTagsForResource`
  - Exact Parameter ARNs:
    - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/mongo_uri`
    - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/mongo_db_name`
    - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/google_api_key`
    - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/clerk_secret_key`

### C. Explicit Deploy Role Prohibitions & Exclusions
The `veenoe-github-actions-dev-deploy` role **DOES NOT** receive and must never be granted:
- `ssm:*` (no administrative wildcard)
- `ssm:GetParametersByPath`
- `ssm:GetParameterHistory`
- `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/*` (no path wildcard; must remain exact 4 parameter ARNs)
- `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/prod/*` (no cross-environment access)
- `kms:*` (SSM parameters rely on default account key `alias/aws/ssm`)
- `secretsmanager:*` (no Secrets Manager permissions)
- Modifications to `infra/bootstrap` IAM roles, policies, or S3 state bucket configuration.

---

## 4. Application Runtime Role: `veenoe-dev-lambda-runtime`

Role ARN: `arn:aws:iam::165835313361:role/veenoe-dev-lambda-runtime`  
Configured in [`infra/app/main.tf`](file:///d:/Veenoe/veenoe-backend/infra/app/main.tf).

### A. Trust Policy
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LambdaAssumeRole",
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### B. Attached Inline Policies

#### 1. CloudWatch Logging (`veenoe-dev-lambda-logging`)
- Actions: `logs:CreateLogStream`, `logs:PutLogEvents`
- Resource: `${aws_cloudwatch_log_group.lambda.arn}:*`

#### 2. SSM Parameter Read Access (`veenoe-dev-lambda-ssm-read`)
- Statement ID: `SSMGetParametersExact`
- Action: `ssm:GetParameters` **only** (with decryption)
- Exact Resources:
  - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/mongo_uri`
  - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/mongo_db_name`
  - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/google_api_key`
  - `arn:aws:ssm:ap-south-1:165835313361:parameter/veenoe/dev/clerk_secret_key`

### C. Explicit Runtime Role Prohibitions
The Lambda execution identity is strictly a consumer:
- **No SSM Writes**: Cannot create, modify, delete, or tag SSM parameters (`PutParameter`, `DeleteParameter`, `AddTagsToResource`).
- **No Terraform State Access**: Cannot read or write S3 Terraform state files.
- **No Deployment Capabilities**: Cannot create or modify Lambda, API Gateway, IAM, or CloudWatch log resources.
- **No GitHub Trust**: Cannot be assumed by GitHub Actions or outside services.
- **Cross-Environment Isolation**: Cannot read `/veenoe/prod/*` parameters.

---

## 5. Production Deployment Role: `veenoe-github-actions-prod-deploy`

Role ARN: `arn:aws:iam::165835313361:role/veenoe-github-actions-prod-deploy`  
Configured in [`infra/bootstrap/main.tf`](file:///d:/Veenoe/veenoe-backend/infra/bootstrap/main.tf).

### A. Trust Policy
Constrained strictly to GitHub Actions running under the `production` environment:
- Subject: `repo:Veenoe/veenoe-backend:environment:production`

### B. Scope & Boundary
- Manages `prod` application resources: `arn:aws:lambda:ap-south-1:165835313361:function:veenoe-prod-*`, etc.
- State access restricted to `backend/prod/*`.
- **VEENOE-9 Scope Boundary**: Production SSM parameter permissions are **not** created or applied as part of VEENOE-9. Production secret architecture will be formally reviewed and provisioned in a future ticket before production release.
