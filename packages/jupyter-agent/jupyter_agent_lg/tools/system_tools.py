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
        format='[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger("jupyterlab")


def create_system_tools(chat_handler) -> List[StructuredTool]:
    """Create system-level tools: RespondToUser, CreatePlan.

    chat_handler: instance with send_status, send_message, display_plan_cards
    """

    async def respond_to_user(message: str, thread_title: str, intent: str | None = None) -> str:
        # Also surface completion as a status for visibility in UIs that highlight statuses
        try:
            if intent == "completion":
                await chat_handler.send_status(message, "success")
                logger.info(f"Sent completion status: {message[:100]}...")
        except Exception as e:
            logger.warning(f"Failed to send status: {e}")
        
        # Send message with thread title - atomic operation
        await chat_handler.send_message(message, thread_title=thread_title)
        logger.info(f"Responded to user: intent={intent or 'none'}, title={thread_title}, message={message[:100]}...")
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
            description="Send a user-visible message to the chat",
            args_schema=RespondToUserArgs,
            coroutine=respond_to_user,
        ),
        StructuredTool.from_function(
            func=create_plan,
            name="CreatePlan",
            description="Create and display an editable plan (cards) in the chat UI",
            args_schema=CreatePlanArgs,
            coroutine=create_plan,
        ),
    ]
    
    # Add category metadata to system tools (these won't be shown to user)
    for tool in tools:
        if not tool.metadata:
            tool.metadata = {}
        tool.metadata['tool_category'] = "System Tools"
    
    return tools
