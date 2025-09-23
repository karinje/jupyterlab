#!/usr/bin/env python3

"""
Jupyter Tools - Real-time notebook manipulation via YDoc.

This module provides tools for manipulating Jupyter notebooks in real-time
by directly modifying the live YNotebook shared model. Changes appear
instantly in the browser via JupyterLab's Real-Time Collaboration (RTC) system.
"""

import aiohttp
import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urljoin

# Set up proper logging using simplified config
try:
    from .logging_config import get_logger
    logger = get_logger()
except ImportError:
    # Fallback if centralized logging not available
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger("jupyterlab")


class JupyterTools:
    """
    High-level tools interface for JupyterLab notebook manipulation.

    Provides tools to interact with Jupyter notebooks through
    real-time YDoc updates, ensuring immediate synchronization with the frontend.
    """

    def __init__(self, base_url: str = "http://localhost:8890", token: str = None):
        """
        Initialize the JupyterTools.

        Args:
            base_url: JupyterLab server URL
            token: Authentication token for the Jupyter server
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = None
        self._kernel_cache = {}  # Cache kernel IDs per notebook path
        self._xsrf_token: Optional[str] = None

        logger.info(f"JupyterTools initialized with base_url: {self.base_url}")

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _get_headers(self, *, xsrf: Optional[str] = None) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        if xsrf:
            headers["X-XSRFToken"] = xsrf
        return headers

    async def _ensure_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def _ensure_xsrf_cookie(self):
        """Ensure we have the _xsrf cookie and header value by visiting /lab once."""
        await self._ensure_session()
        if self._xsrf_token:
            logger.debug(f"Using cached XSRF token: {self._xsrf_token[:10]}...")
            return
        try:
            logger.debug("Fetching XSRF token from /lab")
            url = f"{self.base_url}/lab"
            async with self.session.get(url, headers=self._get_headers()) as resp:
                logger.debug(f"GET /lab response status: {resp.status}")
                logger.debug(f"Response cookies: {dict(resp.cookies)}")
                # Try to read cookie from response
                xsrf_cookie = resp.cookies.get("_xsrf")
                logger.debug(f"_xsrf cookie object: {xsrf_cookie}")
                if xsrf_cookie and xsrf_cookie.value:
                    self._xsrf_token = xsrf_cookie.value
                    logger.info(f"✅ Obtained XSRF token: {self._xsrf_token[:10]}...")
                else:
                    logger.debug("No _xsrf cookie found in response")
                    # Fallback: try cookie jar
                    # Try to extract from cookie jar
                    for cookie in self.session.cookie_jar:
                        if cookie.key == "_xsrf":
                            self._xsrf_token = cookie.value
                            logger.info(f"✅ Found XSRF token in cookie jar: {self._xsrf_token[:10]}...")
                            break
                    else:
                        logger.warning("❌ No XSRF token found anywhere")
        except Exception as e:
            logger.error(f"❌ Failed to obtain XSRF token: {e}")

    async def insert_cell(
        self,
        notebook_path: str,
        content: str,
        cell_type: str = "code",
        cell_index: Union[int, str] = "append",
        cell_id: str = None,
    ) -> Dict[str, Any]:
        """
        Insert a cell into a notebook with real-time YDoc synchronization.

        Args:
            notebook_path: Path to the notebook file
            content: Cell content (code or markdown)
            cell_type: Type of cell ('code' or 'markdown')
            cell_index: Position to insert ('append' or integer index)
            cell_id: Optional cell ID (generated if not provided)

        Returns:
            Dict with status and cell_id
        """
        await self._ensure_session()
        await self._ensure_xsrf_cookie()

        if cell_id is None:
            cell_id = str(uuid.uuid4())

        url = f"{self.base_url}/api/tools/insert-cell"
        data = {
            "path": notebook_path,
            "source": content,
            "cell_type": cell_type,
            "index": cell_index,
            "cell_id": cell_id,
        }

        logger.info(
            f"Inserting {cell_type} cell at index {cell_index} in {notebook_path}"
        )

        headers = self._get_headers(xsrf=self._xsrf_token)
        logger.debug(f"POST headers: {headers}")
        logger.debug(f"POST data: {data}")

        # Ensure _xsrf cookie is sent along with header
        cookies = {'_xsrf': self._xsrf_token} if self._xsrf_token else {}
        logger.debug(f"POST cookies: {cookies}")

        async with self.session.post(
            url, json=data, headers=headers, cookies=cookies
        ) as response:
            logger.info(f"POST response status: {response.status}")
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"POST failed with {response.status}: {error_text}")
                raise Exception(f"Failed to insert cell: {error_text}")

            result = await response.json()
            logger.info(f"Cell inserted successfully: {result}")
            return result

    async def execute_cell(
        self,
        notebook_path: str,
        kernel_id: str,
        cell_id: str = None,
        index: int = None,
        stream: bool = True,
        scroll_to_cell: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute a cell and capture outputs.

        Args:
            notebook_path: Path to the notebook
            kernel_id: ID of the kernel to use
            cell_id: Optional cell ID to execute
            index: Optional cell index to execute
            stream: Whether to stream outputs in real-time
            scroll_to_cell: Whether to scroll notebook to the executed cell

        Returns:
            Dict containing execution results with output confirmation
        """
        await self._ensure_session()
        await self._ensure_xsrf_cookie()

        url = f"{self.base_url}/api/tools/execute-cell"
        data = {
            "path": notebook_path, 
            "kernel_id": kernel_id, 
            "stream": stream,
            "scroll_to_cell": scroll_to_cell
        }

        if cell_id:
            data["cell_id"] = cell_id
        if index is not None:
            data["index"] = index

        logger.info(f"Executing cell in {notebook_path} with kernel {kernel_id} (scroll: {scroll_to_cell})")

        # Ensure _xsrf cookie is sent along with header
        cookies = {'_xsrf': self._xsrf_token} if self._xsrf_token else {}
        logger.debug(f"EXECUTE POST cookies: {cookies}")

        async with self.session.post(
            url, json=data, headers=self._get_headers(xsrf=self._xsrf_token), cookies=cookies
        ) as response:
            logger.info(f"EXECUTE POST response status: {response.status}")
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"EXECUTE POST failed with {response.status}: {error_text}")
                raise Exception(f"Failed to execute cell: {error_text}")

            result = await response.json()
            
            # Confirm outputs are properly attached
            outputs_attached = result.get("outputs_attached", False)
            has_output = result.get("has_output", False)
            outputs_count = result.get("outputs_count", 0)
            
            if has_output and not outputs_attached:
                logger.warning(f"Cell execution completed but outputs may not be properly attached (count: {outputs_count})")
            
            logger.info(f"Cell executed successfully: execution_count={result.get('execution_count')}, "
                       f"outputs_count={outputs_count}, outputs_attached={outputs_attached}, "
                       f"scrolled={result.get('scrolled', False)}")
            
            return result

    async def update_cell(
        self,
        notebook_path: str,
        cell_id: str = None,
        index: int = None,
        source: str = None,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Update a cell's content or metadata.

        Args:
            notebook_path: Path to the notebook
            cell_id: Optional cell ID to update
            index: Optional cell index to update
            source: New source content
            metadata: New metadata

        Returns:
            Dict with update status
        """
        await self._ensure_session()
        await self._ensure_xsrf_cookie()

        url = f"{self.base_url}/api/tools/update-cell"
        data = {"path": notebook_path}

        if cell_id:
            data["cell_id"] = cell_id
        if index is not None:
            data["index"] = index
        if source is not None:
            data["source"] = source
        if metadata is not None:
            data["metadata"] = metadata

        async with self.session.post(
            url, json=data, headers=self._get_headers(xsrf=self._xsrf_token), cookies={'_xsrf': self._xsrf_token} if self._xsrf_token else {}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Failed to update cell: {error_text}")

            result = await response.json()
            logger.info(f"Cell updated successfully: {result}")
            return result

    async def delete_cell(
        self, notebook_path: str, cell_id: str = None, index: int = None
    ) -> Dict[str, Any]:
        """
        Delete a cell from the notebook.

        Args:
            notebook_path: Path to the notebook
            cell_id: Optional cell ID to delete
            index: Optional cell index to delete

        Returns:
            Dict with deletion status
        """
        await self._ensure_session()
        await self._ensure_xsrf_cookie()

        url = f"{self.base_url}/api/tools/delete-cell"
        data = {"path": notebook_path}

        if cell_id:
            data["cell_id"] = cell_id
        if index is not None:
            data["index"] = index

        async with self.session.post(
            url, json=data, headers=self._get_headers(xsrf=self._xsrf_token), cookies={'_xsrf': self._xsrf_token} if self._xsrf_token else {}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Failed to delete cell: {error_text}")

            result = await response.json()
            logger.info(f"Cell deleted successfully: {result}")
            return result

    async def get_notebook_state(self, notebook_path: str) -> Dict[str, Any]:
        """
        Get the current state of a notebook.

        Args:
            notebook_path: Path to the notebook

        Returns:
            Dict with notebook state information
        """
        await self._ensure_session()
        await self._ensure_xsrf_cookie()

        url = f"{self.base_url}/api/tools/notebook-state"
        data = {"path": notebook_path}

        async with self.session.post(
            url, json=data, headers=self._get_headers(xsrf=self._xsrf_token), cookies={'_xsrf': self._xsrf_token} if self._xsrf_token else {}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Failed to get notebook state: {error_text}")

            result = await response.json()
            return result

    async def get_sessions(self) -> Dict[str, Any]:
        """
        Get list of active notebook sessions.

        Returns:
            Dict with list of active sessions
        """
        await self._ensure_session()

        url = f"{self.base_url}/api/tools/sessions"

        async with self.session.get(url, headers=self._get_headers()) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Failed to get sessions: {error_text}")

            result = await response.json()
            return result

    async def insert_code_and_execute(
        self,
        notebook_path: str,
        code: str,
        cell_index: Union[int, str] = "append",
        cell_id: str = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Insert a code cell and execute it, updating outputs in real-time.

        This is the main tool - it inserts code, executes it,
        and ensures outputs are attached before returning.

        Args:
            notebook_path: Path to the notebook
            code: Code to insert and execute
            cell_index: Position to insert ('append' or integer)
            cell_id: Optional cell ID
            timeout: Execution timeout

        Returns:
            Dict with cell_id, outputs, and execution status
        """
        # Generate cell ID if not provided
        if cell_id is None:
            cell_id = str(uuid.uuid4())

        logger.info(f"Insert and execute: {notebook_path}, cell_id: {cell_id}")

        try:
            # Step 1: Insert the cell
            insert_result = await self.insert_cell(
                notebook_path=notebook_path,
                content=code,
                cell_type="code",
                cell_index=cell_index,
                cell_id=cell_id,
            )

            # Get the actual index from insert result
            actual_index = insert_result.get("index")

            # Step 2: Get kernel ID for this notebook
            sessions = await self.get_sessions()
            kernel_id = None
            for session in sessions.get("sessions", []):
                if session.get("path") == notebook_path:
                    kernel_id = session.get("kernel", {}).get("id")
                    break

            if not kernel_id:
                raise Exception(f"No kernel found for notebook: {notebook_path}")

            # Step 3: Execute the cell
            exec_result = await self.execute_cell(
                notebook_path=notebook_path,
                kernel_id=kernel_id,
                index=actual_index,
                stream=True,
            )

            return {
                "cell_id": cell_id,
                "index": actual_index,
                "execution_count": exec_result.get("execution_count"),
                "outputs_count": exec_result.get("outputs_count"),
                "status": "success",
                "message": "Cell inserted and executed successfully",
            }

        except Exception as e:
            logger.error(f"Error in insert_code_and_execute: {e}")
            return {"cell_id": cell_id, "status": "error", "message": str(e)}

    async def insert_markdown(
        self,
        notebook_path: str,
        markdown: str,
        cell_index: Union[int, str] = "append",
        cell_id: str = None,
    ) -> Dict[str, Any]:
        """
        Insert a markdown cell into the notebook.

        Args:
            notebook_path: Path to the notebook
            markdown: Markdown content
            cell_index: Position to insert ('append' or integer)
            cell_id: Optional cell ID

        Returns:
            Dict with insertion status
        """
        return await self.insert_cell(
            notebook_path=notebook_path,
            content=markdown,
            cell_type="markdown",
            cell_index=cell_index,
            cell_id=cell_id,
        )


# Example usage for testing
async def test_jupyter_tools():
    """Test the JupyterTools functionality."""

    async with JupyterTools(base_url="http://localhost:8890", token=None) as tools:
        # Test 1: Insert a markdown cell
        result = await tools.insert_markdown(
            notebook_path="test_tools.ipynb",
            markdown="# Test Tools\nThis is a test of the YDoc-based tools.",
            cell_index="append",
        )
        logger.info(f"Inserted markdown cell: {result}")

        # Test 2: Insert and execute code
        result = await tools.insert_code_and_execute(
            notebook_path="test_tools.ipynb",
            code="print('Hello from JupyterTools!')\nimport numpy as np\nnp.random.rand(3, 3)",
            cell_index="append",
        )
        logger.info(f"Executed code cell: {result}")


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_jupyter_tools())
