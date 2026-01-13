# Thoth

[![PyPI version](https://badge.fury.io/py/thoth.svg)](https://badge.fury.io/py/thoth)
[![Python versions](https://img.shields.io/pypi/pyversions/thoth.svg)](https://pypi.org/project/thoth/)
[![Build Status](https://github.com/TheWinterShadow/Thoth/workflows/CI/badge.svg)](https://github.com/TheWinterShadow/Thoth/actions)
[![Coverage Status](https://codecov.io/gh/TheWinterShadow/Thoth/branch/main/graph/badge.svg)](https://codecov.io/gh/TheWinterShadow/Thoth)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Thoth is a modern Python library providing advanced utilities and tools for developers. Named after the ancient Egyptian god of wisdom and writing, Thoth aims to bring clarity and structure to your Python projects through well-designed, modular utilities.

## 🚀 Features

- **Repository Management**: Clone and track GitLab handbook repository with automated updates
- **Vector Database**: ChromaDB integration for storing and querying document embeddings with semantic search
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
```

### Development Installation

```bash
git clone https://github.com/TheWinterShadow/Thoth.git
cd Thoth
pip install -e ".[dev]"
```

## 🏃‍♂️ Quick Start

### Repository Management

```python
from thoth.ingestion.repo_manager import HandbookRepoManager

# Initialize the repository manager
manager = HandbookRepoManager()

# Clone the GitLab handbook repository
repo_path = manager.clone_handbook()
print(f"Repository cloned to: {repo_path}")

# Get current commit and save metadata
commit_sha = manager.get_current_commit()
manager.save_metadata(commit_sha)

# Update repository and check for changes
manager.update_repository()
metadata = manager.load_metadata()
if metadata:
    changed_files = manager.get_changed_files(metadata["commit_sha"])
    print(f"Changed files: {changed_files}")
```

### Vector Store

```python
from thoth.ingestion.vector_store import VectorStore

# Initialize the vector store (uses all-MiniLM-L6-v2 by default)
vector_store = VectorStore(
    persist_directory="./chroma_db",
    collection_name="handbook_docs"
)

# Initialize with Google Cloud Storage backup (optional)
vector_store_with_gcs = VectorStore(
    persist_directory="./chroma_db",
    collection_name="handbook_docs",
    gcs_bucket_name="thoth-storage-bucket",
    gcs_project_id="thoth-483015"
)

# Add documents - embeddings are automatically generated
documents = [
    "Python is a high-level programming language.",
    "JavaScript is used for web development.",
    "Machine learning is a subset of AI."
]
vector_store.add_documents(documents)

# Search for similar documents using semantic similarity
results = vector_store.search_similar(
    query="programming languages",
    n_results=2
)
print(results["documents"])

# Backup to Google Cloud Storage
backup_name = vector_store_with_gcs.backup_to_gcs()
print(f"Backup created: {backup_name}")

# Restore from backup
vector_store_with_gcs.restore_from_gcs(backup_name="backup_20260112_120000")

# Add documents with metadata for filtering
vector_store.add_documents(
    documents=["Python tutorial", "Advanced Python"],
    metadatas=[
        {"language": "python", "level": "beginner"},
        {"language": "python", "level": "advanced"}
    ]
)

# Search with filters
results = vector_store.search_similar(
    query="Python guide",
    where={"level": "beginner"}
)
```

### Embedding Generation

```python
from thoth.ingestion.embedder import Embedder

# Initialize embedder with default model (all-MiniLM-L6-v2)
embedder = Embedder()

# Generate embeddings for texts
texts = ["Document 1", "Document 2", "Document 3"]
embeddings = embedder.embed(texts, show_progress=True)

# Generate single embedding
embedding = embedder.embed_single("Single document")

# Get model information
info = embedder.get_model_info()
print(f"Embedding dimension: {info['embedding_dimension']}")

# Use alternative model for higher quality
high_quality_embedder = Embedder(model_name="all-mpnet-base-v2")
embeddings = high_quality_embedder.embed(texts)
```

### MCP Server

```python
import thoth
from thoth.utils import (
    # Utility functions will be available here
    # as the project develops
)

# Example usage will be added as features are implemented
print(f"Thoth v{thoth.__version__} - Ready to enhance your Python experience!")
```

## 🏗️ Project Architecture

Thoth follows a modular architecture designed for extensibility and maintainability.

```
thoth/
├── __init__.py          # Main package entry point
├── __about__.py         # Version and metadata
├── health.py            # Health check for Cloud Run deployments
├── ingestion/           # Data ingestion and processing
│   ├── __init__.py
│   ├── chunker.py       # Markdown document chunker
│   ├── embedder.py      # Embedding generation with sentence-transformers
│   ├── gcs_sync.py      # Google Cloud Storage sync for vector DB
│   ├── repo_manager.py  # GitLab handbook repository manager
│   └── vector_store.py  # ChromaDB vector database wrapper
├── mcp_server/          # MCP server implementation
│   ├── __init__.py
│   └── server.py        # Main MCP server
└── utils/               # Utility modules
    ├── __init__.py
    └── logger.py        # Logging utilities
```

For detailed information about the project structure and design decisions, see the [Architecture Guide](https://thewintershadow.github.io/Thoth/ARCHITECTURE.html).

## 🛠️ Development

Interested in contributing? See the [Development Guide](https://thewintershadow.github.io/Thoth/DEVELOPMENT.html) for information on:

- Setting up the development environment
- Code style guidelines
- Testing procedures
- Release workflow

Also check out our [Contributing Guide](CONTRIBUTING.md) for guidelines on submitting pull requests.

## ☁️ Cloud Deployment

Thoth can be deployed to Google Cloud Run for scalable, serverless operation:

```bash
# Quick deployment
./scripts/deploy_cloud_run.sh

# Verify deployment
./scripts/verify_deployment.sh
```

For detailed deployment instructions, see:
- [Cloud Run Deployment Guide](docs/CLOUD_RUN_DEPLOYMENT.md)
- [Environment Configuration](docs/ENVIRONMENT_CONFIG.md)
- [GitHub Actions CI/CD Setup](docs/GITHUB_ACTIONS.md)

Key features:
- Automated deployment with Terraform or gcloud CLI
- GitHub Actions workflows for CI/CD
- Google Cloud Storage integration for vector DB persistence
- Auto-scaling from 0 to 10 instances
- Built-in health checks and monitoring
- Secure service account with minimal permissions

### CI/CD with GitHub Actions

The repository includes automated workflows for continuous integration and deployment:

- **Infrastructure & Cloud Run Deploy**: Automatically provisions GCP infrastructure and deploys to Cloud Run on push to main
- **Continuous Delivery**: Publishes to PyPI and deploys infrastructure on releases
- **CI**: Runs tests and quality checks on all pull requests
- **Documentation**: Builds and deploys Sphinx documentation
- **Security**: CodeQL static analysis for vulnerability detection

See [GitHub Actions Setup Guide](docs/GITHUB_ACTIONS.md) for detailed configuration and usage.

## 📖 Documentation

### Online Documentation
- **[Full Documentation](https://thewintershadow.github.io/Thoth/)** - Complete API docs and guides
- **[API Reference](https://thewintershadow.github.io/Thoth/api/modules.html)** - Auto-generated API documentation
- **[Architecture Guide](https://thewintershadow.github.io/Thoth/ARCHITECTURE.html)** - System design and structure
- **[Development Guide](https://thewintershadow.github.io/Thoth/DEVELOPMENT.html)** - Contributing and development workflow
- **[MCP Tools](https://thewintershadow.github.io/Thoth/MCP_TOOLS.html)** - Model Context Protocol tools reference
- **[Test Coverage](https://thewintershadow.github.io/Thoth/TEST_COVERAGE.html)** - Testing strategy and coverage
- **[Coverage Report](https://thewintershadow.github.io/Thoth/coverage/index.html)** - Live test coverage report

### Local Documentation
Build and view documentation locally:

```bash
# Build documentation
hatch run docs:build

# View documentation
open docs/build/index.html
```

For a complete documentation index, see [docs/README.md](docs/README.md).

## 🐛 Issues and Feature Requests

Found a bug or have a feature request? Please check the [issue tracker](https://github.com/TheWinterShadow/Thoth/issues) and create a new issue if needed.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Named after Thoth, the ancient Egyptian deity of wisdom, writing, and judgment
- Inspired by the Python community's commitment to readable, maintainable code
- Built with modern Python development practices in mind

---

**Thoth** - *Bringing wisdom to your Python code*
