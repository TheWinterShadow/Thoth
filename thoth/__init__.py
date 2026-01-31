"""Thoth: semantic search and ingestion for handbook documentation.

This package provides:
- **Ingestion**: Git repository sync, document parsing (Markdown, PDF, DOCX, text),
  chunking, embedding, and storage in LanceDB.
- **MCP Server**: Model Context Protocol server exposing semantic search tools
  for AI assistants.
- **Shared**: Vector store (LanceDB), embedder (sentence-transformers), CLI,
  monitoring, health checks, and GCS sync utilities.

Entry points:
- CLI: ``thoth`` command (see thoth.shared.cli)
- MCP server: ``python -m thoth.mcp.http_wrapper``
- Ingestion worker: ``python -m thoth.ingestion.worker``
"""
