# Dockerfile for Lambda container image (refresh service)

FROM public.ecr.aws/lambda/python:3.11

# Install system dependencies
RUN yum install -y git && \
    yum clean all && \
    rm -rf /var/cache/yum

# Copy requirements
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir \
    boto3>=1.28.0 \
    chromadb>=0.4.0,<0.6.0 \
    sentence-transformers>=2.2.0 \
    torch>=2.0.0,<2.6.0 \
    gitpython>=3.1.0 \
    pyyaml>=6.0

# Copy application code
COPY thoth/ ${LAMBDA_TASK_ROOT}/thoth/

# Set handler
CMD [ "thoth.refresh.handler.handler" ]

