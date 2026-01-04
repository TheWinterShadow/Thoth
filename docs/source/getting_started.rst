Getting Started
===============

Installation
------------

From PyPI (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install thoth

Development Installation
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   git clone https://github.com/TheWinterShadow/Thoth.git
   cd Thoth
   pip install -e ".[dev]"

Quick Start
-----------

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   import thoth
   from thoth.mcp_server import ThothMCPServer
   
   # Create an MCP server instance
   server = ThothMCPServer(name="my-server", version="1.0.0")
   
   # Run the server
   import asyncio
   asyncio.run(server.run())

Running the MCP Server
~~~~~~~~~~~~~~~~~~~~~~

To start the Thoth MCP server:

.. code-block:: bash

   python -m thoth.mcp_server.server

Or use the synchronous entry point:

.. code-block:: python

   from thoth.mcp_server import run_server
   
   run_server()

Next Steps
----------

- Explore the :doc:`MCP_TOOLS` documentation
- Read the :doc:`api/mcp_server` API reference
- Check out :doc:`DEVELOPMENT` for contributing
