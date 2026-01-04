MCP Server Overview
===================

The Thoth MCP (Model Context Protocol) Server provides a framework for building 
remote tool and resource servers that can be accessed via the MCP protocol.

Architecture
------------

The server is built on top of the official MCP Python SDK and provides:

- **Tool Registration**: Define and register custom tools
- **Resource Management**: Manage and serve resources
- **Async Support**: Full async/await support for modern Python
- **Type Safety**: Complete type annotations throughout
- **Extensibility**: Easy to extend with new tools and resources

Core Components
---------------

Server Class
~~~~~~~~~~~~

The :class:`thoth.mcp_server.server.ThothMCPServer` class is the main entry point:

.. code-block:: python

   from thoth.mcp_server import ThothMCPServer
   
   server = ThothMCPServer(
       name="my-server",
       version="1.0.0"
   )

Protocol Handlers
~~~~~~~~~~~~~~~~~

The server implements the following MCP protocol handlers:

- ``list_tools()``: Returns available tools
- ``call_tool()``: Executes a tool by name
- ``list_resources()``: Returns available resources
- ``read_resource()``: Reads a resource by URI

Available Tools
---------------

See :doc:`../MCP_TOOLS` for complete tool documentation.

Ping Tool
~~~~~~~~~

A simple connectivity test tool:

.. code-block:: json

   {
     "name": "ping",
     "arguments": {
       "message": "Hello!"
     }
   }

Response: ``"pong: Hello!"``

Running the Server
------------------

Command Line
~~~~~~~~~~~~

.. code-block:: bash

   python -m thoth.mcp_server.server

Programmatically
~~~~~~~~~~~~~~~~

.. code-block:: python

   from thoth.mcp_server import run_server
   
   run_server()

Async Mode
~~~~~~~~~~

.. code-block:: python

   import asyncio
   from thoth.mcp_server import ThothMCPServer
   
   async def main():
       server = ThothMCPServer()
       await server.run()
   
   asyncio.run(main())

Extending the Server
--------------------

Adding New Tools
~~~~~~~~~~~~~~~~

To add a new tool, modify the ``_setup_handlers()`` method:

.. code-block:: python

   @self.server.list_tools()
   async def list_tools() -> list[Tool]:
       return [
           Tool(
               name="my_tool",
               description="My custom tool",
               inputSchema={
                   "type": "object",
                   "properties": {
                       "param": {
                           "type": "string",
                           "description": "A parameter"
                       }
                   },
                   "required": ["param"]
               }
           )
       ]
   
   @self.server.call_tool()
   async def call_tool(name: str, arguments: dict) -> list[TextContent]:
       if name == "my_tool":
           # Handle tool logic
           result = f"Processed: {arguments['param']}"
           return [TextContent(type="text", text=result)]

Adding Resources
~~~~~~~~~~~~~~~~

Resources can be added similarly through the resource handlers:

.. code-block:: python

   @self.server.list_resources()
   async def list_resources() -> list[Resource]:
       return [
           Resource(
               uri="thoth://my-resource",
               name="My Resource",
               description="A custom resource"
           )
       ]
   
   @self.server.read_resource()
   async def read_resource(uri: str) -> str:
       if uri == "thoth://my-resource":
           return "Resource content"
       raise ValueError(f"Resource not found: {uri}")

Testing
-------

See :doc:`../TEST_COVERAGE` for comprehensive testing documentation.

Further Reading
---------------

- :doc:`../MCP_TOOLS` - Available tools documentation
- :doc:`../api/mcp_server` - API reference
- `Model Context Protocol Specification <https://modelcontextprotocol.io/>`_
