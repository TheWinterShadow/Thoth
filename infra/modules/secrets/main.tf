# Secrets Manager module for secure credential storage

# GitLab token secret
resource "aws_secretsmanager_secret" "gitlab_token" {
  name        = "${var.project_name}/${var.environment}/gitlab-token"
  description = "GitLab personal access token"

  kms_key_id = var.kms_key_id != "" ? var.kms_key_id : null

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-${var.environment}-gitlab-token"
      Environment = var.environment
      Purpose     = "gitlab-authentication"
    }
  )
}

resource "aws_secretsmanager_secret_version" "gitlab_token" {
  secret_id = aws_secretsmanager_secret.gitlab_token.id
  # Use placeholder - actual value should be set via AWS CLI or console
  secret_string = var.gitlab_token != "" ? var.gitlab_token : "PLACEHOLDER_UPDATE_ME"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# GitLab URL secret
resource "aws_secretsmanager_secret" "gitlab_url" {
  name        = "${var.project_name}/${var.environment}/gitlab-url"
  description = "GitLab base URL"

  kms_key_id = var.kms_key_id != "" ? var.kms_key_id : null

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-${var.environment}-gitlab-url"
      Environment = var.environment
      Purpose     = "gitlab-configuration"
    }
  )
}

resource "aws_secretsmanager_secret_version" "gitlab_url" {
  secret_id = aws_secretsmanager_secret.gitlab_url.id
  secret_string = var.gitlab_url != "" ? var.gitlab_url : "https://gitlab.com"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# API key secret
resource "aws_secretsmanager_secret" "api_key" {
  name        = "${var.project_name}/${var.environment}/api-key"
  description = "API key for HTTP endpoint authentication"

  kms_key_id = var.kms_key_id != "" ? var.kms_key_id : null

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-${var.environment}-api-key"
      Environment = var.environment
      Purpose     = "api-authentication"
    }
  )
}

resource "aws_secretsmanager_secret_version" "api_key" {
  secret_id = aws_secretsmanager_secret.api_key.id
  secret_string = var.api_key != "" ? var.api_key : "PLACEHOLDER_UPDATE_ME"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

