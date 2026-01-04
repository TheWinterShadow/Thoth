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
copyright_text = "2025 TheWinterShadow"
author = "TheWinterShadow"
release = "1.0.0"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------

html_theme = "alabaster"
html_static_path = ["_static"]
