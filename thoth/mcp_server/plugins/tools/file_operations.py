"""File operations tool plugin."""

import logging
from pathlib import Path
from typing import Any

from thoth.mcp_server.plugins.base import BaseToolPlugin

logger = logging.getLogger(__name__)


class FileOperationsPlugin(BaseToolPlugin):
    """Plugin providing file operation tools."""

    def __init__(self, name: str = "file_operations", version: str = "1.0.0"):
        """Initialize file operations plugin.

        Args:
            name: Plugin name
            version: Plugin version
        """
        super().__init__(name, version)
        self.base_path: Path | None = None

    def initialize(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the file operations plugin.

        Args:
            config: Configuration dictionary with:
                - base_path: Base path for file operations (optional)
        """
        base_path = config.get("base_path") if config else None
        if base_path:
            self.base_path = Path(base_path)
            if not self.base_path.exists():
                self.base_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created base path: {self.base_path}")

    def cleanup(self) -> None:
        """Clean up plugin resources."""
        self.base_path = None

    def get_tools(self) -> list[dict[str, Any]]:
        """Get list of file operation tools.

        Returns:
            List of tool definitions compatible with MCP Tool type
        """
        return [
            {
                "name": "read_file",
                "description": "Read contents of a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write contents to a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to write",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "list_files",
                "description": "List files in a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the directory to list",
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Whether to list recursively",
                            "default": False,
                        },
                    },
                    "required": ["path"],
                },
            },
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a file operation tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool name is invalid
            FileNotFoundError: If file not found
            PermissionError: If permission denied
        """
        if tool_name == "read_file":
            return await self._read_file(arguments["path"])

        if tool_name == "write_file":
            return await self._write_file(arguments["path"], arguments["content"])

        if tool_name == "list_files":
            recursive = arguments.get("recursive", False)
            return await self._list_files(arguments["path"], recursive)

        msg = f"Unknown tool: {tool_name}"
        raise ValueError(msg)

    async def _read_file(self, path: str) -> dict[str, Any]:
        """Read a file.

        Args:
            path: File path

        Returns:
            Dictionary with file contents
        """
        file_path = self._resolve_path(path)

        if not file_path.exists():
            msg = f"File not found: {path}"
            raise FileNotFoundError(msg)

        if not file_path.is_file():
            msg = f"Path is not a file: {path}"
            raise ValueError(msg)

        try:
            content = file_path.read_text(encoding="utf-8")
            return {
                "path": str(file_path),
                "content": content,
                "size": len(content),
            }
        except Exception:
            logger.exception(f"Failed to read file {path}")
            raise

    async def _write_file(self, path: str, content: str) -> dict[str, Any]:
        """Write to a file.

        Args:
            path: File path
            content: Content to write

        Returns:
            Dictionary with write result
        """
        file_path = self._resolve_path(path)

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            file_path.write_text(content, encoding="utf-8")
            return {
                "path": str(file_path),
                "size": len(content),
                "status": "written",
            }
        except Exception:
            logger.exception(f"Failed to write file {path}")
            raise

    async def _list_files(self, path: str, recursive: bool = False) -> dict[str, Any]:
        """List files in a directory.

        Args:
            path: Directory path
            recursive: Whether to list recursively

        Returns:
            Dictionary with file list
        """
        dir_path = self._resolve_path(path)

        if not dir_path.exists():
            msg = f"Directory not found: {path}"
            raise FileNotFoundError(msg)

        if not dir_path.is_dir():
            msg = f"Path is not a directory: {path}"
            raise ValueError(msg)

        try:
            files: list[dict[str, Any]] = []
            if recursive:
                # Recursively search all subdirectories
                files.extend(
                    {
                        "path": str(file_path.relative_to(dir_path)),
                        "full_path": str(file_path),
                        "size": file_path.stat().st_size,
                    }
                    for file_path in dir_path.rglob("*")
                    if file_path.is_file()
                )
            else:
                # Only list files in the immediate directory
                files.extend(
                    {
                        "path": file_path.name,
                        "full_path": str(file_path),
                        "size": file_path.stat().st_size,
                    }
                    for file_path in dir_path.iterdir()
                    if file_path.is_file()
                )

            return {
                "path": str(dir_path),
                "files": files,
                "count": len(files),
            }
        except Exception:
            logger.exception(f"Failed to list files in {path}")
            raise

    def _resolve_path(self, path: str) -> Path:
        """Resolve a file path relative to base path if set.

        Args:
            path: File or directory path

        Returns:
            Resolved Path object
        """
        file_path = Path(path)

        # If base_path is set and path is relative, resolve relative to base_path
        if self.base_path and not file_path.is_absolute():
            return self.base_path / file_path

        return file_path
