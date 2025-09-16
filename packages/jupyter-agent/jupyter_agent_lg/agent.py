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

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ChatHandler:
    """Handles communication with chat UI"""

    def __init__(self, server_url: str, token: str = None):
        self.server_url = server_url
        self.token = token
        self.default_notebook_path: Optional[str] = None

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
                        "type": status_type,
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
        *,
        notebook_path: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        """Send message to chat UI"""
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
                        "thread_id": thread_id,
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                logger.info(f"💬 Message sent: {message[:100]}...")
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")

    async def display_plan_cards(self, plan_steps: List[Dict[str, str]]):
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
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                logger.info(f"📋 Plan cards displayed: {len(plan_steps)} steps")
        except Exception as e:
            logger.warning(f"Failed to display plan cards: {e}")


class DataAnalysisAgent:
    """
    LangGraph-based agent for iterative data analysis

    Features:
    - Pure LLM-driven decision making
    - Dynamic planning with user interaction
    - Multi-step analysis with context awareness
    - Real-time status updates
    - Multi-LLM suppor
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
        self.anthropic_llm = (
            ChatAnthropic(
                api_key=anthropic_api_key,
                model="claude-3-5-sonnet-20241022",
                temperature=0.2,
            )
            if anthropic_api_key
            else None
        )

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
        self.anthropic_llm_with_tools = (
            self.anthropic_llm.bind_tools(
                augmented_tools, parallel_tool_calls=False, tool_choice="any"
            )
            if self.anthropic_llm
            else None
        )
        if self.anthropic_llm_with_tools:
            try:
                setattr(
                    self.anthropic_llm_with_tools,
                    "_bound_tool_names",
                    [t.name for t in augmented_tools],
                )
            except Exception:
                pass

        # Build LangGraph workflow
        self.workflow = self._build_graph()

        logger.info(
            f"🤖 DataAnalysisAgent initialized with {len(original_tools)} tools (augmented schemas for binding)"
        )

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
            result = await self._execute_single_tool(first_call)
            tool_msg = ToolMessage(
                content=str(result), name=name, tool_call_id=first_call.get("id")
            )
            # Route based on tool name/inten
            route = "continue"
            if name == "RespondToUser":
                route = "end"
                # Always surface the RespondToUser message as final_result so the UI shows exact text
                preserved_state["final_result"] = args.get(
                    "message", ""
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
                # Mirror status into chat bubble for immediate visibility in the UI
                if hasattr(self.chat_handler, "send_message"):
                    try:
                        await self.chat_handler.send_message(
                            f"[status] {status_message}"
                        )
                    except Exception:
                        pass
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
        if self.anthropic_llm:
            self.anthropic_llm_with_tools = self.anthropic_llm.bind_tools(
                all_tools, parallel_tool_calls=False
            )

        # Rebuild workflow
        self.workflow = self._build_graph()

        logger.info(f"✅ Updated tools and workflow for notebook: {new_notebook_path}")

    async def process_request(
        self,
        request: str,
        notebook_path: str,
        conversation_history: List[Dict[str, str]],
        model: str = "gpt-4o",
        provider: str = "openai",
        mcp_servers: Dict = None,
    ) -> str:
        """Process a user request through the LangGraph workflow"""
        try:
            print(f"🔥 AGENT PROCESS_REQUEST CALLED: {request[:50]}...")
            logger.info(f"🚀 Processing request: {request[:100]}...")

            # Update tools if notebook path changed
            if notebook_path != self.default_notebook_path:
                self.update_notebook_path(notebook_path)
            # Ensure chat messages (status/text) route to the current notebook over WS
            try:
                self.chat_handler.default_notebook_path = notebook_path
            except Exception:
                pass
            # Keep internal default in sync to avoid repeated updates on subsequent turns
            self.default_notebook_path = notebook_path

            # Create initial state
            initial_state = create_initial_state(
                request, notebook_path, conversation_history, model, provider
            )

            # DEBUG: Check initial state creation
            logger.info(
                f"🔍 Initial state created with keys: {list(initial_state.keys())}"
            )
            logger.info(
                f"🔍 notebook_path in initial_state: {initial_state.get('notebook_path', 'MISSING')}"
            )

            # Get current notebook state and available data sources
            initial_state[
                "notebook_cells"
            ] = await self.notebook_state_manager.get_complete_notebook_state(
                notebook_path
            )
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

            await self.chat_handler.send_status(
                "🤖 LangGraph agent starting analysis...", "info"
            )

            # Run the workflow
            print(
                f"🔥 ABOUT TO CALL WORKFLOW with state keys: {list(initial_state.keys())}"
            )
            logger.info(
                f"🚀 About to call workflow.ainvoke with state keys: {list(initial_state.keys())}"
            )
            final_state = await self.workflow.ainvoke(initial_state)
            print(
                f"🔥 WORKFLOW COMPLETED with final state keys: {list(final_state.keys())}"
            )
            logger.info(
                f"🏁 Workflow completed with final state keys: {list(final_state.keys())}"
            )

            # Extract result to return
            result = final_state.get("final_result", "Analysis completed")

            await self.chat_handler.send_status("✅ Analysis completed", "success")
            return result

        except Exception as e:
            print(f"🔥 AGENT EXCEPTION: {e}")
            logger.error(f"❌ Error processing request: {e}")
            await self.chat_handler.send_status(f"❌ Error: {e}", "error")
            return f"Error processing request: {e}"

    async def analyze_and_decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Core decision node - LLM analyzes context and decides next action via tool calls"""
        try:
            print(f"🔥 ANALYZE_AND_DECIDE CALLED with state keys: {list(state.keys())}")
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

            # Always refresh notebook state
            state[
                "notebook_cells"
            ] = await self.notebook_state_manager.get_complete_notebook_state(
                notebook_path
            )
            logger.info(
                f"🧠 [analyze_and_decide] notebook_cells={len(state['notebook_cells'])} for path={notebook_path}"
            )

            provider = state.get("llm_provider", "openai")
            llm = (
                self.openai_llm_with_tools
                if provider == "openai"
                else self.anthropic_llm_with_tools
            )
            if not llm:
                raise ValueError(f"No LLM configured for provider: {provider}")

            context_prompt = self._create_context_prompt(state)
            if "messages" not in state:
                state["messages"] = []

            system_message = {"role": "system", "content": context_prompt}
            user_message = None
            if state.get("original_request"):
                user_message = {"role": "user", "content": state["original_request"]}
            conversation_messages = (
                [system_message]
                + ([user_message] if user_message else [])
                + state["messages"]
            )

            logger.warning(
                f"🧠 [analyze_and_decide] invoking LLM with messages={len(conversation_messages)} (system+{len(state['messages'])})"
            )
            logger.warning(
                f"conversation_messages={conversation_messages}\n"
                f"state['messages']={state['messages']}"
                f" bound_tools={getattr(llm, '_bound_tool_names', [])}"
            )
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
            tool_response = await llm.ainvoke(conversation_messages)

            # Log tool_calls summary and details BEFORE any mutation
            tc = getattr(tool_response, "tool_calls", []) or []
            logger.warning(
                f"🧠 [analyze_and_decide] LLM returned tool_calls={len(tc)} names={[c.get('name') for c in tc]}"
            )
            for idx, c in enumerate(tc):
                try:
                    logger.warning(
                        f"🧠 [analyze_and_decide] tool[{idx}] id={c.get('id')} name={c.get('name')} args={c.get('args')}"
                    )
                except Exception:
                    logger.warning(
                        f"🧠 [analyze_and_decide] tool[{idx}] (unprintable args)"
                    )
            if tool_response.content:
                cpreview = tool_response.content[:200].replace("\n", " ")
                logger.warning(f"🧠 [analyze_and_decide] content preview='{cpreview}'")

            # Always append the AI tool message; execution/validation will enforce the contrac
            state["messages"].append(tool_response)
            # If no tool_calls, inject a short nudge for the self-loop path (retry cap handled by routing)
            if not getattr(tool_response, "tool_calls", []):
                attempts = state.get("correction_attempts", 0) + 1
                state["correction_attempts"] = attempts
                if attempts <= 3:
                    nudge = {
                        "role": "system",
                        "content": "Call exactly one tool now. Include a short status_message describing the step.",
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

    def _create_context_prompt(self, state: Dict[str, Any]) -> str:
        """Create context prompt for LLM decision making"""
        notebook_summary = self._summarize_notebook(state.get("notebook_cells", []))
        conversation_summary = self._format_conversation(
            state.get("conversation_history", [])
        )

        prompt = f"""
 You are a data analysis agent working in JupyterLab. Decide what to do next and EXPRESS your decision via TOOL CALLS ONLY.

 Tool-calling contract (STRICT):
 - Produce exactly ONE tool call per turn.
 - Include a short status_message in the tool args, summarizing the step you are about to perform.
 - Never emit plain-text answers unless you are explicitly using RespondToUser. If you intend to finish, call RespondToUser(intent="completion").
 If a single user request requires multiple actions, emit one tool at a time and rely on the next turn to continue. Do NOT emit multiple tools in a single turn.
 If you previously returned no tools, correct yourself by emitting exactly one valid tool call now.

 CONTRACT (per turn):
 - Call EXACTLY ONE tool from this set: Jupyter tools, Snowflake tools, RespondToUser, CreatePlan.
 - Use RespondToUser(intent="completion") when you are finished.
 - Always include a concise status_message in the tool args to communicate progress to the user.

 Example (format only):
 - Assistant tool_calls:
   - insert_and_execute_cell(code="import matplotlib.pyplot as plt\n...", cell_type="code", position="end", status_message="Insert new code cell to plot x vs x**2")

 Available payload tool categories:
 - Jupyter tools: insert_and_execute_cell, delete_cell, etc.
 - Snowflake tools: query_snowflake, list_snowflake_tables, get_table_schema, get_database_info
 - RespondToUser(message, intent?)
 - CreatePlan(plan_steps)

 Guidance:
 - Use Jupyter tools for notebook edits/execution.
 - Use Snowflake tools for external data queries.
 - Use RespondToUser to talk to the user (clarifications, updates). For completion, call RespondToUser(intent="completion").
 - Use CreatePlan to present a multi-step plan (explicit plan_steps).

 Contex
 --------
 User Request: {state["original_request"]}

 Current Notebook State:
 {notebook_summary}

 Conversation History:
 {conversation_summary}

 Current Iteration: {state.get("current_iteration", 0)}
"""
        return prompt

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

    async def complete_analysis(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Complete the analysis and provide summary"""
        try:
            logger.info("🏁 Completing analysis...")

            # Generate summary
            summary = self._generate_summary(state)

            # Send final message
            await self.chat_handler.send_message(f"## Analysis Complete\n\n{summary}")

            state["is_complete"] = True
            state["final_result"] = summary

            await self.chat_handler.send_status("✅ Analysis completed successfully")
            logger.info("🏁 Analysis completed")

            return state

        except Exception as e:
            logger.error(f"❌ Error completing analysis: {e}")
            state["reasoning"] = f"Error completing analysis: {e}"
            return state

    def _summarize_notebook(self, notebook_cells: List[Dict]) -> str:
        """Create a concise summary of notebook state"""
        if not notebook_cells:
            return "Empty notebook"

        code_cells = [c for c in notebook_cells if c.get("type") == "code"]
        markdown_cells = [c for c in notebook_cells if c.get("type") == "markdown"]
        cells_with_output = [c for c in code_cells if c.get("outputs")]

        summary = f"Notebook has {len(notebook_cells)} cells ({len(code_cells)} code, {len(markdown_cells)} markdown)"

        if cells_with_output:
            summary += f", {len(cells_with_output)} cells have outputs"

        # Add recent code snippets
        recent_code = []
        for cell in code_cells[-3:]:  # Last 3 code cells
            source = cell.get("source", "")
            if source and len(source) < 200:
                recent_code.append(f"- {source.strip()}")

        if recent_code:
            summary += "\n\nRecent code:\n" + "\n".join(recent_code)

        return summary

    def _format_conversation(self, conversation_history: List[Dict]) -> str:
        """Format conversation history for context"""
        if not conversation_history:
            return "No previous conversation"

        formatted = []
        for msg in conversation_history[-5:]:  # Last 5 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 100:
                content = content[:100] + "..."
            formatted.append(f"{role}: {content}")

        return "\n".join(formatted)

    def _generate_summary(self, state: Dict[str, Any]) -> str:
        """Generate analysis summary"""
        notebook_cells = state.get("notebook_cells", [])
        conversation_history = state.get("conversation_history", [])

        code_cells = len([c for c in notebook_cells if c.get("type") == "code"])
        iterations = state.get("current_iteration", 0)

        return f"""
The data analysis session has been completed.

**Summary:**
- Original request: {state.get("original_request", "N/A")}
- Notebook cells created: {code_cells}
- Analysis iterations: {iterations}
- Conversation exchanges: {len(conversation_history)}

The notebook now contains the complete analysis workflow with code and results.
"""
