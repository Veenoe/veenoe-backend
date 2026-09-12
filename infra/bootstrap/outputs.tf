output "state_bucket_name" {
  description = "The name of the S3 bucket used for Terraform remote state."
  value       = aws_s3_bucket.state.id
}

output "state_bucket_arn" {
  description = "The ARN of the S3 bucket used for Terraform remote state."
  value       = aws_s3_bucket.state.arn
}

output "github_oidc_provider_arn" {
  description = "The ARN of the GitHub Actions OIDC identity provider."
  value       = aws_iam_openid_connect_provider.github.arn
}

output "dev_role_arn" {
  description = "The ARN of the IAM role for GitHub Actions development deployments."
  value       = aws_iam_role.dev_deploy.arn
}

output "prod_role_arn" {
  description = "The ARN of the IAM role for GitHub Actions production deployments."
  value       = aws_iam_role.prod_deploy.arn
}

output "bootstrap_state_key" {
  description = "The S3 key prefix for the bootstrap stack remote state."
  value       = "bootstrap/terraform.tfstate"
}

output "dev_state_key" {
  description = "The S3 key prefix for the development environment application remote state."
  value       = "backend/dev/terraform.tfstate"
}

output "prod_state_key" {
  description = "The S3 key prefix for the production environment application remote state."
  value       = "backend/prod/terraform.tfstate"
}

output "aws_region" {
  description = "The AWS region where bootstrap resources reside."
  value       = local.aws_region
}
