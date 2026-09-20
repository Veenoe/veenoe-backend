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

variable "enable_custom_domain" {
  type        = bool
  description = "Whether to configure a custom domain name for API Gateway."
  default     = false
}

variable "custom_domain_name" {
  type        = string
  description = "Custom domain name override. If blank, defaults to api-dev.veenoe.com for dev and api.veenoe.com for prod."
  default     = ""
}
