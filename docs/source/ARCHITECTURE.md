# Thoth Architecture

This document describes the architecture and design decisions behind the Thoth library.

## Overview

Thoth is designed as a modular Python library that provides utilities and tools for developers. The architecture emphasizes:

- **Modularity**: Each utility is self-contained and can be used independently
- **Type Safety**: Full type annotations throughout the codebase
- **Performance**: Efficient implementations with minimal overhead
- **Extensibility**: Easy to add new utilities without affecting existing code
- **Maintainability**: Clear separation of concerns and well-defined interfaces

## Project Structure

```
thoth/
├── __init__.py          # Main package entry point, version exports
├── __about__.py         # Version and metadata information
└── utils/               # Utility modules collection
    ├── __init__.py      # Utils package initialization
    ├── text.py          # Text processing utilities (planned)
    ├── data.py          # Data manipulation utilities (planned)
    ├── io.py            # Input/output utilities (planned)
    └── system.py        # System interaction utilities (planned)

docs/                    # Documentation
├── ARCHITECTURE.md      # This file
├── DEVELOPMENT.md       # Development guidelines
└── source/              # Sphinx documentation source
    ├── conf.py
    └── index.rst

tests/                   # Test suite
├── __init__.py
├── test_thoth.py        # Main package tests
└── test_utils/          # Utilities tests (planned)
    ├── __init__.py
    ├── test_text.py
    ├── test_data.py
    ├── test_io.py
    └── test_system.py

pyproject.toml          # Project configuration
CONTRIBUTING.md         # Contribution guidelines
LICENSE                 # MIT License
README.md               # Project overview
```

## Design Principles

### 1. Zero-Dependency Core

The core Thoth package has no external dependencies, ensuring:
- Minimal installation footprint
- Reduced dependency conflicts
- Faster installation times
- Greater reliability

Optional dependencies can be added for specific utilities that require them.

### 2. Type Safety

All public APIs include comprehensive type hints:
```python
from typing import TypeVar, Generic, Optional, Union, List, Dict

T = TypeVar('T')

def process_data(data: List[T], transform: Optional[callable] = None) -> List[T]:
    """Process data with optional transformation."""
    if transform is None:
        return data[:]
    return [transform(item) for item in data]
```

### 3. Modular Design

Each utility module is independent and can be imported separately:
```python
# Import specific utilities
from thoth.utils.text import normalize_whitespace
from thoth.utils.data import flatten_dict

# Or import collections
from thoth.utils import text, data
```

### 4. Consistent API Design

All utilities follow consistent patterns:
- Clear, descriptive function names
- Comprehensive docstrings with examples
- Consistent parameter naming conventions
- Predictable return types
- Proper error handling

### 5. Performance Considerations

- Use built-in Python functions when possible
- Implement custom solutions only when necessary
- Profile critical paths
- Provide both simple and optimized versions when appropriate

## Module Organization

### Core Package (`thoth/`)

The main package contains:
- `__init__.py`: Package initialization and version exports
- `__about__.py`: Version and metadata (following modern Python practices)

### Utilities Package (`thoth/utils/`)

Organized by functional domain:

- **Text Utilities** (`text.py`): String manipulation, formatting, parsing
- **Data Utilities** (`data.py`): Data structure manipulation, transformations
- **I/O Utilities** (`io.py`): File operations, serialization, data loading
- **System Utilities** (`system.py`): OS interactions, environment handling

### Testing Strategy

- Unit tests for each utility function
- Integration tests for complex interactions
- Property-based testing for data transformations
- Performance benchmarks for critical functions

## Extension Points

### Adding New Utilities

1. Create new module in `thoth/utils/`
2. Follow the established patterns and type hints
3. Add comprehensive tests
4. Update documentation
5. Export in `thoth/utils/__init__.py`

### Plugin Architecture (Future)

The architecture is designed to support plugins:
```python
# Future plugin example
from thoth.plugins import register_plugin

@register_plugin('custom_utils')
class CustomUtilities:
    def custom_function(self, data):
        pass
```

## Dependencies Management

### Core Dependencies
- Python 3.9+ (for modern type hints and performance)
- No external runtime dependencies

### Development Dependencies
- `black`: Code formatting
- `isort`: Import sorting
- `flake8`: Linting
- `mypy`: Type checking
- `pytest`: Testing framework
- `coverage`: Test coverage
- `sphinx`: Documentation generation

### Optional Dependencies
Future utilities may introduce optional dependencies:
```toml
[project.optional-dependencies]
data = ["pandas>=1.0", "numpy>=1.20"]
web = ["requests>=2.25", "beautifulsoup4>=4.9"]
dev = ["black", "isort", "flake8", "mypy", "pytest", "coverage"]
```

## Configuration

### Type Checking Configuration
```ini
# mypy.ini
[mypy]
python_version = 3.9
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
```

### Code Style Configuration
```toml
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py39']

[tool.ruff]
line-length = 88
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.ruff.lint.isort]
known-first-party = ["thoth"]
```

## Future Considerations

### Async Support
Some utilities may benefit from async versions:
```python
async def async_process_files(files: List[Path]) -> List[Result]:
    """Async version of file processing."""
    pass
```

### C Extensions
Performance-critical utilities might use C extensions:
```python
try:
    from thoth._speedups import fast_algorithm
except ImportError:
    from thoth._fallback import fast_algorithm
```

### Compatibility
- Maintain backward compatibility within major versions
- Use deprecation warnings for breaking changes
- Follow semantic versioning

This architecture provides a solid foundation for growth while maintaining simplicity and usability.