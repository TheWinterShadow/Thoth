terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration - should be set via backend config
  # terraform init -backend-config="bucket=thoth-terraform-state" -backend-config="dynamodb_table=thoth-terraform-state-lock"
  backend "s3" {
    # Configured via backend config or environment variables
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "thoth"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# S3 bucket for vector DB storage
module "s3_storage" {
  source = "./modules/s3"

  bucket_name     = var.s3_bucket_name
  bucket_location = var.s3_bucket_location
  environment     = var.environment
  project_name    = "thoth"
}

# Secrets Manager for secure credential storage
module "secrets" {
  source = "./modules/secrets"

  project_name = "thoth"
  environment  = var.environment
  kms_key_id   = var.kms_key_id
}

# ECR repository for Lambda container images
module "ecr" {
  source = "./modules/ecr"

  repository_name = var.ecr_repository_name
  environment     = var.environment
  project_name    = "thoth"
}

# IAM role for MCP server Lambda
module "iam_mcp_server" {
  source = "./modules/iam"

  role_name    = "${var.project_name}-mcp-server-lambda-role"
  service_name = "mcp-server"
  environment  = var.environment

  policies = [
    {
      name = "S3Access"
      statements = [
        {
          effect = "Allow"
          actions = [
            "s3:GetObject",
            "s3:ListBucket",
          ]
          resources = [
            "${module.s3_storage.bucket_arn}/*",
            module.s3_storage.bucket_arn,
          ]
        },
      ]
    },
    {
      name = "SecretsManagerAccess"
      statements = [
        {
          effect = "Allow"
          actions = [
            "secretsmanager:GetSecretValue",
          ]
          resources = [
            module.secrets.secret_arns["gitlab-token"],
            module.secrets.secret_arns["gitlab-url"],
            module.secrets.secret_arns["api-key"],
          ]
        },
      ]
    },
    {
      name = "DynamoDBAccess"
      statements = [
        {
          effect = "Allow"
          actions = [
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
            "dynamodb:Query",
          ]
          resources = [
            module.dynamodb.table_arn,
          ]
        },
      ]
    },
  ]
}

# IAM role for refresh service Lambda
module "iam_refresh_service" {
  source = "./modules/iam"

  role_name    = "${var.project_name}-refresh-service-lambda-role"
  service_name = "refresh-service"
  environment  = var.environment

  policies = [
    {
      name = "S3Access"
      statements = [
        {
          effect = "Allow"
          actions = [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:ListBucket",
          ]
          resources = [
            "${module.s3_storage.bucket_arn}/*",
            module.s3_storage.bucket_arn,
          ]
        },
      ]
    },
    {
      name = "SecretsManagerAccess"
      statements = [
        {
          effect = "Allow"
          actions = [
            "secretsmanager:GetSecretValue",
          ]
          resources = [
            module.secrets.secret_arns["gitlab-token"],
            module.secrets.secret_arns["gitlab-url"],
          ]
        },
      ]
    },
  ]
}

# DynamoDB table for connection state/cache (optional)
module "dynamodb" {
  source = "./modules/dynamodb"

  table_name   = "${var.project_name}-${var.environment}-mcp-state"
  environment   = var.environment
  project_name  = var.project_name
  kms_key_id   = var.kms_key_id
}

# API Gateway HTTP API
module "api_gateway" {
  source = "./modules/api-gateway"

  api_name             = "${var.project_name}-${var.environment}-mcp-api"
  environment          = var.environment
  project_name         = var.project_name
  lambda_function_name = module.lambda_mcp_server.function_name
  lambda_invoke_arn    = module.lambda_mcp_server.function_invoke_arn
  domain_name          = var.api_domain_name
}

# MCP Server Lambda function
module "lambda_mcp_server" {
  source = "./modules/lambda"

  function_name = "${var.project_name}-${var.environment}-mcp-server"
  handler       = "thoth.mcp_server.lambda_handler.handler"
  runtime       = "python3.11"
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout

  environment_variables = {
    ENVIRONMENT          = var.environment
    S3_BUCKET_NAME       = module.s3_storage.bucket_name
    DYNAMODB_TABLE_NAME  = module.dynamodb.table_name
    LOG_LEVEL            = var.log_level
  }

  iam_role_arn = module.iam_mcp_server.role_arn

  layers = var.lambda_layers

  tags = {
    Service = "mcp-server"
  }
}

# Refresh Service Lambda function (container image)
module "lambda_refresh_service" {
  source = "./modules/lambda"

  function_name = "${var.project_name}-${var.environment}-refresh-service"
  description   = "Refresh Service Lambda function"
  package_type  = "Image"
  image_uri     = "${module.ecr.repository_url}:latest"
  memory_size   = var.refresh_lambda_memory_size
  timeout       = var.refresh_lambda_timeout
  environment   = var.environment

  environment_variables = {
    ENVIRONMENT    = var.environment
    S3_BUCKET_NAME = module.s3_storage.bucket_name
    LOG_LEVEL      = var.log_level
  }

  iam_role_arn = module.iam_refresh_service.role_arn

  tags = {
    Service = "refresh-service"
  }
}

# EventBridge rules for scheduled refresh jobs
module "eventbridge" {
  source = "./modules/eventbridge"

  project_name = var.project_name
  environment  = var.environment

  rules = [
    {
      name                = "daily-sync"
      description         = "Daily handbook synchronization"
      schedule_expression = "cron(0 2 * * ? *)" # 2 AM UTC daily
      lambda_function_arn = module.lambda_refresh_service.function_arn
      input = jsonencode({
        sync_type = "daily"
      })
    },
    {
      name                = "hourly-incremental-sync"
      description         = "Hourly incremental handbook synchronization"
      schedule_expression = "cron(0 * * * ? *)" # Every hour
      lambda_function_arn = module.lambda_refresh_service.function_arn
      input = jsonencode({
        sync_type   = "incremental"
        incremental = true
      })
    },
  ]
}
