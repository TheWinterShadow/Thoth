output "secret_arns" {
  description = "Map of secret names to ARNs"
  value = {
    "gitlab-token" = aws_secretsmanager_secret.gitlab_token.arn
    "gitlab-url"   = aws_secretsmanager_secret.gitlab_url.arn
    "api-key"      = aws_secretsmanager_secret.api_key.arn
  }
}

output "secret_names" {
  description = "Map of secret names to full names"
  value = {
    "gitlab-token" = aws_secretsmanager_secret.gitlab_token.name
    "gitlab-url"   = aws_secretsmanager_secret.gitlab_url.name
    "api-key"      = aws_secretsmanager_secret.api_key.name
  }
}

