"""
System Tools for LangGraph Agent

This module creates system-level tools for the LangGraph agent including
user communication and plan creation functionality.
"""

from typing import List
import logging
from langchain_core.tools import StructuredTool
from ..schemas import RespondToUserArgs, CreatePlanArgs, PlanStepOutput

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


def create_system_tools(chat_handler) -> List[StructuredTool]:
    """Create system-level tools: RespondToUser, CreatePlan.

    chat_handler: instance with send_status, send_message, display_plan_cards
    """

    async def respond_to_user(
        message: str, thread_title: str, intent: str | None = None
    ) -> str:
        # Send message with thread title - atomic operation
        await chat_handler.send_message(message, thread_title=thread_title)
        logger.info(
            f"Responded to user: intent={intent or 'none'}, title={thread_title}, message={message[:100]}..."
        )
        return f"responded: intent={intent or 'none'}, title_saved=True"

    async def create_plan(plan_steps: List[PlanStepOutput]) -> str:
        steps = [
            step.model_dump() if hasattr(step, "model_dump") else dict(step)
            for step in plan_steps
        ]
        await chat_handler.display_plan_cards(steps)
        logger.info(f"Created plan with {len(steps)} steps")
        return f"plan_created: steps={len(steps)}"

    tools = [
        StructuredTool.from_function(
            func=respond_to_user,
            name="RespondToUser",
            description="""MANDATORY: Send a message to the user. This is the ONLY way to communicate with the user.

CRITICAL: You MUST use this tool for ANY response to the user. Never generate plain text responses - they will not reach the chat interface and the user will never see them.

Use for:
- Asking clarifying questions (intent="clarification")
- Providing status updates (intent="status_update") 
- Completing tasks (intent="completion")
- Explaining results or next steps
- ANY communication intended for the user

Always include a descriptive thread_title (3-8 words) summarizing the conversation topic.
Examples: "Sales Data Analysis", "ML Model Training", "Database Query Help".

REMEMBER: Plain text responses are invisible to users - always use this tool!""",
            args_schema=RespondToUserArgs,
            coroutine=respond_to_user,
        ),
        StructuredTool.from_function(
            func=create_plan,
            name="CreatePlan",
            description="""Create interactive plan cards for multi-step tasks. Use when:
- Task requires 3+ distinct operations
- User input would improve the approach
- Complex analysis needs user review
- Ambiguous requests need clarification

Each plan step should be:
- Specific and actionable (1-2 sentences maximum)
- Clear about expected outcome
- Ordered logically (3-7 steps optimal)

The user can edit these cards before you proceed. When user says "proceed",
implement the EDITED cards, not the original request.""",
            args_schema=CreatePlanArgs,
            coroutine=create_plan,
        ),
    ]

    # Add category metadata to system tools (these won't be shown to user)
    for tool in tools:
        if not tool.metadata:
            tool.metadata = {}
        tool.metadata["tool_category"] = "System Tools"

    return tools
