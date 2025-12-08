"""
MCP Client for LangGraph Agent

Provides a client wrapper for connecting to MCP servers (like Snowflake)
and calling their tools from the LangGraph agent.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

try:
    from mcp import stdio_client, StdioServerParameters, ClientSession
except ImportError:
    stdio_client = None
    StdioServerParameters = None
    ClientSession = None

# Set up logging
try:
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("mcp_client")


class MCPClient:
    """
    MCP Client wrapper for LangGraph agent.
    
    Manages connections to MCP servers and provides methods to call their tools.
    """
    
    def __init__(self, mcp_servers_config: Dict[str, Dict[str, Any]] = None):
        """
        Initialize MCP Client.
        
        Args:
            mcp_servers_config: Dict of server configs, e.g.:
                {
                    "snowflake": {
                        "command": "uvx",
                        "args": ["mcp-snowflake-server", ...],
                        "env": {"SNOWFLAKE_ACCOUNT": "..."}
                    }
                }
        """
        self.servers_config = mcp_servers_config or {}
        self._sessions: Dict[str, Any] = {}  # server_name -> (session, read, write)
        self._connected = False
        
        if stdio_client is None:
            logger.warning("MCP package not installed. MCP tools will not work.")
    
    async def connect(self) -> bool:
        """
        Connect to all configured MCP servers.
        
        Returns:
            True if at least one server connected successfully
        """
        if not self.servers_config:
            logger.info("No MCP servers configured")
            return False
            
        if stdio_client is None:
            logger.error("MCP package not available")
            return False
        
        connected_any = False
        
        for server_name, config in self.servers_config.items():
            try:
                logger.info(f"🔌 Connecting to MCP server: {server_name}")
                
                # Create server parameters
                params = StdioServerParameters(
                    command=config.get("command"),
                    args=config.get("args", []),
                    env=config.get("env"),
                )
                
                # Connect using stdio_client context manager
                # We need to keep the context manager active, so we'll manage it manually
                client_cm = stdio_client(params)
                read, write = await client_cm.__aenter__()
                
                # Create and initialize session
                session = ClientSession(read, write)
                await session.initialize()
                
                # Store session info
                self._sessions[server_name] = {
                    "session": session,
                    "context_manager": client_cm,
                    "read": read,
                    "write": write,
                }
                
                # List available tools
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools] if tools_result.tools else []
                logger.info(f"✅ Connected to {server_name}. Available tools: {tool_names}")
                
                connected_any = True
                
            except Exception as e:
                logger.error(f"❌ Failed to connect to MCP server {server_name}: {e}")
        
        self._connected = connected_any
        return connected_any
    
    async def disconnect(self):
        """Disconnect from all MCP servers."""
        for server_name, session_info in self._sessions.items():
            try:
                cm = session_info.get("context_manager")
                if cm:
                    await cm.__aexit__(None, None, None)
                logger.info(f"🔌 Disconnected from {server_name}")
            except Exception as e:
                logger.warning(f"Error disconnecting from {server_name}: {e}")
        
        self._sessions.clear()
        self._connected = False
    
    def is_connected(self) -> bool:
        """Check if any MCP server is connected."""
        return self._connected and len(self._sessions) > 0
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any] = None) -> Any:
        """
        Call a tool on an MCP server.
        
        Args:
            server_name: Name of the MCP server (e.g., "snowflake")
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result
        """
        if server_name not in self._sessions:
            raise ValueError(f"MCP server '{server_name}' not connected")
        
        session = self._sessions[server_name]["session"]
        
        try:
            logger.info(f"🔧 Calling MCP tool: {server_name}/{tool_name}")
            result = await session.call_tool(tool_name, arguments or {})
            
            # Extract content from result
            if hasattr(result, 'content') and result.content:
                # MCP returns content as list of content items
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
    
    async def list_tools(self, server_name: str) -> List[str]:
        """
        List available tools on an MCP server.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            List of tool names
        """
        if server_name not in self._sessions:
            return []
        
        session = self._sessions[server_name]["session"]
        result = await session.list_tools()
        return [t.name for t in result.tools] if result.tools else []
    
    # Convenience methods for Snowflake tools
    
    async def query(self, server_name: str, sql: str) -> str:
        """Execute SQL query on database."""
        return await self.call_tool(server_name, "query", {"query": sql})
    
    async def list_tables(self, server_name: str, schema: str = None) -> List[str]:
        """List tables in database."""
        args = {}
        if schema:
            args["schema"] = schema
        result = await self.call_tool(server_name, "list_tables", args)
        # Parse result to extract table names
        if isinstance(result, str):
            # Try to parse as list
            try:
                tables = json.loads(result)
                if isinstance(tables, list):
                    return tables
            except:
                pass
            # Return as single-item list or split by newlines
            return [t.strip() for t in result.split('\n') if t.strip()]
        return result if isinstance(result, list) else [str(result)]
    
    async def get_schema(self, server_name: str, table_name: str) -> str:
        """Get schema for a table."""
        return await self.call_tool(server_name, "describe_table", {"table_name": table_name})
    
    async def get_info(self, server_name: str) -> str:
        """Get database connection info."""
        # Try common tool names for getting info
        for tool_name in ["get_info", "info", "connection_info"]:
            try:
                return await self.call_tool(server_name, tool_name, {})
            except:
                pass
        return "Database info not available"


# Global MCP client instance (lazy initialization)
_global_mcp_client: Optional[MCPClient] = None


async def get_mcp_client(config: Dict[str, Dict[str, Any]] = None) -> MCPClient:
    """
    Get or create global MCP client.
    
    Args:
        config: MCP servers configuration. If provided, creates new client.
        
    Returns:
        MCPClient instance
    """
    global _global_mcp_client
    
    if config is not None:
        # Create new client with config
        if _global_mcp_client:
            await _global_mcp_client.disconnect()
        _global_mcp_client = MCPClient(config)
        await _global_mcp_client.connect()
    
    if _global_mcp_client is None:
        _global_mcp_client = MCPClient({})
    
    return _global_mcp_client

