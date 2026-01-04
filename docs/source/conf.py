# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# set of options see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

from pathlib import Path
import sys

sys.path.insert(0, str(Path("../..").resolve()))

# -- Project information -----------------------------------------------------

project = "Thoth"
copyright_text = "2026 TheWinterShadow"
author = "TheWinterShadow"
release = "1.0.0"
version = "1.0.0"

# -- General configuration ---------------------------------------------------

extensions = [
    # Sphinx core extensions
    "sphinx.ext.autodoc",  # Auto-generate docs from docstrings
    "sphinx.ext.napoleon",  # Support for NumPy and Google style docstrings
    "sphinx.ext.viewcode",  # Add links to highlighted source code
    "sphinx.ext.intersphinx",  # Link to other project's documentation
    "sphinx.ext.autosummary",  # Generate summary tables for modules
    "sphinx.ext.todo",  # Support for todo items
    "sphinx.ext.coverage",  # Check documentation coverage
    # Markdown support
    "myst_parser",  # Parse Markdown files
]

# AutoDoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
    "show-inheritance": True,
}

# Napoleon settings (for Google/NumPy style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# MyST Parser settings (Markdown support)
myst_enable_extensions = [
    "colon_fence",  # ::: can be used instead of ``` for code blocks
    "deflist",  # Definition lists
    "html_admonition",  # HTML-style admonitions
    "html_image",  # HTML-style images
    "replacements",  # Text replacements
    "smartquotes",  # Smart quotes
    "substitution",  # Variable substitutions
    "tasklist",  # Task lists with checkboxes
]

myst_heading_anchors = 3  # Auto-generate anchors for headings up to level 3

# AutoSummary settings
autosummary_generate = True  # Turn on autosummary
autosummary_imported_members = True

# Intersphinx mapping (link to other projects' docs)
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Todo extension settings
todo_include_todos = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Source file suffixes
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# -- Options for HTML output -------------------------------------------------

html_theme = "breeze"
html_static_path = ["_static"]

# Alabaster theme options
html_theme_options = {
    "description": "Python utilities and MCP server framework",
    "github_user": "TheWinterShadow",
    "github_repo": "Thoth",
    "github_banner": True,
    "github_button": True,
    "github_type": "star",
    "fixed_sidebar": True,
}

html_title = f"{project} v{version}"
html_short_title = project

# -- Options for LaTeX output ------------------------------------------------

latex_elements = {
    "papersize": "letterpaper",
    "pointsize": "10pt",
}

latex_documents = [
    (
        "index",
        "Thoth.tex",
        "Thoth Documentation",
        "TheWinterShadow",
        "manual",
    ),
]
