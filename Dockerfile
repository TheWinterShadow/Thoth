# ==============================================================================
# Multi-Stage Dockerfile for Thoth MCP Server
# Optimized for minimal image size with CPU-only PyTorch
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder - Install dependencies and build the application
# ------------------------------------------------------------------------------
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /build

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy only necessary files first to leverage Docker cache
COPY pyproject.toml README.md ./
COPY thoth/__about__.py ./thoth/__about__.py

# Install CPU-only PyTorch first (much smaller than default GPU version)
# Use --index-url to ensure we get CPU-only versions
# Install torch BEFORE other dependencies to avoid pulling GPU version
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "torch>=2.0.0,<2.6.0" \
        --index-url https://download.pytorch.org/whl/cpu

# Now install the application (this will skip torch since it's already installed)
RUN pip install --no-cache-dir .

# Copy the entire application
COPY . .

# ------------------------------------------------------------------------------
# Stage 2: Runtime - Create minimal runtime image
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install only runtime system dependencies (git for repository cloning)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /build/thoth /app/thoth

# Create necessary directories for data persistence
RUN mkdir -p /app/data/chroma_db /app/data/handbook_vectors /app/data/handbook_repo

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# MCP uses stdio transport by default, so no ports are exposed here.
# If you configure the server to use TCP transport instead, you may add:
# EXPOSE 8000

# Set the entrypoint to run the MCP server
ENTRYPOINT ["python", "-m", "thoth.mcp_server.server"]

# Health check to verify the container is running
# This checks if the Python process is alive
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"
