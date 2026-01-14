# AWS Deployment Guide

This guide covers deploying the Thoth MCP server to AWS using Lambda and API Gateway.

## Architecture

The Thoth MCP server is deployed on AWS using a serverless architecture:

- **API Gateway HTTP API**: Entry point for HTTP requests
- **AWS Lambda**: Serverless compute for MCP server and refresh service
- **Amazon S3**: Storage for vector database backups
- **AWS Secrets Manager**: Secure credential storage
- **Amazon DynamoDB**: Connection state and caching
- **Amazon EventBridge**: Scheduled jobs for data refresh
- **Amazon ECR**: Container image registry

## Prerequisites

1. AWS Account with appropriate permissions
2. Terraform >= 1.0 installed
3. AWS CLI configured
4. Docker (for container images)

## Initial Setup

### 1. Bootstrap Terraform Backend

First, create the S3 bucket and DynamoDB table for Terraform state:

```bash
cd infra/bootstrap
terraform init
terraform apply \
  -var="region=us-east-1" \
  -var="environment=dev"
```

This creates:
- S3 bucket: `thoth-terraform-state`
- DynamoDB table: `thoth-terraform-state-lock`

### 2. Configure Backend

Update `infra/backend.tf` or use backend config:

```bash
cd infra
terraform init \
  -backend-config="bucket=thoth-terraform-state" \
  -backend-config="key=terraform/state" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=thoth-terraform-state-lock"
```

### 3. Deploy Infrastructure

```bash
terraform plan \
  -var="aws_region=us-east-1" \
  -var="environment=dev"

terraform apply \
  -var="aws_region=us-east-1" \
  -var="environment=dev"
```

### 4. Set Secrets

After infrastructure is deployed, set secrets in AWS Secrets Manager:

```bash
# GitLab token
aws secretsmanager put-secret-value \
  --secret-id thoth/dev/gitlab-token \
  --secret-string "YOUR_GITLAB_TOKEN"

# GitLab URL
aws secretsmanager put-secret-value \
  --secret-id thoth/dev/gitlab-url \
  --secret-string "https://gitlab.com"

# API key
aws secretsmanager put-secret-value \
  --secret-id thoth/dev/api-key \
  --secret-string "YOUR_API_KEY"
```

## Lambda Deployment

### MCP Server (Lambda Layers)

The MCP server uses Lambda layers for faster cold starts:

```bash
# Build layer
./scripts/build-lambda-layer.sh

# Deploy layer
aws lambda publish-layer-version \
  --layer-name thoth-mcp-layer \
  --zip-file fileb://lambda-layers/thoth-mcp-layer.zip \
  --compatible-runtimes python3.11

# Update function to use layer
aws lambda update-function-configuration \
  --function-name thoth-dev-mcp-server \
  --layers arn:aws:lambda:us-east-1:ACCOUNT:layer:thoth-mcp-layer:VERSION
```

### Refresh Service (Container Image)

The refresh service uses a container image:

```bash
# Build and push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

docker build -t thoth-mcp:latest -f lambda/Dockerfile .
docker tag thoth-mcp:latest ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/thoth-mcp:latest
docker push ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/thoth-mcp:latest

# Update Lambda function
aws lambda update-function-code \
  --function-name thoth-dev-refresh-service \
  --image-uri ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/thoth-mcp:latest
```

## Configuration

### Environment Variables

Lambda functions use environment variables:

- `ENVIRONMENT`: Environment name (dev, staging, prod)
- `S3_BUCKET_NAME`: S3 bucket for vector DB storage
- `DYNAMODB_TABLE_NAME`: DynamoDB table for state
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

### MCP Server Configuration

Create `config.yaml`:

```yaml
rag:
  setups:
    - name: handbook
      plugin_type: handbook
      config:
        persist_directory: /tmp/chroma_db
        collection_name: thoth_documents
        s3_bucket_name: thoth-storage-bucket
        s3_region: us-east-1

plugins:
  file_operations:
    base_path: /tmp/files
  handbook_tools:
    default_rag_setup: handbook
```

## Monitoring

### CloudWatch Logs

View logs:

```bash
aws logs tail /aws/lambda/thoth-dev-mcp-server --follow
aws logs tail /aws/lambda/thoth-dev-refresh-service --follow
```

### CloudWatch Metrics

Monitor:
- Lambda invocations
- Lambda errors
- Lambda duration
- API Gateway requests
- API Gateway errors

## Troubleshooting

### Lambda Cold Starts

- Use Lambda layers for MCP server
- Optimize package size
- Consider provisioned concurrency (cost trade-off)

### API Gateway Errors

- Check Lambda function logs
- Verify IAM permissions
- Check API Gateway integration settings

### S3 Access Issues

- Verify IAM role permissions
- Check bucket policies
- Ensure bucket exists

## Cost Optimization

For low traffic (~1000 requests/month):

- **API Gateway**: Free tier (1M requests)
- **Lambda**: Free tier (1M requests, 400K GB-seconds)
- **S3**: Free tier (5GB storage)
- **Total**: ~$0.00-0.50/month

## CI/CD

See `.github/workflows/infra-deploy.yml` for automated deployment.

## Rollback

To rollback a Lambda function:

```bash
# List versions
aws lambda list-versions-by-function --function-name thoth-dev-mcp-server

# Update to previous version
aws lambda update-function-configuration \
  --function-name thoth-dev-mcp-server \
  --function-version PREVIOUS_VERSION
```

