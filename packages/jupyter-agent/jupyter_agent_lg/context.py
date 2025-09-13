"""
Context management for LangGraph Data Analysis Agent

Handles efficient notebook state retrieval and intelligent output summarization
to provide LLMs with complete context without token explosion.
"""

import logging
from typing import Dict, List, Any
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)


class NotebookStateManager:
    """Efficient notebook state retrieval and management"""

    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"token {token}"}

    async def get_complete_notebook_state(self, notebook_path: str) -> List[Dict]:
        """Get all cells with intelligently summarized outputs"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.server_url}/api/contents/{notebook_path}",
                    headers=self.headers,
                ) as resp:
                    if resp.status != 200:
                        logger.error(
                            f"Failed to load notebook {notebook_path}: {resp.status}"
                        )
                        return []

                    notebook_data = await resp.json()
                    notebook_content = notebook_data.get("content", {})
                    cells = notebook_content.get("cells", [])

                    # Summarize cells for LLM context
                    summarized_cells = []
                    for i, cell in enumerate(cells):
                        cell_summary = self._summarize_cell(cell, i)
                        summarized_cells.append(cell_summary)

                    logger.info(
                        f"📊 Retrieved {len(summarized_cells)} cells from {notebook_path}"
                    )
                    return summarized_cells

        except Exception as e:
            logger.error(f"Error loading notebook state: {e}")
            return []

    def _summarize_cell(self, cell: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Smart cell summarization to avoid token explosion"""
        cell_summary = {
            "index": index,
            "type": cell.get("cell_type", "unknown"),
            "id": cell.get("id", f"cell-{index}"),
            "execution_count": cell.get("execution_count"),
            "source": self._summarize_source(cell.get("source", [])),
            "outputs": self._summarize_outputs(cell.get("outputs", [])),
            "metadata": cell.get("metadata", {}),
        }

        return cell_summary

    def _summarize_source(self, source: List[str] | str) -> str:
        """Summarize cell source code"""
        if isinstance(source, list):
            source_text = "".join(source)
        else:
            source_text = source

        # Truncate very long source code
        if len(source_text) > 2000:
            return source_text[:2000] + "\n... [truncated]"

        return source_text

    def _summarize_outputs(self, outputs: List[Dict]) -> List[Dict]:
        """Smart output summarization to avoid token explosion"""
        summarized = []

        for output in outputs:
            output_type = output.get("output_type", "unknown")

            if output_type == "execute_result" or output_type == "display_data":
                summary = self._summarize_data_output(output)
            elif output_type == "stream":
                summary = self._summarize_stream_output(output)
            elif output_type == "error":
                summary = self._summarize_error_output(output)
            else:
                summary = {"type": output_type, "content": "unknown output type"}

            summarized.append(summary)

        return summarized

    def _summarize_data_output(self, output: Dict) -> Dict:
        """Summarize data outputs (plots, tables, etc.)"""
        data = output.get("data", {})
        summary = {
            "type": output.get("output_type"),
            "execution_count": output.get("execution_count"),
        }

        # Text output
        if "text/plain" in data:
            text = data["text/plain"]
            if isinstance(text, list):
                text = "".join(text)

            # Truncate long text output
            if len(text) > 1000:
                summary["text"] = text[:1000] + "\n... [truncated]"
            else:
                summary["text"] = text

        # HTML output (DataFrames, etc.)
        if "text/html" in data:
            summary["has_html"] = True
            # Try to extract table info for DataFrames
            html_content = data["text/html"]
            if isinstance(html_content, list):
                html_content = "".join(html_content)

            if "<table" in html_content.lower():
                summary["content_type"] = "dataframe_table"
                # Extract basic table info
                if "shape:" in html_content:
                    import re

                    shape_match = re.search(r"(\d+) rows × (\d+) columns", html_content)
                    if shape_match:
                        summary["table_shape"] = (
                            f"{shape_match.group(1)} rows × {shape_match.group(2)} columns"
                        )

        # Image output (plots)
        if "image/png" in data:
            summary["has_plot"] = True
            summary["content_type"] = "matplotlib_plot"

        if "image/svg+xml" in data:
            summary["has_svg"] = True
            summary["content_type"] = "svg_plot"

        # JSON output
        if "application/json" in data:
            summary["has_json"] = True
            try:
                json_data = data["application/json"]
                if isinstance(json_data, dict) and len(json_data) < 10:
                    summary["json_preview"] = json_data
                else:
                    summary["json_size"] = len(str(json_data))
            except:
                summary["json_preview"] = "complex json data"

        return summary

    def _summarize_stream_output(self, output: Dict) -> Dict:
        """Summarize stream outputs (stdout/stderr)"""
        text = output.get("text", "")
        if isinstance(text, list):
            text = "".join(text)

        summary = {
            "type": "stream",
            "name": output.get("name", "stdout"),
        }

        # Truncate long stream output
        if len(text) > 500:
            summary["text"] = text[:500] + "\n... [truncated]"
        else:
            summary["text"] = text

        return summary

    def _summarize_error_output(self, output: Dict) -> Dict:
        """Summarize error outputs"""
        return {
            "type": "error",
            "ename": output.get("ename", "Unknown"),
            "evalue": output.get("evalue", ""),
            "traceback_lines": len(output.get("traceback", [])),
        }

    async def get_execution_history(
        self, notebook_path: str, limit: int = 10
    ) -> List[Dict]:
        """Get recent execution history with results"""
        try:
            # For now, extract from notebook cells
            # In the future, this could be stored separately for better tracking
            cells = await self.get_complete_notebook_state(notebook_path)

            execution_history = []
            for cell in cells:
                if cell.get("execution_count") and cell.get("outputs"):
                    execution_history.append(
                        {
                            "execution_count": cell["execution_count"],
                            "source": cell["source"][:200] + "..."
                            if len(cell["source"]) > 200
                            else cell["source"],
                            "outputs_summary": len(cell["outputs"]),
                            "cell_id": cell["id"],
                            "timestamp": datetime.utcnow().isoformat(),  # Approximate
                        }
                    )

            # Sort by execution count and return recent ones
            execution_history.sort(key=lambda x: x["execution_count"], reverse=True)
            return execution_history[:limit]

        except Exception as e:
            logger.error(f"Error getting execution history: {e}")
            return []

    async def get_available_data_sources(self, mcp_servers: Dict = None) -> List[Dict]:
        """Get available data sources from MCP servers and notebook variables"""
        data_sources = []

        # Add MCP servers as data sources
        if mcp_servers:
            for server_name, config in mcp_servers.items():
                data_sources.append(
                    {
                        "type": "mcp_server",
                        "name": server_name,
                        "description": f"MCP server: {server_name}",
                        "config": config,
                    }
                )

        # TODO: In the future, could inspect notebook variables for DataFrames
        # This would require executing code to introspect the namespace

        return data_sources

    def create_context_summary(
        self,
        notebook_cells: List[Dict],
        execution_history: List[Dict],
        conversation_history: List[Dict],
    ) -> str:
        """Create a concise context summary for LLM prompts"""

        # Ensure inputs are not None
        notebook_cells = notebook_cells or []
        execution_history = execution_history or []
        conversation_history = conversation_history or []

        # Count different types of cells and outputs
        code_cells = len([c for c in notebook_cells if c.get("type") == "code"])
        markdown_cells = len([c for c in notebook_cells if c.get("type") == "markdown"])
        cells_with_output = len([c for c in notebook_cells if c.get("outputs")])

        # Recent executions
        recent_executions = len(
            [h for h in execution_history if h.get("execution_count", 0) > 0]
        )

        # Conversation length
        conversation_length = len(conversation_history)

        summary = f"""
Current Notebook Context:
- Total cells: {len(notebook_cells)} ({code_cells} code, {markdown_cells} markdown)
- Cells with outputs: {cells_with_output}
- Recent executions: {recent_executions}
- Conversation messages: {conversation_length}
        """.strip()

        return summary
