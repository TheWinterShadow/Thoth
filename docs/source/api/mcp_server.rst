MCP Server Module
=================

The Model Context Protocol (MCP) server module provides the core server implementation
and plugin system for extensible MCP functionality.

Server Module
-------------

.. automodule:: thoth.mcp_server.server
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Configuration Module
--------------------

.. automodule:: thoth.mcp_server.config
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Plugin System
-------------

Base Plugin Classes
~~~~~~~~~~~~~~~~~~~

.. automodule:: thoth.mcp_server.plugins.base
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Plugin Registry
~~~~~~~~~~~~~~~

.. automodule:: thoth.mcp_server.plugins.registry
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

RAG Plugins
~~~~~~~~~~~

RAG Manager
^^^^^^^^^^^

.. automodule:: thoth.mcp_server.plugins.rag.manager
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Handbook RAG Plugin
^^^^^^^^^^^^^^^^^^^

.. automodule:: thoth.mcp_server.plugins.rag.handbook
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Tool Plugins
~~~~~~~~~~~~

File Operations Plugin
^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: thoth.mcp_server.plugins.tools.file_operations
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Handbook Tools Plugin
^^^^^^^^^^^^^^^^^^^^^

.. automodule:: thoth.mcp_server.plugins.tools.handbook_tools
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Lambda Handler
--------------

.. automodule:: thoth.mcp_server.lambda_handler
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Classes
-------

ThothMCPServer
~~~~~~~~~~~~~~

.. autoclass:: thoth.mcp_server.server.ThothMCPServer
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

MCPConfig
~~~~~~~~~

.. autoclass:: thoth.mcp_server.config.MCPConfig
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

PluginRegistry
~~~~~~~~~~~~~~

.. autoclass:: thoth.mcp_server.plugins.registry.PluginRegistry
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

RAGManager
~~~~~~~~~~

.. autoclass:: thoth.mcp_server.plugins.rag.manager.RAGManager
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Functions
---------

.. autofunction:: thoth.mcp_server.server.invoker
.. autofunction:: thoth.mcp_server.server.run_server
.. autofunction:: thoth.mcp_server.config.get_config
.. autofunction:: thoth.mcp_server.plugins.registry.get_registry

Package Contents
----------------

.. automodule:: thoth.mcp_server
   :members:
   :undoc-members:
   :show-inheritance:
