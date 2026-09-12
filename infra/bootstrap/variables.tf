variable "aws_region" {
  type        = string
  description = "The AWS region where bootstrap resources (e.g. S3 state bucket) will be created."
  default     = "ap-south-1"
}

variable "github_repository" {
  type        = string
  description = "The GitHub organization and repository allowed to assume deployment roles (in 'owner/repo' format)."
  default     = "Veenoe/veenoe-backend"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must follow 'owner/repo' format."
  }
}

variable "dev_environment_name" {
  type        = string
  description = "The GitHub environment name whose workflows are allowed to assume the development deployment role."
  default     = "development"
}

variable "prod_environment_name" {
  type        = string
  description = "The GitHub environment name whose workflows are allowed to assume the production deployment role."
  default     = "Production"
}

variable "aws_profile" {
  type        = string
  description = "The AWS CLI profile to use for local operations. Keep empty in CI/CD environments."
  default     = ""
}

variable "allowed_account_ids" {
  type        = list(string)
  description = "List of allowed AWS account IDs to prevent accidental operations in the wrong account."
  default     = ["165835313361"]
}

variable "state_bucket_name" {
  type        = string
  description = "Explicit name for the S3 state bucket. If left empty, defaults to 'veenoe-terraform-state-<account_id>'."
  default     = ""
}

variable "dev_deploy_role_name" {
  type        = string
  description = "Name of the IAM role used by GitHub Actions for development deployments."
  default     = "veenoe-github-actions-dev-deploy"
}

variable "prod_deploy_role_name" {
  type        = string
  description = "Name of the IAM role used by GitHub Actions for production deployments."
  default     = "veenoe-github-actions-prod-deploy"
}

variable "github_oidc_client_ids" {
  type        = list(string)
  description = "List of allowed audiences for the GitHub OIDC provider. STS requires 'sts.amazonaws.com'."
  default     = ["sts.amazonaws.com"]
}
