# Partial backend configuration.
# Environment-specific settings (bucket, key, region, encrypt, use_lockfile)
# are provided at initialization time via backend config files (e.g. dev.backend.hcl).
terraform {
  backend "s3" {}
}
