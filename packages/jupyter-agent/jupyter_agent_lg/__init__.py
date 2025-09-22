"""
LangGraph Data Analysis Agent for JupyterLab

This package provides a sophisticated LLM-driven agent that can perform
iterative data analysis tasks using LangGraph for workflow orchestration.

Key Features:
- Pure LLM-driven decision making (no hardcoded logic)
- Dynamic planning with interactive user feedback
- Multi-step analysis with full context awareness
- Real-time status updates to chat UI
- Integration with existing JupyterAgent tools
- Multi-LLM support (OpenAI, Anthropic, Google)
"""

from .agent import JupyterAgent
from .state import create_initial_state, increment_iteration
from .context import NotebookStateManager
from .schemas import LLMDecision
from .tools import create_jupyter_tools

__version__ = "1.0.0"

__all__ = [
    "JupyterAgent",
    "create_initial_state",
    "increment_iteration",
    "NotebookStateManager",
    "LLMDecision",
    "create_jupyter_tools",
]
