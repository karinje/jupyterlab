#!/usr/bin/env python3
"""
JupyterLab Agent Tools - High-level tools for AI agents to interact with notebooks

This module provides the JupyterAgent class with tools designed for LLM agents
to insert code, execute it, and capture outputs in Jupyter notebooks.
"""

import asyncio
import json
import uuid
import aiohttp
import websockets
from typing import Dict, List, Union
from .room_proxy import RoomProxy


class JupyterAgent:
    """
    High-level agent interface for JupyterLab notebook manipulation.

    Manages authentication, kernel connections, and provides tools for
    AI agents to interact with notebooks seamlessly.
    """

    def __init__(self, server_url: str = "http://127.0.0.1:8890", token: str = None):
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.default_kernel_id = None

    async def _ensure_token(self):
        """Auto-discover token if not provided"""
        if self.token:
            return self.token

        # Try to extract token from server
        async with aiohttp.ClientSession() as session:
            async with session.get(self.server_url) as resp:
                if resp.status == 302:
                    location = resp.headers.get("Location", "")
                    import re

                    token_match = re.search(r"token=([a-f0-9]+)", location)
                    if token_match:
                        self.token = token_match.group(1)
                        return self.token

        raise Exception("Could not auto-discover token. Please provide it explicitly.")

    async def _ensure_kernel(self, kernel_id: str = None) -> str:
        """Get or create a kernel"""
        if kernel_id:
            return kernel_id

        if self.default_kernel_id:
            return self.default_kernel_id

        # Create new kernel
        token = await self._ensure_token()
        headers = {"Authorization": f"token {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/api/kernels",
                headers=headers,
                json={"name": "python3"},
            ) as resp:
                if resp.status == 201:
                    kernel_data = await resp.json()
                    self.default_kernel_id = kernel_data["id"]
                    return self.default_kernel_id
                else:
                    raise Exception(f"Failed to create kernel: {resp.status}")

    # 🔥 PRIMARY TOOL - Most common agent operation
    async def insert_code_and_execute(
        self,
        notebook_path: str,
        code: str,
        cell_type: str = "code",
        position: str = "end",
        kernel_id: str = None,
    ) -> Dict:
        """
        Complete workflow: Insert cell + Execute code + Capture outputs

        This is the PRIMARY tool agents will use most frequently.

        Args:
            notebook_path: Path to notebook (e.g., "analysis.ipynb")
            code: Python code to execute
            cell_type: "code" or "markdown"
            position: "start", "end", or integer index
            kernel_id: Optional specific kernel ID

        Returns:
            {
                "cell_id": "uuid-string",
                "outputs": [...],  # All kernel outputs (plots, text, errors)
                "execution_count": 5,
                "status": "ok|error",
                "error": "error message if failed"
            }
        """
        try:
            # Step 1: Insert cell
            cell_id = await self.insert_cell(notebook_path, code, cell_type, position)

            # Step 2: Execute code (only for code cells)
            if cell_type == "code":
                result = await self.execute_cell(
                    notebook_path, cell_id=cell_id, kernel_id=kernel_id
                )

                # Step 3: Update cell with outputs
                if result["outputs"]:
                    await self.update_cell_outputs(
                        notebook_path,
                        cell_id,
                        result["outputs"],
                        result.get("execution_count"),
                    )

                return {
                    "cell_id": cell_id,
                    "outputs": result["outputs"],
                    "execution_count": result.get("execution_count"),
                    "status": result["status"],
                }
            else:
                # Markdown cell - no execution needed
                return {
                    "cell_id": cell_id,
                    "outputs": [],
                    "execution_count": None,
                    "status": "ok",
                }

        except Exception as e:
            return {
                "cell_id": None,
                "outputs": [],
                "execution_count": None,
                "status": "error",
                "error": str(e),
            }

    async def insert_cell(
        self,
        notebook_path: str,
        content: str,
        cell_type: str = "code",
        position: Union[str, int] = "end",
    ) -> str:
        """
        Insert a new cell into the notebook.

        Args:
            notebook_path: Path to notebook
            content: Cell content (code or markdown)
            cell_type: "code" or "markdown"
            position: "start", "end", or integer index

        Returns:
            cell_id: UUID of the inserted cell
        """
        token = await self._ensure_token()

        # Convert position to index
        if position == "end":
            index = 0  # Insert at beginning for now (will be improved)
        elif position == "start":
            index = 0
        else:
            index = int(position)

        # Generate unique cell ID
        cell_id = str(uuid.uuid4())

        # Build Y-document update
        from pycrdt import Doc, Map, Array, Text

        ydoc = Doc()
        cells = ydoc["cells"] = Array()

        cell_map = {
            "id": cell_id,
            "cell_type": cell_type,
            "source": Text(content),
            "metadata": Map({}),
        }

        if cell_type == "code":
            cell_map["execution_count"] = None
            cell_map["outputs"] = Array()

        cell = Map(cell_map)

        with ydoc.transaction():
            cells.insert(index, cell)

        cell_update = ydoc.get_update()

        # Apply via RoomProxy - this is the WORKING approach from test_complete_flow.py
        import asyncio

        # Longer delay to prevent XSRF token conflicts in rapid operations
        await asyncio.sleep(0.5)

        async with RoomProxy(
            path=notebook_path, server_url=self.server_url, token=token
        ) as room:
            await room.apply_yupdate(cell_update)

        return cell_id

    async def execute_cell(
        self,
        notebook_path: str,
        cell_id: str = None,
        content: str = None,
        kernel_id: str = None,
    ) -> Dict:
        """
        Execute code in a kernel and return outputs.

        Args:
            notebook_path: Path to notebook
            cell_id: UUID of cell to execute (gets content from cell)
            content: Code to execute (overrides cell content)
            kernel_id: Optional specific kernel ID

        Returns:
            {
                "outputs": [...],
                "execution_count": int,
                "status": "ok|error"
            }
        """
        token = await self._ensure_token()
        kernel_id = await self._ensure_kernel(kernel_id)

        # Get code to execute
        if content:
            code = content
        elif cell_id:
            # Get cell content
            cell_data = await self.get_cell_content(notebook_path, cell_id)
            code = cell_data.get("source", "")
        else:
            raise ValueError("Must provide either cell_id or content")

        # Execute via kernel WebSocket
        ws_url = f"ws://127.0.0.1:{self.server_url.split(':')[-1]}/api/kernels/{kernel_id}/channels?token={token}"

        outputs = []
        execution_count = None
        status = "ok"

        try:
            async with websockets.connect(ws_url) as websocket:
                # Create execution request
                msg_id = str(uuid.uuid4())
                execute_msg = {
                    "header": {
                        "msg_id": msg_id,
                        "msg_type": "execute_request",
                        "username": "agent",
                        "session": str(uuid.uuid4()),
                        "date": "",
                        "version": "5.3",
                    },
                    "parent_header": {},
                    "metadata": {},
                    "content": {
                        "code": code,
                        "silent": False,
                        "store_history": True,
                        "user_expressions": {},
                        "allow_stdin": False,
                        "stop_on_error": True,
                    },
                    "buffers": [],
                    "channel": "shell",
                }

                await websocket.send(json.dumps(execute_msg))

                # Collect outputs
                timeout_count = 0
                max_timeouts = 100  # 10 seconds

                while timeout_count < max_timeouts:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        msg = json.loads(message)
                        msg_type = msg.get("header", {}).get("msg_type", "")

                        if msg_type == "stream":
                            outputs.append(
                                {
                                    "output_type": "stream",
                                    "name": msg["content"]["name"],
                                    "text": msg["content"]["text"],
                                }
                            )
                        elif msg_type == "execute_result":
                            outputs.append(
                                {
                                    "output_type": "execute_result",
                                    "execution_count": msg["content"][
                                        "execution_count"
                                    ],
                                    "data": msg["content"]["data"],
                                    "metadata": msg["content"].get("metadata", {}),
                                }
                            )
                        elif msg_type == "display_data":
                            outputs.append(
                                {
                                    "output_type": "display_data",
                                    "data": msg["content"]["data"],
                                    "metadata": msg["content"].get("metadata", {}),
                                }
                            )
                        elif msg_type == "error":
                            outputs.append(
                                {
                                    "output_type": "error",
                                    "ename": msg["content"]["ename"],
                                    "evalue": msg["content"]["evalue"],
                                    "traceback": msg["content"]["traceback"],
                                }
                            )
                            status = "error"
                        elif msg_type == "execute_reply":
                            execution_count = msg["content"]["execution_count"]
                            if msg["content"]["status"] == "error":
                                status = "error"
                            break

                    except asyncio.TimeoutError:
                        timeout_count += 1

        except Exception as e:
            status = "error"
            outputs.append(
                {
                    "output_type": "error",
                    "ename": "ConnectionError",
                    "evalue": str(e),
                    "traceback": [str(e)],
                }
            )

        return {
            "outputs": outputs,
            "execution_count": execution_count,
            "status": status,
        }

    async def update_cell_outputs(
        self,
        notebook_path: str,
        cell_id: str,
        outputs: List,
        execution_count: int = None,
    ) -> bool:
        """
        Insert outputs into specific cell by UUID.

        Args:
            notebook_path: Path to notebook
            cell_id: UUID of target cell
            outputs: List of output objects from kernel
            execution_count: Execution count to set

        Returns:
            bool: Success status
        """
        token = await self._ensure_token()

        # Find cell index by ID
        cell_data = await self.get_cell_content(notebook_path)
        cells = cell_data.get("cells", [])

        target_index = None
        for i, cell in enumerate(cells):
            if cell.get("id") == cell_id:
                target_index = i
                break

        if target_index is None:
            raise ValueError(f"Cell with ID {cell_id} not found")

        # Call update endpoint
        headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }

        update_data = {
            "path": notebook_path,
            "cell_index": target_index,
            "outputs": outputs,
            "execution_count": execution_count,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.server_url}/api/agent/notebook/update_outputs",
                headers=headers,
                json=update_data,
            ) as resp:
                return resp.status == 200

    async def get_cell_content(self, notebook_path: str, cell_id: str = None) -> Dict:
        """
        Get cell content by UUID or all cells.

        Args:
            notebook_path: Path to notebook
            cell_id: Optional UUID of specific cell

        Returns:
            dict: Cell data or notebook data
        """
        token = await self._ensure_token()
        headers = {"Authorization": f"token {token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.server_url}/api/contents/{notebook_path}", headers=headers
            ) as resp:
                notebook_data = await resp.json()

                if cell_id:
                    # Find specific cell
                    cells = notebook_data.get("content", {}).get("cells", [])
                    for cell in cells:
                        if cell.get("id") == cell_id:
                            return cell
                    raise ValueError(f"Cell with ID {cell_id} not found")
                else:
                    # Return all notebook data
                    return notebook_data.get("content", {})

    async def insert_markdown(
        self, notebook_path: str, markdown: str, position: Union[str, int] = "end"
    ) -> str:
        """
        Quick markdown cell insertion (no execution needed).

        Args:
            notebook_path: Path to notebook
            markdown: Markdown content
            position: "start", "end", or integer index

        Returns:
            cell_id: UUID of inserted cell
        """
        return await self.insert_cell(notebook_path, markdown, "markdown", position)


# Convenience functions for direct tool use
async def insert_code_and_execute(
    notebook_path: str,
    code: str,
    server_url: str = "http://127.0.0.1:8890",
    token: str = None,
) -> Dict:
    """
    Standalone function for the most common operation.
    Creates a JupyterAgent instance and executes the primary workflow.
    """
    agent = JupyterAgent(server_url, token)
    return await agent.insert_code_and_execute(notebook_path, code)
