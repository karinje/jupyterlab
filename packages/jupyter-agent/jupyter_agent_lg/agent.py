"""
LangGraph Data Analysis Agen

The main agent class that orchestrates data analysis workflows using LangGraph
for state management and decision routing. Provides pure LLM-driven analysis
with dynamic planning and user interaction.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from datetime import datetime

from .state import create_initial_state, increment_iteration
from .context import NotebookStateManager
from .tools import create_jupyter_tools
from jupyter_tools_bridge.tools import JupyterTools
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from pydantic import create_model, Field, BaseModel

# Set up proper logging using simplified config
try:
    from jupyter_tools_bridge.logging_config import get_logger

    logger = get_logger()
except ImportError:
    # Fallback if centralized logging not available
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger("jupyterlab")


class ChatHandler:
    """Handles communication with chat UI"""

    def __init__(self, server_url: str, token: str = None):
        self.server_url = server_url
        self.token = token
        self.default_notebook_path: Optional[str] = None
        self.current_thread_id: Optional[str] = None  # Track current thread

    async def send_status(
        self,
        message: str,
        status_type: str = "working",
        *,
        notebook_path: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        """Send status update to chat UI"""
        try:
            import aiohttp

            headers = {}
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.server_url}/api/chat/status",
                    json={
                        "type": "status",  # Always use "status" type for proper broadcast handling
                        "status": status_type,  # Move the actual status to status field
                        "message": message,
                        "timestamp": datetime.utcnow().isoformat(),
                        "notebook_path": notebook_path or self.default_notebook_path,
                        "tool_call_id": tool_call_id,
                        "thread_id": thread_id,
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                logger.info(f"📡 Status sent: {message}")
        except Exception as e:
            logger.warning(f"Failed to send status: {e}")

    async def send_message(
        self,
        message: str,
        notebook_path: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        thread_title: Optional[str] = None,
    ):
        """Send a message to the chat UI"""
        try:
            import aiohttp

            headers = {}
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.server_url}/api/chat/message",
                    json={
                        "content": message,
                        "timestamp": datetime.utcnow().isoformat(),
                        "notebook_path": notebook_path or self.default_notebook_path,
                        "tool_call_id": tool_call_id,
                        "thread_id": thread_id or self.current_thread_id,
                        "thread_title": thread_title,
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                logger.info(f"💬 Message sent: {message[:100]}...")
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")

    async def display_plan_cards(
        self,
        plan_steps: List[Dict[str, str]],
        notebook_path: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        """Display plan steps as editable cards in chat UI"""
        try:
            import aiohttp

            headers = {}
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.server_url}/api/chat/plan_cards",
                    json={
                        "plan_steps": plan_steps,
                        "notebook_path": notebook_path or self.default_notebook_path,
                        "timestamp": datetime.utcnow().isoformat(),
                        "thread_id": thread_id,
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                logger.info(f"📋 Plan cards displayed: {len(plan_steps)} steps")
        except Exception as e:
            logger.warning(f"Failed to display plan cards: {e}")

    async def save_tool_interactions(
        self,
        messages: List[Dict[str, Any]],
        notebook_path: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        """Save tool call and result messages to conversation thread for persistence"""
        try:
            import aiohttp

            headers = {}
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.server_url}/api/chat/save_tool_messages",
                    json={
                        "messages": messages,
                        "notebook_path": notebook_path or self.default_notebook_path,
                        "thread_id": thread_id or self.current_thread_id,
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                logger.info(f"💾 Saved {len(messages)} tool interaction messages to thread")
        except Exception as e:
            logger.warning(f"Failed to save tool interactions: {e}")

    async def save_thread_title(
        self,
        title: str,
        notebook_path: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        """Save thread title to conversation metadata"""
        try:
            import aiohttp

            headers = {}
            if self.token:
                headers["Authorization"] = f"token {self.token}"

            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.server_url}/api/chat/thread-title",
                    json={
                        "title": title,
                        "notebook_path": notebook_path or self.default_notebook_path,
                        "thread_id": thread_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                logger.info(f"💾 Thread title saved: {title}")
        except Exception as e:
            logger.warning(f"Failed to save thread title: {e}")


class JupyterAgent:
    """
    LangGraph-based agent for Jupyter notebook tasks

    Features:
    - Pure LLM-driven decision making
    - Dynamic planning with user interaction
    - Multi-step analysis with context awareness
    - Real-time status updates
    - Multi-LLM support
    """

    def __init__(
        self,
        server_url: str,
        token: str,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_notebook_path: str = "analysis.ipynb",
        chat_handler: Optional[ChatHandler] = None,
    ):
        self.server_url = server_url
        self.token = token
        self.default_notebook_path = default_notebook_path
        self.current_task = None  # Track current processing task for cancellation

        # Initialize components
        self.notebook_state_manager = NotebookStateManager(server_url, token)
        # Allow DI of a custom chat transport from the frontend/backend integration
        self.chat_handler = chat_handler or ChatHandler(server_url, token)
        # Default notebook path for chat routing
        self.chat_handler.default_notebook_path = default_notebook_path
        self.jupyter_tools_client = JupyterTools(server_url, token)

        # Initialize LLMs directly
        self.openai_llm = (
            ChatOpenAI(api_key=openai_api_key, model="gpt-4o", temperature=0.2)
            if openai_api_key
            else None
        )
        self.claude_llm = (
            ChatAnthropic(
                api_key=anthropic_api_key,
                model="claude-3-5-sonnet-20241022",
                temperature=0.2,
            )
            if anthropic_api_key
            else None
        )
        # Gemini support - uncomment when API key available
        # from langchain_google_genai import ChatGoogleGenerativeAI
        # self.gemini_llm = ChatGoogleGenerativeAI(
        #     api_key=gemini_api_key, 
        #     model="gemini-2.0-flash-exp",
        #     temperature=0.2
        # )
        self.gemini_llm = None

        # Create tools and LLMs with tools ONCE
        self.jupyter_tools = create_jupyter_tools(
            self.jupyter_tools_client, default_notebook_path
        )

        # Create system tools (RespondToUser, CreatePlan)
        from .tools import create_system_tools

        self.system_tools = create_system_tools(self.chat_handler)

        # Optionally: load MCP tools if available
        try:
            from .tools.mcp_tools import create_mcp_tools

            self.mcp_tools = create_mcp_tools(
                None
            )  # TODO: inject real MCP client when ready
        except Exception:
            self.mcp_tools = []

        original_tools = self.system_tools + self.jupyter_tools + self.mcp_tools

        # Augment tool input schemas at bind time to add an optional status_message everywhere
        def _augment_tools_with_status_message(tools):
            augmented = []
            for t in tools:
                try:
                    args_schema = getattr(t, "args_schema", None)
                    if not args_schema or not issubclass(args_schema, BaseModel):
                        augmented.append(t)
                        continue
                    # Build a new Pydantic model extending the existing schema with optional status_message
                    # Pydantic v2: use model_fields mapping to FieldInfo
                    try:
                        base_fields = getattr(args_schema, "model_fields", {})
                        fields = {
                            name: (f.annotation, f) for name, f in base_fields.items()
                        }
                    except Exception:
                        # Fallback for older models
                        fields = {}
                    StatusModel = create_model(  # type: ignore
                        f"{args_schema.__name__}WithStatus",
                        **fields,
                        status_message=(
                            Optional[str],
                            Field(
                                default=None,
                                description="Short status to display before executing this action",
                            ),
                        ),
                        __base__=args_schema,
                    )
                    from langchain_core.tools import StructuredTool

                    new_tool = StructuredTool.from_function(
                        func=t.func,
                        name=t.name,
                        description=t.description,
                        args_schema=StatusModel,
                        coroutine=t.coroutine,
                        metadata=getattr(t, "metadata", None),  # Preserve metadata
                    )
                    augmented.append(new_tool)
                except Exception as e:
                    logger.warning(
                        f"failed to augment tool {getattr(t, 'name', str(t))}: {e}"
                    )
                    augmented.append(t)
            return augmented

        augmented_tools = _augment_tools_with_status_message(original_tools)

        self.openai_llm_with_tools = (
            self.openai_llm.bind_tools(
                augmented_tools, parallel_tool_calls=False, tool_choice="any"
            )
            if self.openai_llm
            else None
        )
        if self.openai_llm_with_tools:
            try:
                setattr(
                    self.openai_llm_with_tools,
                    "_bound_tool_names",
                    [t.name for t in augmented_tools],
                )
            except Exception:
                pass
        
        self.claude_llm_with_tools = (
            self.claude_llm.bind_tools(
                augmented_tools, parallel_tool_calls=False, tool_choice="any"
            )
            if self.claude_llm
            else None
        )
        if self.claude_llm_with_tools:
            try:
                setattr(
                    self.claude_llm_with_tools,
                    "_bound_tool_names",
                    [t.name for t in augmented_tools],
                )
            except Exception:
                pass
        
        self.gemini_llm_with_tools = (
            self.gemini_llm.bind_tools(
                augmented_tools, parallel_tool_calls=False, tool_choice="any"
            )
            if self.gemini_llm
            else None
        )
        if self.gemini_llm_with_tools:
            try:
                setattr(
                    self.gemini_llm_with_tools,
                    "_bound_tool_names",
                    [t.name for t in augmented_tools],
                )
            except Exception:
                pass

        # Build LangGraph workflow
        self.workflow = self._build_graph()

        logger.info(
            f"🤖 JupyterAgent initialized with {len(original_tools)} tools (augmented schemas for binding)"
        )

        # Store tool info for API access
        self._bound_tools = original_tools
        self._tool_categories = self._categorize_tools(original_tools)

    def _categorize_tools(self, tools) -> Dict[str, list]:
        """Categorize tools by their metadata - NO HARDCODING!"""
        categories = {}

        for tool in tools:
            tool_name = getattr(tool, "name", str(tool))

            # Get tool_category from metadata
            tool_metadata = getattr(tool, "metadata", {}) or {}
            tool_category = tool_metadata.get("tool_category", "Other Tools")

            # Skip system tools - don't show to user
            if tool_category == "System Tools":
                continue

            # Use the tool's own category metadata
            if tool_category not in categories:
                categories[tool_category] = []
            categories[tool_category].append(tool_name)

        return categories

    def get_available_tool_categories(self) -> list:
        """Get list of available tool categories (public API)"""
        return list(self._tool_categories.keys())

    def get_tool_info(self) -> Dict[str, Any]:
        """Get complete tool information (public API)"""

        return {
            "categories": list(self._tool_categories.keys()),
            "tools": self._tool_categories,
            "total_tools": len(self._bound_tools),
        }

    def _list_bound_tools_and_params(self, llm) -> List[Dict[str, Any]]:
        """Return provider-agnostic view of bound tools from a tool-bound LLM runnable.

        Supports OpenAI (tools=[{"type":"function","function":{...}}]) and Anthropic
        (tools=[{"name":..., "input_schema":{...}}]) formats. Falls back gracefully.
        """
        result: List[Dict[str, Any]] = []
        try:
            raw_tools = []
            if hasattr(llm, "kwargs") and isinstance(getattr(llm, "kwargs"), dict):
                raw_tools = llm.kwargs.get("tools", []) or []
            for t in raw_tools:
                tool_name = "unknown"
                params_schema: Dict[str, Any] = {}
                if isinstance(t, dict) and "function" in t:
                    fn = t.get("function", {}) or {}
                    tool_name = fn.get("name", "unknown")
                    params_schema = fn.get("parameters", {}) or {}
                elif isinstance(t, dict) and "input_schema" in t:
                    tool_name = t.get("name", "unknown")
                    params_schema = t.get("input_schema", {}) or {}
                else:
                    if isinstance(t, dict):
                        tool_name = t.get("name", "unknown")
                        params_schema = t.get("parameters", {}) or {}

                props: Dict[str, Any] = params_schema.get("properties", {}) or {}
                required = set(params_schema.get("required", []) or [])
                params_list: List[Dict[str, Any]] = []
                for param_name, meta in props.items():
                    if not isinstance(meta, dict):
                        params_list.append(
                            {
                                "name": param_name,
                                "type": "unknown",
                                "required": param_name in required,
                                "description": "",
                            }
                        )
                        continue
                    ptype = (
                        meta.get("type")
                        or meta.get("anyOf")
                        or meta.get("$ref")
                        or "unknown"
                    )
                    params_list.append(
                        {
                            "name": param_name,
                            "type": ptype,
                            "required": param_name in required,
                            "description": meta.get("description", ""),
                        }
                    )

                result.append({"tool": tool_name, "params": params_list})
        except Exception as e:
            logger.warning(f"tool enumeration failed: {e}")
        return result

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(dict)

        workflow.add_node("analyze_and_decide", self.analyze_and_decide)
        workflow.add_node("tools", self.execute_tools)

        workflow.set_entry_point("analyze_and_decide")

        # analyze -> tools or analyze (self-loop)
        def route_from_analyze(state: Dict[str, Any]) -> str:
            messages = state.get("messages", [])
            if not messages:
                return "retry"
            # Find the most recent assistant message object (with potential tool_calls)
            candidate = None
            for msg in reversed(messages):
                # LangChain AIMessage has attribute 'tool_calls'; system/user dicts will no
                if hasattr(msg, "tool_calls"):
                    candidate = msg
                    break
            if candidate is None:
                return "retry"
            tool_calls = getattr(candidate, "tool_calls", []) or []
            return "tools" if len(tool_calls) > 0 else "retry"

        workflow.add_conditional_edges(
            "analyze_and_decide",
            route_from_analyze,
            {
                "tools": "tools",
                "retry": "analyze_and_decide",
            },
        )

        # tools -> analyze or END
        def route_from_tools(state: Dict[str, Any]) -> str:
            return state.get("route_after_tools", "continue")

        workflow.add_conditional_edges(
            "tools",
            route_from_tools,
            {
                "continue": "analyze_and_decide",
                "end": END,
            },
        )

        return workflow.compile()

    async def execute_tools(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute exactly the first tool_call from the last AI message and route accordingly."""
        try:
            from langchain_core.messages import ToolMessage

            logger.info("🛠️ [tools] start")
            preserved_state = dict(state)
            preserved_state["route_after_tools"] = "continue"
            messages = state.get("messages", [])
            if not messages:
                preserved_state["route_after_tools"] = "end"
                return preserved_state
            last_message = messages[-1]
            tool_calls = getattr(last_message, "tool_calls", []) or []
            if not tool_calls:
                preserved_state["route_after_tools"] = "end"
                return preserved_state
            first_call = tool_calls[0]
            name = first_call.get("name")
            args = first_call.get("args", {}) or {}
            logger.warning(
                f"🛠️ [tools] executing name={name} args={args} id={first_call.get('id')}"
            )
            # Execute only the first tool_call and append its ToolMessage
            # Special handling for CreatePlan to pass state context
            if name == "CreatePlan":
                result = await self._execute_create_plan_with_context(first_call, state)
            else:
                result = await self._execute_single_tool(first_call)

            tool_msg = ToolMessage(
                content=str(result), name=name, tool_call_id=first_call.get("id")
            )
            # Route based on tool name/intent
            route = "continue"
            if name == "RespondToUser":
                route = "end"
                # Always surface the RespondToUser message as final_result so the UI shows exact text
                preserved_state["final_result"] = args.get("message", "")
            elif name == "CreatePlan":
                route = "end"  # Wait for user response after creating plan
                preserved_state["final_result"] = (
                    "Plan created. Please review and let me know how to proceed."
                )
            preserved_state["route_after_tools"] = route
            preserved_state["messages"] = messages + [tool_msg]
            preserved_state["last_payload_name"] = name
            preserved_state["last_payload_args"] = args
            logger.info(f"🛠️ [tools] route_after_tools={route}")
            return preserved_state

        except Exception as e:
            logger.error(f"❌ [tools] exception: {e}")
            state["route_after_tools"] = "end"
            return state

    async def _execute_single_tool(self, tool_call: Dict[str, Any]):
        """Find and execute a single tool call from the aggregated tool list."""
        name = tool_call.get("name")
        args = dict(tool_call.get("args", {}) or {})
        # Uniform status extraction: allow any tool to carry an optional status_message
        status_message = args.pop("status_message", None)
        try:
            if (
                status_message
                and hasattr(self, "chat_handler")
                and hasattr(self.chat_handler, "send_status")
            ):
                logger.info(f"🛎️ [tools] sending status_message: {status_message}")
                await self.chat_handler.send_status(status_message, "working")
                # Status message is sent via send_status() which creates proper status messages
        except Exception:
            pass
        # Aggregate tools we bound
        tools = (
            getattr(self, "system_tools", [])
            + getattr(self, "jupyter_tools", [])
            + getattr(self, "mcp_tools", [])
        )
        for t in tools:
            if t.name == name:
                if asyncio.iscoroutinefunction(t.func):
                    return await t.func(**args)
                return t.func(**args)
        return f"Tool {name} not found"

    async def _execute_create_plan_with_context(
        self, tool_call: Dict[str, Any], state: Dict[str, Any]
    ):
        """Execute CreatePlan tool with state context (notebook_path, thread_id)"""
        args = dict(tool_call.get("args", {}) or {})
        plan_steps = args.get("plan_steps", [])

        # Convert plan steps to dict format
        steps = [
            step.model_dump() if hasattr(step, "model_dump") else dict(step)
            for step in plan_steps
        ]

        # Get context from state
        notebook_path = state.get("notebook_path")
        thread_id = state.get("thread_id")

        # Call display_plan_cards with context
        await self.chat_handler.display_plan_cards(steps, notebook_path, thread_id)
        logger.info(
            f"Created plan with {len(steps)} steps (notebook: {notebook_path}, thread: {thread_id})"
        )
        return f"plan_created: steps={len(steps)}"

    def update_notebook_path(self, new_notebook_path: str):
        """Update tools and LLMs when notebook path changes"""
        logger.info(f"🔄 Updating notebook path to: {new_notebook_path}")

        # Recreate Jupyter tools with new notebook path
        self.jupyter_tools = create_jupyter_tools(
            self.jupyter_tools_client, new_notebook_path
        )

        # System tools depend only on chat handler; keep as-is
        from .tools import create_system_tools

        self.system_tools = create_system_tools(self.chat_handler)

        # Recreate MCP tools if applicable (kept as-is here)
        try:
            from .tools.mcp_tools import create_mcp_tools

            self.mcp_tools = create_mcp_tools(None)
        except Exception:
            self.mcp_tools = []

        all_tools = self.system_tools + self.jupyter_tools + self.mcp_tools

        # Rebind tools to LLMs
        if self.openai_llm:
            self.openai_llm_with_tools = self.openai_llm.bind_tools(
                all_tools, parallel_tool_calls=False
            )
        if self.claude_llm:
            self.claude_llm_with_tools = self.claude_llm.bind_tools(
                all_tools, parallel_tool_calls=False
            )
        if self.gemini_llm:
            self.gemini_llm_with_tools = self.gemini_llm.bind_tools(
                all_tools, parallel_tool_calls=False
            )

        # Rebuild workflow
        self.workflow = self._build_graph()

        logger.info(f"✅ Updated tools and workflow for notebook: {new_notebook_path}")

    def cancel_current_task(self):
        """Cancel the currently running task if any"""
        if self.current_task and not self.current_task.done():
            logger.info("🛑 Cancelling current agent task")
            self.current_task.cancel()
            return True
        return False

    async def _persist_tool_messages(
        self, final_state: Dict[str, Any], notebook_path: str, thread_id: str
    ):
        """Extract and save tool interaction messages to conversation thread.
        
        Converts LangChain message objects to OpenAI-compatible dict format and saves them.
        These messages are filtered from UI display but included in LLM context.
        """
        try:
            from langchain_core.messages import AIMessage, ToolMessage

            messages = final_state.get("messages", [])
            if not messages:
                logger.info("💾 No state messages to persist - state['messages'] is empty")
                return

            # Get initial conversation length to determine which messages are NEW
            initial_conv_history = final_state.get("conversation_history", [])
            logger.info(
                f"💾 state['messages'] has {len(messages)} total messages"
            )
            logger.info(
                f"💾 conversation_history had {len(initial_conv_history)} messages at start"
            )
            
            # Log EXACT content of state["messages"] for debugging
            import json
            for i, msg in enumerate(messages):
                msg_type = type(msg).__name__
                tool_calls = getattr(msg, "tool_calls", [])
                tool_call_id = getattr(msg, "tool_call_id", None)
                name = getattr(msg, "name", None)
                content_preview = str(getattr(msg, "content", ""))[:80]
                logger.info(
                    f"💾   state['messages'][{i}]: type={msg_type}, "
                    f"tool_calls={len(tool_calls) if tool_calls else 0}, "
                    f"tool_call_id={tool_call_id}, name={name}, content={content_preview}"
                )

            # Convert LangChain messages to OpenAI-compatible format
            messages_to_save = []

            # Save ALL messages from state["messages"] - they're all from THIS workflow run
            for msg in messages:
                # AIMessage with tool_calls - save all tools uniformly
                if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", []):
                    tool_calls = msg.tool_calls
                    if tool_calls:
                        tool_name = tool_calls[0].get("name")
                        
                        # Save all tool calls uniformly (except CreatePlan which is handled in ToolMessage)
                        if tool_name != "CreatePlan":
                            # Save COMPLETE message dict for cache integrity
                            msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else msg.dict() if hasattr(msg, "dict") else {}
                            # Add our metadata
                            if "metadata" not in msg_dict:
                                msg_dict["metadata"] = {}
                            msg_dict["metadata"]["messageType"] = "tool_call"
                            messages_to_save.append(msg_dict)
                        # CreatePlan is handled in ToolMessage section below

                # ToolMessage (result from tool execution)
                elif isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, "name", "unknown")
                    
                    # Special handling for CreatePlan - save as user message with plan format
                    if tool_name == "CreatePlan":
                        # Extract plan steps from the AIMessage that called CreatePlan
                        # Find the corresponding AIMessage with CreatePlan tool_call
                        for prev_msg in messages:
                            if isinstance(prev_msg, AIMessage) and getattr(prev_msg, "tool_calls", []):
                                prev_tool_calls = prev_msg.tool_calls
                                if prev_tool_calls and prev_tool_calls[0].get("name") == "CreatePlan":
                                    # Extract plan_steps from the tool call arguments
                                    plan_steps = prev_tool_calls[0].get("args", {}).get("plan_steps", [])
                                    
                                    # Convert to [CARD:title|description] format
                                    plan_content = "Final plan that needs to be implemented:\n\n"
                                    for step in plan_steps:
                                        title = step.get("title", "")
                                        description = step.get("description", "")
                                        plan_content += f"[CARD:{title}|{description}]\n"
                                    
                                    # Save as user message (so LLM treats it as instructions)
                                    messages_to_save.append({
                                        "role": "user",
                                        "content": plan_content.strip(),
                                        "metadata": {"messageType": "plan"}
                                    })
                                    break
                    else:
                        # Regular tool message - save COMPLETE dict for cache integrity
                        msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else msg.dict() if hasattr(msg, "dict") else {}
                        # Add our metadata
                        if "metadata" not in msg_dict:
                            msg_dict["metadata"] = {}
                        msg_dict["metadata"]["messageType"] = "tool_result"
                        messages_to_save.append(msg_dict)

            # Save to conversation thread if we have messages
            if messages_to_save:
                logger.info(
                    f"💾 Persisting {len(messages_to_save)} tool interaction messages"
                )
                await self.chat_handler.save_tool_interactions(
                    messages_to_save, notebook_path, thread_id
                )
            else:
                logger.info("💾 No tool interaction messages to persist (only RespondToUser/CreatePlan)")

        except Exception as e:
            logger.error(f"❌ Failed to persist tool messages: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def process_request(
        self,
        request: str,
        notebook_path: str,
        conversation_history: List[Dict[str, str]],
        model: str = "gpt-4o",
        provider: str = "openai",
        mcp_servers: Dict = None,
        thread_id: str = None,
    ) -> str:
        """Process a user request through the LangGraph workflow"""
        try:
            logger.info(f"�� Processing request: {request[:100]}...")

            # Update tools if notebook path changed
            if notebook_path != self.default_notebook_path:
                self.update_notebook_path(notebook_path)
            # Ensure chat messages (status/text) route to the current notebook over WS
            try:
                self.chat_handler.default_notebook_path = notebook_path
                self.chat_handler.current_thread_id = (
                    thread_id  # Set current thread for this request
                )
            except Exception:
                pass
            # Keep internal default in sync to avoid repeated updates on subsequent turns
            self.default_notebook_path = notebook_path

            # Initialize state
            initial_state = create_initial_state(
                request, notebook_path, conversation_history, model, provider, thread_id
            )

            # DEBUG: Check initial state creation
            logger.info(
                f"🔍 Initial state created with keys: {list(initial_state.keys())}"
            )
            logger.info(
                f"🔍 notebook_path in initial_state: {initial_state.get('notebook_path', 'MISSING')}"
            )

            # Get current notebook state and available data sources  
            notebook_multimodal_content = await self.notebook_state_manager.get_complete_notebook_state(
                notebook_path
            )
            # Store minimal cell info for state tracking
            initial_state["notebook_cells"] = [{"index": i} for i in range(len([item for item in notebook_multimodal_content if "Index" in item.get("text", "")]))]
            initial_state[
                "execution_history"
            ] = await self.notebook_state_manager.get_execution_history(notebook_path)
            initial_state[
                "available_data_sources"
            ] = await self.notebook_state_manager.get_available_data_sources(
                mcp_servers
            )

            # DEBUG: Check state before workflow
            logger.info(
                f"🔍 State before workflow with keys: {list(initial_state.keys())}"
            )
            logger.info(
                f"🔍 notebook_path before workflow: {initial_state.get('notebook_path', 'MISSING')}"
            )

            # Run the workflow with cancellation support
            logger.info(
                f"🚀 About to call workflow.ainvoke with state keys: {list(initial_state.keys())}"
            )
            task = asyncio.create_task(self.workflow.ainvoke(initial_state))
            self.current_task = task
            final_state = await task
            self.current_task = None
            logger.info(
                f"🏁 Workflow completed with final state keys: {list(final_state.keys())}"
            )

            # CRITICAL: Persist tool interaction messages to conversation thread
            # This ensures tool calls/results survive across agent invocations
            await self._persist_tool_messages(final_state, notebook_path, thread_id)

            # Extract result to return
            result = final_state.get("final_result", "Analysis completed")

            # Don't send "analysis completed" status - let user decide when they're done
            return result

        except asyncio.CancelledError:
            logger.info("🛑 Agent execution cancelled by user - this is normal")
            self.current_task = None
            return "Task cancelled by user request"
        except Exception as e:
            logger.error(f"❌ Error processing request: {e}")
            self.current_task = None
            return f"Error processing request: {e}"

    def _create_system_instructions(self) -> str:
        """Create system instructions without conversation history"""
        return """You are a data analysis agent working in JupyterLab. You have access to a live Jupyter notebook and can execute code, create visualizations, and manipulate cells in real-time.

CONTEXT YOU RECEIVE:
1. **Conversation History**: All previous user messages and your responses in this thread
2. **Current Notebook State**: Complete contents of the active notebook including:
   - ALL cells (code, markdown, empty) with their actual 0-based indices
   - Execution status for each code cell (executed with count, or not executed)
   - Full source code for every cell (not truncated)
   - Output indicators (plots, data, text)

HOW TO RESPOND:
- Read the conversation history to understand what the user wants
- Check the notebook state to see what's already been done
- Use Jupyter tools to modify the notebook (insert code, delete cells, etc.)
- The notebook you see IS the notebook the user is working in - your actions affect it directly

TOOL-CALLING CONTRACT (STRICT):
- Produce exactly ONE tool call per turn
- Include a short status_message in tool args, summarizing the step you are about to perform
- Never emit plain-text answers unless using RespondToUser
- If task is complete, call RespondToUser(intent="completion")

AVAILABLE TOOLS & USAGE:

🔧 JUPYTER TOOLS:
- insert_and_execute_cell(code, cell_type="code", position="end")
  USE FOR: Python code execution, data analysis, visualization, computation
  OUTPUTS: execution_count, text/DataFrame/plot outputs, real-time cell in UI
  CONTEXT: Check notebook state first, build on existing work, use meaningful variables

- delete_cell(cell_index)
  USE FOR: Removing failed/duplicate/obsolete cells (use sparingly)
  CONTEXT: Verify index, consider variable dependencies

💬 COMMUNICATION TOOLS:
- RespondToUser(message, intent, thread_title)
  USE FOR: User communication, task completion, clarification requests
  INTENTS: "completion" (ends turn), "clarification" (needs input), "status_update" (continues)
  THREAD_TITLE: 3-8 words describing conversation topic

📋 PLANNING TOOLS:
- CreatePlan(plan_steps)
  USE FOR: Multi-step tasks (3+ operations), complex analysis, ambiguous requests
  STEPS: Specific, actionable, 1-2 sentences, logically ordered, 3-7 steps optimal
  WORKFLOW: Create plan → User edits cards → User says "proceed" → Execute edited cards

🗄️ DATABASE TOOLS (only when user mentions databases/SQL):
- query_snowflake(query, database, schema_name)
- list_snowflake_tables(database, schema_name)
- get_table_schema(table_name, database)
- get_database_info()

PLAN CARD WORKFLOW (CRITICAL):

WHEN TO CREATE PLANS:
- Multi-step tasks requiring 3+ distinct operations
- Complex analysis where user input would improve approach
- Ambiguous requests needing clarification structure
- High-stakes operations requiring user approval

PLAN PRECEDENCE RULES:
- Latest plan cards supersede ALL user requests before the plan
- User messages AFTER a plan can modify or invalidate it
- If user edits cards, implement EDITED version, not original request
- Each plan creates a context boundary in conversation

PLAN EXECUTION TRIGGERS:
- User says: "proceed", "go ahead", "implement this", "looks good", "start"
- User provides implementation feedback: "begin with step 1"
- User asks execution questions: "how will you do step 2?"

PLAN INVALIDATION SIGNALS:
- User requests completely different task: "forget that, do X instead"
- User says: "never mind", "cancel that", "ignore the plan"
- User provides contradictory requirements

CONVERSATION ANALYSIS:
- Read conversation chronologically to understand context
- Identify plan boundaries (user messages with [CARD:title|description] and messageType="plan")
- Plans appear as user messages saying "Final plan that needs to be implemented:"
- Determine current user intent (latest plan + subsequent messages)
- Ignore superseded requests (messages before latest active plan)
- If plan cards were edited, implement EDITED content, not original request

DECISION EXAMPLES:

Simple Request: "Plot sales over time"
→ insert_and_execute_cell(code="plt.plot(df['date'], df['sales'])", status_message="Creating sales timeline plot")

Complex Request: "Build comprehensive sales analysis with predictions"
→ CreatePlan([Data loading, EDA, trend analysis, forecasting model, visualization])

Clarification Needed: "Analyze the data" (no specifics)
→ RespondToUser(message="I'd be happy to analyze your data. Could you specify what type of analysis you're looking for?", intent="clarification")

Plan Execution: User edited cards and said "proceed"
→ Execute first edited card step with insert_and_execute_cell

Task Complete: Analysis finished with results
→ RespondToUser(message="Analysis complete. Results show...", intent="completion")

The conversation history shows you everything - read it naturally and respond appropriately to the user's current intent."""


    async def analyze_and_decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Core decision node - LLM analyzes context and decides next action via tool calls"""
        try:
            logger.info("🧠 [analyze_and_decide] start")

            # Update iteration counter for safety
            state = increment_iteration(state)
            logger.info(
                f"🧠 [analyze_and_decide] current_iteration={state.get('current_iteration')}\n"
            )

            notebook_path = state.get("notebook_path")
            if not notebook_path:
                logger.error(
                    "❌ [analyze_and_decide] missing notebook_path; routing to respond"
                )
                state["next_action"] = "respond"
                return state

            # Always refresh notebook state - get COMPLETE ready-to-use multimodal content
            notebook_multimodal_content = await self.notebook_state_manager.get_complete_notebook_state(
                notebook_path
            )
            # Store raw cell count for state (agent logic still needs this for iteration tracking)
            state["notebook_cells"] = [{"index": i} for i in range(len([item for item in notebook_multimodal_content if "Index" in item.get("text", "")]))]
            
            logger.info(f"🧠 [analyze_and_decide] Got {len(notebook_multimodal_content)} multimodal items for path={notebook_path}")

            provider = state.get("llm_provider", "openai")
            
            # Select LLM based on provider
            if provider == "openai":
                llm = self.openai_llm_with_tools
            elif provider == "claude":
                llm = self.claude_llm_with_tools
            elif provider == "gemini":
                llm = self.gemini_llm_with_tools
            else:
                llm = self.openai_llm_with_tools  # Default fallback
            
            if not llm:
                raise ValueError(f"No LLM configured for provider: {provider}")

            # Create system message (TEXT ONLY - OpenAI doesn't allow images in system!)
            system_instructions = self._create_system_instructions()
            system_message = {"role": "system", "content": system_instructions}
            
            # Create notebook context as USER message (OpenAI requires images in user role!)
            # This maintains perfect sequence: cell code → outputs → images → next cell
            notebook_context_content = []
            notebook_context_content.extend(notebook_multimodal_content)  # Already has everything in sequence!
            
            # Add iteration info at the end (NOT cached - changes every turn)
            notebook_context_content.append({
                "type": "text", 
                "text": f"\nCRITICAL: Use the notebook state to understand what work has already been completed. You can SEE the actual plots and charts that were generated. Current Iteration: {state.get('current_iteration', 0)}"
            })
            
            # For Claude: Add cache control to the last stable content item (before iteration info)
            if provider == "claude" and len(notebook_context_content) > 1:
                # Mark the last notebook content item (before iteration info) as cacheable
                last_notebook_item_idx = len(notebook_context_content) - 2  # -2 because we just added iteration info
                if last_notebook_item_idx >= 0:
                    notebook_context_content[last_notebook_item_idx]["cache_control"] = {"type": "ephemeral"}
                    logger.info(f"🔖 Added Anthropic cache_control marker at position {last_notebook_item_idx}")

            notebook_context_message = {"role": "user", "content": notebook_context_content}
            
            # Count images for logging
            image_count = len([item for item in notebook_context_content if item.get("type") == "image_url"])
            logger.info(f"🖼️ Created notebook context (USER role) with {len(notebook_context_content)} items ({image_count} images)")
            
            # Log COMPLETE notebook context being sent to LLM
            logger.info("📋 [NOTEBOOK CONTEXT] Complete notebook context being sent to LLM (as USER message):")
            for i, item in enumerate(notebook_context_content):
                item_type = item.get("type", "unknown")
                if item_type == "text":
                    text_content = item.get("text", "")
                    logger.info(f"📋 [CONTEXT][{i}] TEXT ({len(text_content)} chars): {text_content}")
                elif item_type == "image_url":
                    url = item.get("image_url", {}).get("url", "")
                    if "data:" in url and "base64," in url:
                        parts = url.split(";")
                        mime_type = parts[0].replace("data:", "") if parts else "unknown"
                        data_part = url.split("base64,")[1] if "base64," in url else ""
                        data_size = len(data_part)
                        logger.info(f"📋 [CONTEXT][{i}] IMAGE: {mime_type}, {data_size} base64 chars")
                    else:
                        logger.info(f"📋 [CONTEXT][{i}] IMAGE: {url[:100]}...")

            # Build complete message history: system → notebook → conversation (optimal for caching!)
            # This order ensures: system cached, notebook cached incrementally, conversation cached
            messages = [system_message, notebook_context_message]

            # Add ALL conversation history AFTER notebook context
            conversation_history = state.get("conversation_history", [])
            if conversation_history:
                logger.info(
                    f"🧠 [analyze_and_decide] Including {len(conversation_history)} conversation messages AFTER notebook context"
                )
                messages.extend(conversation_history)  # ALL messages from thread
            else:
                logger.info(
                    "🧠 [analyze_and_decide] No conversation history to include"
                )
            
            logger.info(f"🔄 Message order: system(1) → notebook(1) → conversation({len(conversation_history)}) = {len(messages)} total")

            # Note: Current user message is already included in conversation_history
            # Don't add original_request separately - it's just the first message in the thread

            if "messages" not in state:
                state["messages"] = []

            # Add any additional state messages (tool responses, etc.)
            messages.extend(state["messages"])

            logger.info(
                f"🧠 [analyze_and_decide] Final message count: {len(messages)} (system=1, notebook=1, conversation={len(conversation_history)}, state={len(state['messages'])})"
            )
            logger.info(f"🔖 Cache optimization: System + Notebook prefix stable, conversation grows, state messages appended")

            # Log EXACT message structure as it will be sent to LLM (no formatting/truncation)
            import json
            for i, msg in enumerate(messages):
                # Convert to dict for logging (handles both LangChain objects and dicts)
                if hasattr(msg, "dict"):  # LangChain message object
                    msg_dict = msg.dict()
                elif hasattr(msg, "model_dump"):  # Pydantic v2
                    msg_dict = msg.model_dump()
                else:  # Already a dict
                    msg_dict = msg
                
                # Log the EXACT structure that LLM sees
                logger.debug(f"  Message {i}: {json.dumps(msg_dict, indent=2)}")

            # Introspect the bound runnable to fetch the raw OpenAI tools payload, if available
            try:
                raw_tools = []
                if hasattr(llm, "kwargs") and isinstance(getattr(llm, "kwargs"), dict):
                    raw_tools = llm.kwargs.get("tools", []) or []
                tool_names_from_llm = []
                for t in raw_tools:
                    fn = t.get("function", {}) if isinstance(t, dict) else {}
                    name = fn.get("name") if isinstance(fn, dict) else None
                    if name:
                        tool_names_from_llm.append(name)
                self_tool_names = [
                    t.name
                    for t in (
                        getattr(self, "system_tools", [])
                        + getattr(self, "jupyter_tools", [])
                        + getattr(self, "mcp_tools", [])
                    )
                ]
                logger.warning(
                    f"introspected_llm_tools={tool_names_from_llm} self_tools={self_tool_names}"
                )
                # Detailed schema dump
                detailed = self._list_bound_tools_and_params(llm)
                logger.warning(f"tool_schemas={detailed}")
            except Exception as _e:
                logger.warning(f"tool introspection failed: {_e}")
            tool_response = await llm.ainvoke(messages)

            # Log tool_calls summary and details BEFORE any mutation
            tc = getattr(tool_response, "tool_calls", []) or []

            # Extract tool names properly - LangChain tool_calls are dictionaries
            tool_names = [
                c.get("name", "unknown")
                if isinstance(c, dict)
                else getattr(c, "name", "unknown")
                for c in tc
            ]

            logger.warning(
                f"🧠 [analyze_and_decide] LLM returned tool_calls={len(tc)} names={tool_names}"
            )
            for idx, c in enumerate(tc):
                try:
                    # Extract tool call details - tool_calls are dictionaries in LangChain
                    if isinstance(c, dict):
                        tool_id = c.get("id", "unknown")
                        tool_name = c.get("name", "unknown")
                        tool_args = c.get("args", {})
                    else:
                        # Fallback for object-style access
                        tool_id = getattr(c, "id", "unknown")
                        tool_name = getattr(c, "name", "unknown")
                        tool_args = getattr(c, "args", {})

                    logger.warning(
                        f"🧠 [analyze_and_decide] tool[{idx}] id={tool_id} name={tool_name} args={tool_args}"
                    )
                except Exception:
                    logger.warning(
                        f"🧠 [analyze_and_decide] tool[{idx}] (unprintable args)"
                    )
            if tool_response.content:
                cpreview = tool_response.content[:200].replace("\n", " ")
                logger.warning(f"🧠 [analyze_and_decide] content preview='{cpreview}'")

            # Always append the AI tool message; execution/validation will enforce the contract
            # If this is a tool call, create a more informative message for LLM context
            if getattr(tool_response, "tool_calls", []):
                # Extract status_message from first tool call for better context
                first_tool_call = tool_response.tool_calls[0]
                tool_name = first_tool_call.get("name", "unknown_tool")
                tool_args = first_tool_call.get("args", {})
                status_msg = tool_args.get("status_message", "")
                
                # Create informative content instead of empty string
                if status_msg:
                    tool_response.content = f"[{tool_name}] {status_msg}"
                else:
                    tool_response.content = f"[{tool_name}] Executing tool..."
                    
            state["messages"].append(tool_response)
            # If no tool_calls, inject a user-style correction nudge (retry cap handled by routing)
            if not getattr(tool_response, "tool_calls", []):
                attempts = state.get("correction_attempts", 0) + 1
                state["correction_attempts"] = attempts
                if attempts <= 3:
                    nudge = {
                        "role": "user",
                        "content": "You just provided a text response, but I can't see it in the chat. According to the system instructions, you were supposed to call a tool (like RespondToUser if the task is complete, or another action tool if you need to continue). What did you mean to do?",
                    }
                    state["messages"].append(nudge)
            logger.info(
                "🧠 [analyze_and_decide] appended AI message; ready for tools or retry"
            )
            return state

        except Exception as e:
            logger.error(f"❌ [analyze_and_decide] exception: {e}")
            state["next_action"] = "respond"
            state["reasoning"] = f"Error occurred: {e}"
            return state

    async def create_plan(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Create analysis plan with interactive cards"""
        try:
            logger.info("📋 Creating analysis plan...")

            # Get plan steps from LLM decision (already generated in analyze_and_decide)
            plan_steps = state.get("plan_steps", [])

            if not plan_steps:
                logger.warning("No plan steps found in state")
                return state

            # Add UUIDs to plan steps
            import uuid

            for step in plan_steps:
                step["step_id"] = str(uuid.uuid4())

            # Display plan as editable cards in chat UI
            await self.chat_handler.display_plan_cards(plan_steps)

            # Store plan in state
            state["plan_steps"] = plan_steps

            await self.chat_handler.send_status(
                f"📋 Created plan with {len(plan_steps)} steps"
            )
            logger.info(f"📋 Created plan with {len(plan_steps)} steps")

            return state

        except Exception as e:
            logger.error(f"❌ Error creating plan: {e}")
            state["reasoning"] = f"Error creating plan: {e}"
            return state

    async def respond(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Handle conversational responses"""
        try:
            # Get message from LLM decision (already generated in analyze_and_decide)
            message = state.get("response_message")

            if not message:
                logger.warning("No response message found in state")
                message = "I'm here to help with your data analysis. What would you like to work on?"

            logger.info(f"💬 Sending response: {message[:100]}...")

            # Send the response message
            await self.chat_handler.send_message(message)

            # Add to conversation history
            if "conversation_history" not in state:
                state["conversation_history"] = []

            state["conversation_history"].append(
                {
                    "role": "assistant",
                    "content": message,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            return state

        except Exception as e:
            logger.error(f"❌ Error sending response: {e}")
            state["reasoning"] = f"Error sending response: {e}"
            return state


    def _generate_summary(self, state: Dict[str, Any]) -> str:
        """Generate analysis summary"""
        notebook_cells = state.get("notebook_cells", [])
        conversation_history = state.get("conversation_history", [])

        code_cells = len([c for c in notebook_cells if c.get("type") == "code"])
        iterations = state.get("current_iteration", 0)

        # Get first user message from conversation history as the original request
        first_user_message = "N/A"
        for msg in conversation_history:
            if msg.get("role") == "user":
                first_user_message = msg.get("content", "N/A")[:100] + (
                    "..." if len(msg.get("content", "")) > 100 else ""
                )
                break

        return f"""
The data analysis session has been completed.

**Summary:**
- Initial request: {first_user_message}
- Notebook cells created: {code_cells}
- Analysis iterations: {iterations}
- Conversation exchanges: {len(conversation_history)}

The notebook now contains the complete analysis workflow with code and results.
"""
