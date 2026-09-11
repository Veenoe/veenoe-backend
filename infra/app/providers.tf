provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Veenoe"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
