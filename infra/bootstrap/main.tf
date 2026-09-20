locals {
  account_id = data.aws_caller_identity.current.account_id
  aws_region = data.aws_region.current.name

  state_bucket_name = var.state_bucket_name != "" ? var.state_bucket_name : "veenoe-terraform-state-${local.account_id}"
}

# ==============================================================================
# S3 Remote State Bucket
# ==============================================================================

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket_name

  tags = {
    Name        = local.state_bucket_name
    Description = "Remote state storage and locking for Veenoe Terraform deployments"
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_policy" "enforce_tls" {
  bucket = aws_s3_bucket.state.id

  policy = data.aws_iam_policy_document.enforce_tls.json
}

# Enforces in-flight encryption by denying any non-HTTPS requests (aws:SecureTransport = false)
data "aws_iam_policy_document" "enforce_tls" {
  statement {
    sid     = "EnforceHTTPSRequestsOnly"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*"
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

# ==============================================================================
# GitHub Actions OIDC Identity Provider
# ==============================================================================

# Note: In AWS IAM and Terraform AWS Provider >= v5.38.0, thumbprint_list is optional
# because AWS validates certificates for token.actions.githubusercontent.com using
# trusted root CAs. Leaving thumbprint_list omitted prevents pipeline breakage on
# GitHub certificate rotations.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = var.github_oidc_client_ids

  tags = {
    Name = "github-actions-oidc-provider"
  }
}

# ==============================================================================
# Development Deployment Role & Policies
# ==============================================================================

resource "aws_iam_role" "dev_deploy" {
  name        = var.dev_deploy_role_name
  description = "Role assumed by GitHub Actions for Veenoe development deployments"

  assume_role_policy = data.aws_iam_policy_document.dev_trust_policy.json

  tags = {
    Environment = "development"
    Role        = "Deployment"
  }
}

data "aws_iam_policy_document" "dev_trust_policy" {
  statement {
    sid     = "GitHubActionsDevAssumeRoleWithWebIdentity"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = var.github_oidc_client_ids
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.dev_environment_name}"]
    }
  }
}

resource "aws_iam_role_policy" "dev_state_access" {
  name   = "veenoe-dev-terraform-state-access"
  role   = aws_iam_role.dev_deploy.id
  policy = data.aws_iam_policy_document.dev_state_access.json
}

data "aws_iam_policy_document" "dev_state_access" {
  statement {
    sid     = "StateBucketListDev"
    effect  = "Allow"
    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.state.arn
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "backend/dev/*",
        "backend/dev"
      ]
    }
  }

  statement {
    sid    = "StateBucketObjectsDev"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [
      "${aws_s3_bucket.state.arn}/backend/dev/*"
    ]
  }
}

resource "aws_iam_role_policy" "dev_app_deploy" {
  name   = "veenoe-dev-application-deploy-scope"
  role   = aws_iam_role.dev_deploy.id
  policy = data.aws_iam_policy_document.dev_app_deploy.json
}

data "aws_iam_policy_document" "dev_app_deploy" {
  statement {
    sid    = "LambdaManageDev"
    effect = "Allow"
    actions = [
      "lambda:CreateFunction",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:DeleteFunction",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetFunctionEventInvokeConfig",
      "lambda:ListVersionsByFunction",
      "lambda:PublishVersion",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:ListTags",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:GetPolicy"
    ]
    resources = [
      "arn:aws:lambda:${local.aws_region}:${local.account_id}:function:veenoe-dev-*"
    ]
  }

  statement {
    sid    = "APIGatewayManageDev"
    effect = "Allow"
    actions = [
      "apigateway:GET",
      "apigateway:POST",
      "apigateway:PUT",
      "apigateway:PATCH",
      "apigateway:DELETE"
    ]
    resources = [
      "arn:aws:apigateway:${local.aws_region}::/apis",
      "arn:aws:apigateway:${local.aws_region}::/apis/*",
      "arn:aws:apigateway:${local.aws_region}::/domainnames",
      "arn:aws:apigateway:${local.aws_region}::/domainnames/*",
      "arn:aws:apigateway:${local.aws_region}::/tags/*"
    ]
  }

  statement {
    sid    = "ACMDescribeCertificatesDev"
    effect = "Allow"
    actions = [
      "acm:DescribeCertificate",
      "acm:ListCertificates",
      "acm:GetCertificate",
      "acm:ListTagsForCertificate"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DynamoDBManageDev"
    effect = "Allow"
    actions = [
      "dynamodb:CreateTable",
      "dynamodb:UpdateTable",
      "dynamodb:DeleteTable",
      "dynamodb:DescribeTable",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:ListTagsOfResource"
    ]
    resources = [
      "arn:aws:dynamodb:${local.aws_region}:${local.account_id}:table/veenoe-dev-*"
    ]
  }

  statement {
    sid    = "LambdaGetAdapterLayerDev"
    effect = "Allow"
    actions = [
      "lambda:GetLayerVersion"
    ]
    resources = [
      "arn:aws:lambda:${local.aws_region}:753240598075:layer:LambdaAdapterLayerX86:*"
    ]
  }

  statement {
    sid    = "LogsDescribeDev"
    effect = "Allow"
    actions = [
      "logs:DescribeLogGroups"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "LogsManageDev"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy",
      "logs:ListTagsForResource",
      "logs:TagResource",
      "logs:UntagResource"
    ]
    resources = [
      "arn:aws:logs:${local.aws_region}:${local.account_id}:log-group:/aws/lambda/veenoe-dev-*",
      "arn:aws:logs:${local.aws_region}:${local.account_id}:log-group:/aws/lambda/veenoe-dev-*:*"
    ]
  }

  statement {
    sid    = "IAMManageRuntimeRoleDev"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:TagRole",
      "iam:UntagRole"
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/veenoe-dev-*"
    ]
  }

  statement {
    sid    = "IAMPassRoleToLambdaDev"
    effect = "Allow"
    actions = [
      "iam:PassRole"
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/veenoe-dev-*"
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  statement {
    sid    = "SSMManageParametersDev"
    effect = "Allow"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:PutParameter",
      "ssm:DeleteParameter",
      "ssm:AddTagsToResource",
      "ssm:RemoveTagsFromResource",
      "ssm:ListTagsForResource"
    ]
    resources = [
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/dev/mongo_uri",
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/dev/mongo_db_name",
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/dev/google_api_key",
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/dev/clerk_secret_key"
    ]
  }

  statement {
    sid    = "SSMDescribeParametersDev"
    effect = "Allow"
    actions = [
      "ssm:DescribeParameters"
    ]
    resources = ["*"]
  }
}

# ==============================================================================
# Production Deployment Role & Policies
# ==============================================================================

resource "aws_iam_role" "prod_deploy" {
  name        = var.prod_deploy_role_name
  description = "Role assumed by GitHub Actions for Veenoe production deployments"

  assume_role_policy = data.aws_iam_policy_document.prod_trust_policy.json

  tags = {
    Environment = var.prod_environment_name
    Role        = "Deployment"
  }
}

data "aws_iam_policy_document" "prod_trust_policy" {
  statement {
    sid     = "GitHubActionsProdAssumeRoleWithWebIdentity"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = var.github_oidc_client_ids
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.prod_environment_name}"]
    }
  }
}

resource "aws_iam_role_policy" "prod_state_access" {
  name   = "veenoe-prod-terraform-state-access"
  role   = aws_iam_role.prod_deploy.id
  policy = data.aws_iam_policy_document.prod_state_access.json
}

data "aws_iam_policy_document" "prod_state_access" {
  statement {
    sid     = "StateBucketListProd"
    effect  = "Allow"
    actions = ["s3:ListBucket"]
    resources = [
      aws_s3_bucket.state.arn
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "backend/prod/*",
        "backend/prod"
      ]
    }
  }

  statement {
    sid    = "StateBucketObjectsProd"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ]
    resources = [
      "${aws_s3_bucket.state.arn}/backend/prod/*"
    ]
  }
}

resource "aws_iam_role_policy" "prod_app_deploy" {
  name   = "veenoe-prod-application-deploy-scope"
  role   = aws_iam_role.prod_deploy.id
  policy = data.aws_iam_policy_document.prod_app_deploy.json
}

data "aws_iam_policy_document" "prod_app_deploy" {
  statement {
    sid    = "LambdaManageProd"
    effect = "Allow"
    actions = [
      "lambda:CreateFunction",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:DeleteFunction",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetFunctionEventInvokeConfig",
      "lambda:ListVersionsByFunction",
      "lambda:PublishVersion",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:ListTags",
      "lambda:AddPermission",
      "lambda:RemovePermission",
      "lambda:GetPolicy"
    ]
    resources = [
      "arn:aws:lambda:${local.aws_region}:${local.account_id}:function:veenoe-prod-*"
    ]
  }

  statement {
    sid    = "APIGatewayManageProd"
    effect = "Allow"
    actions = [
      "apigateway:GET",
      "apigateway:POST",
      "apigateway:PUT",
      "apigateway:PATCH",
      "apigateway:DELETE"
    ]
    resources = [
      "arn:aws:apigateway:${local.aws_region}::/apis",
      "arn:aws:apigateway:${local.aws_region}::/apis/*",
      "arn:aws:apigateway:${local.aws_region}::/domainnames",
      "arn:aws:apigateway:${local.aws_region}::/domainnames/*",
      "arn:aws:apigateway:${local.aws_region}::/tags/*"
    ]
  }

  statement {
    sid    = "ACMDescribeCertificatesProd"
    effect = "Allow"
    actions = [
      "acm:DescribeCertificate",
      "acm:ListCertificates",
      "acm:GetCertificate",
      "acm:ListTagsForCertificate"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DynamoDBManageProd"
    effect = "Allow"
    actions = [
      "dynamodb:CreateTable",
      "dynamodb:UpdateTable",
      "dynamodb:DeleteTable",
      "dynamodb:DescribeTable",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:ListTagsOfResource"
    ]
    resources = [
      "arn:aws:dynamodb:${local.aws_region}:${local.account_id}:table/veenoe-prod-*"
    ]
  }

  statement {
    sid    = "LambdaGetAdapterLayerProd"
    effect = "Allow"
    actions = [
      "lambda:GetLayerVersion"
    ]
    resources = [
      "arn:aws:lambda:${local.aws_region}:753240598075:layer:LambdaAdapterLayerX86:*"
    ]
  }

  statement {
    sid    = "LogsDescribeProd"
    effect = "Allow"
    actions = [
      "logs:DescribeLogGroups"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "LogsManageProd"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy",
      "logs:ListTagsForResource",
      "logs:TagResource",
      "logs:UntagResource"
    ]
    resources = [
      "arn:aws:logs:${local.aws_region}:${local.account_id}:log-group:/aws/lambda/veenoe-prod-*",
      "arn:aws:logs:${local.aws_region}:${local.account_id}:log-group:/aws/lambda/veenoe-prod-*:*"
    ]
  }

  statement {
    sid    = "IAMManageRuntimeRoleProd"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:TagRole",
      "iam:UntagRole"
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/veenoe-prod-*"
    ]
  }

  statement {
    sid    = "IAMPassRoleToLambdaProd"
    effect = "Allow"
    actions = [
      "iam:PassRole"
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/veenoe-prod-*"
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }
}
