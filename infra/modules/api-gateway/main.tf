# API Gateway HTTP API module

resource "aws_apigatewayv2_api" "this" {
  name          = var.api_name
  protocol_type   = "HTTP"
  description   = "HTTP API for Thoth MCP Server"
  version       = "1.0"

  cors_configuration {
    allow_origins = var.cors_allow_origins
    allow_methods = var.cors_allow_methods
    allow_headers = var.cors_allow_headers
    max_age       = var.cors_max_age
  }

  tags = merge(
    var.tags,
    {
      Name        = var.api_name
      Environment = var.environment
      Purpose     = "mcp-server-api"
    }
  )
}

# Default stage
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_logs.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = true
    throttling_burst_limit   = var.throttling_burst_limit
    throttling_rate_limit    = var.throttling_rate_limit
  }
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_logs" {
  name              = "/aws/apigateway/${var.api_name}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name        = "${var.api_name}-logs"
      Environment = var.environment
    }
  )
}

# Lambda integration
resource "aws_apigatewayv2_integration" "lambda" {
  api_id = aws_apigatewayv2_api.this.id

  integration_type   = "AWS_PROXY"
  integration_uri     = var.lambda_invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds  = var.integration_timeout_ms
}

# Routes
resource "aws_apigatewayv2_route" "messages" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "POST /messages"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "sse" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "GET /sse"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "GET /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

# API key (optional, for rate limiting)
resource "aws_apigatewayv2_api_key" "this" {
  count = var.enable_api_key ? 1 : 0
  name  = "${var.api_name}-key"

  tags = merge(
    var.tags,
    {
      Name        = "${var.api_name}-key"
      Environment = var.environment
    }
  )
}

