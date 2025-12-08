"""
MCP (Model Context Protocol) tools for external data sources

These tools provide access to external databases and services through MCP,
particularly Snowflake for data querying.
"""

from langchain.tools import StructuredTool
from typing import Optional, List
import logging
import json

from ..schemas import SnowflakeQueryArgs, ListTablesArgs

# Set up proper logging using simplified config
try:
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
except ImportError:
    # Fallback if centralized logging not available
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger("jupyterlab")


def create_mcp_tools(mcp_client) -> List[StructuredTool]:
    """
    Create MCP/Snowflake data access tools

    Args:
        mcp_client: MCPClient instance for external data access

    Returns:
        List of StructuredTool instances for LangChain
    """

    async def query_snowflake(sql: str, limit: Optional[int] = 1000) -> str:
        """
        Execute SQL query on Snowflake database.

        Args:
            sql: SQL query to execute
            limit: Maximum number of rows to return

        Returns:
            Query results as formatted string
        """
        try:
            # Add limit to query if not present
            sql_lower = sql.lower()
            if "limit" not in sql_lower and limit:
                sql = f"{sql.rstrip(';')} LIMIT {limit}"

            # Execute query
            result = await mcp_client.query("snowflake", sql)

            if not result:
                return "Query returned no results"

            # Format results for LLM
            if isinstance(result, list):
                num_rows = len(result)
                if num_rows == 0:
                    return "Query returned 0 rows"

                # Show preview of results
                preview_rows = min(5, num_rows)
                preview = result[:preview_rows]

                output = f"Query returned {num_rows} rows. "
                if num_rows > preview_rows:
                    output += f"Showing first {preview_rows} rows:\n"
                else:
                    output += "Results:\n"

                # Format as readable text
                output += json.dumps(preview, indent=2, default=str)

                if num_rows > preview_rows:
                    output += f"\n... and {num_rows - preview_rows} more rows"

                return output
            else:
                return f"Query result: {result}"

        except Exception as e:
            logger.error(f"Error in query_snowflake: {e}")
            return f"Error executing query: {str(e)}"

    async def list_snowflake_tables(database: str = None, schema_name: str = None) -> str:
        """
        List available tables in Snowflake database.

        Args:
            database: Database name (optional)
            schema_name: Schema name to list tables from

        Returns:
            List of available tables
        """
        try:
            schema = schema_name or "public"
            tables = await mcp_client.list_tables("snowflake", schema)

            if not tables:
                return f"No tables found in schema '{schema}'"

            output = f"Available tables in '{schema}' schema:\n"
            for table in tables:
                output += f"  - {table}\n"

            return output

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
            schema_info = await mcp_client.get_schema("snowflake", table_name)

            if not schema_info:
                return f"No schema information found for table '{table_name}'"

            output = f"Schema for table '{table_name}':\n"

            # Format schema information
            if isinstance(schema_info, list):
                for column in schema_info:
                    col_name = column.get("name", "unknown")
                    col_type = column.get("type", "unknown")
                    nullable = column.get("nullable", True)

                    output += f"  - {col_name}: {col_type}"
                    if not nullable:
                        output += " (NOT NULL)"
                    output += "\n"
            else:
                output += json.dumps(schema_info, indent=2, default=str)

            return output

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
            info = await mcp_client.get_info("snowflake")

            if not info:
                return "No database information available"

            output = "Database Information:\n"
            output += json.dumps(info, indent=2, default=str)

            return output

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
