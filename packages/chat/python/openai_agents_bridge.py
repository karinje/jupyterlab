#!/usr/bin/env python3
"""
OpenAI Agents Bridge for JupyterLab Chat MCP Integration

This script acts as a bridge between the JupyterLab TypeScript frontend
and the OpenAI Agents SDK with MCP server support.

ALL chat requests go through this bridge for security - the OpenAI LLM
will decide when to use MCP tools.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict

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


async def send_message_with_mcp(data: Dict[str, Any]) -> Dict[str, Any]:
    """Send a message using OpenAI Agents SDK - LLM decides when to use MCP tools"""
    try:
        # Import OpenAI Agents SDK
        from openai_agents import Agent, MCPServerStdio, run

        # Extract request data
        message = data.get("message", "")
        model = data.get("model", "gpt-4o-mini")
        api_key = data.get("apiKey", "")
        mcp_servers_config = data.get("mcpServers", {})

        if not api_key:
            return {"error": "OpenAI API key is required"}

        if not message:
            return {"error": "Message is required"}

        # Set OpenAI API key
        os.environ["OPENAI_API_KEY"] = api_key

        # Create MCP servers (if any configured)
        mcp_server_instances = []

        for server_name, config in mcp_servers_config.items():
            command = config.get("command")
            args = config.get("args", [])
            env = config.get("env", {})

            if command:
                try:
                    server = MCPServerStdio(command=command, args=args, env={**os.environ, **env})
                    await server.connect()
                    mcp_server_instances.append(server)
                    logger.info(f"✅ Connected to MCP server: {server_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to connect to MCP server {server_name}: {e}")

        try:
            # Create agent with MCP servers (empty list if none configured)
            # The LLM will decide when to use available tools
            agent = Agent(
                name="JupyterLab Assistant",
                instructions="You are a helpful assistant integrated into JupyterLab. When you have access to MCP tools (like database connections), use them to help users query and analyze their data effectively. Otherwise, provide helpful general assistance.",
                model=model,
                mcpServers=mcp_server_instances,
            )

            # Run the agent - LLM decides whether to use MCP tools
            result = await run(agent, message)

            return {
                "response": result.finalOutput,
                "mcpServersConnected": len(mcp_server_instances),
                "toolsUsed": len(getattr(result, "tool_calls", [])),
            }

        finally:
            # Clean up MCP servers
            for server in mcp_server_instances:
                try:
                    server.close()
                except Exception as e:
                    logger.error(f"Error closing MCP server: {e}")

    except ImportError as e:
        return {
            "error": f"OpenAI Agents SDK not installed. Please run: pip install openai-agents\nDetails: {e}"
        }
    except Exception as e:
        return {"error": f"Failed to process request: {e!s}"}


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python openai_agents_bridge.py <command>"}))
        sys.exit(1)

    command = sys.argv[1]

    if command == "send_message":
        # Read input from stdin
        try:
            input_data = sys.stdin.read()
            data = json.loads(input_data)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON input: {e}"}))
            sys.exit(1)

        # Process the request - LLM decides when to use MCP tools
        result = await send_message_with_mcp(data)

        # Output result as JSON
        print(json.dumps(result))

    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
