# Development Guide

This guide provides information for developers who want to contribute to the Thoth project.

## Table of Contents

- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Release Process](#release-process)
- [Troubleshooting](#troubleshooting)

## Development Setup

### Prerequisites

- Python 3.10 to 3.12 (Python 3.13 is not yet supported by dependencies)
- Git
- A text editor or IDE (VS Code recommended)

### Environment Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/TheWinterShadow/Thoth.git
   cd Thoth
   ```

2. **Create a virtual environment**:
   ```bash
   # Using venv
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Or using conda
   conda create -n thoth python=3.11
   conda activate thoth
   ```

3. **Install development dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

4. **Verify installation**:
   ```bash
   python -c "import thoth; print(f'Thoth v{thoth.__version__} installed successfully!')"
   ```

### Development Tools

The development environment includes:

- **ruff**: Linting, formatting, and import sorting
- **mypy**: Static type checking
- **pytest**: Testing framework
- **pytest-asyncio**: Async test support
- **coverage**: Test coverage measurement
- **sphinx**: Documentation generation

## Development Workflow

### Git Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code standards below

3. **Run quality checks**:
   ```bash
   # Format code and fix linting issues
   ruff check --fix thoth/ tests/
   ruff format thoth/ tests/

   # Type checking
   mypy thoth/

   # Run tests
   pytest
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add new utility function for text processing"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   # Then create a Pull Request on GitHub
   ```

### Commit Message Guidelines

We follow conventional commit format:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Examples:
```
feat: add text normalization utility
fix: handle edge case in data processing
docs: update installation instructions
test: add tests for new utility functions
```

## Code Standards

### Python Style Guide

We follow PEP 8 with some modifications:

- Line length: 88 characters (Black default)
- Use double quotes for strings
- Use type hints for all public functions
- Use docstrings for all public functions and classes

### Type Hints

All public APIs must include type hints:

```python
from typing import List, Optional, Union, Dict, Any

def process_text(
    text: str, 
    normalize: bool = True,
    encoding: Optional[str] = None
) -> str:
    """Process text with optional normalization.
    
    Args:
        text: Input text to process
        normalize: Whether to normalize whitespace
        encoding: Text encoding (auto-detected if None)
        
    Returns:
        Processed text string
        
    Raises:
        ValueError: If text is empty
        UnicodeError: If encoding is invalid
    """
    if not text:
        raise ValueError("Text cannot be empty")
    
    # Implementation here
    return processed_text
```

### Documentation Standards

#### Docstring Format

Use Google-style docstrings:

```python
def example_function(param1: str, param2: int) -> bool:
    """Brief description of the function.
    
    Longer description if needed. This can span multiple
    lines and include more detailed explanations.
    
    Args:
        param1: Description of the first parameter
        param2: Description of the second parameter
        
    Returns:
        Description of the return value
        
    Raises:
        ValueError: When param2 is negative
        TypeError: When param1 is not a string
        
    Example:
        >>> result = example_function("hello", 42)
        >>> print(result)
        True
    """
    pass
```

#### Inline Comments

- Use inline comments sparingly
- Explain *why*, not *what*
- Keep comments up to date with code changes

### Code Organization

#### File Structure

```python
"""Module docstring explaining the purpose of this module."""

# Standard library imports
import os
import sys
from pathlib import Path

# Third-party imports (if any)
import requests

# Local imports
from thoth.shared.utils.logger import get_logger

# Constants
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3

# Type definitions
ResultType = Union[str, int, float]

# Main implementation
class UtilityClass:
    """Class implementation."""
    pass

def utility_function() -> None:
    """Function implementation."""
    pass
```

#### Import Organization

Use isort to organize imports:

1. Standard library imports
2. Third-party imports
3. Local imports

## Testing

### Test Structure

```
tests/
├── __init__.py
├── conftest.py             # Pytest configuration and fixtures
├── test_thoth.py           # Main package tests
├── ingestion/              # Ingestion module tests
│   ├── __init__.py
│   ├── test_chunker.py
│   ├── test_repo_manager.py
│   └── test_pipeline.py
├── mcp/                    # MCP server tests
│   ├── __init__.py
│   └── test_server.py
└── shared/                 # Shared utilities tests
    ├── __init__.py
    ├── test_embedder.py
    ├── test_vector_store.py
    └── test_gcs_sync.py
```

### Writing Tests

#### Test Naming

- Test files: `test_<module>.py`
- Test classes: `Test<ClassName>`
- Test methods: `test_<functionality>`

#### Test Examples

```python
import pytest
from thoth.shared.embedder import Embedder

class TestEmbedder:
    """Tests for the Embedder class."""

    def test_embed_single_document(self):
        """Test embedding a single document."""
        embedder = Embedder()
        embedding = embedder.embed_single("Hello world")
        assert len(embedding) > 0

    def test_embed_multiple_documents(self):
        """Test embedding multiple documents."""
        embedder = Embedder()
        embeddings = embedder.embed(["Doc 1", "Doc 2"])
        assert len(embeddings) == 2

    def test_embed_empty_string(self):
        """Test embedding an empty string."""
        embedder = Embedder()
        embedding = embedder.embed_single("")
        assert len(embedding) > 0  # Still returns embedding

    @pytest.mark.parametrize("text,expected_dim", [
        ("Short text", 384),
        ("Longer text with more words", 384),
    ])
    def test_embedding_dimensions(self, text, expected_dim):
        """Test embedding dimensions match expected size."""
        embedder = Embedder()
        embedding = embedder.embed_single(text)
        assert len(embedding) == expected_dim
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=thoth --cov-report=html

# Run specific test file
pytest tests/test_utils/test_text.py

# Run specific test
pytest tests/test_utils/test_text.py::TestTextUtilities::test_normalize_whitespace_basic

# Run tests in parallel
pytest -n auto
```

### Coverage Requirements

- Maintain >90% test coverage
- All new code must include tests
- Test both success and failure cases
- Include edge cases and boundary conditions

## Documentation

### Building Documentation

```bash
cd docs/
make html
# Open docs/build/html/index.html in browser
```

### Documentation Structure

- **README.md**: Project overview and quick start
- **docs/ARCHITECTURE.md**: Architecture and design decisions
- **docs/DEVELOPMENT.md**: This development guide
- **docs/source/**: Sphinx documentation source
- **CONTRIBUTING.md**: Contribution guidelines

### Adding API Documentation

Use Sphinx autodoc to generate API documentation from docstrings:

```python
# In docs/source/api.rst
API Reference
=============

.. automodule:: thoth.shared.embedder
   :members:
   :undoc-members:
   :show-inheritance:
```

## Release Process

### Version Management

Versions are managed in `thoth/__about__.py`:

```python
__version__ = "1.2.3"
```

### Release Checklist

1. **Update version number** in `__about__.py`
2. **Update CHANGELOG.md** with new features and fixes
3. **Run full test suite**: `pytest`
4. **Check code quality**: Run all linting tools
5. **Build documentation**: Ensure docs build without errors
6. **Create release commit**: `git commit -m "chore: release v1.2.3"`
7. **Tag release**: `git tag v1.2.3`
8. **Push to GitHub**: `git push origin main --tags`
9. **Build and publish**: GitHub Actions will handle PyPI publication

### Semantic Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking changes
- **MINOR** (0.1.0): New features, backward compatible
- **PATCH** (0.0.1): Bug fixes, backward compatible

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Reinstall in development mode
pip install -e ".[dev]"
```

#### Test Failures
```bash
# Run tests with verbose output
pytest -v

# Run specific failing test
pytest tests/test_specific.py::test_failing_function -v
```

#### Type Checking Errors
```bash
# Run mypy on specific file
mypy thoth/shared/embedder.py

# Ignore specific error (use sparingly)
# type: ignore[error-code]
```

#### Code Formatting Issues
```bash
# Auto-format code
black thoth/ tests/
ruff check --fix thoth/ tests/

# Check what would change without applying
black --check thoth/ tests/
ruff check thoth/ tests/
```

### Getting Help

- Check existing [GitHub Issues](https://github.com/TheWinterShadow/Thoth/issues)
- Read the [Contributing Guidelines](../CONTRIBUTING.md)
- Join the discussion in GitHub Discussions
- Contact the maintainers: elijah.j.winter@outlook.com

### Development Environment Debugging

#### VS Code Configuration

Create `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "ruff.lint.enable": true,
    "python.linting.mypyEnabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"],
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
        "source.organizeImports": true
    }
}
```

#### Pre-commit Hooks

Install pre-commit hooks to automatically check code before commits:

```bash
pip install pre-commit
pre-commit install
```

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.1
    hooks:
      - id: mypy
        additional_dependencies:
          - types-requests

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.2
    hooks:
      - id: gitleaks
```

This development guide should provide everything needed to contribute effectively to the Thoth project. Happy coding!