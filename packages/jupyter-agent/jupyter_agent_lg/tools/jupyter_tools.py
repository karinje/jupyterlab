"""
Jupyter notebook manipulation tools for the LangGraph agent
"""

import logging
from typing import List, Dict
from langchain_core.tools import StructuredTool
from ..schemas import (
    InsertCellArgs,
    DeleteCellArgs,
    # GetNotebookCellsArgs - removed, tool disabled
    # ExecuteCodeArgs - removed, tool no longer exists
)

logger = logging.getLogger(__name__)


def create_jupyter_tools(jupyter_agent, notebook_path: str) -> List[StructuredTool]:
    """Create Jupyter notebook manipulation tools with correct notebook path"""

    # Capture logger in closure scope
    tool_logger = logger

    async def insert_and_execute_cell(
        code: str, cell_type: str = "code", position: str = "end"
    ) -> str:
        """Insert and execute a cell in the notebook"""
        try:
            print(
                f"🔧 TOOL CALLED: insert_and_execute_cell with code: {str(code)[:50]}..."
            )
            # HYPOTHESIS TEST: Log what's being inserted and when
            code_preview = (
                (code[:50] + "...")
                if isinstance(code, str) and len(code) > 50
                else str(code)
            )
            tool_logger.info(f"🔧 INSERTING CELL: {cell_type} at {position}")
            tool_logger.info(f"🔧 Code preview: {code_preview}")

            # Check what type of plot this is
            code_lower = code.lower()
            if "y**2" in code_lower or "**2" in code_lower:
                tool_logger.info("🔧 ⚠️  This is a y**2 plot!")
            if "y**3" in code_lower or "x**3" in code_lower or "**3" in code_lower:
                tool_logger.info("🔧 ⚠️  This is a y**3/x**3 plot!")

            if cell_type == "code":
                tool_logger.info(
                    f"🔧 CALLING insert_code_and_execute with notebook_path: {notebook_path}"
                )
                result = await jupyter_agent.insert_code_and_execute(
                    notebook_path, code, position=position
                )
                tool_logger.info("🔧 ✅ CELL INSERTION COMPLETED")
                # Safely extract outputs from result
                outputs = result.get("outputs", []) if isinstance(result, dict) else []
                return f"Code executed successfully. Result: {_format_outputs(outputs)}"
            else:
                tool_logger.info("🔧 CALLING insert_cell for markdown")
                result = await jupyter_agent.insert_cell(
                    notebook_path, code, cell_type="markdown", position=position
                )
                tool_logger.info("🔧 ✅ MARKDOWN INSERTION COMPLETED")
                return f"Markdown cell inserted successfully at position: {position}"
        except Exception as e:
            tool_logger.error(f"Error inserting/executing cell: {e}")
            return f"Error: {str(e)}"

    async def delete_cell(cell_index: int) -> str:
        """Delete a cell from the notebook"""
        try:
            # JupyterAgent doesn't have delete_cell method yet
            # This would need to be implemented in the future
            return "Delete cell functionality not yet implemented in JupyterAgent"
        except Exception as e:
            tool_logger.error(f"Error deleting cell: {e}")
            return f"Error: {str(e)}"

    # Create the tools
    tools = [
        StructuredTool.from_function(
            func=insert_and_execute_cell,
            name="insert_and_execute_cell",
            description="Insert and execute a code cell or insert a markdown cell in the notebook",
            args_schema=InsertCellArgs,
            coroutine=insert_and_execute_cell,
        ),
        StructuredTool.from_function(
            func=delete_cell,
            name="delete_cell",
            description="Delete a cell from the notebook by index",
            args_schema=DeleteCellArgs,
            coroutine=delete_cell,
        ),
        # DISABLED: get_notebook_cells - redundant since context already provides all cell info
        # StructuredTool.from_function(
        #     func=get_notebook_cells,
        #     name="get_notebook_cells",
        #     description="Get information about all cells in the notebook",
        #     args_schema=GetNotebookCellsArgs,
        #     coroutine=get_notebook_cells
        # )
    ]

    tool_logger.info(
        f"Created {len(tools)} Jupyter tools for notebook: {notebook_path}"
    )
    return tools


def _format_outputs(outputs: List[Dict]) -> str:
    """Format notebook outputs for LLM context"""
    if not outputs or not isinstance(outputs, list):
        return "No output"

    formatted = []
    # Safely limit to first 3 outputs
    safe_outputs = outputs[:3] if len(outputs) > 3 else outputs
    for output in safe_outputs:
        output_type = output.get("output_type", "unknown")

        if output_type == "stream":
            text = output.get("text", "")
            if isinstance(text, list):
                text = "".join(text)
            # Safely slice text
            text_preview = (
                text[:200] if isinstance(text, str) and len(text) > 200 else str(text)
            )
            formatted.append(f"Stream: {text_preview}")

        elif output_type in ["execute_result", "display_data"]:
            data = output.get("data", {})
            if "text/plain" in data:
                text = data["text/plain"]
                if isinstance(text, list):
                    text = "".join(text)
                # Safely slice text
                text_preview = (
                    text[:200]
                    if isinstance(text, str) and len(text) > 200
                    else str(text)
                )
                formatted.append(f"Result: {text_preview}")
            elif "text/html" in data:
                formatted.append("HTML output (table/dataframe)")
            elif "image/png" in data:
                formatted.append("Image/plot generated")

        elif output_type == "error":
            ename = output.get("ename", "Error")
            evalue = output.get("evalue", "")
            formatted.append(f"Error: {ename}: {evalue}")

    return "; ".join(formatted) if formatted else "No readable output"
