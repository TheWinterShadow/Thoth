# Thoth Documentation

This directory contains the Sphinx documentation for the Thoth project.

## Structure

```
docs/
├── source/              # Sphinx source files
│   ├── conf.py         # Sphinx configuration
│   ├── index.rst       # Main documentation index
│   ├── getting_started.rst
│   ├── api/            # Auto-generated API docs
│   │   ├── modules.rst
│   │   ├── thoth.rst
│   │   ├── mcp_server.rst
│   │   └── utils.rst
│   └── mcp_server/     # MCP server documentation
│       └── overview.rst
├── build/              # Built documentation (HTML)
├── *.md                # Markdown documentation files
├── Makefile            # Documentation build commands
└── README_DOCS.md      # This file
```

## Features

### Autodoc Support
- Automatically generates documentation from Python docstrings
- Supports Google and NumPy style docstrings
- Includes source code links

### Markdown Support
- All `.md` files in the docs directory are included
- Uses MyST Parser for rich Markdown features
- Supports GitHub Flavored Markdown extensions

### API Documentation
- Complete API reference auto-generated from code
- Module, class, and function documentation
- Inheritance diagrams and type annotations

## Building Documentation

### Using Hatch (Recommended)

```bash
# Build HTML documentation
hatch run docs:build

# Clean and rebuild
hatch run docs:clean

# Generate coverage report
hatch test --cov --cov-report=html:docs/build/coverage --cov-report=term

# Or use the script
hatch run cov-html
```

### Using Make

```bash
# Build HTML documentation
cd docs && make html

# Clean build directory
cd docs && make clean

# Live rebuild (with sphinx-autobuild)
cd docs && make livehtml
```

### Manual Build

```bash
sphinx-build -b html docs/source docs/build
```

## Viewing Documentation

After building, open `docs/build/index.html` in your browser:

```bash
# Linux/Mac
open docs/build/index.html

# Or use Python's built-in server
python -m http.server --directory docs/build
```

## Adding Documentation

### Adding Markdown Files

1. Create a `.md` file in the `docs/` directory
2. Add it to `docs/source/index.rst` in the appropriate toctree:

```rst
.. toctree::
   :maxdepth: 2
   :caption: Your Section:

   ../YOUR_FILE
```

### Adding Python Module Documentation

Python modules with proper docstrings are automatically included in the API reference.

**Docstring Example:**

```python
def my_function(param: str) -> str:
    """
    Short description.
    
    Longer description with more details about the function.
    
    Args:
        param: Description of parameter
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When something goes wrong
        
    Example:
        >>> my_function("test")
        'result'
    """
    return f"result: {param}"
```

### Creating New Documentation Pages

1. Create a new `.rst` file in `docs/source/`
2. Add content using reStructuredText
3. Include it in a toctree in `index.rst`

**Example RST:**

```rst
My New Page
===========

Introduction
------------

This is a new documentation page.

Code Example
------------

.. code-block:: python

   from thoth import something
   something.do_thing()
```

## Configuration

### Sphinx Configuration (`source/conf.py`)

Key settings:

- **Extensions**: autodoc, napoleon, myst_parser, viewcode, etc.
- **MyST Features**: Markdown parsing with extended features
- **Theme**: Alabaster with GitHub integration
- **AutoDoc**: Automatic API documentation generation

### Markdown Features

Enabled MyST extensions:

- ✅ Fenced code blocks with `::: syntax`
- ✅ Definition lists
- ✅ Task lists with checkboxes
- ✅ Auto-linkify URLs
- ✅ Smart quotes
- ✅ HTML admonitions

## Themes

Current theme: **Alabaster**

To change the theme, modify `html_theme` in `source/conf.py`:

```python
html_theme = "sphinx_rtd_theme"  # Read the Docs theme
# or
html_theme = "furo"              # Furo theme
```

Install theme dependencies in `pyproject.toml` if needed.

## Troubleshooting

### Import Errors

If Sphinx can't import your modules:

1. Check `sys.path` in `conf.py`
2. Ensure the package is installed: `pip install -e .`

### Missing Docstrings

If documentation is incomplete:

1. Add docstrings to your Python code
2. Use `:undoc-members:` option in RST files
3. Check `autodoc_default_options` in `conf.py`

### Markdown Not Rendering

If Markdown files aren't showing:

1. Verify `myst-parser` is installed
2. Check file path in toctree (relative to `source/`)
3. Ensure file extension is in `source_suffix`

## References

- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [MyST Parser](https://myst-parser.readthedocs.io/)
- [Alabaster Theme](https://alabaster.readthedocs.io/)
- [Google Style Docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
