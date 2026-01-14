output "api_id" {
  description = "ID of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.this.id
}

output "api_arn" {
  description = "ARN of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.this.arn
}

output "api_url" {
  description = "URL of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "stage_id" {
  description = "ID of the default stage"
  value       = aws_apigatewayv2_stage.default.id
}

output "api_key_id" {
  description = "ID of the API key (if enabled)"
  value       = var.enable_api_key ? aws_apigatewayv2_api_key.this[0].id : null
}

