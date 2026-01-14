# Lambda Deployment Guide

This guide covers deploying Thoth components to AWS Lambda.

## Deployment Strategies

### MCP Server: Lambda Layers

The MCP server uses Lambda layers for:
- Faster cold starts
- Smaller package size
- Easier dependency management

**Build Layer:**

```bash
./scripts/build-lambda-layer.sh
```

This creates `lambda-layers/thoth-mcp-layer.zip` with all dependencies.

**Deploy Layer:**

```bash
aws lambda publish-layer-version \
  --layer-name thoth-mcp-layer \
  --zip-file fileb://lambda-layers/thoth-mcp-layer.zip \
  --compatible-runtimes python3.11
```

**Attach to Function:**

```bash
aws lambda update-function-configuration \
  --function-name thoth-dev-mcp-server \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:thoth-mcp-layer:VERSION
```

### Refresh Service: Container Image

The refresh service uses a container image because:
- Includes full ingestion pipeline
- Larger dependencies (torch, sentence-transformers)
- Less frequent updates

**Build Image:**

```bash
docker build -t thoth-mcp:latest -f lambda/Dockerfile .
```

**Push to ECR:**

```bash
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.us-east-1.amazonaws.com

docker tag thoth-mcp:latest ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/thoth-mcp:latest
docker push ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/thoth-mcp:latest
```

**Update Function:**

```bash
aws lambda update-function-code \
  --function-name thoth-dev-refresh-service \
  --image-uri ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/thoth-mcp:latest
```

## Function Configuration

### Memory and Timeout

**MCP Server:**
- Memory: 512MB-1GB
- Timeout: 15 minutes (max)

**Refresh Service:**
- Memory: 2GB-4GB
- Timeout: 15 minutes (max)

### Environment Variables

Set via Terraform or AWS CLI:

```bash
aws lambda update-function-configuration \
  --function-name thoth-dev-mcp-server \
  --environment Variables={
    ENVIRONMENT=dev,
    S3_BUCKET_NAME=thoth-storage-bucket,
    DYNAMODB_TABLE_NAME=thoth-dev-mcp-state,
    LOG_LEVEL=INFO
  }
```

## Cold Start Optimization

1. **Use Lambda Layers**: Reduces package size
2. **Minimize Dependencies**: Only include what's needed
3. **Lazy Loading**: Load plugins on first use
4. **Provisioned Concurrency**: For critical functions (cost trade-off)

## Testing Locally

### Test Lambda Handler

```python
import json
from thoth.mcp_server.lambda_handler import handler

event = {
    "requestContext": {
        "http": {
            "method": "GET"
        }
    },
    "rawPath": "/health"
}

response = handler(event, None)
print(json.dumps(response, indent=2))
```

### Test with SAM Local

```bash
sam local invoke MCPServerFunction --event test-event.json
```

## Monitoring

### CloudWatch Metrics

- Invocations
- Errors
- Duration
- Throttles

### CloudWatch Logs

```bash
aws logs tail /aws/lambda/thoth-dev-mcp-server --follow
```

## Troubleshooting

### Import Errors

- Check layer includes all dependencies
- Verify Python version matches
- Check import paths

### Timeout Issues

- Increase timeout
- Optimize code
- Check external dependencies

### Memory Issues

- Increase memory allocation
- Optimize data structures
- Check for memory leaks

