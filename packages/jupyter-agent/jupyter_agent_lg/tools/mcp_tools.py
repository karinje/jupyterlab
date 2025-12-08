"""
MCP (Model Context Protocol) tools for external data sources

These tools provide access to external databases and services through MCP,
particularly Snowflake for data querying.

The MCP server only exposes 'execute_query', so all tools use SQL.
"""

from langchain.tools import StructuredTool
from typing import Optional, List
import json

from ..schemas import SnowflakeQueryArgs, ListTablesArgs

# Set up proper logging using simplified config
try:
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
except ImportError:
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger("jupyterlab")


# Global MCP client - will be initialized when needed
_mcp_client = None


def set_mcp_client(client):
    """Set the global MCP client instance"""
    global _mcp_client
    _mcp_client = client
    logger.info(f"🔌 MCP client set: {client is not None}")


def get_mcp_client():
    """Get the global MCP client instance"""
    return _mcp_client


def create_mcp_tools() -> List[StructuredTool]:
    """
    Create MCP/Snowflake data access tools.

    These tools use the global MCP client which should be initialized
    via set_mcp_client() before the tools are invoked.

    All tools use 'execute_query' MCP tool with SQL since that's
    the only tool the MCP server exposes.

    Returns:
        List of StructuredTool instances for LangChain
    """

    async def query_snowflake(query: str, database: str = None, schema_name: str = None) -> str:
        """
        Execute SQL query on Snowflake database.

        Args:
            query: SQL query to execute
            database: Database name (optional)
            schema_name: Schema name (optional)

        Returns:
            Query results as formatted string
        """
        try:
            client = get_mcp_client()
            if client is None or not client.is_connected():
                return "Error: MCP client not connected. Please check Snowflake MCP configuration."

            logger.info(f"🔍 Executing Snowflake query: {query[:100]}...")

            # Execute query via MCP's execute_query tool
            result = await client.call_tool("execute_query", {"query": query})

            if not result:
                return "Query returned no results"

            return f"Query result:\n{result}"

        except Exception as e:
            logger.error(f"Error in query_snowflake: {e}")
            return f"Error executing query: {str(e)}"

    async def list_snowflake_tables(database: str = None, schema_name: str = None) -> str:
        """
        List available tables in Snowflake database.

        Args:
            database: Database name (optional)
            schema_name: Schema name to list tables from (optional)

        Returns:
            List of available tables
        """
        try:
            client = get_mcp_client()
            if client is None or not client.is_connected():
                return "Error: MCP client not connected. Please check Snowflake MCP configuration."

            logger.info(f"🔍 Listing Snowflake tables...")

            # Use SQL to list tables (execute_query is the only MCP tool available)
            sql = "SHOW TABLES"
            if schema_name:
                sql = f"SHOW TABLES IN SCHEMA {schema_name}"
            if database:
                sql = f"SHOW TABLES IN DATABASE {database}"

            result = await client.call_tool("execute_query", {"query": sql})

            if not result:
                return "No tables found"

            return f"Available tables:\n{result}"

        except Exception as e:
            logger.error(f"Error in list_snowflake_tables: {e}")
            return f"Error listing tables: {str(e)}"

    async def get_table_schema(table_name: str) -> str:
        """
        Get schema information for a specific table.

        Args:
            table_name: Name of the table

        Returns:
            Table schema information
        """
        try:
            client = get_mcp_client()
            if client is None or not client.is_connected():
                return "Error: MCP client not connected. Please check Snowflake MCP configuration."

            logger.info(f"🔍 Getting schema for table: {table_name}")

            # Use SQL to describe table
            sql = f"DESCRIBE TABLE {table_name}"
            result = await client.call_tool("execute_query", {"query": sql})

            if not result:
                return f"No schema information found for table '{table_name}'"

            return f"Schema for table '{table_name}':\n{result}"

        except Exception as e:
            logger.error(f"Error in get_table_schema: {e}")
            return f"Error getting table schema: {str(e)}"

    async def get_database_info() -> str:
        """
        Get general information about the connected database.

        Returns:
            Database connection and metadata information
        """
        try:
            client = get_mcp_client()
            if client is None or not client.is_connected():
                return "Error: MCP client not connected. Please check Snowflake MCP configuration."

            logger.info("🔍 Getting database info...")

            # Use SQL to get current context
            sql = "SELECT CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE(), CURRENT_USER()"
            result = await client.call_tool("execute_query", {"query": sql})

            if not result:
                return "No database information available"

            return f"Database Information:\n{result}"

        except Exception as e:
            logger.error(f"Error in get_database_info: {e}")
            return f"Error getting database info: {str(e)}"

    # Create and return tools with category metadata
    tools = [
        StructuredTool.from_function(
            func=query_snowflake,
            name="query_snowflake",
            description="Execute SQL query on Snowflake database",
            args_schema=SnowflakeQueryArgs,
            coroutine=query_snowflake,
        ),
        StructuredTool.from_function(
            func=list_snowflake_tables,
            name="list_snowflake_tables",
            description="List available tables in Snowflake database",
            args_schema=ListTablesArgs,
            coroutine=list_snowflake_tables,
        ),
        StructuredTool.from_function(
            func=get_table_schema,
            name="get_table_schema",
            description="Get schema information for a specific Snowflake table",
            coroutine=get_table_schema,
        ),
        StructuredTool.from_function(
            func=get_database_info,
            name="get_database_info",
            description="Get general information about the Snowflake database connection",
            coroutine=get_database_info,
        ),
    ]

    # Add category metadata to all MCP tools
    for tool in tools:
        if not tool.metadata:
            tool.metadata = {}
        tool.metadata['tool_category'] = "Snowflake MCP Tools"

    return tools
