variable "aws_region" {
  type        = string
  description = "AWS region to deploy the application runtime."
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Target deployment environment (e.g. dev, prod)."
  default     = "dev"
}

variable "lambda_memory_size" {
  type        = number
  description = "Memory allocated to the Lambda function in MB."
  default     = 512
}

variable "lambda_timeout" {
  type        = number
  description = "Lambda function execution timeout in seconds."
  default     = 30
}

variable "log_retention_in_days" {
  type        = number
  description = "CloudWatch log retention period in days."
  default     = 14
}

variable "lambda_adapter_layer_arn" {
  type        = string
  description = "ARN of the AWS Lambda Web Adapter layer."
  default     = "arn:aws:lambda:ap-south-1:753240598075:layer:LambdaAdapterLayerX86:29"
}

variable "lambda_artifact_path" {
  type        = string
  description = "Relative path to the Lambda ZIP artifact from the Terraform root module."
  default     = "../../dist/veenoe-backend.zip"
}

# --- Application Configuration Placeholders for Smoke Testing ---
# These non-sensitive placeholder values allow the FastAPI application to import and start
# without contacting external systems, enabling the VEENOE-7 smoke test (GET /).
# In production / full-service wiring, these will be populated from Secrets Manager / SSM.
variable "smoke_mongo_uri" {
  type        = string
  description = "Placeholder MongoDB URI for smoke test startup."
  default     = "mongodb://localhost:27017"
}

variable "smoke_mongo_db_name" {
  type        = string
  description = "Placeholder MongoDB DB name for smoke test startup."
  default     = "test_viva_db"
}

variable "smoke_google_api_key" {
  type        = string
  description = "Placeholder Google API Key for smoke test startup."
  default     = "test_google_api_key"
  sensitive   = true
}

variable "smoke_clerk_secret_key" {
  type        = string
  description = "Placeholder Clerk Secret Key for smoke test startup."
  default     = "sk_test_mock_clerk_secret_key"
  sensitive   = true
}
