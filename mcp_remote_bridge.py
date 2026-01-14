#!/usr/bin/env python3
"""Bridge script to connect Claude Desktop (stdio) to remote Thoth MCP server (SSE)."""

import asyncio
import json
import logging
import subprocess
import sys

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)


async def get_auth_token() -> str:
    """Get Google Cloud ID token for authentication."""
    # Activate service account and get token
    key_file = "/tmp/claude-desktop-key.json"
    audience = "https://thoth-mcp-server-ygu2hch2fq-uc.a.run.app"

    try:
        # Activate service account
        subprocess.run(
            ["gcloud", "auth", "activate-service-account", f"--key-file={key_file}"],
            check=True,
            capture_output=True,
        )

        # Get ID token
        result = subprocess.run(
            ["gcloud", "auth", "print-identity-token", f"--audiences={audience}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        logger.exception("Error getting auth token")
        sys.exit(1)


async def main():
    """Run the MCP bridge."""
    # Get authentication token
    token = await get_auth_token()

    # Remote server URL
    server_url = "https://thoth-mcp-server-ygu2hch2fq-uc.a.run.app/sse"

    # Create headers with authentication
    headers = {"Authorization": f"Bearer {token}"}

    # Connect to remote SSE server
    async with sse_client(server_url, headers) as (read, write), ClientSession(read, write) as session:
        # Initialize session
        await session.initialize()

        # Bridge stdio to MCP session
        async def read_stdin():
            """Read from stdin and send to MCP server."""
            loop = asyncio.get_event_loop()
            while True:
                try:
                    line = await loop.run_in_executor(None, sys.stdin.readline)
                    if not line:
                        break

                    # Parse JSON-RPC request
                    request = json.loads(line)

                    # Forward to MCP server based on method
                    method = request.get("method")
                    request_id = request.get("id")

                    # Handle notification (no response needed)
                    if method == "notifications/initialized":
                        continue

                    if method == "initialize":
                        # Return initialization response
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {"tools": {}, "resources": {}},
                                "serverInfo": {"name": "thoth-remote-bridge", "version": "1.0.0"},
                            },
                        }
                    elif method == "tools/list":
                        result = await session.list_tools()
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {"tools": [tool.model_dump() for tool in result.tools]},
                        }
                    elif method == "resources/list":
                        # Return empty resources list
                        response = {"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}}
                    elif method == "tools/call":
                        params = request.get("params", {})
                        result = await session.call_tool(params.get("name"), params.get("arguments", {}))
                        response = {"jsonrpc": "2.0", "id": request_id, "result": result.model_dump()}
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {"code": -32601, "message": f"Method not found: {method}"},
                        }

                    # Write response to stdout
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

                except json.JSONDecodeError as e:
                    sys.stdout.write(
                        json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": f"Parse error: {e}"}}) + "\n"
                    )
                    sys.stdout.flush()
                except (RuntimeError, OSError) as e:
                    sys.stdout.write(
                        json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": f"Internal error: {e}"}})
                        + "\n"
                    )
                    sys.stdout.flush()

        # Start reading from stdin
        await read_stdin()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError, ValueError):
        logger.exception("Fatal error")
        sys.exit(1)
