resource "aws_dynamodb_table" "sessions" {
  # Fixed 5/5 capacity per environment keeps DEV + PROD at 10/10, within the
  # provisioned free allowance if other account usage and eligibility permit.
  # No autoscaling: sustained traffic is throttled rather than increasing spend.
  # Raise capacity or enable bounded scaling through Actions after measuring
  # throttling/latency, item sizes, and agreeing a monthly operating budget.
  name           = "${local.name_prefix}-sessions"
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "pk"
  range_key      = "sk"
  table_class    = "STANDARD"

  # Prevent accidental PROD table deletion; this is not a backup or recovery plan.
  deletion_protection_enabled = var.environment == "prod"

  # Optional features are deliberately omitted, so provider defaults keep them off:
  # - PITR/backups: enable when history needs an agreed recovery window and budget,
  #   even at low traffic; load is not the reason to defer data-loss protection.
  # - Streams: enable only for a concrete event consumer, not for basic CRUD.
  # - Replicas: add only for multi-region availability/latency requirements with
  #   funding for replicated writes and storage in every participating Region.
  # - Customer-managed KMS: use only for required key control/auditing; the default
  #   AWS-owned key already encrypts the table without a separate KMS-key charge.
  # - TTL: off to retain history; enable only after defining a retention policy.
  #   TTL itself is not a paid backup and must not replace lifecycle reconciliation.
  # No secondary indexes: current keys serve all access patterns. Add an index
  # only for a new measured query need, accounting for its storage/write capacity.

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  tags = {
    Repository = "veenoe-backend"
  }
}

resource "aws_iam_role_policy" "lambda_sessions" {
  name   = "${local.name_prefix}-lambda-sessions"
  role   = aws_iam_role.lambda_runtime.id
  policy = data.aws_iam_policy_document.lambda_sessions.json
}

data "aws_iam_policy_document" "lambda_sessions" {
  statement {
    sid = "SessionsForThisEnvironment"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:DeleteItem",
    ]
    resources = [aws_dynamodb_table.sessions.arn]
  }
}

output "sessions_table_name" {
  value = aws_dynamodb_table.sessions.name
}
