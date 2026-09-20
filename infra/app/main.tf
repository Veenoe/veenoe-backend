locals {
  name_prefix   = "veenoe-${var.environment}"
  function_name = "${local.name_prefix}-backend"
  account_id    = data.aws_caller_identity.current.account_id
  aws_region    = data.aws_region.current.name

  # Environment-aware custom domain resolution
  custom_domain_enabled = var.enable_custom_domain
  custom_domain_name    = var.custom_domain_name != "" ? var.custom_domain_name : (var.environment == "prod" ? "api.veenoe.com" : "api-dev.veenoe.com")
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ==============================================================================
# CloudWatch Logs (Explicitly Managed)
# ==============================================================================

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_in_days
}

# ==============================================================================
# Lambda Runtime IAM Role (Least Privilege)
# ==============================================================================

resource "aws_iam_role" "lambda_runtime" {
  name        = "${local.name_prefix}-lambda-runtime"
  description = "Execution role for ${local.function_name} with minimal logging permissions"

  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    sid     = "LambdaServiceAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "lambda_logging" {
  name   = "${local.name_prefix}-lambda-logging"
  role   = aws_iam_role.lambda_runtime.id
  policy = data.aws_iam_policy_document.lambda_logging.json
}

data "aws_iam_policy_document" "lambda_logging" {
  statement {
    sid    = "LambdaLogEvents"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "${aws_cloudwatch_log_group.lambda.arn}:*"
    ]
  }
}

resource "aws_iam_role_policy" "lambda_ssm_read" {
  name   = "${local.name_prefix}-lambda-ssm-read"
  role   = aws_iam_role.lambda_runtime.id
  policy = data.aws_iam_policy_document.lambda_ssm_read.json
}

data "aws_iam_policy_document" "lambda_ssm_read" {
  statement {
    sid     = "SSMGetParametersExact"
    effect  = "Allow"
    actions = ["ssm:GetParameters"]
    resources = [
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/${var.environment}/mongo_uri",
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/${var.environment}/mongo_db_name",
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/${var.environment}/google_api_key",
      "arn:aws:ssm:${local.aws_region}:${local.account_id}:parameter/veenoe/${var.environment}/clerk_secret_key"
    ]
  }
}

# ==============================================================================
# Lambda Function with Lambda Web Adapter
# ==============================================================================

resource "aws_lambda_function" "backend" {
  function_name = local.function_name
  description   = "Veenoe FastAPI backend running on AWS Lambda with Lambda Web Adapter"
  role          = aws_iam_role.lambda_runtime.arn

  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "run.sh"

  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  filename         = "${path.module}/${var.lambda_artifact_path}"
  source_code_hash = filebase64sha256("${path.module}/${var.lambda_artifact_path}")

  layers = [var.lambda_adapter_layer_arn]

  environment {
    variables = {
      # Lambda Web Adapter contract
      AWS_LAMBDA_EXEC_WRAPPER                = "/opt/bootstrap"
      PORT                                   = "8080"
      AWS_LWA_READINESS_CHECK_PATH           = "/"
      AWS_LWA_READINESS_CHECK_HEALTHY_STATUS = "200-399"
      AWS_LWA_INVOKE_MODE                    = "buffered"

      # Application runtime configuration pointer (SSM Parameter Store)
      VEENOE_SSM_PARAMETER_PREFIX = "/veenoe/${var.environment}"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_logging,
    aws_iam_role_policy.lambda_ssm_read
  ]
}

# ==============================================================================
# API Gateway HTTP API & Proxy Integration
# ==============================================================================

resource "aws_apigatewayv2_api" "http_api" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "HTTP API Gateway proxy for Veenoe FastAPI backend"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.backend.invoke_arn
  payload_format_version = "2.0"
}

# Minimal route for smoke testing: GET / only
resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Production database connectivity health check route: GET /health
resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Authenticated viva session start route: POST /api/v1/viva/start
resource "aws_apigatewayv2_route" "viva_start" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /api/v1/viva/start"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Catch-all proxy route: forwards all other paths and methods (including CORS OPTIONS preflights) to Lambda
resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true
}

# Resource-based permission allowing API Gateway to invoke the Lambda function
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# ==============================================================================
# API Gateway Custom Domain & API Mapping (Environment-Safe)
# ==============================================================================

data "aws_acm_certificate" "api" {
  count       = local.custom_domain_enabled ? 1 : 0
  domain      = local.custom_domain_name
  statuses    = ["ISSUED"]
  most_recent = true
}

resource "aws_apigatewayv2_domain_name" "api" {
  count       = local.custom_domain_enabled ? 1 : 0
  domain_name = local.custom_domain_name

  domain_name_configuration {
    certificate_arn = data.aws_acm_certificate.api[0].arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "api" {
  count       = local.custom_domain_enabled ? 1 : 0
  api_id      = aws_apigatewayv2_api.http_api.id
  domain_name = aws_apigatewayv2_domain_name.api[0].id
  stage       = aws_apigatewayv2_stage.default.id
}
