import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.application import ExtensionApp
from tornado import web

# Import our JupyterAgent tools
from jupyter_agent_bridge.tools import JupyterAgent

# Module-level debug to confirm our code is loaded
logging.getLogger(__name__).info("🔥🔥🔥 JUPYTERLAB CHAT MODULE IMPORTED - NEW VERSION! 🔥🔥🔥")

# Import function_tool decorator for OpenAI Agents SDK
try:
    from agents import function_tool
except ImportError:
    # Fallback if agents package not available
    def function_tool(func):
        return func

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages chat conversation threads in notebook metadata"""
    
    def __init__(self, serverapp):
        self.serverapp = serverapp
    
    async def load_conversation_history(self, notebook_path: str) -> Dict:
        """Load conversation threads from notebook metadata"""
        try:
            # Get notebook content via Contents API
            import aiohttp
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            token = self._get_server_token()
            headers = {"Authorization": f"token {token}"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{server_url}/api/contents/{notebook_path}", headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(f"Failed to load notebook {notebook_path}: {resp.status}")
                        return self._create_empty_conversations()
                    
                    notebook_data = await resp.json()
                    metadata = notebook_data.get("content", {}).get("metadata", {})
                    return metadata.get("chat_conversations", self._create_empty_conversations())
        
        except Exception as e:
            logger.error(f"Error loading conversation history: {e}")
            return self._create_empty_conversations()
    
    async def save_conversation_message(self, notebook_path: str, message: Dict, thread_id: Optional[str] = None) -> str:
        """Save a message to conversation thread and return thread_id"""
        try:
            # Load current conversations
            conversations = await self.load_conversation_history(notebook_path)
            
            # Create new thread if needed
            if not thread_id:
                thread_id = str(uuid.uuid4())
                conversations["threads"][thread_id] = {
                    "created": datetime.utcnow().isoformat(),
                    "last_updated": datetime.utcnow().isoformat(),
                    "title": self._generate_thread_title(message.get("content", "")),
                    "messages": []
                }
                conversations["active_thread"] = thread_id
                conversations["thread_order"].insert(0, thread_id)
            
            # Add message to thread
            if thread_id in conversations["threads"]:
                conversations["threads"][thread_id]["messages"].append({
                    **message,
                    "timestamp": datetime.utcnow().isoformat()
                })
                conversations["threads"][thread_id]["last_updated"] = datetime.utcnow().isoformat()
                conversations["active_thread"] = thread_id
                
                # Update thread order (move to front)
                if thread_id in conversations["thread_order"]:
                    conversations["thread_order"].remove(thread_id)
                conversations["thread_order"].insert(0, thread_id)
            
            # Save back to notebook
            await self._save_conversations_to_notebook(notebook_path, conversations)
            return thread_id
            
        except Exception as e:
            logger.error(f"Error saving conversation message: {e}")
            return thread_id or str(uuid.uuid4())
    
    def _create_empty_conversations(self) -> Dict:
        """Create empty conversation structure"""
        return {
            "threads": {},
            "active_thread": None,
            "thread_order": []
        }
    
    def _generate_thread_title(self, first_message: str) -> str:
        """Generate thread title from first user message"""
        if not first_message:
            return f"Chat {datetime.utcnow().strftime('%H:%M')}"
        
        # Take first 50 chars, clean up
        title = first_message[:50].strip()
        if len(first_message) > 50:
            title += "..."
        return title
    
    def _get_server_token(self) -> Optional[str]:
        """Get server token for API calls"""
        if hasattr(self.serverapp, 'identity_provider') and hasattr(self.serverapp.identity_provider, 'token'):
            return self.serverapp.identity_provider.token
        if hasattr(self.serverapp, 'token'):
            return self.serverapp.token
        return None
    
    async def _save_conversations_to_notebook(self, notebook_path: str, conversations: Dict):
        """Save conversations back to notebook metadata"""
        try:
            import aiohttp
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            token = self._get_server_token()
            headers = {"Authorization": f"token {token}"}
            
            async with aiohttp.ClientSession() as session:
                # Get current notebook
                async with session.get(f"{server_url}/api/contents/{notebook_path}", headers=headers) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to load notebook for saving: {resp.status}")
                        return
                    
                    notebook_data = await resp.json()
                    
                # Update metadata
                if "metadata" not in notebook_data["content"]:
                    notebook_data["content"]["metadata"] = {}
                notebook_data["content"]["metadata"]["chat_conversations"] = conversations
                
                # Save notebook
                save_data = {
                    "type": "notebook",
                    "content": notebook_data["content"]
                }
                
                async with session.put(f"{server_url}/api/contents/{notebook_path}", headers=headers, json=save_data) as resp:
                    if resp.status != 200:
                        logger.error(f"Failed to save notebook conversations: {resp.status}")
                    else:
                        logger.info(f"💾 Saved conversation to {notebook_path}")
                        
        except Exception as e:
            logger.error(f"Error saving conversations to notebook: {e}")


class ChatOpenAIHandler(APIHandler):
    """Handler for OpenAI chat requests with MCP server support"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mcp_servers = {}
        self.conversation_manager = ConversationManager(self.serverapp)

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    async def post(self):
        """Handle POST requests to /api/chat/openai"""
        self.log.info("🚨🚨🚨 CHAT HANDLER CALLED - VERSION 2 - NEW CODE LOADED! 🚨🚨🚨")
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
            notebook_path = context.get("notebook_path", "Untitled.ipynb")
            thread_id = body.get("thread_id")  # Optional: continue existing thread
            parse_time = time.time() - parse_start
            logger.info(f"⚡ Request parsing took {parse_time:.3f}s")
            self.log.info(f"🎯 USING MODEL: {model} (from request body)")

            # Load conversation history
            history_start = time.time()
            conversations = await self.conversation_manager.load_conversation_history(notebook_path)
            active_thread_id = thread_id or conversations.get("active_thread")
            
            # Get conversation context for LLM
            conversation_context = []
            if active_thread_id and active_thread_id in conversations.get("threads", {}):
                conversation_context = conversations["threads"][active_thread_id].get("messages", [])
                logger.info(f"📚 Loaded {len(conversation_context)} previous messages from thread {active_thread_id[:8]}...")
            
            history_time = time.time() - history_start
            logger.info(f"⚡ Conversation history loading took {history_time:.3f}s")

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

            # Create JupyterAgent instance for notebook manipulation
            jupyter_agent_start = time.time()
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            # Get token from server
            token = None
            if hasattr(self.serverapp, 'identity_provider') and hasattr(self.serverapp.identity_provider, 'token'):
                token = self.serverapp.identity_provider.token
            if not token and hasattr(self.serverapp, 'token'):
                token = self.serverapp.token
            
            logger.info(f"🔑 Using server token: {token[:16] + '...' if token else 'None'}")
            
            jupyter_agent = JupyterAgent(server_url, token)
            jupyter_agent_time = time.time() - jupyter_agent_start
            logger.info(f"⚡ JupyterAgent setup took {jupyter_agent_time:.3f}s")

            # Create function tools from JupyterAgent methods
            tools_start = time.time()
            
            @function_tool
            async def insert_code_and_execute(code: str, notebook_path: str = "Untitled.ipynb", cell_type: str = "code", position: str = "end", kernel_id: str = None):
                """Insert code into a notebook cell, execute it, and capture outputs (PRIMARY TOOL)"""
                return await jupyter_agent.insert_code_and_execute(notebook_path, code, cell_type, position, kernel_id)

            @function_tool
            async def insert_cell(source: str, notebook_path: str = "Untitled.ipynb", cell_type: str = "code", position: str = "end"):
                """Insert a new cell with specified content"""
                return await jupyter_agent.insert_cell(notebook_path, source, cell_type, position)

            @function_tool
            async def execute_cell(notebook_path: str = "Untitled.ipynb", cell_id: str = None, content: str = None, kernel_id: str = None):
                """Execute code in a specified cell or provided content and get its outputs"""
                return await jupyter_agent.execute_cell(notebook_path, cell_id, content, kernel_id)

            @function_tool
            async def update_cell_outputs(notebook_path: str = "Untitled.ipynb", cell_id: str = None, outputs: str = None, execution_count: int = None):
                """Update a cell's outputs with execution results. Pass outputs as JSON string."""
                if outputs and isinstance(outputs, str):
                    import json
                    outputs_list = json.loads(outputs)
                else:
                    outputs_list = outputs
                return await jupyter_agent.update_cell_outputs(notebook_path, cell_id, outputs_list, execution_count)

            @function_tool
            async def get_cell_content(notebook_path: str = "Untitled.ipynb", cell_id: str = None):
                """Get cell content by UUID or all cells in the notebook"""
                return await jupyter_agent.get_cell_content(notebook_path, cell_id)

            @function_tool
            async def insert_markdown(markdown: str, notebook_path: str = "Untitled.ipynb", position: str = "end"):
                """Insert markdown cells for documentation and explanations"""
                return await jupyter_agent.insert_markdown(notebook_path, markdown, position)

            jupyter_tools = [
                insert_code_and_execute,
                insert_cell,
                execute_cell,
                update_cell_outputs,
                get_cell_content,
                insert_markdown,
            ]
            
            tools_time = time.time() - tools_start
            logger.info(f"⚡ JupyterAgent tools setup took {tools_time:.3f}s")

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

            # Create agent with both JupyterAgent tools and MCP servers
            agent_start = time.time()
            agent = Agent(
                name="JupyterLab Chat Assistant",
                model=model,
                tools=jupyter_tools,  # Add our JupyterAgent tools
                mcp_servers=mcp_server_instances,  # Keep MCP servers
                instructions="""You are a helpful JupyterLab assistant with access to both notebook manipulation tools and external data tools.

## Notebook Manipulation Tools:
- **insert_code_and_execute**: Insert and execute code, capture outputs (primary tool for 90% of operations)
- **insert_cell**: Add cells without execution
- **execute_cell**: Run existing cells
- **get_cell_content**: Read notebook content and cell details
- **insert_markdown**: Add documentation and explanations
- **update_cell_outputs**: Update cell outputs (advanced use)

## External Data Tools:
- **MCP tools**: When available, use for database queries, API calls, and external data access

## Guidelines:
- Use **insert_code_and_execute** for most coding tasks (it handles insertion, execution, and output capture)
- Use **insert_markdown** to explain your work and provide context
- Use **get_cell_content** to understand the current notebook state before making changes
- When users ask for data analysis, plots, or calculations, create and execute the appropriate code
- Be helpful and execute code when users request it

IMPORTANT: When a user asks for a plan, task breakdown, or steps to accomplish something, format your response using cards. Each card should follow this exact format:
[CARD:Title|Description]

For example:
[CARD:Research the topic|Gather information about the subject from reliable sources]
[CARD:Create outline|Structure the main points and subtopics]
[CARD:Write first draft|Begin writing the content based on the outline]

For regular questions that don't require planning, respond normally.""",
            )
            agent_time = time.time() - agent_start
            logger.info(f"⚡ Agent creation took {agent_time:.3f}s")

            # Save user message to conversation history
            save_user_start = time.time()
            user_message = {"role": "user", "content": message}
            active_thread_id = await self.conversation_manager.save_conversation_message(
                notebook_path, user_message, active_thread_id
            )
            save_user_time = time.time() - save_user_start
            logger.info(f"⚡ User message saving took {save_user_time:.3f}s")

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

            # Save assistant response to conversation history
            save_assistant_start = time.time()
            
            # Extract tool calls from OpenAI Agents SDK response - CORRECT APPROACH
            tool_calls = []
            
            # Debug: log response structure
            logger.info(f"🔍 Response type: {type(response)}")
            logger.info(f"🔍 Response attributes: {dir(response)}")
            
            # The correct way: OpenAI Agents SDK stores tool information in result.new_items
            if hasattr(response, 'new_items') and response.new_items:
                logger.info(f"🔍 Found {len(response.new_items)} new_items")
                
                for i, item in enumerate(response.new_items):
                    logger.info(f"🔍 Item {i}: type={type(item).__name__}")
                    
                    # Look for ToolCallItem (when tool is called) and ToolCallOutputItem (tool result)
                    item_type = type(item).__name__
                    if 'ToolCall' in item_type:
                        logger.info(f"🔧 Found tool call item: {item_type}")
                        
                        # Extract tool call information
                        tool_name = "unknown"
                        tool_args = "{}"
                        tool_id = f"call_{len(tool_calls)}"
                        
                        if hasattr(item, 'raw_item'):
                            raw_item = item.raw_item
                            if hasattr(raw_item, 'name'):
                                tool_name = raw_item.name
                            if hasattr(raw_item, 'arguments'):
                                tool_args = raw_item.arguments
                            if hasattr(raw_item, 'id'):
                                tool_id = raw_item.id
                        elif hasattr(item, 'name'):
                            tool_name = item.name
                        
                        tool_calls.append({
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_args if isinstance(tool_args, str) else str(tool_args)
                            }
                        })
                        logger.info(f"🔧 Extracted tool call: {tool_name}")
            else:
                logger.info("🔍 No new_items found in response")
            
            # Log what we found for debugging
            logger.info(f"🔧 Extracted {len(tool_calls)} tool calls from response")
            for tool_call in tool_calls:
                func_name = tool_call.get('function', {}).get('name', 'unknown')
                logger.info(f"   - Tool: {func_name}")
            
            assistant_message = {
                "role": "assistant", 
                "content": str(response.final_output) if response.final_output else str(response),
                "tool_calls": tool_calls
            }
            await self.conversation_manager.save_conversation_message(
                notebook_path, assistant_message, active_thread_id
            )
            save_assistant_time = time.time() - save_assistant_start
            logger.info(f"⚡ Assistant message saving took {save_assistant_time:.3f}s")

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
                "jupyter_tools_available": len(jupyter_tools),
                "thread_id": active_thread_id,
                "notebook_path": notebook_path,
            }
            response_prep_time = time.time() - response_prep_start
            logger.info(f"⚡ Response preparation took {response_prep_time:.3f}s")

            total_time = time.time() - request_start
            logger.info(f"🏁 Total request time: {total_time:.3f}s")
            logger.info(
                f"📊 Breakdown - Parse: {parse_time:.3f}s, History: {history_time:.3f}s, Settings: {settings_time:.3f}s, Import: {import_time:.3f}s, Key: {key_time:.3f}s, JupyterAgent: {jupyter_agent_time:.3f}s, Tools: {tools_time:.3f}s, MCP: {mcp_time:.3f}s, Agent: {agent_time:.3f}s, SaveUser: {save_user_time:.3f}s, Runner: {runner_time:.3f}s, SaveAssistant: {save_assistant_time:.3f}s, Cleanup: {cleanup_time:.3f}s, Prep: {response_prep_time:.3f}s"
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
