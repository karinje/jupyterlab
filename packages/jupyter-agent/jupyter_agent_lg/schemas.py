"""
Pydantic schemas for LLM structured outputs and tool arguments
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class PlanStepOutput(BaseModel):
    """Individual step in an analysis plan"""

    title: str = Field(description="Brief title for this step")
    description: str = Field(
        description="Detailed description of what this step involves"
    )


class LLMDecision(BaseModel):
    """Structured output for LLM decision making"""

    action: Literal["tools", "create_plan", "respond", "complete"] = Field(
        description="The next action to take"
    )
    reasoning: str = Field(description="Why this action was chosen")
    status_message: Optional[str] = Field(
        default=None,
        description="User-friendly status message to display in chat (for non-respond actions)",
    )

    # Action-specific fields
    message: Optional[str] = Field(
        default=None, description="Response message for 'respond' action"
    )
    plan_steps: Optional[List[PlanStepOutput]] = Field(
        default=None, description="Plan steps for 'create_plan' action"
    )


# Tool argument schemas
class InsertCellArgs(BaseModel):
    """Arguments for insert_and_execute_cell tool"""

    code: str = Field(description="Python code to insert and execute")
    cell_type: Literal["code", "markdown"] = Field(
        default="code", description="Type of cell to insert"
    )
    position: Literal["start", "end"] = Field(
        default="end",
        description="Where to insert the cell: 'start' for beginning, 'end' for bottom",
    )


class ExecuteCodeArgs(BaseModel):
    """Arguments for execute_code tool"""

    code: str = Field(description="Python code to execute in existing cell")


class DeleteCellArgs(BaseModel):
    """Arguments for delete_cell tool"""

    cell_index: int = Field(description="Index of the cell to delete (0-based)")
    status_message: Optional[str] = Field(
        default=None,
        description="Brief status message describing what you're deleting (e.g., 'Removing failed analysis cell')"
    )


class UpdateCellArgs(BaseModel):
    """Arguments for update_cell tool"""

    cell_index: int = Field(description="Index of the cell to update (0-based)")
    source: Optional[str] = Field(default=None, description="New source content for the cell")
    metadata: Optional[dict] = Field(default=None, description="New metadata for the cell")
    status_message: Optional[str] = Field(
        default=None,
        description="Brief status message describing what you're updating (e.g., 'Fixing code error in analysis')"
    )


class InsertMarkdownArgs(BaseModel):
    """Arguments for insert_markdown tool"""

    markdown: str = Field(description="Markdown content to insert")
    position: Literal["start", "end"] = Field(
        default="end",
        description="Where to insert the cell: 'start' for beginning, 'end' for bottom",
    )
    status_message: Optional[str] = Field(
        default=None,
        description="Brief status message describing what documentation you're adding (e.g., 'Adding analysis explanation')"
    )


# DISABLED: GetNotebookCellsArgs - tool removed as redundant
# class GetNotebookCellsArgs(BaseModel):
#     """Arguments for get_notebook_cells tool (no arguments needed)"""
#     pass


# MCP/Snowflake tool schemas
class SnowflakeQueryArgs(BaseModel):
    """Arguments for Snowflake query tool"""

    query: str = Field(description="SQL query to execute")
    database: Optional[str] = Field(default=None, description="Database name")
    schema_name: Optional[str] = Field(
        default=None,
        description="Schema name (renamed from 'schema' to avoid Pydantic warning)",
    )


class ListTablesArgs(BaseModel):
    """Arguments for listing Snowflake tables"""

    database: Optional[str] = Field(default=None, description="Database name")
    schema_name: Optional[str] = Field(
        default=None,
        description="Schema name (renamed from 'schema' to avoid Pydantic warning)",
    )


class RespondToUserArgs(BaseModel):
    """Arguments for RespondToUser tool"""

    message: str = Field(description="Message to show to the user in chat")
    intent: Optional[Literal["completion", "clarification", "status_update"]] = Field(
        default=None, description="Optional intent tag for the response"
    )
    thread_title: str = Field(
        description="REQUIRED: Generate a concise, descriptive title (3-8 words) summarizing this conversation topic. Examples: 'Data visualization plots', 'Sales analysis discussion', 'Python debugging help'"
    )


class CreatePlanArgs(BaseModel):
    """Arguments for CreatePlan tool"""

    plan_steps: List[PlanStepOutput] = Field(
        description="List of plan steps to render as editable cards"
    )
