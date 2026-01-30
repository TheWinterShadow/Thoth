Thoth Documentation
===================

Thoth is a Model Context Protocol (MCP) server that provides semantic search
capabilities over handbook documentation for AI assistants like Claude.

.. note::

   Thoth processes your documentation into vector embeddings and serves them
   via the MCP protocol, enabling AI assistants to search and retrieve relevant
   content.

Quick Links
-----------

- :doc:`getting_started` - Set up and run Thoth locally
- :doc:`architecture/index` - System design and data flows
- :doc:`api/index` - Python API and HTTP endpoints
- :doc:`architecture/deployment` - CI/CD and infrastructure

.. toctree::
   :maxdepth: 2
   :caption: Getting Started
   :hidden:

   getting_started
   md/DEVELOPMENT

.. toctree::
   :maxdepth: 2
   :caption: Architecture
   :hidden:

   architecture/index
   architecture/ingestion
   architecture/mcp-server
   architecture/deployment

.. toctree::
   :maxdepth: 2
   :caption: API Reference
   :hidden:

   api/index
   Interactive API (Swagger) <api/http>

.. toctree::
   :maxdepth: 2
   :caption: Infrastructure
   :hidden:

   infrastructure/index

.. toctree::
   :maxdepth: 2
   :caption: Configuration
   :hidden:

   md/ENVIRONMENT_CONFIG
   md/SECRETS_SETUP

.. toctree::
   :maxdepth: 2
   :caption: Testing
   :hidden:

   testing

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
