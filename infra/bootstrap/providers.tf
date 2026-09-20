provider "aws" {
  region              = var.aws_region
  profile             = var.aws_profile != "" ? var.aws_profile : null
  allowed_account_ids = var.allowed_account_ids

  default_tags {
    tags = {
      Project     = "Veenoe"
      ManagedBy   = "Terraform"
      Component   = "Bootstrap"
      Environment = "Management"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
