# ==============================================================================
# SSM Parameter Store Placeholders (DEV Prototype Only)
# ==============================================================================
# Provisions the parameter containers with non-sensitive placeholder values.
# Real credentials must be populated out-of-band by the operator after first apply.
# Drift on 'value' is intentionally ignored so operator updates are not reverted.

resource "aws_ssm_parameter" "mongo_uri" {
  count = var.environment == "dev" ? 1 : 0

  name        = "/veenoe/${var.environment}/mongo_uri"
  description = "MongoDB connection string for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type        = "SecureString"
  tier        = "Standard"
  value       = "VEENOE_REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "mongo_db_name" {
  count = var.environment == "dev" ? 1 : 0

  name        = "/veenoe/${var.environment}/mongo_db_name"
  description = "MongoDB database name for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type        = "String"
  tier        = "Standard"
  value       = "VEENOE_REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "google_api_key" {
  count = var.environment == "dev" ? 1 : 0

  name        = "/veenoe/${var.environment}/google_api_key"
  description = "Google AI Studio API key for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type        = "SecureString"
  tier        = "Standard"
  value       = "VEENOE_REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "clerk_secret_key" {
  count = var.environment == "dev" ? 1 : 0

  name        = "/veenoe/${var.environment}/clerk_secret_key"
  description = "Clerk secret key for Veenoe DEV backend (placeholder - operator must populate real value out-of-band)"
  type        = "SecureString"
  tier        = "Standard"
  value       = "VEENOE_REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
