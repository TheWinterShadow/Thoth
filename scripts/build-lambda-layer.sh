#!/bin/bash
# Build script for Lambda layer

set -e

LAYER_NAME="thoth-mcp-layer"
PYTHON_VERSION="3.11"
BUILD_DIR="lambda-layers/${LAYER_NAME}"
PACKAGE_DIR="${BUILD_DIR}/python"

echo "Building Lambda layer: ${LAYER_NAME}"

# Clean previous build
rm -rf "${BUILD_DIR}"
mkdir -p "${PACKAGE_DIR}"

# Install dependencies to package directory
pip install \
    --platform manylinux2014_x86_64 \
    --target "${PACKAGE_DIR}" \
    --implementation cp \
    --python-version "${PYTHON_VERSION}" \
    --only-binary=:all: \
    --upgrade \
    mcp \
    starlette \
    chromadb \
    sentence-transformers \
    torch \
    boto3 \
    pyyaml

# Create zip file
cd "${BUILD_DIR}"
zip -r "../${LAYER_NAME}.zip" python/

echo "Lambda layer built: lambda-layers/${LAYER_NAME}.zip"

