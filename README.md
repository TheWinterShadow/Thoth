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

# Initialize the vector store
vector_store = VectorStore(
    persist_directory="./chroma_db",
    collection_name="handbook_docs"
)

# Add documents
documents = [
    "Python is a high-level programming language.",
    "JavaScript is used for web development.",
    "Machine learning is a subset of AI."
]
vector_store.add_documents(documents)

# Search for similar documents
results = vector_store.search_similar(
    query="programming languages",
    n_results=2
)
print(results["documents"])

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
├── ingestion/           # Data ingestion and processing
│   ├── __init__.py
│   ├── chunker.py       # Markdown document chunker
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
