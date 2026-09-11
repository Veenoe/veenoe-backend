terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # NOTE: During the very first bootstrap run before the S3 bucket exists,
  # run `terraform init -backend=false` or comment out this block.
  # Once the bucket is created, run:
  #   terraform init -migrate-state \
  #     -backend-config="bucket=<STATE_BUCKET_NAME>" \
  #     -backend-config="key=bootstrap/terraform.tfstate" \
  #     -backend-config="region=<AWS_REGION>"
  backend "s3" {
    bucket       = "veenoe-terraform-state-165835313361"
    key          = "bootstrap/terraform.tfstate"
    region       = "ap-south-1"
    use_lockfile = true
    encrypt      = true
  }
}
