# Thoth MCP Tools Documentation

This document describes the available tools in the Thoth MCP Server.

## Available Tools

### ping

A simple connectivity test tool that verifies MCP server responsiveness.

**Purpose**: Verify that the MCP server is running and responding to tool calls correctly.

**Parameters**:
- `message` (string, optional): Custom message to echo back in the response
  - Default: `"ping"`
  - Description: Optional message to echo back in the response

**Returns**: Text content with format `"pong: {message}"`

**Examples**:

1. Basic ping without arguments:
   ```json
   {
     "name": "ping",
     "arguments": {}
   }
   ```
   Response: `"pong: ping"`

2. Ping with custom message:
   ```json
   {
     "name": "ping",
     "arguments": {
       "message": "Hello, Thoth!"
     }
   }
   ```
   Response: `"pong: Hello, Thoth!"`

**Use Cases**:
- Verify server connectivity
- Test MCP protocol communication
- Health check for the server
- Debugging and troubleshooting

**Error Handling**:
- No errors expected under normal operation
- Invalid tool names will raise `ValueError`

## Testing Tools Locally

To test the tools locally:

1. Start the MCP server:
   ```bash
   python -m thoth.mcp_server.server
   ```

2. Use an MCP client to connect and call tools via stdio

3. Or run the unit tests:
   ```bash
   hatch test
   ```

## Adding New Tools

To add a new tool to the server:

1. Update the `list_tools()` handler in `thoth/mcp/server/server.py` to include your tool definition
2. Add handling logic in the `call_tool()` handler
3. Create unit tests in `tests/mcp_server/test_mcp_server.py`
4. Document the tool in this file

Example tool definition structure:
```python
Tool(
    name="your_tool_name",
    description="Description of what your tool does",
    inputSchema={
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "Description of param1"
            }
        },
        "required": ["param1"]  # List required parameters
    }
)
```
