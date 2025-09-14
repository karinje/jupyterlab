"""
LangGraph Data Analysis Agent

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
from .schemas import LLMDecision
from .tools import create_jupyter_tools
from jupyter_tools_bridge.tools import JupyterTools
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class ChatHandler:
    """Handles communication with chat UI"""

    def __init__(self, server_url: str, token: str = None):
        self.server_url = server_url
        self.token = token

    async def send_status(self, message: str, status_type: str = "working"):
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
                    },
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                logger.info(f"📡 Status sent: {message}")
        except Exception as e:
            logger.warning(f"Failed to send status: {e}")

    async def send_message(self, message: str):
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
    - Multi-LLM support
    """

    def __init__(
        self,
        server_url: str,
        token: str,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_notebook_path: str = "analysis.ipynb",
    ):
        self.server_url = server_url
        self.token = token
        self.default_notebook_path = default_notebook_path

        # Initialize components
        self.notebook_state_manager = NotebookStateManager(server_url, token)
        self.chat_handler = ChatHandler(server_url, token)
        self.jupyter_tools_client = JupyterTools(server_url, token)

        # Initialize LLMs directly
        self.openai_llm = (
            ChatOpenAI(api_key=openai_api_key, model="gpt-4o")
            if openai_api_key
            else None
        )
        self.anthropic_llm = (
            ChatAnthropic(api_key=anthropic_api_key, model="claude-3-5-sonnet-20241022")
            if anthropic_api_key
            else None
        )

        # Create tools and LLMs with tools ONCE
        self.jupyter_tools = create_jupyter_tools(
            self.jupyter_tools_client, default_notebook_path
        )
        self.openai_llm_with_tools = (
            self.openai_llm.bind_tools(self.jupyter_tools, parallel_tool_calls=False)
            if self.openai_llm
            else None
        )
        self.anthropic_llm_with_tools = (
            self.anthropic_llm.bind_tools(self.jupyter_tools, parallel_tool_calls=False)
            if self.anthropic_llm
            else None
        )

        # Build LangGraph workflow
        self.workflow = self._build_graph()

        logger.info(
            f"🤖 DataAnalysisAgent initialized with {len(self.jupyter_tools)} tools"
        )

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("analyze_and_decide", self.analyze_and_decide)
        workflow.add_node(
            "tools", self.execute_tools
        )  # Use our custom method instead of ToolNode
        workflow.add_node("create_plan", self.create_plan)
        workflow.add_node("respond", self.respond)
        workflow.add_node("complete_analysis", self.complete_analysis)

        # Set entry point
        workflow.set_entry_point("analyze_and_decide")

        # Add conditional edges based on next_action
        def route_decision(state: Dict[str, Any]) -> str:
            next_action = state.get("next_action", "complete_analysis")

            # Safety check for max iterations
            if state.get("current_iteration", 0) >= 10:
                logger.warning("🛑 Max iterations reached, completing analysis")
                return "complete_analysis"

            # Check if analysis is complete
            if state.get("is_complete", False):
                return END

            return next_action

        workflow.add_conditional_edges(
            "analyze_and_decide",
            route_decision,
            {
                "tools": "tools",
                "create_plan": "create_plan",
                "respond": "respond",
                "complete_analysis": "complete_analysis",
                END: END,
            },
        )

        # All other nodes go back to analyze_and_decide
        workflow.add_edge("tools", "analyze_and_decide")
        workflow.add_edge("create_plan", "analyze_and_decide")
        workflow.add_edge("respond", "analyze_and_decide")
        workflow.add_edge("complete_analysis", END)

        return workflow.compile()

    async def execute_tools(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tools and preserve state"""
        try:
            print(f"🔥 EXECUTE_TOOLS CALLED with state keys: {list(state.keys())}")
            logger.info("🔧 Executing tools...")

            # Preserve ALL original state
            preserved_state = dict(state)

            # Get the last message which should contain tool calls
            messages = state.get("messages", [])
            if not messages:
                logger.error("❌ No messages in state for tool execution")
                return state

            last_message = messages[-1]
            if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
                logger.error("❌ No tool calls in last message")
                return state

            print(f"🔥 EXECUTING {len(last_message.tool_calls)} TOOL CALLS")
            logger.info(f"🔧 Executing {len(last_message.tool_calls)} tool calls")

            # Execute each tool call
            tool_results = []
            for tool_call in last_message.tool_calls:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("args", {})
                tool_call_id = tool_call.get("id")

                print(f"🔥 EXECUTING TOOL: {tool_name} with args: {tool_args}")
                logger.info(f"🔧 Executing tool: {tool_name}")

                # Find and execute the tool
                tool_result = None
                for tool in self.jupyter_tools:
                    if tool.name == tool_name:
                        try:
                            if asyncio.iscoroutinefunction(tool.func):
                                tool_result = await tool.func(**tool_args)
                            else:
                                tool_result = tool.func(**tool_args)
                            break
                        except Exception as e:
                            logger.error(f"❌ Tool {tool_name} failed: {e}")
                            tool_result = f"Error executing {tool_name}: {e}"

                if tool_result is None:
                    tool_result = f"Tool {tool_name} not found"

                # Create tool message
                from langchain_core.messages import ToolMessage

                tool_message = ToolMessage(
                    content=str(tool_result), name=tool_name, tool_call_id=tool_call_id
                )
                tool_results.append(tool_message)

                print(f"🔥 TOOL {tool_name} RESULT: {str(tool_result)[:100]}...")
                logger.info(f"🔧 Tool {tool_name} completed")

            # Add tool results to messages while preserving ALL other state
            preserved_state["messages"] = messages + tool_results

            print(
                f"🔥 EXECUTE_TOOLS COMPLETED, preserved state keys: {list(preserved_state.keys())}"
            )
            logger.info(
                f"🔧 Tool execution completed, state keys preserved: {list(preserved_state.keys())}"
            )

            # CRITICAL: Add delay to ensure notebook state is fully committed
            await asyncio.sleep(0.5)
            logger.info("⏱️ Waited for notebook state to stabilize")

            return preserved_state

        except Exception as e:
            print(f"🔥 EXECUTE_TOOLS EXCEPTION: {e}")
            logger.error(f"❌ Error in tool execution: {e}")
            # Preserve original state even on error
            state["reasoning"] = f"Tool execution error: {e}"
            return state

    def update_notebook_path(self, new_notebook_path: str):
        """Update tools and LLMs when notebook path changes"""
        logger.info(f"🔄 Updating notebook path to: {new_notebook_path}")

        # Recreate tools with new notebook path
        self.jupyter_tools = create_jupyter_tools(self.jupyter_tools_client, new_notebook_path)

        # Rebind tools to LLMs
        if self.openai_llm:
            self.openai_llm_with_tools = self.openai_llm.bind_tools(
                self.jupyter_tools, parallel_tool_calls=False
            )
        if self.anthropic_llm:
            self.anthropic_llm_with_tools = self.anthropic_llm.bind_tools(
                self.jupyter_tools, parallel_tool_calls=False
            )

        # Rebuild workflow with new tools
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

            # Extract result
            result = final_state.get("final_result", "Analysis completed")

            await self.chat_handler.send_status("✅ Analysis completed", "success")
            return result

        except Exception as e:
            print(f"🔥 AGENT EXCEPTION: {e}")
            logger.error(f"❌ Error processing request: {e}")
            await self.chat_handler.send_status(f"❌ Error: {e}", "error")
            return f"Error processing request: {e}"

    async def analyze_and_decide(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Core decision node - LLM analyzes context and decides next action"""
        try:
            print(f"🔥 ANALYZE_AND_DECIDE CALLED with state keys: {list(state.keys())}")
            logger.info("🧠 Analyzing context and making decision...")

            # Debug: Check state keys
            logger.info(f"🔍 State keys at start: {list(state.keys())}")
            logger.info(f"🔍 State values preview: {dict(list(state.items())[:5])}")

            # Update iteration counter for safety
            state = increment_iteration(state)

            # Ensure notebook_path is available
            notebook_path = state.get("notebook_path")
            if not notebook_path:
                logger.error("❌ No notebook_path in state!")
                logger.error(f"❌ Available state keys: {list(state.keys())}")
                logger.error(f"❌ State dump: {state}")
                state["next_action"] = "complete_analysis"
                state["reasoning"] = "Missing notebook_path in state"
                return state

            # Always refresh notebook state
            notebook_cells = (
                await self.notebook_state_manager.get_complete_notebook_state(
                    notebook_path
                )
            )
            state["notebook_cells"] = notebook_cells

            # HYPOTHESIS TEST: Log what cells are actually in the context
            logger.info(
                f"🔍 CONTEXT ANALYSIS - Iteration {state.get('current_iteration', 0)}"
            )
            logger.info(f"🔍 Found {len(notebook_cells)} cells in notebook context:")

            has_y_squared = False
            has_y_cubed = False

            for i, cell in enumerate(notebook_cells):
                cell_type = cell.get("type", "unknown")
                source = cell.get("source", "")
                if isinstance(source, str) and len(source) > 100:
                    source_preview = source[:100] + "..."
                else:
                    source_preview = source

                logger.info(f"   Cell {i}: {cell_type} - {source_preview}")

                # Check for the specific plots the user mentioned
                source_str = str(source).lower()
                if "y**2" in source_str or "**2" in source_str:
                    has_y_squared = True
                    logger.info(f"   ⚠️  FOUND y**2 plot in cell {i}")
                if "y**3" in source_str or "x**3" in source_str or "**3" in source_str:
                    has_y_cubed = True
                    logger.info(f"   ⚠️  FOUND y**3/x**3 plot in cell {i}")

            logger.info(
                f"🔍 CONTEXT SUMMARY: y**2 present: {has_y_squared}, y**3 present: {has_y_cubed}"
            )
            logger.info(f"🔍 User request: {state['original_request']}")

            # Get LLM instance (already has tools bound)
            provider = state.get("llm_provider", "openai")
            llm = (
                self.openai_llm_with_tools
                if provider == "openai"
                else self.anthropic_llm_with_tools
            )

            if not llm:
                raise ValueError(f"No LLM configured for provider: {provider}")

            # DEBUG: Check what tools are available
            print(f"🔥 TOOLS AVAILABLE: {len(self.jupyter_tools)} tools")
            for i, tool in enumerate(self.jupyter_tools):
                print(f"🔥 Tool {i+1}: {tool.name} - {tool.description}")

            # Create context prompt (will be used as system message)
            context_prompt = self._create_context_prompt(state)

            # LOG CONTEXT DETAILS
            logger.info(f"🧠 Context prompt length: {len(context_prompt)} chars")
            logger.info(f"🧠 Current iteration: {state.get('current_iteration', 0)}")
            logger.info(
                f"🧠 User request in context: {state.get('original_request', 'MISSING')}"
            )
            logger.info(f"🧠 Context prompt preview: {context_prompt[:500]}...")

            # Initialize tool conversation messages if not present (separate from context)
            if "messages" not in state:
                state["messages"] = []

            # Clean up old messages to prevent conversation from getting too long
            # Optional trimming: keep only the last N messages if configured
            max_tool_messages = getattr(self, "max_tool_messages", None)
            if isinstance(max_tool_messages, int) and max_tool_messages > 0:
                if len(state["messages"]) > max_tool_messages:
                    state["messages"] = state["messages"][-max_tool_messages:]
                    logger.info(
                        f"🧹 Trimmed tool messages to last {max_tool_messages} entries"
                    )

            # DEBUG: Log current messages
            logger.info(f"🔍 Current tool messages in state: {len(state['messages'])}")
            for i, msg in enumerate(state["messages"]):
                if hasattr(msg, "role"):
                    logger.info(
                        f"   Message {i}: role={msg.role}, has_tool_calls={hasattr(msg, 'tool_calls') and bool(msg.tool_calls)}"
                    )
                else:
                    logger.info(f"   Message {i}: {type(msg)} - {str(msg)[:100]}")

            # Prepare messages for LLM: system context + tool conversation
            system_message = {"role": "system", "content": context_prompt}
            conversation_messages = [system_message] + state["messages"]

            logger.info(
                f"🧠 Total conversation messages: {len(conversation_messages)} (1 system + {len(state['messages'])} tool messages)"
            )

            # Get LLM response
            print(f"🔥 CALLING LLM WITH {len(conversation_messages)} MESSAGES")
            tool_response = await llm.ainvoke(conversation_messages)
            print(f"�� LLM RESPONSE TYPE: {type(tool_response)}")
            print(f"🔥 LLM RESPONSE HAS TOOL_CALLS: {hasattr(tool_response, 'tool_calls')}")
            if hasattr(tool_response, 'tool_calls'):
                print(f"🔥 TOOL_CALLS COUNT: {len(tool_response.tool_calls) if tool_response.tool_calls else 0}")
            print(f"🔥 LLM RESPONSE CONTENT: {tool_response.content[:200] if tool_response.content else 'NO CONTENT'}")

            if tool_response.tool_calls:
                # LLM wants to use tools
                print(f"🔥 LLM REQUESTED {len(tool_response.tool_calls)} TOOL CALLS")
                state["next_action"] = "tools"
                if tool_response.content:
                    await self.chat_handler.send_status(tool_response.content)

                # LOG DETAILED TOOL CALL INFO
                logger.info(
                    f"🔧 LLM requested {len(tool_response.tool_calls)} tool calls"
                )
                for i, tool_call in enumerate(tool_response.tool_calls):
                    print(
                        f"🔥 TOOL {i + 1}: {tool_call.get('name', 'unknown')} - {tool_call.get('args', {})}"
                    )
                    logger.info(
                        f"   Tool {i + 1}: {tool_call.get('name', 'unknown')} - {tool_call.get('args', {})}"
                    )

                # Add the LLM response with tool calls to tool conversation (NOT including system message)
                state["messages"].append(tool_response)

            else:
                # Get structured decision using LLMDecision schema (use base LLM without tools for structured output)
                base_llm = (
                    self.openai_llm if provider == "openai" else self.anthropic_llm
                )
                llm_with_schema = base_llm.with_structured_output(LLMDecision)
                decision = await llm_with_schema.ainvoke([system_message])

                # DEBUG: Log the decision details
                logger.info("🎯 LLM Decision Details:")
                logger.info(f"   Action: {decision.action}")
                logger.info(f"   Reasoning: {decision.reasoning}")
                logger.info(f"   Status Message: {decision.status_message}")
                logger.info(
                    f"   User Request in State: {state.get('original_request', 'MISSING')}"
                )

                state["next_action"] = decision.action
                state["reasoning"] = decision.reasoning

                # Store action-specific data
                if decision.message:
                    state["response_message"] = decision.message
                if decision.plan_steps:
                    state["plan_steps"] = decision.plan_steps

                # Send status update (except for respond action)
                if decision.status_message and decision.action != "respond":
                    await self.chat_handler.send_status(decision.status_message)

                logger.info(f"🎯 Decision: {decision.action} - {decision.reasoning}")

            return state

        except Exception as e:
            logger.error(f"❌ Error in analyze_and_decide: {e}")
            state["next_action"] = "complete_analysis"
            state["reasoning"] = f"Error occurred: {e}"
            return state

    def _create_context_prompt(self, state: Dict[str, Any]) -> str:
        """Create context prompt for LLM decision making"""
        notebook_summary = self._summarize_notebook(state.get("notebook_cells", []))
        conversation_summary = self._format_conversation(
            state.get("conversation_history", [])
        )

        prompt = f"""
You are a data analysis agent working in JupyterLab. Analyze the current context and decide what to do next.

**User Request:** {state["original_request"]}

**Current Notebook State:**
{notebook_summary}

**Conversation History:**
{conversation_summary}

**Current Iteration:** {state.get("current_iteration", 0)}

**Available Actions:**
1. **tools** - Use Jupyter notebook tools (insert/execute code, delete cells, etc.)
2. **create_plan** - Create a structured analysis plan with steps
3. **respond** - Send a conversational message to the user
4. **complete** - Finish the analysis

**Instructions:**
- IMPORTANT: If the user is asking for code, plots, data analysis, or any computational task, you MUST use "tools" action
- If you need to manipulate the notebook (add code, execute, etc.), use "tools" action
- If the user needs a plan for complex analysis, use "create_plan" action
- If you need to ask questions or provide updates, use "respond" action
- ONLY use "complete" action if the user's request has been fully satisfied with working code and results
- Always provide clear reasoning for your decision
- For tool actions, provide a helpful status message describing what you're doing
- The notebook state above is current - avoid calling get_notebook_cells unless you need fresh data
- When inserting cells, use position="end" to add at the bottom of the notebook
- Focus on the user's specific request rather than creating duplicate or similar code

**CRITICAL: For requests like "plot x,y**2" or any data visualization/analysis, you MUST use "tools" action to insert and execute the necessary Python code.**
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
