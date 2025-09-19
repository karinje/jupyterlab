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

    async def respond_to_user(message: str, intent: str | None = None, thread_title: str | None = None) -> str:
        # Also surface completion as a status for visibility in UIs that highlight statuses
        try:
            if intent == "completion":
                await chat_handler.send_status(message, "success")
                logger.info(f"Sent completion status: {message[:100]}...")
        except Exception as e:
            logger.warning(f"Failed to send status: {e}")
        
        # Save thread title if provided
        if thread_title:
            try:
                await chat_handler.save_thread_title(thread_title)
                logger.info(f"Saved thread title: {thread_title}")
            except Exception as e:
                logger.warning(f"Failed to save thread title: {e}")
        
        await chat_handler.send_message(message)
        logger.info(f"Responded to user: intent={intent or 'none'}, title={thread_title or 'none'}, message={message[:100]}...")
        return f"responded: intent={intent or 'none'}, title_saved={bool(thread_title)}"

    async def create_plan(plan_steps: List[PlanStepOutput]) -> str:
        steps = [
            step.model_dump() if hasattr(step, "model_dump") else dict(step)
            for step in plan_steps
        ]
        await chat_handler.display_plan_cards(steps)
        logger.info(f"Created plan with {len(steps)} steps")
        return f"plan_created: steps={len(steps)}"

    return [
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
