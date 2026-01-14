"""Pytest configuration and fixtures."""

import os
from unittest.mock import MagicMock

import boto3
import pytest

# Try moto 4.0+ imports first, fall back to older imports
try:
    from moto import mock_aws

    # Use mock_aws for moto 4.0+ (mocks all AWS services)
    _MOTO_VERSION_4_PLUS = True
except ImportError:
    # Fall back to individual mocks for older moto versions
    try:
        from moto import mock_dynamodb, mock_s3, mock_secretsmanager

        _MOTO_VERSION_4_PLUS = False
    except ImportError:
        # Try submodule imports as last resort
        from moto.mock_dynamodb import mock_dynamodb
        from moto.mock_s3 import mock_s3
        from moto.mock_secretsmanager import mock_secretsmanager

        _MOTO_VERSION_4_PLUS = False


@pytest.fixture
def aws_credentials():
    """Mock AWS credentials."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def s3_client(aws_credentials):
    """Mock S3 client."""
    if _MOTO_VERSION_4_PLUS:
        with mock_aws():
            yield boto3.client("s3", region_name="us-east-1")
    else:
        with mock_s3():
            yield boto3.client("s3", region_name="us-east-1")


@pytest.fixture
def s3_bucket(s3_client):
    """Create a test S3 bucket."""
    bucket_name = "test-thoth-bucket"
    s3_client.create_bucket(Bucket=bucket_name)
    return bucket_name


@pytest.fixture
def secrets_manager_client(aws_credentials):
    """Mock Secrets Manager client."""
    if _MOTO_VERSION_4_PLUS:
        with mock_aws():
            yield boto3.client("secretsmanager", region_name="us-east-1")
    else:
        with mock_secretsmanager():
            yield boto3.client("secretsmanager", region_name="us-east-1")


@pytest.fixture
def dynamodb_client(aws_credentials):
    """Mock DynamoDB client."""
    if _MOTO_VERSION_4_PLUS:
        with mock_aws():
            yield boto3.client("dynamodb", region_name="us-east-1")
    else:
        with mock_dynamodb():
            yield boto3.client("dynamodb", region_name="us-east-1")


@pytest.fixture
def lambda_event():
    """Sample Lambda event from API Gateway."""
    return {
        "version": "2.0",
        "routeKey": "GET /health",
        "rawPath": "/health",
        "headers": {
            "content-type": "application/json",
        },
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/health",
            },
            "requestId": "test-request-id",
        },
    }


@pytest.fixture
def lambda_context():
    """Mock Lambda context."""
    context = MagicMock()
    context.function_name = "test-function"
    context.function_version = "$LATEST"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
    context.memory_limit_in_mb = 512
    context.aws_request_id = "test-request-id"
    return context
