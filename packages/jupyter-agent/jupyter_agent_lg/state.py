"""
State management for LangGraph Data Analysis Agent

Defines the complete state schema that the LLM uses for decision making,
including conversation history, notebook state, planning, and control flow.
"""

import logging
from typing import Dict, List, Optional, Any, TypedDict, Literal
from dataclasses import dataclass
from datetime import datetime
import uuid

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


@dataclass
class PlanStep:
    """Individual step in an analysis plan"""

    step_id: str
    title: str
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    result: Optional[Any] = None
    created_at: str = ""
    completed_at: Optional[str] = None

    def __post_init__(self):
        if not self.step_id:
            self.step_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def mark_completed(self, result: Any = None):
        """Mark step as completed with optional result"""
        self.status = "completed"
        self.result = result
        self.completed_at = datetime.utcnow().isoformat()

    def mark_failed(self, error: str):
        """Mark step as failed with error message"""
        self.status = "failed"
        self.result = {"error": error}
        self.completed_at = datetime.utcnow().isoformat()


@dataclass
class Decision:
    """LLM decision with structured output"""

    action: str
    params: Dict[str, Any]
    reasoning: str
    status_message: str
    confidence: float = 0.8

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "action": self.action,
            "params": self.params,
            "reasoning": self.reasoning,
            "status_message": self.status_message,
            "confidence": self.confidence,
        }


class AnalysisState(TypedDict, total=False):
    """
    Complete context for LLM decision-making in the data analysis workflow.

    This state is passed to every LangGraph node and contains all information
    the LLM needs to make informed decisions about next actions.
    """

    # Core context - always present
    original_request: str
    notebook_path: str
    conversation_history: List[Dict[str, str]]  # All chat messages

    # Notebook state - updated dynamically
    notebook_cells: List[Dict[str, Any]]  # Complete cells with outputs
    execution_history: List[Dict]  # All code executions with results

    # Planning - created and modified by LLM
    plan: Optional[List[Dict[str, Any]]]  # Current analysis plan (serialized PlanSteps)
    completed_steps: List[str]  # Step IDs that are done

    # LLM decisions - updated each cycle
    next_action: str  # What to do next
    action_params: Dict[str, Any]  # Parameters for the action
    reasoning: str  # Why this decision was made

    # External resources - from MCP/APIs
    available_data_sources: List[Dict]  # Available databases, APIs, etc.

    # Control flow
    is_complete: bool  # Whether analysis is finished
    error_count: int  # Number of errors encountered
    max_iterations: int  # Safety limit
    current_iteration: int  # Current iteration count

    # Agent configuration
    llm_model: str  # Which model to use
    llm_provider: str  # Which provider (openai, anthropic, etc.)

    # Status tracking
    last_status_update: Optional[str]  # Last status sent to UI
    start_time: str  # When analysis started


class StateManager:
    """Manages state transitions and validation"""

    def __init__(self):
        self.required_fields = [
            "original_request",
            "notebook_path",
            "conversation_history",
            "notebook_cells",
            "execution_history",
        ]

    def create_initial_state(
        self,
        request: str,
        notebook_path: str,
        conversation_history: List[Dict[str, str]],
        model: str = "gpt-4o",
        provider: str = "openai",
    ) -> AnalysisState:
        """Create initial state for new analysis"""
        return AnalysisState(
            original_request=request,
            notebook_path=notebook_path,
            conversation_history=conversation_history,
            notebook_cells=[],
            execution_history=[],
            plan=None,
            completed_steps=[],
            next_action="analyze_and_decide",
            action_params={},
            reasoning="Starting analysis",
            available_data_sources=[],
            is_complete=False,
            error_count=0,
            max_iterations=50,  # Safety limit
            current_iteration=0,
            llm_model=model,
            llm_provider=provider,
            last_status_update=None,
            start_time=datetime.utcnow().isoformat(),
        )

    def validate_state(self, state: AnalysisState) -> bool:
        """Validate that state has required fields"""
        for field in self.required_fields:
            if field not in state:
                return False
        return True

    def increment_iteration(self, state: AnalysisState) -> AnalysisState:
        """Increment iteration counter and check limits"""
        state["current_iteration"] = state.get("current_iteration", 0) + 1

        # Safety check - prevent infinite loops
        if state["current_iteration"] >= state.get("max_iterations", 50):
            state["is_complete"] = True
            state["next_action"] = "complete_analysis"
            state["reasoning"] = "Reached maximum iteration limit"

        return state

    def add_error(self, state: AnalysisState, error: str) -> AnalysisState:
        """Add error to state and update error count"""
        state["error_count"] = state.get("error_count", 0) + 1

        # Add error to conversation history
        error_message = {
            "role": "system",
            "content": f"Error occurred: {error}",
            "timestamp": datetime.utcnow().isoformat(),
        }
        state["conversation_history"].append(error_message)

        # If too many errors, complete with failure
        if state["error_count"] >= 5:
            state["is_complete"] = True
            state["next_action"] = "complete_analysis"
            state["reasoning"] = "Too many errors encountered"

        return state

    def serialize_plan(self, plan_steps: List[PlanStep]) -> List[Dict[str, Any]]:
        """Serialize plan steps for state storage"""
        return [
            {
                "step_id": step.step_id,
                "title": step.title,
                "description": step.description,
                "status": step.status,
                "result": step.result,
                "created_at": step.created_at,
                "completed_at": step.completed_at,
            }
            for step in plan_steps
        ]

    def deserialize_plan(self, plan_data: List[Dict[str, Any]]) -> List[PlanStep]:
        """Deserialize plan steps from state storage"""
        return [
            PlanStep(
                step_id=step_data["step_id"],
                title=step_data["title"],
                description=step_data["description"],
                status=step_data["status"],
                result=step_data.get("result"),
                created_at=step_data["created_at"],
                completed_at=step_data.get("completed_at"),
            )
            for step_data in plan_data
        ]


# Standalone helper functions for simplified state management
def create_initial_state(
    request: str,
    notebook_path: str,
    conversation_history: List[Dict[str, str]] = None,
    model: str = "gpt-4o",
    provider: str = "openai",
    thread_id: str = None,
) -> Dict[str, Any]:
    """Create initial state for new analysis"""
    if conversation_history is None:
        conversation_history = []

    return {
        "original_request": request,
        "notebook_path": notebook_path,
        "conversation_history": conversation_history,
        "notebook_cells": [],
        "plan_steps": [],
        "next_action": "analyze_and_decide",
        "reasoning": "Starting analysis",
        "response_message": None,
        "current_status": "initializing",
        "last_status_update": None,
        "llm_model": model,
        "llm_provider": provider,
        "current_iteration": 0,
        "max_iterations": 50,
        "is_complete": False,
        "start_time": datetime.utcnow().isoformat(),
        "session_id": str(uuid.uuid4()),
        "thread_id": thread_id,  # Add thread_id to state
    }


def increment_iteration(state: Dict[str, Any]) -> Dict[str, Any]:
    """Increment iteration counter and check limits"""
    state["current_iteration"] = state.get("current_iteration", 0) + 1

    # Safety check - prevent infinite loops
    if state["current_iteration"] >= state.get("max_iterations", 50):
        state["is_complete"] = True
        state["next_action"] = "complete_analysis"
        state["reasoning"] = "Reached maximum iteration limit"

    return state
