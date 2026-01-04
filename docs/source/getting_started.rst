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

Using the Repository Manager
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ingestion module provides tools for managing the GitLab handbook repository:

.. code-block:: python

   from pathlib import Path
   from thoth.ingestion.repo_manager import HandbookRepoManager
   
   # Initialize the repository manager
   manager = HandbookRepoManager()
   
   # Clone the handbook repository
   repo_path = manager.clone_handbook()
   print(f"Repository cloned to: {repo_path}")
   
   # Get current commit
   commit_sha = manager.get_current_commit()
   print(f"Current commit: {commit_sha}")
   
   # Save metadata for tracking
   manager.save_metadata(commit_sha)
   
   # Later, update the repository
   manager.update_repository()
   
   # Check for changed files
   metadata = manager.load_metadata()
   if metadata:
       changed_files = manager.get_changed_files(metadata["commit_sha"])
       print(f"Changed files: {changed_files}")

Next Steps
----------

- Explore the :doc:`MCP_TOOLS` documentation
- Read the :doc:`api/mcp_server` API reference
- Learn about :doc:`api/ingestion` for repository management
- Check out :doc:`DEVELOPMENT` for contributing
