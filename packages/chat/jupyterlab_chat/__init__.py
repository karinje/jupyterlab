import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional

from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.application import ExtensionApp
from tornado import web

logger = logging.getLogger(__name__)


class ChatOpenAIHandler(APIHandler):
    """Handler for OpenAI chat requests with MCP server support"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mcp_servers = {}

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    async def post(self):
        """Handle POST requests to /api/chat/openai"""
        request_start = time.time()
        logger.info(f"🚀 Request started at {request_start}")

        try:
            # Parse request body
            parse_start = time.time()
            body = json.loads(self.request.body)
            message = body.get("message", "")
            model = body.get("model", "gpt-4o-mini")
            mcp_servers_config = body.get("mcpServers", {})
            context = body.get("context", {})
            parse_time = time.time() - parse_start
            logger.info(f"⚡ Request parsing took {parse_time:.3f}s")

            # Get settings from JupyterLab - the RIGHT way
            settings_start = time.time()
            try:
                # Access the settings directly from the server app
                settings_dir = self.settings.get(
                    "jupyter_config_dir", os.path.expanduser("~/.jupyter")
                )
                lab_settings_dir = os.path.join(settings_dir, "lab", "user-settings")
                chat_settings_file = os.path.join(
                    lab_settings_dir, "@jupyterlab", "chat-extension", "plugin.jupyterlab-settings"
                )

                api_key = ""
                settings_mcp_servers = {}

                if os.path.exists(chat_settings_file):
                    with open(chat_settings_file) as f:
                        settings_data = json.load(f)
                        api_key = settings_data.get("openaiApiKey", "")
                        settings_mcp_servers = settings_data.get("mcpServers", {})
                        logger.info(f"✅ Settings loaded from: {chat_settings_file}")

                # Use MCP servers from settings if not provided in request
                if not mcp_servers_config and settings_mcp_servers:
                    mcp_servers_config = settings_mcp_servers

            except Exception as e:
                logger.error(f"Error reading settings: {e}")
                api_key = ""

            settings_time = time.time() - settings_start
            logger.info(f"⚡ Settings loading took {settings_time:.3f}s")
            logger.info(
                f"API key present: {bool(api_key)}, MCP servers: {list(mcp_servers_config.keys())}"
            )

            if not api_key:
                self.set_status(400)
                self.write({"error": "OpenAI API key not configured in JupyterLab Chat settings"})
                return

            # Import OpenAI Agents SDK
            import_start = time.time()
            try:
                from agents import Agent, Runner, set_default_openai_key
                from agents.mcp import MCPServerStdio
                from agents.mcp.server import MCPServerStdioParams

                logger.info("✅ OpenAI Agents SDK imported successfully")
            except ImportError as e:
                logger.error(f"❌ OpenAI Agents SDK not installed: {e}")
                self.set_status(500)
                self.write({"error": "OpenAI Agents SDK not installed"})
                return
            except Exception as e:
                logger.error(f"❌ Error importing OpenAI Agents SDK: {e}")
                self.set_status(500)
                self.write({"error": f"Error importing OpenAI Agents SDK: {e}"})
                return

            import_time = time.time() - import_start
            logger.info(f"⚡ SDK import took {import_time:.3f}s")

            # Set OpenAI API key
            key_start = time.time()
            set_default_openai_key(api_key)
            key_time = time.time() - key_start
            logger.info(f"⚡ API key setup took {key_time:.3f}s")

            # Set up MCP servers
            mcp_start = time.time()
            mcp_server_instances = []
            for server_name, config in mcp_servers_config.items():
                server_connect_start = time.time()
                try:
                    params = MCPServerStdioParams(
                        command=config.get("command"),
                        args=config.get("args", []),
                        env=config.get("env", {}),
                    )
                    mcp_server = MCPServerStdio(params, name=server_name)

                    # Use asyncio.wait_for to prevent hanging connections
                    try:
                        await asyncio.wait_for(mcp_server.connect(), timeout=10.0)
                        mcp_server_instances.append(mcp_server)
                        server_connect_time = time.time() - server_connect_start
                        logger.info(
                            f"⚡ Connected to MCP server {server_name} in {server_connect_time:.3f}s"
                        )
                    except asyncio.TimeoutError:
                        server_connect_time = time.time() - server_connect_start
                        logger.error(
                            f"❌ Timeout connecting to MCP server {server_name} after {server_connect_time:.3f}s"
                        )
                except Exception as e:
                    server_connect_time = time.time() - server_connect_start
                    logger.error(
                        f"❌ Failed to connect to MCP server {server_name} in {server_connect_time:.3f}s: {e}"
                    )

            mcp_time = time.time() - mcp_start
            logger.info(f"⚡ Total MCP server setup took {mcp_time:.3f}s")

            # Create agent with MCP servers
            agent_start = time.time()
            agent = Agent(
                name="JupyterLab Chat Assistant",
                model=model,
                mcp_servers=mcp_server_instances,
                instructions="""You are a helpful assistant integrated into JupyterLab. You can help with code, analysis, and notebook manipulation. When you need to interact with cells, you can reference them by index (e.g., "cell 0", "cell 1").

IMPORTANT: When a user asks for a plan, task breakdown, or steps to accomplish something, format your response using cards. Each card should follow this exact format:
[CARD:Title|Description]

For example:
[CARD:Research the topic|Gather information about the subject from reliable sources]
[CARD:Create outline|Structure the main points and subtopics]
[CARD:Write first draft|Begin writing the content based on the outline]

For regular questions that don't require planning, respond normally.

You have access to MCP tools that can help you interact with external systems. Use them when appropriate.""",
            )
            agent_time = time.time() - agent_start
            logger.info(f"⚡ Agent creation took {agent_time:.3f}s")

            # Run the agent
            runner_start = time.time()
            logger.info(f"🤖 Starting agent execution with message: {message[:100]}...")
            try:
                # Add timeout to prevent hanging
                response = await asyncio.wait_for(Runner.run(agent, message), timeout=60.0)
            except asyncio.TimeoutError:
                logger.error("❌ Agent execution timed out after 60 seconds")
                raise Exception("Agent execution timed out - please try a simpler query")
            runner_time = time.time() - runner_start
            logger.info(f"⚡ Agent execution took {runner_time:.3f}s")

            # Clean up MCP servers
            cleanup_start = time.time()
            for server in mcp_server_instances:
                try:
                    # Try different cleanup methods since the API is inconsistent
                    if hasattr(server, "disconnect"):
                        await server.disconnect()
                    elif hasattr(server, "close"):
                        await server.close()
                    elif hasattr(server, "__aexit__"):
                        await server.__aexit__(None, None, None)
                    # Force cleanup of the underlying process if available
                    elif hasattr(server, "_process") and server._process:
                        try:
                            server._process.terminate()
                        except:
                            pass
                except AttributeError as e:
                    # Expected error - MCP SDK doesn't have consistent cleanup API
                    logger.debug(f"MCP server cleanup AttributeError (expected): {e}")
                except RuntimeError as e:
                    if "Attempted to exit cancel scope" in str(e):
                        # Expected asyncio cleanup error - ignore it
                        logger.debug(f"MCP server asyncio cleanup error (expected): {e}")
                    else:
                        logger.warning(f"Unexpected RuntimeError during MCP cleanup: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error closing MCP server: {e}")
            cleanup_time = time.time() - cleanup_start
            logger.info(f"⚡ MCP cleanup took {cleanup_time:.3f}s")

            # Return response
            response_prep_start = time.time()
            response_data = {
                "response": str(response.final_output) if response.final_output else str(response),
                "mcp_servers_used": len(mcp_server_instances),
            }
            response_prep_time = time.time() - response_prep_start
            logger.info(f"⚡ Response preparation took {response_prep_time:.3f}s")

            total_time = time.time() - request_start
            logger.info(f"🏁 Total request time: {total_time:.3f}s")
            logger.info(
                f"📊 Breakdown - Parse: {parse_time:.3f}s, Settings: {settings_time:.3f}s, Import: {import_time:.3f}s, Key: {key_time:.3f}s, MCP: {mcp_time:.3f}s, Agent: {agent_time:.3f}s, Runner: {runner_time:.3f}s, Cleanup: {cleanup_time:.3f}s, Prep: {response_prep_time:.3f}s"
            )

            self.write(response_data)

        except Exception as e:
            total_time = time.time() - request_start
            logger.error(f"❌ Error in ChatOpenAIHandler after {total_time:.3f}s: {e}")
            logger.error(f"❌ Exception type: {type(e)}")
            import traceback

            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            self.set_status(500)
            self.write({"error": str(e)})


class ChatExtension(ExtensionApp):
    """JupyterLab Chat Extension Server"""

    name = "jupyterlab_chat"

    def initialize_handlers(self):
        """Initialize the extension's handlers"""
        handlers = [
            (r"/api/chat/openai", ChatOpenAIHandler),
        ]
        self.handlers.extend(handlers)


def _jupyter_server_extension_points():
    """Entry point for the server extension"""
    return [{"module": "jupyterlab_chat"}]


def _load_jupyter_server_extension(server_app):
    """Load the extension"""
    extension = ChatExtension()
    extension.initialize_settings()
    extension.initialize_handlers()
    server_app.web_app.add_handlers(".*$", extension.handlers)
    server_app.log.info("JupyterLab Chat extension loaded")
