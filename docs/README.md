# Thoth Documentation Index

Welcome to the Thoth documentation! This index provides links to all available documentation.

## 📚 Main Documentation

### Getting Started
- **[README](../README.md)** - Project overview, installation, and quick start
- **[Getting Started Guide](https://thewintershadow.github.io/Thoth/getting_started.html)** - Detailed setup instructions

### Core Documentation
- **[Architecture](https://thewintershadow.github.io/Thoth/ARCHITECTURE.html)** - System architecture and design decisions
- **[Development Guide](https://thewintershadow.github.io/Thoth/DEVELOPMENT.html)** - Contributing and development workflow
- **[MCP Tools](https://thewintershadow.github.io/Thoth/MCP_TOOLS.html)** - Model Context Protocol tools documentation
- **[Test Coverage](https://thewintershadow.github.io/Thoth/TEST_COVERAGE.html)** - Testing strategy and coverage reports

### Project Information
- **[Contributing](../CONTRIBUTING.md)** - How to contribute to the project
- **[License](../LICENSE)** - MIT License

## 🔧 Technical Documentation

### Setup Guides
- **[Sphinx Setup](SPHINX_SETUP.md)** - Documentation build system configuration
- **[Coverage Setup](COVERAGE_SETUP.md)** - Test coverage integration guide

### Build Artifacts
- **[HTML Documentation](build/index.html)** - Built Sphinx documentation
- **[Coverage Report](build/coverage/index.html)** - HTML test coverage report
- **[API Reference](build/api/modules.html)** - Auto-generated API documentation

## 📖 Documentation Sections

### User Guide
Documentation for users of the Thoth library:
- Project README
- Getting Started
- API Reference

### MCP Server
Model Context Protocol server documentation:
- [MCP Server Overview](https://thewintershadow.github.io/Thoth/mcp_server/overview.html)
- [Available Tools](https://thewintershadow.github.io/Thoth/MCP_TOOLS.html)
- Tool implementation examples

### Development
Documentation for contributors and developers:
- [Architecture Guide](https://thewintershadow.github.io/Thoth/ARCHITECTURE.html)
- [Development Workflow](https://thewintershadow.github.io/Thoth/DEVELOPMENT.html)
- [Test Coverage](https://thewintershadow.github.io/Thoth/TEST_COVERAGE.html)
- [API Documentation](https://thewintershadow.github.io/Thoth/api/modules.html)

## 🏗️ Building Documentation

### Build HTML Documentation
```bash
# Build Sphinx documentation
hatch run docs:build

# Clean and rebuild
hatch run docs:clean
```

### Generate Coverage Reports
```bash
# Generate coverage HTML report
hatch run cov-html

# View coverage
open docs/build/coverage/index.html
```

### View Documentation Locally
```bash
# Serve documentation on http://localhost:8000
hatch run docs:serve

# Or manually
python -m http.server 8000 --directory docs/build
```

## 📂 Directory Structure

```
docs/
├── README.md                   # This file - documentation index
├── SPHINX_SETUP.md            # Sphinx configuration guide
├── COVERAGE_SETUP.md          # Coverage integration guide
├── source/                    # Sphinx source files
│   ├── conf.py                # Sphinx configuration
│   ├── index.rst              # Main documentation index
│   ├── getting_started.rst    # Getting started guide
│   ├── ARCHITECTURE.md        # Architecture documentation
│   ├── DEVELOPMENT.md         # Development guide
│   ├── MCP_TOOLS.md           # MCP tools reference
│   ├── TEST_COVERAGE.md       # Test coverage docs
│   ├── coverage_summary.md    # Coverage report summary
│   ├── api/                   # API documentation
│   │   ├── modules.rst
│   │   ├── thoth.rst
│   │   ├── mcp_server.rst
│   │   └── utils.rst
│   └── mcp_server/
│       └── overview.rst
├── build/                     # Generated documentation
│   ├── index.html             # Built docs entry point
│   ├── coverage/              # Coverage reports
│   └── ...
├── Makefile                   # Documentation build commands
└── README_DOCS.md             # Detailed docs guide
```

## 🎯 Quick Links

### For Users
- [Installation](../README.md#installation)
- [Quick Start](../README.md#quick-start)
- [API Documentation](https://thewintershadow.github.io/Thoth/api/modules.html)

### For Developers
- [Contributing Guidelines](../CONTRIBUTING.md)
- [Development Setup](https://thewintershadow.github.io/Thoth/DEVELOPMENT.html)
- [Architecture Overview](https://thewintershadow.github.io/Thoth/ARCHITECTURE.html)
- [Running Tests](https://thewintershadow.github.io/Thoth/TEST_COVERAGE.html)

### For Documentation Contributors
- [Sphinx Setup Guide](SPHINX_SETUP.md)
- [Adding Documentation](README_DOCS.md#adding-documentation)
- [Building Docs](README_DOCS.md#building-documentation)

## 🌐 Online Documentation

When published, documentation is available at:
- **GitHub Pages**: https://thewintershadow.github.io/Thoth/
- **Repository**: https://github.com/TheWinterShadow/Thoth

## 📝 Documentation Standards

### Markdown Files
- **Root Level**: Only README.md and CONTRIBUTING.md (for GitHub visibility)
- **docs/source/**: All other documentation (ARCHITECTURE.md, DEVELOPMENT.md, etc.)
- Use UPPERCASE.md for major documentation files

### Sphinx Documentation (docs/source/)
- Use .rst for Sphinx-specific pages
- Use .md for content pages
- Auto-generate API docs from docstrings

### Docstrings (Code)
- Use Google or NumPy style
- Include examples where helpful
- Document all public APIs

## 🔄 Documentation Workflow

1. **Edit**: Modify markdown files in docs/source/ or .rst files
2. **Build**: Run `hatch run docs:build`
3. **Review**: Open `docs/build/index.html` in browser
4. **Commit**: Commit source files (not build artifacts)
5. **Deploy**: CI/CD builds and publishes to GitHub Pages

## ❓ Need Help?

- Check [README_DOCS.md](README_DOCS.md) for detailed documentation guide
- Review [SPHINX_SETUP.md](SPHINX_SETUP.md) for build system details
- See [Development Guide](https://thewintershadow.github.io/Thoth/DEVELOPMENT.html) for contribution workflow
- Open an issue on [GitHub](https://github.com/TheWinterShadow/Thoth/issues)

---

**Last Updated**: January 4, 2026
**Sphinx Version**: 8.2.3
**MyST Parser Version**: 4.0.1
