# ==============================================================================
# SSM Parameter Store Placeholders (DEV Prototype Only)
# ==============================================================================
# Provisions the parameter containers with non-sensitive placeholder values.
# Real credentials must be populated out-of-band by the operator after first apply.
# Drift on write-only secret values is intentionally ignored so operator updates
# are not reverted, and real secrets never enter refreshed Terraform state.

resource "aws_ssm_parameter" "mongo_uri" {
  count = var.environment == "dev" ? 1 : 0

  name             = "/veenoe/${var.environment}/mongo_uri"
  description      = "MongoDB connection string for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type             = "SecureString"
  tier             = "Standard"
  key_id           = "alias/aws/ssm"
  value_wo         = "VEENOE_REPLACE_ME"
  value_wo_version = 1

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "veenoe-backend"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      value_wo,
      value_wo_version,
    ]
  }
}

resource "aws_ssm_parameter" "mongo_db_name" {
  count = var.environment == "dev" ? 1 : 0

  name        = "/veenoe/${var.environment}/mongo_db_name"
  description = "MongoDB database name for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type        = "String"
  tier        = "Standard"
  value       = "VEENOE_REPLACE_ME"

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "veenoe-backend"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [value]
  }
}

resource "aws_ssm_parameter" "google_api_key" {
  count = var.environment == "dev" ? 1 : 0

  name             = "/veenoe/${var.environment}/google_api_key"
  description      = "Google AI Studio API key for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type             = "SecureString"
  tier             = "Standard"
  key_id           = "alias/aws/ssm"
  value_wo         = "VEENOE_REPLACE_ME"
  value_wo_version = 1

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "veenoe-backend"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      value_wo,
      value_wo_version,
    ]
  }
}

resource "aws_ssm_parameter" "clerk_secret_key" {
  count = var.environment == "dev" ? 1 : 0

  name             = "/veenoe/${var.environment}/clerk_secret_key"
  description      = "Clerk secret key for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type             = "SecureString"
  tier             = "Standard"
  key_id           = "alias/aws/ssm"
  value_wo         = "VEENOE_REPLACE_ME"
  value_wo_version = 1

  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "veenoe-backend"
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes = [
      value_wo,
      value_wo_version,
    ]
  }
}
