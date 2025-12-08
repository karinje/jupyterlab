"""
Context management for LangGraph Data Analysis Agent

Handles efficient notebook state retrieval and intelligent output summarization
to provide LLMs with complete context without token explosion.
"""

import logging
from typing import Dict, List, Optional
import aiohttp
from datetime import datetime

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


class NotebookStateManager:
    """Efficient notebook state retrieval and management"""

    def __init__(self, server_url: str, token: str):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"token {token}"}
        # Truncation settings (defaults): no truncation for source; conservative for outputs
        self.max_source_chars: Optional[int] = (
            None  # None => do not truncate code/markdown
        )
        self.max_text_plain_chars: int = 10000  # execute_result/display_data text/plain
        self.max_stream_chars: int = 5000  # stream text

    def _normalize_notebook_path(self, notebook_path: str) -> str:
        """Strip RTC: prefix from notebook paths for Contents API compatibility"""
        if notebook_path and notebook_path.startswith("RTC:"):
            return notebook_path[4:]  # Remove "RTC:" prefix
        return notebook_path

    async def get_complete_notebook_state(self, notebook_path: str) -> List[Dict]:
        """Get all cells ready for LLM context - ONE PASS, NO REDUNDANCY

        Returns:
            List[Dict]: cells with everything needed for multimodal LLM
        """
        try:
            # Normalize path (strip RTC: prefix)
            notebook_path = self._normalize_notebook_path(notebook_path)

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
                    raw_cells = notebook_content.get("cells", [])

                    # SINGLE PASS: Process all cells and create complete multimodal content
                    complete_multimodal_content = (
                        self._create_complete_multimodal_content(raw_cells)
                    )

                    logger.info(
                        f"📊 Processed {len(raw_cells)} cells into complete multimodal content from {notebook_path}"
                    )
                    return complete_multimodal_content

        except Exception as e:
            logger.error(f"Error loading notebook state: {e}")
            return []

    def _create_complete_multimodal_content(self, raw_cells: List[Dict]) -> List[Dict]:
        """SINGLE PASS: Create complete multimodal content ready for LLM system message"""

        # Start with context header
        complete_content = [
            {
                "type": "text",
                "text": """Current Context:
--------
Notebook Context Guide:

The notebook state below shows ALL cells with their ACTUAL indices (0-based). This includes:
- Code cells (executed and not executed)
- Markdown cells
- Empty cells
- Images from plots/charts (you can see these images directly)

CRITICAL INDEX USAGE:
- Cell indices shown as "Cell [N]" are 0-based positions in the notebook
- When using delete_cell(cell_index), use the EXACT index N shown in "Cell [N]"
- Do NOT skip or renumber - use the index exactly as shown

Cell Status Indicators:
- ✅ Code cell (executed #N) = Cell was run successfully (execution count N)
- ✅ Code cell (executed #N) with outputs = Cell produced results/plots/data
- ⏸️ Code cell (not executed) = Code cell exists but hasn't been run yet
- 📝 Markdown cell = Documentation/text cell
- Empty cells are shown with no content after the cell header

Current Notebook State:
All Notebook Cells (0-based indexing):
""",
            }
        ]

        # Process each cell in sequence
        for i, raw_cell in enumerate(raw_cells):
            cell_type = raw_cell.get("cell_type", "unknown")
            execution_count = raw_cell.get("execution_count")
            raw_source = raw_cell.get("source", [])
            raw_outputs = raw_cell.get("outputs", [])

            # Truncate source if needed
            if isinstance(raw_source, list):
                source_text = "".join(raw_source)
            else:
                source_text = raw_source

            if self.max_source_chars and len(source_text) > self.max_source_chars:
                source_text = source_text[: self.max_source_chars] + "\n... [truncated]"

            # Build cell text and extract images in ONE PASS
            if cell_type == "code":
                if execution_count is not None:
                    status = f"✅ Code cell (executed #{execution_count})"
                    if raw_outputs:
                        status += " with outputs"
                else:
                    status = "⏸️ Code cell (not executed)"

                cell_text = f"Cell [{i}]: {status}\n{source_text}\n"

                # Process outputs and extract images
                cell_has_any_images = False
                if raw_outputs:
                    cell_text += "  Outputs:\n"
                    for output_idx, output in enumerate(raw_outputs):
                        output_type = output.get("output_type", "unknown")

                        if output_type == "error":
                            ename = output.get("ename", "Unknown")
                            evalue = output.get("evalue", "")
                            cell_text += f"    ❌ ERROR: {ename}: {evalue}\n"

                        elif output_type == "stream":
                            text = output.get("text", "")
                            if isinstance(text, list):
                                text = "".join(text)
                            if len(text) > self.max_stream_chars:
                                text = (
                                    text[: self.max_stream_chars] + "\n... [truncated]"
                                )
                            cell_text += (
                                f"    📝 {output.get('name', 'stdout')}: {text}\n"
                            )

                        elif output_type in ["execute_result", "display_data"]:
                            data = output.get("data", {})

                            # Text output
                            if "text/plain" in data:
                                text = data["text/plain"]
                                if isinstance(text, list):
                                    text = "".join(text)
                                if len(text) > self.max_text_plain_chars:
                                    text = (
                                        text[: self.max_text_plain_chars]
                                        + "\n... [truncated]"
                                    )
                                cell_text += f"    📊 Result: {text}\n"

                            # DataFrame detection
                            if "text/html" in data:
                                html_content = data["text/html"]
                                if isinstance(html_content, list):
                                    html_content = "".join(html_content)
                                if "<table" in html_content.lower():
                                    import re

                                    shape_match = re.search(
                                        r"(\d+) rows × (\d+) columns", html_content
                                    )
                                    if shape_match:
                                        cell_text += f"    📊 DataFrame: {shape_match.group(1)} rows × {shape_match.group(2)} columns\n"

                            # Check for images in this output
                            output_has_images = (
                                "image/png" in data or "image/jpeg" in data
                            )

                            if output_has_images:
                                # Add accumulated cell_text before images
                                if not cell_has_any_images:
                                    # First image in cell - add all the cell text so far
                                    complete_content.append(
                                        {"type": "text", "text": cell_text}
                                    )
                                    cell_has_any_images = True

                                # Add each image type that exists in this output
                                if "image/png" in data:
                                    png_data = data["image/png"]
                                    if isinstance(png_data, str) and png_data:
                                        complete_content.append(
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:image/png;base64,{png_data}"
                                                },
                                            }
                                        )
                                        cell_text += f"    📊 [IMAGE {output_idx + 1}] PNG Chart/Plot - You can see this image\n"

                                if "image/jpeg" in data:
                                    jpeg_data = data["image/jpeg"]
                                    if isinstance(jpeg_data, str) and jpeg_data:
                                        complete_content.append(
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:image/jpeg;base64,{jpeg_data}"
                                                },
                                            }
                                        )
                                        cell_text += f"    📊 [IMAGE {output_idx + 1}] JPEG Chart/Plot - You can see this image\n"

                            # JSON data
                            if "application/json" in data:
                                json_data = data["application/json"]
                                if isinstance(json_data, dict) and len(json_data) < 10:
                                    cell_text += f"    📋 JSON: {json_data}\n"
                                else:
                                    cell_text += f"    📋 JSON data (size: {len(str(json_data))})\n"

                # Add final cell text only if we didn't already add it for images
                if not cell_has_any_images:
                    complete_content.append({"type": "text", "text": cell_text + "\n"})
                else:
                    # We already added text before images, but may have accumulated more text after
                    # Add any trailing text that came after images
                    complete_content.append({"type": "text", "text": "\n"})

            elif cell_type == "markdown":
                cell_text = f"Cell [{i}]: 📝 Markdown cell\n{source_text}\n\n"
                complete_content.append({"type": "text", "text": cell_text})

            else:
                cell_text = f"Cell [{i}]: {cell_type} cell\n{source_text}\n\n"
                complete_content.append({"type": "text", "text": cell_text})

        return complete_content

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
