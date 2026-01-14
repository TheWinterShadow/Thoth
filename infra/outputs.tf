# Root module outputs

output "api_gateway_url" {
  description = "URL of the API Gateway HTTP API"
  value       = module.api_gateway.api_url
}

output "lambda_function_name" {
  description = "Name of the MCP server Lambda function"
  value       = module.lambda_mcp_server.function_name
}

output "lambda_function_arn" {
  description = "ARN of the MCP server Lambda function"
  value       = module.lambda_mcp_server.function_arn
}

output "refresh_lambda_function_name" {
  description = "Name of the refresh service Lambda function"
  value       = module.lambda_refresh_service.function_name
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket for vector DB storage"
  value       = module.s3_storage.bucket_name
}

output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = module.ecr.repository_url
}

