from typing import List
from langchain_core.tools import StructuredTool
from ..schemas import RespondToUserArgs, CreatePlanArgs, PlanStepOutput


def create_system_tools(chat_handler) -> List[StructuredTool]:
    """Create system-level tools: RespondToUser, CreatePlan.

    chat_handler: instance with send_status, send_message, display_plan_cards
    """

    async def respond_to_user(message: str, intent: str | None = None) -> str:
        # Also surface completion as a status for visibility in UIs that highlight statuses
        try:
            if intent == "completion":
                await chat_handler.send_status(message, "success")
        except Exception:
            pass
        await chat_handler.send_message(message)
        return f"responded: intent={intent or 'none'}"

    async def create_plan(plan_steps: List[PlanStepOutput]) -> str:
        steps = [
            step.model_dump() if hasattr(step, "model_dump") else dict(step)
            for step in plan_steps
        ]
        await chat_handler.display_plan_cards(steps)
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
