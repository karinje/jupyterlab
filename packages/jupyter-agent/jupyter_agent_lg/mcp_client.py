"""
MCP Client for LangGraph Agent

Uses OpenAI Agents SDK's MCPServerStdio which we know works.
This wraps the same MCP server used by OpenAI Agents SDK.
"""

import asyncio
from typing import Dict, Any, Optional, List

# Set up logging
try:
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("mcp_client")

# Try to import OpenAI Agents SDK MCP
try:
    from agents.mcp import MCPServerStdio
    from agents.mcp.server import MCPServerStdioParams
    OPENAI_MCP_AVAILABLE = True
except ImportError:
    OPENAI_MCP_AVAILABLE = False
    logger.warning("OpenAI Agents SDK not installed. MCP tools will not work.")


class MCPClient:
    """
    MCP Client wrapper for LangGraph agent.
    Uses OpenAI Agents SDK's MCPServerStdio for reliable connection.
    """

    def __init__(self):
        self._server: Optional[MCPServerStdio] = None
        self._connected = False
        self._server_name = None

    async def connect(self, server_config: Dict[str, Any], server_name: str = "snowflake") -> bool:
        """
        Connect to MCP server using OpenAI Agents SDK's MCPServerStdio.

        Args:
            server_config: Config dict with 'command', 'args', 'env'
            server_name: Name identifier for this server

        Returns:
            True if connected successfully
        """
        if not OPENAI_MCP_AVAILABLE:
            logger.error("OpenAI Agents SDK not available for MCP")
            return False

        try:
            import os as _os
            self._server_name = server_name
            command = server_config.get("command")
            args = server_config.get("args", [])
            config_env = server_config.get("env", {})

            # Merge with current environment (MCP server needs PATH, etc.)
            env = _os.environ.copy()
            env.update(config_env)

            logger.info(f"🔌 Connecting to MCP server '{server_name}' via OpenAI Agents SDK...")
            logger.info(f"   Command: {command} {' '.join(args)}")
            logger.info(f"   Env keys: {list(config_env.keys())}")

            # Create server parameters (same as working test)
            params = MCPServerStdioParams(
                command=command,
                args=args,
                env=env,
            )

            # Create and connect using OpenAI's MCPServerStdio
            self._server = MCPServerStdio(params, name=server_name)
            await asyncio.wait_for(self._server.connect(), timeout=30.0)

            # List available tools to verify connection
            if hasattr(self._server, "list_tools"):
                tools = await self._server.list_tools()
                tool_names = [t.name for t in tools] if tools else []
                logger.info(f"✅ Connected to MCP server '{server_name}'")
                logger.info(f"   Available tools: {tool_names}")
            else:
                logger.info(f"✅ Connected to MCP server '{server_name}'")

            self._connected = True
            return True

        except asyncio.TimeoutError:
            logger.error(f"❌ Timeout connecting to MCP server '{server_name}'")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from MCP server."""
        if self._server:
            try:
                if hasattr(self._server, "disconnect"):
                    await self._server.disconnect()
                logger.info(f"🔌 Disconnected from MCP server '{self._server_name}'")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")

        self._server = None
        self._connected = False

    def is_connected(self) -> bool:
        """Check if MCP server is connected."""
        return self._connected and self._server is not None

    def get_server(self) -> Optional[MCPServerStdio]:
        """Get the underlying MCPServerStdio for direct use."""
        return self._server if self._connected else None

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> str:
        """
        Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        if not self.is_connected():
            raise ValueError("MCP client not connected")

        try:
            logger.info(f"🔧 Calling MCP tool: {tool_name}")

            # Use OpenAI Agents SDK's tool calling
            if hasattr(self._server, "call_tool"):
                result = await self._server.call_tool(tool_name, arguments or {})
            else:
                # Fallback to session-based call if available
                result = await self._server._session.call_tool(tool_name, arguments or {})

            # Extract content from result
            if hasattr(result, 'content') and result.content:
                contents = []
                for item in result.content:
                    if hasattr(item, 'text'):
                        contents.append(item.text)
                    elif hasattr(item, 'data'):
                        contents.append(str(item.data))
                return "\n".join(contents) if contents else str(result)

            return str(result)

        except Exception as e:
            logger.error(f"❌ Error calling MCP tool {tool_name}: {e}")
            raise

    # Convenience methods matching what mcp_tools.py expects

    async def query(self, server_name: str, sql: str) -> str:
        """Execute SQL query."""
        return await self.call_tool("execute_query", {"query": sql})

    async def list_tables(self, server_name: str, schema: str = None) -> List[str]:
        """List tables."""
        args = {}
        if schema:
            args["schema"] = schema
        result = await self.call_tool("list_tables", args)

        # Try to parse as list
        if isinstance(result, str):
            lines = [l.strip() for l in result.split('\n') if l.strip()]
            tables = [l.strip('- ') for l in lines if l.startswith('-') or not any(c in l for c in [':', '='])]
            return tables if tables else lines
        return [result] if result else []

    async def get_schema(self, server_name: str, table_name: str) -> str:
        """Get table schema."""
        return await self.call_tool("describe_table", {"table_name": table_name})

    async def get_info(self, server_name: str) -> str:
        """Get database info."""
        for tool_name in ["get_connection_info", "connection_info", "info"]:
            try:
                return await self.call_tool(tool_name, {})
            except Exception:
                continue
        return "Database info not available"
