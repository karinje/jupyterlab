"""
Jupyter Tools for LangGraph Agent

This module creates structured tools for the LangGraph agent to interact
with Jupyter notebooks via the JupyterTools bridge.
"""

from langchain.tools import StructuredTool
from typing import List, Dict
import logging

# Set up proper logging using simplified config
try:
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
    tool_logger = get_logger()  # Same logger for tools
except ImportError:
    # Fallback if centralized logging not available
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger("jupyterlab")
    tool_logger = logging.getLogger("jupyterlab")

from ..schemas import (
    InsertCellArgs,
    DeleteCellArgs,
    # GetNotebookCellsArgs - removed, tool disabled
    # ExecuteCodeArgs - removed, tool no longer exists
)


def create_jupyter_tools(
    jupyter_tools_client, notebook_path: str
) -> List[StructuredTool]:
    """Create Jupyter notebook manipulation tools with correct notebook path"""

    # Capture logger in closure scope
    tool_logger = logger

    async def insert_and_execute_cell(
        code: str, cell_type: str = "code", position: str = "end"
    ) -> str:
        """Insert and execute a cell in the notebook"""
        try:
            tool_logger.info(
                f"🔧 TOOL CALLED: insert_and_execute_cell with code: {str(code)[:50]}..."
            )
            code_preview = (
                (code[:50] + "...")
                if isinstance(code, str) and len(code) > 50
                else str(code)
            )
            tool_logger.info(f"🔧 INSERTING CELL: {cell_type} at {position}")
            tool_logger.info(f"🔧 Code preview: {code_preview}")

            if cell_type == "code":
                tool_logger.info(
                    f"🔧 CALLING insert_code_and_execute with notebook_path: {notebook_path}"
                )
                # Map position to cell_index per JupyterTools API
                cell_index = "append" if position == "end" else 0
                result = await jupyter_tools_client.insert_code_and_execute(
                    notebook_path=notebook_path, code=code, cell_index=cell_index
                )
                tool_logger.info("🔧 ✅ CELL INSERTION COMPLETED")
                exec_count = result.get("execution_count")
                outputs_count = result.get("outputs_count")
                return f"Code executed successfully. execution_count={exec_count}, outputs_count={outputs_count}"
            else:
                tool_logger.info("🔧 CALLING insert_cell for markdown")
                cell_index = "append" if position == "end" else 0
                await jupyter_tools_client.insert_cell(
                    notebook_path=notebook_path,
                    content=code,
                    cell_type="markdown",
                    cell_index=cell_index,
                )
                tool_logger.info("🔧 ✅ MARKDOWN INSERTION COMPLETED")
                return f"Markdown cell inserted successfully at position: {position}"
        except Exception as e:
            tool_logger.error(f"Error inserting/executing cell: {e}")
            return f"Error: {str(e)}"

    async def delete_cell(cell_index: int) -> str:
        """Delete a cell from the notebook"""
        try:
            result = await jupyter_tools_client.delete_cell(
                notebook_path=notebook_path, index=cell_index
            )
            status = result.get("status", "unknown")
            deleted_index = result.get("deleted_index", cell_index)
            if status == "ok" or status == "success":
                return f"Cell {deleted_index} deleted"
            return f"Failed to delete cell {deleted_index}: {result}"
        except Exception as e:
            tool_logger.error(f"Error deleting cell: {e}")
            return f"Error: {str(e)}"

    # Create the tools with category metadata
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
    ]
    
    # Add category metadata to all Jupyter tools
    for tool in tools:
        if not tool.metadata:
            tool.metadata = {}
        tool.metadata['tool_category'] = "Jupyter Notebook Tools"

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
