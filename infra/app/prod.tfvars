environment              = "prod"
aws_region               = "ap-south-1"
lambda_memory_size       = 512
lambda_timeout           = 30
log_retention_in_days    = 30
lambda_adapter_layer_arn = "arn:aws:lambda:ap-south-1:753240598075:layer:LambdaAdapterLayerX86:29"
lambda_artifact_path     = "../../dist/veenoe-backend.zip"

smoke_mongo_uri        = "mongodb://localhost:27017"
smoke_mongo_db_name    = "prod_viva_db"
smoke_google_api_key   = "test_google_api_key"
smoke_clerk_secret_key = "sk_test_mock_clerk_secret_key"
