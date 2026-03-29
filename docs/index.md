# Thoth

[![PyPI version](https://badge.fury.io/py/thoth.svg)](https://badge.fury.io/py/thoth)
[![Python versions](https://img.shields.io/pypi/pyversions/thoth.svg)](https://pypi.org/project/thoth/)
[![Build Status](https://github.com/TheWinterShadow/Thoth/workflows/CI/badge.svg)](https://github.com/TheWinterShadow/Thoth/actions)
[![Coverage Status](https://codecov.io/gh/TheWinterShadow/Thoth/branch/main/graph/badge.svg)](https://codecov.io/gh/TheWinterShadow/Thoth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Thoth is a modern Python library providing advanced utilities and tools for developers. Named after the ancient Egyptian god of wisdom and writing, Thoth aims to bring clarity and structure to your Python projects through well-designed, modular utilities.

## 🚀 Features

- **Repository Management**: Clone and track GitLab handbook repository with automated updates
- **Vector Database**: LanceDB integration for storing and querying document embeddings with semantic search
- **Cloud Storage**: Google Cloud Storage integration for vector DB persistence and backup
- **Embedding Generation**: Efficient batch embedding generation using sentence-transformers models
- **Cloud Deployment**: Ready-to-deploy to Google Cloud Run with automated deployment scripts
- **MCP Server**: Model Context Protocol server for AI assistant integration
- **Modular Design**: Clean, composable utility functions
- **Type Safety**: Full type annotations with mypy support
- **High Performance**: Optimized implementations for common tasks
- **Easy Integration**: Minimal dependencies with optional extensions
- **Well Documented**: Comprehensive documentation and examples
- **Thoroughly Tested**: Extensive test coverage with automated CI/CD

## 📦 Installation

### From PyPI (Recommended)

```bash
pip install thoth
```

### CPU-Only Installation (Faster, Smaller)

For CPU-only PyTorch (recommended for most use cases):

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install thoth
