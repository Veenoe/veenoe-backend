output "environment" {
  description = "Target deployment environment."
  value       = var.environment
}

output "aws_region" {
  description = "AWS region of the deployed application stack."
  value       = local.aws_region
}

output "lambda_function_name" {
  description = "Name of the backend Lambda function."
  value       = aws_lambda_function.backend.function_name
}

output "lambda_function_arn" {
  description = "ARN of the backend Lambda function."
  value       = aws_lambda_function.backend.arn
}

output "lambda_log_group_name" {
  description = "Name of the CloudWatch log group for Lambda execution logs."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "api_id" {
  description = "ID of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.http_api.id
}

output "api_endpoint" {
  description = "Base URL endpoint of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.http_api.api_endpoint
}

output "health_url" {
  description = "Public URL for the smoke test health check endpoint (GET /)."
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/"
}

output "db_health_url" {
  description = "Public URL for the database health check endpoint (GET /health)."
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}/health"
}

output "custom_domain_name" {
  description = "Custom domain name assigned to the API Gateway."
  value       = local.custom_domain_enabled ? aws_apigatewayv2_domain_name.api[0].domain_name : null
}

output "custom_domain_target" {
  description = "Target API Gateway domain name to point DNS CNAME records to."
  value       = local.custom_domain_enabled ? aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name : null
}

output "custom_domain_url" {
  description = "Public base URL for the custom domain."
  value       = local.custom_domain_enabled ? "https://${aws_apigatewayv2_domain_name.api[0].domain_name}" : null
}
