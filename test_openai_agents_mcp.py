#!/usr/bin/env python3
"""
Test OpenAI Agents SDK with MCP Snowflake server.
This verifies MCP works independently of JupyterLab/LangGraph.
"""

import asyncio
import os


async def test_mcp_snowflake():
    """Test MCP Snowflake connection using OpenAI Agents SDK"""

    try:
        from agents import Agent, Runner, set_default_openai_key
        from agents.mcp import MCPServerStdio
        from agents.mcp.server import MCPServerStdioParams
    except ImportError:
        print("❌ OpenAI Agents SDK not installed. Run: pip install openai-agents")
        return False

    # Get OpenAI API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable not set")
        return False

    set_default_openai_key(api_key)

    # MCP server config (same as JupyterLab settings would use)
    mcp_config = {
        "command": "uvx",
        "args": ["mcp-snowflake-server"],
        "env": {
            "SNOWFLAKE_USER": os.environ.get("SNOWFLAKE_USER", "TOTCOTTAGE"),
            "SNOWFLAKE_ACCOUNT": os.environ.get(
                "SNOWFLAKE_ACCOUNT", "NPOVSJB-PNB00757"
            ),
            "SNOWFLAKE_DATABASE": os.environ.get(
                "SNOWFLAKE_DATABASE", "SNOWFLAKE_LEARNING_DB"
            ),
            "SNOWFLAKE_WAREHOUSE": os.environ.get(
                "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_LEARNING_WH"
            ),
            "SNOWFLAKE_PASSWORD": os.environ.get("SNOWFLAKE_PASSWORD", ""),
        },
    }

    print("🔌 Connecting to MCP Snowflake server...")
    print(f"   Command: {mcp_config['command']} {' '.join(mcp_config['args'])}")

    try:
        # Create MCP server connection
        params = MCPServerStdioParams(
            command=mcp_config["command"],
            args=mcp_config["args"],
            env=mcp_config["env"],
        )

        mcp_server = MCPServerStdio(params, name="snowflake")
        await asyncio.wait_for(mcp_server.connect(), timeout=30.0)

        print("✅ MCP server connected!")

        # List available tools
        if hasattr(mcp_server, "list_tools"):
            tools = await mcp_server.list_tools()
            print(f"📋 Available tools: {[t.name for t in tools]}")

        # Create agent with MCP server
        agent = Agent(
            name="Snowflake Test Agent",
            model="gpt-4o-mini",
            mcp_servers=[mcp_server],
            instructions="You are a database assistant. List the available tables.",
        )

        print("\n🤖 Running agent to list tables...")
        response = await asyncio.wait_for(
            Runner.run(
                agent, "What tables are available in Snowflake? Just list them."
            ),
            timeout=60.0,
        )

        print(f"\n📊 Agent response:\n{response.final_output}")

        # Cleanup
        if hasattr(mcp_server, "disconnect"):
            await mcp_server.disconnect()

        print("\n✅ MCP Snowflake test PASSED!")
        return True

    except asyncio.TimeoutError:
        print("❌ Timeout connecting to MCP server")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Testing OpenAI Agents SDK with MCP Snowflake")
    print("=" * 60)
    print("\nRequired environment variables:")
    print("  - OPENAI_API_KEY")
    print("  - SNOWFLAKE_PASSWORD (or set in script)")
    print()

    success = asyncio.run(test_mcp_snowflake())
    exit(0 if success else 1)
