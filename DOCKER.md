# Docker Deployment Guide for Thoth MCP Server

This document provides instructions for deploying the Thoth MCP Server using Docker.

## Quick Start

### Building the Image

```bash
docker build -t thoth-mcp:latest .
```

The Docker image is optimized for production with:
- **Multi-stage build** for minimal image size
- **CPU-only PyTorch** to reduce image size and dependencies
- **Slim base image** (python:3.11-slim)
- Layer caching for faster rebuilds

### Running the Container

#### Using Docker CLI

```bash
docker run -d \
  --name thoth-mcp-server \
  -v $(pwd)/handbook_vectors:/app/data/handbook_vectors \
  -v $(pwd)/chroma_db:/app/data/chroma_db \
  -v $(pwd)/handbook_repo:/app/data/handbook_repo \
  -e HANDBOOK_DB_PATH=/app/data/handbook_vectors \
  thoth-mcp:latest
```

#### Using Docker Compose

```bash
docker-compose up -d
```

To build and run in one command:

```bash
docker-compose up -d --build
```

## Volume Mounts

The container uses three persistent volumes:

- `/app/data/chroma_db` - ChromaDB database for vector storage
- `/app/data/handbook_vectors` - Handbook embeddings and vectors
- `/app/data/handbook_repo` - Cloned handbook repository

Mount these to your host filesystem to persist data across container restarts.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONUNBUFFERED` | `1` | Enable Python unbuffered output |
| `PYTHONDONTWRITEBYTECODE` | `1` | Prevent Python from writing `.pyc` files |
| `HANDBOOK_DB_PATH` | `/app/data/handbook_vectors` | Path to handbook vector database |

## Image Size

The optimized image size is approximately **1.6-1.7 GB**, reduced from ~6.2 GB when using GPU (CUDA) dependencies.

Optimization techniques used:
1. **Multi-stage build** - Build dependencies are discarded in the final image
2. **CPU-only PyTorch** - No CUDA libraries (~2.5 GB savings)
3. **Minimal base image** - Using `python:3.11-slim` instead of full image
4. **Layer optimization** - Dependencies installed before application code
5. **`.dockerignore`** - Excludes unnecessary files from build context

## Health Checks

The container includes a health check that runs every 30 seconds to verify the Python environment is functioning.

View health status:
```bash
docker inspect --format='{{.State.Health.Status}}' thoth-mcp-server
```

## Logs

View container logs:
```bash
docker logs thoth-mcp-server
```

Follow logs in real-time:
```bash
docker logs -f thoth-mcp-server
```

## Stopping and Removing

```bash
# Stop the container
docker stop thoth-mcp-server

# Remove the container
docker rm thoth-mcp-server

# Remove the image
docker rmi thoth-mcp:latest
```

With Docker Compose:
```bash
docker-compose down
```

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker logs thoth-mcp-server
```

### Out of Memory

Increase Docker memory limits in Docker Desktop settings or add resource limits to docker-compose.yml:

```yaml
deploy:
  resources:
    limits:
      memory: 4G
```

### Volume Permission Issues

Ensure the volume directories exist and have proper permissions:
```bash
mkdir -p handbook_vectors chroma_db handbook_repo
chmod 755 handbook_vectors chroma_db handbook_repo
```

## Production Considerations

1. **Resource Limits**: Set appropriate CPU and memory limits
2. **Logging**: Configure log rotation to prevent disk space issues
3. **Monitoring**: Use Docker health checks and monitoring tools
4. **Updates**: Regularly rebuild images with security patches
5. **Backups**: Regularly backup volume data

## Building for Different Architectures

For ARM-based systems (e.g., Apple Silicon):
```bash
docker buildx build --platform linux/arm64 -t thoth-mcp:latest .
```

For multi-platform builds:
```bash
docker buildx build --platform linux/amd64,linux/arm64 -t thoth-mcp:latest .
```
