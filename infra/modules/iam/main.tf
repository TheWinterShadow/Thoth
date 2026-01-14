# IAM role and policies module

# IAM role
resource "aws_iam_role" "this" {
  name        = var.role_name
  description = var.role_description

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = var.service_principal
        }
        Action = "sts:AssumeRole"
      },
    ]
  })

  tags = merge(
    var.tags,
    {
      Name        = var.role_name
      Environment = var.environment
      Service     = var.service_name
    }
  )
}

# IAM policies
resource "aws_iam_role_policy" "this" {
  for_each = { for idx, policy in var.policies : policy.name => policy }

  name   = "${var.role_name}-${each.value.name}"
  role   = aws_iam_role.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = each.value.statements
  })
}

# CloudWatch Logs policy (always added for Lambda)
resource "aws_iam_role_policy" "cloudwatch_logs" {
  count = var.add_cloudwatch_logs_policy ? 1 : 0

  name = "${var.role_name}-cloudwatch-logs"
  role = aws_iam_role.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
    ]
  })
}

