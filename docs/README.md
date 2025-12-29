# Documentation

This directory contains the Sphinx documentation.

## Building Documentation

To build the documentation:

```bash
# Build documentation
hatch run dev:docs

# Clean build (rebuild everything)
hatch run dev:docs-clean

# Serve documentation locally on port 8000
hatch run dev:docs-serve
```

## Structure

- `source/` - Documentation source files
  - `conf.py` - Sphinx configuration
  - `index.rst` - Main documentation page
  - `installation.rst` - Installation instructions
  - `usage.rst` - Usage examples and CLI reference
  - `api.rst` - API documentation (auto-generated)
  - `development.rst` - Development and contributing guide
  - `_static/` - Static files (CSS, images, etc.)
  - `_templates/` - Custom Sphinx templates
- `build/` - Generated HTML documentation (gitignored)

## Viewing Documentation

After building, open `build/index.html` in your browser or use the serve command:

```bash
hatch run dev:docs-serve
```

Then visit http://localhost:8000

## Documentation Format

The documentation uses reStructuredText (.rst) format and supports:

- Code blocks with syntax highlighting
- Cross-references to API documentation  
- Intersphinx links to Python, boto3, and click documentation
- MyST parser for Markdown support

## Theme

Uses the [Furo](https://pradyunsg.me/furo/) theme for a modern, clean appearance.
