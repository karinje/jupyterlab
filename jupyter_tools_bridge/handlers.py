"""
Jupyter Tools Bridge - Handlers for real-time notebook manipulation via YDoc.

This module provides REST API handlers that allow tools to manipulate
Jupyter notebooks in real-time by directly modifying the live YNotebook
shared model. Changes appear instantly in the browser via JupyterLab's
Real-Time Collaboration (RTC) system.
"""

import json
import uuid
from typing import Optional, Dict, Any
import logging

from tornado.web import HTTPError
from jupyter_server.base.handlers import APIHandler
from jupyter_ydoc import YNotebook
from jupyter_client import KernelManager, BlockingKernelClient

# Use ServerApp logger so INFO messages show up
# logger = logging.getLogger(__name__)


class BaseToolsHandler(APIHandler):
    """Base handler with common functionality for tools operations."""

    @property
    def log(self):
        """Get the ServerApp logger."""
        return self.settings.get("serverapp").log if self.settings.get("serverapp") else logging.getLogger(__name__)

    @property
    def kernel_manager(self) -> KernelManager:
        """Get the kernel manager from the server."""
        return self.settings["kernel_manager"]

    def _ynb_attr(self, ynb: YNotebook, name: str) -> bool:
        has = hasattr(ynb, name)
        # logger.info(f"[ynb_attr] {name} present? {has}")
        return has

    def ynb_cell_count(self, ynb: YNotebook) -> int:
        """Return number of cells in a YNotebook robustly with logging."""
        try:
            # Prefer explicit API if available
            if self._ynb_attr(ynb, "ycells"):
                try:
                    n = len(ynb.ycells)  # YArray-like
                    # logger.info(f"[ynb_cell_count] via ycells -> {n}")
                    return n
                except Exception as e:
                    # logger.error(f"[ynb_cell_count] len(ycells) failed: {e}")
                    pass
            if self._ynb_attr(ynb, "cells"):
                try:
                    n = len(ynb.cells)
                    # logger.info(f"[ynb_cell_count] via cells -> {n}")
                    return n
                except Exception as e:
                    # logger.error(f"[ynb_cell_count] len(cells) failed: {e}")
                    pass
            # Fallback: probe with get_cell until it fails
            if self._ynb_attr(ynb, "get_cell"):
                i = 0
                while True:
                    try:
                        c = ynb.get_cell(i)
                        # logger.debug(
                        #     f"[ynb_cell_count] probe index {i} -> {'ok' if c is not None else 'none'}"
                        # )
                        if c is None:
                            break
                        i += 1
                    except Exception:
                        break
                # logger.info(f"[ynb_cell_count] via get_cell loop -> {i}")
                return i
        except Exception as e:
            # logger.error(f"[ynb_cell_count] error: {e}")
            pass
        # logger.info("[ynb_cell_count] default 0")
        return 0

    def iter_cells(self, ynb: YNotebook):
        """Yield (index, cell_dict) for all cells with verbose logging."""
        n = self.ynb_cell_count(ynb)
        # logger.info(f"[iter_cells] count={n}")
        for i in range(n):
            cell = None
            try:
                if self._ynb_attr(ynb, "get_cell"):
                    cell = ynb.get_cell(i)
                elif self._ynb_attr(ynb, "cells"):
                    cell = ynb.cells[i]
                elif self._ynb_attr(ynb, "ycells"):
                    # ycells might contain structured entries; try direct
                    cell = ynb.ycells[i]
                else:
                    # logger.error("[iter_cells] no way to access cells")
                    break
                # logger.debug(
                #     f"[iter_cells] i={i} type={type(cell)} keys={list(cell.keys()) if isinstance(cell, dict) else 'n/a'}"
                # )
            except Exception as e:
                # logger.error(f"[iter_cells] failed to read cell {i}: {e}")
                break
            yield i, cell

    async def get_live_notebook(self, path: str) -> Optional[YNotebook]:
        """
        Get the live YNotebook for a given path per backend-ydoc-agent-spec.md.

        Attempting to follow spec section 5.1, but with workarounds for
        the singleton pattern issues we're encountering.

        Args:
            path: The notebook path relative to the server root

        Returns:
            The live YNotebook instance or None if not found
        """
        try:
            self.log.info(f"[get_live_notebook] start path={path}")
            self.log.info(f"[get_live_notebook] settings keys={list(self.settings.keys())}")

            # Try order: settings['ydoc_extension'] -> settings['jupyter_server_ydoc'] -> extension_manager -> singleton
            ydoc_ext = None

            # 1) Stored by our extension loader
            ydoc_ext = self.settings.get("ydoc_extension")
            self.log.info(f"[get_live_notebook] ydoc_extension in settings? {'yes' if ydoc_ext else 'no'}")

            # 2) Directly provided by jupyter_server_ydoc in settings
            if not ydoc_ext:
                ydoc_ext = self.settings.get("jupyter_server_ydoc")
                self.log.info(f"[get_live_notebook] jupyter_server_ydoc in settings? {'yes' if ydoc_ext else 'no'}")

            # 3) Extension manager (metadata objects only, but log for visibility)
            if not ydoc_ext:
                serverapp = self.settings.get("serverapp")
                self.log.info(f"[get_live_notebook] serverapp present? {'yes' if serverapp else 'no'}")
                if serverapp and hasattr(serverapp, "extension_manager"):
                    ext_manager = serverapp.extension_manager
                    names = list(getattr(ext_manager, "extensions", {}).keys())
                    self.log.info(f"[get_live_notebook] extension_manager extensions={names}")
                    # NOTE: These are ExtensionPackage instances, not live extension; do not use directly

            # 4) Last resort: singleton
            if not ydoc_ext:
                try:
                    from jupyter_server_ydoc import YDocExtension

                    ydoc_ext = YDocExtension.instance()
                    self.log.info(f"[get_live_notebook] YDocExtension.instance() -> {'ok' if ydoc_ext else 'none'}")
                except Exception as e:
                    self.log.error(f"[get_live_notebook] YDocExtension.instance() failed: {e}")

            if not ydoc_ext:
                self.log.error("[get_live_notebook] Could not obtain YDocExtension by any method")
                return None

            has_get_doc = hasattr(ydoc_ext, "get_document")
            self.log.info(f"[get_live_notebook] ydoc_ext type={type(ydoc_ext)}, has get_document? {has_get_doc}")
            if not has_get_doc:
                self.log.error("[get_live_notebook] YDocExtension object has no get_document - cannot proceed")
                return None

            self.log.info(f"[get_live_notebook] calling get_document(path={path}, copy=False)")
            ydoc = await ydoc_ext.get_document(
                path=path, content_type="notebook", file_format="json", copy=False
            )
            self.log.info(f"[get_live_notebook] get_document returned type={type(ydoc) if ydoc else None}")

            if ydoc is None:
                self.log.error(f"[get_live_notebook] get_document returned None (notebook likely not open): {path}")
                return None

            if not isinstance(ydoc, YNotebook):
                self.log.error(f"[get_live_notebook] object is not YNotebook: {type(ydoc)}")
                return None

            self.log.info(f"[get_live_notebook] SUCCESS live YNotebook for {path}")
            return ydoc

        except Exception as e:
            self.log.error(f"[get_live_notebook] Failed: {e}", exc_info=True)
            return None

    def get_kernel_client(self, kernel_id: str) -> Optional[BlockingKernelClient]:
        """
        Get a kernel client for the given kernel ID.

        Args:
            kernel_id: The kernel ID

        Returns:
            A BlockingKernelClient or None if kernel not found
        """
        try:
            if kernel_id not in self.kernel_manager:
                return None

            kernel = self.kernel_manager.get_kernel(kernel_id)
            client = kernel.client()
            client.start_channels()
            return client

        except Exception as e:
            # logger.error(f"Failed to get kernel client for {kernel_id}: {e}")
            return None

    def generate_cell_id(self) -> str:
        """Generate a unique cell ID."""
        return str(uuid.uuid4())

    def map_to_nbformat_output(
        self, msg_type: str, content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Map kernel IOPub messages to nbformat output format.

        Args:
            msg_type: The message type from IOPub
            content: The message content

        Returns:
            An nbformat-compatible output dictionary
        """
        if msg_type == "stream":
            return {
                "output_type": "stream",
                "name": content.get("name", "stdout"),
                "text": content.get("text", ""),
            }

        elif msg_type == "display_data":
            return {
                "output_type": "display_data",
                "data": content.get("data", {}),
                "metadata": content.get("metadata", {}),
            }

        elif msg_type == "execute_result":
            return {
                "output_type": "execute_result",
                "execution_count": content.get("execution_count"),
                "data": content.get("data", {}),
                "metadata": content.get("metadata", {}),
            }

        elif msg_type == "error":
            return {
                "output_type": "error",
                "ename": content.get("ename", ""),
                "evalue": content.get("evalue", ""),
                "traceback": content.get("traceback", []),
            }

        else:
            # logger.warning(f"Unknown message type: {msg_type}")
            return None


class InsertCellHandler(BaseToolsHandler):
    """Handler for inserting cells into a notebook."""

    async def post(self):
        """Insert a new cell into the notebook."""
        try:
            data = self.get_json_body()

            # Extract parameters
            path = data.get("path")
            index = data.get("index", "append")
            cell_type = data.get("cell_type", "code")
            source = data.get("source", "")
            cell_id = data.get("cell_id", self.generate_cell_id())
            metadata = data.get("metadata", {})

            if not path:
                raise HTTPError(400, "Missing required parameter: path")

            if cell_type not in ["code", "markdown", "raw"]:
                raise HTTPError(400, f"Invalid cell_type: {cell_type}")

            # Get the live notebook
            notebook = await self.get_live_notebook(path)
            if not notebook:
                raise HTTPError(404, f"Notebook not found or not open: {path}")

            # Create the cell as per spec
            cell = {
                "id": cell_id,
                "cell_type": cell_type,
                "source": source,
                "metadata": metadata if isinstance(metadata, dict) else {},
                "execution_state": "idle",
                "execution_count": None,
                "outputs": [] if cell_type == "code" else None,
                # nbformat expects attachments to be a mapping, not None
                "attachments": {},
            }

            # Insert the cell using YNotebook API
            if index == "append":
                pre_count = self.ynb_cell_count(notebook)
                notebook.append_cell(cell)
                actual_index = pre_count
            else:
                # Convert to integer index
                idx = int(index)
                if idx < 0:
                    count = self.ynb_cell_count(notebook)
                    idx = max(0, count + idx + 1)

                ycell = notebook.create_ycell(cell)
                notebook.set_ycell(idx, ycell)
                actual_index = idx

            # logger.info(f"Inserted {cell_type} cell at index {actual_index} in {path}")

            self.finish(
                json.dumps(
                    {"status": "success", "cell_id": cell_id, "index": actual_index}
                )
            )

        except HTTPError:
            raise
        except Exception as e:
            # logger.error(f"Error inserting cell: {e}", exc_info=True)
            raise HTTPError(500, str(e))


class UpdateCellHandler(BaseToolsHandler):
    """Handler for updating cell content."""

    async def post(self):
        """Update a cell's source or metadata."""
        try:
            data = self.get_json_body()

            # Extract parameters
            path = data.get("path")
            cell_id = data.get("cell_id")
            index = data.get("index")
            source = data.get("source")
            metadata = data.get("metadata")

            if not path:
                raise HTTPError(400, "Missing required parameter: path")

            if not cell_id and index is None:
                raise HTTPError(400, "Must provide either cell_id or index")

            # Get the live notebook
            notebook = await self.get_live_notebook(path)
            if not notebook:
                raise HTTPError(404, f"Notebook not found or not open: {path}")

            # Find the cell
            target_index = None
            if index is not None:
                target_index = int(index)
            elif cell_id:
                for i, cell in self.iter_cells(notebook):
                    if isinstance(cell, dict) and cell.get("id") == cell_id:
                        target_index = i
                        break

            count = self.ynb_cell_count(notebook)
            if target_index is None or target_index >= count:
                raise HTTPError(404, "Cell not found")

            # Update the cell
            cell = notebook.get_cell(target_index)

            if source is not None:
                cell["source"] = source

            if metadata is not None:
                cell["metadata"].update(metadata)

            notebook.set_cell(target_index, cell)

            # logger.info(f"Updated cell at index {target_index} in {path}")

            self.finish(json.dumps({"status": "success", "index": target_index}))

        except HTTPError:
            raise
        except Exception as e:
            # logger.error(f"Error updating cell: {e}", exc_info=True)
            raise HTTPError(500, str(e))


class DeleteCellHandler(BaseToolsHandler):
    """Handler for deleting cells from a notebook."""

    async def post(self):
        """Delete a cell from the notebook."""
        try:
            data = self.get_json_body()

            # Extract parameters
            path = data.get("path")
            cell_id = data.get("cell_id")
            index = data.get("index")

            if not path:
                raise HTTPError(400, "Missing required parameter: path")

            # Get the live notebook
            notebook = await self.get_live_notebook(path)
            if not notebook:
                raise HTTPError(404, f"Notebook not found or not open: {path}")

            count = self.ynb_cell_count(notebook)
            if count == 0:
                raise HTTPError(404, "Notebook has no cells")

            # Resolve target index
            target_index = None
            if isinstance(index, str) and index.lower() == "last":
                target_index = count - 1
            elif index is not None:
                idx = int(index)
                target_index = max(0, count + idx) if idx < 0 else idx
            elif cell_id:
                for i, cell in self.iter_cells(notebook):
                    if isinstance(cell, dict) and cell.get("id") == cell_id:
                        target_index = i
                        break
            else:
                # Default: delete the last cell
                target_index = count - 1

            if target_index is None or target_index < 0 or target_index >= count:
                raise HTTPError(404, "Cell not found")

            # Delete the cell
            before = self.ynb_cell_count(notebook)
            notebook.ycells.pop(target_index)
            after = self.ynb_cell_count(notebook)
            # logger.info(
            #     f"Deleted cell at index {target_index} from {path} (count {before} -> {after})"
            # )

            self.finish(
                json.dumps(
                    {
                        "status": "success",
                        "deleted_index": target_index,
                        "cells_remaining": self.ynb_cell_count(notebook),
                    }
                )
            )

        except HTTPError:
            raise
        except Exception as e:
            # logger.error(f"Error deleting cell: {e}", exc_info=True)
            raise HTTPError(500, str(e))


class ExecuteCellHandler(BaseToolsHandler):
    """Handler for executing cells and updating outputs in real-time."""

    async def post(self):
        """Execute a cell and stream outputs back to it."""
        try:
            data = self.get_json_body()

            # Extract parameters
            path = data.get("path")
            cell_id = data.get("cell_id")
            index = data.get("index")
            kernel_id = data.get("kernel_id")
            stream_outputs = data.get("stream", True)

            if not path:
                raise HTTPError(400, "Missing required parameter: path")

            if not kernel_id:
                raise HTTPError(400, "Missing required parameter: kernel_id")

            if not cell_id and index is None:
                raise HTTPError(400, "Must provide either cell_id or index")

            # Get the live notebook
            notebook = await self.get_live_notebook(path)
            if not notebook:
                raise HTTPError(404, f"Notebook not found or not open: {path}")

            # Find the cell
            target_index = None
            if index is not None:
                target_index = int(index)
            elif cell_id:
                for i, cell in self.iter_cells(notebook):
                    if isinstance(cell, dict) and cell.get("id") == cell_id:
                        target_index = i
                        break

            count = self.ynb_cell_count(notebook)
            if target_index is None or target_index >= count:
                raise HTTPError(404, "Cell not found")

            # Get the cell and verify it's a code cell
            cell = notebook.get_cell(target_index)
            if cell.get("cell_type") != "code":
                raise HTTPError(400, "Can only execute code cells")

            # Get kernel client (already starts channels)
            client = self.get_kernel_client(kernel_id)
            if not client:
                raise HTTPError(404, f"Kernel not found: {kernel_id}")

            try:
                # Clear existing outputs
                cell["outputs"] = []
                cell["execution_count"] = None
                notebook.set_cell(target_index, cell)

                # Execute the code
                code = cell.get("source", "")
                # logger.info(f"[execute] sending execute_request, len(code)={len(code)}")
                msg_id = client.execute(
                    code, store_history=True, allow_stdin=False, stop_on_error=False
                )
                if hasattr(msg_id, "__await__"):
                    msg_id = await msg_id
                # logger.info(f"[execute] got msg_id={msg_id}")

                outputs = []
                execution_count = None

                # Process IOPub messages
                while True:
                    try:
                        raw = client.get_iopub_msg(timeout=30)
                        msg = await raw if hasattr(raw, "__await__") else raw

                        if not isinstance(msg, dict):
                            # logger.warning(
                            #     f"[execute] unexpected msg type: {type(msg)}"
                            # )
                            continue

                        if msg.get("parent_header", {}).get("msg_id") != msg_id:
                            continue

                        msg_type = msg.get("header", {}).get("msg_type")
                        content = msg.get("content", {})

                        # Always capture execution_count from execute_input at start of execution
                        if msg_type == "execute_input":
                            ec = content.get("execution_count")
                            # logger.info(f"[execute] execute_input exec_count={ec}")
                            if ec is not None:
                                execution_count = ec
                                if stream_outputs:
                                    if cell.get("execution_count") != ec:
                                        cell["execution_count"] = ec
                                        notebook.set_cell(target_index, cell)
                            continue

                        if msg_type in [
                            "stream",
                            "display_data",
                            "execute_result",
                            "error",
                        ]:
                            output = self.map_to_nbformat_output(msg_type, content)
                            if output:
                                outputs.append(output)
                                if msg_type == "execute_result":
                                    execution_count = content.get("execution_count")
                                if stream_outputs:
                                    cell["outputs"] = outputs
                                    if execution_count is not None:
                                        cell["execution_count"] = execution_count
                                    notebook.set_cell(target_index, cell)
                        elif (
                            msg_type == "status"
                            and content.get("execution_state") == "idle"
                        ):
                            break
                    except TimeoutError:
                        # logger.warning("Timeout waiting for kernel response")
                        break
                    except Exception as e:
                        # logger.error(
                        #     f"[execute] error reading IOPub: {e}", exc_info=True
                        # )
                        break

                # Final update with all outputs
                if not stream_outputs:
                    cell["outputs"] = outputs
                    if execution_count is not None:
                        cell["execution_count"] = execution_count
                    notebook.set_cell(target_index, cell)

                # logger.info(f"Executed cell at index {target_index} in {path}")

                self.finish(
                    json.dumps(
                        {
                            "status": "success",
                            "index": target_index,
                            "execution_count": execution_count,
                            "outputs_count": len(outputs),
                        }
                    )
                )

            finally:
                # Clean up kernel client
                try:
                    if hasattr(client, "stop_channels"):
                        stopped = client.stop_channels()
                        if hasattr(stopped, "__await__"):
                            await stopped
                except Exception as e:
                    # logger.warning(f"stop_channels failed: {e}")
                    pass

        except HTTPError:
            raise
        except Exception as e:
            # logger.error(f"Error executing cell: {e}", exc_info=True)
            raise HTTPError(500, str(e))


class GetNotebookStateHandler(BaseToolsHandler):
    """Handler for getting current notebook state."""

    async def post(self):
        """Get a snapshot of the current notebook state."""
        try:
            data = self.get_json_body()
            path = data.get("path")

            if not path:
                raise HTTPError(400, "Missing required parameter: path")

            # Get the live notebook
            notebook = await self.get_live_notebook(path)
            if not notebook:
                raise HTTPError(404, f"Notebook not found or not open: {path}")

            # Build state summary
            cells_summary = []
            try:
                for i, cell in self.iter_cells(notebook):
                    if not isinstance(cell, dict):
                        # logger.info(f"[state] non-dict cell at {i}: {type(cell)}")
                        continue
                    cell_info = {
                        "index": i,
                        "id": cell.get("id"),
                        "type": cell.get("cell_type"),
                        "source_length": len(cell.get("source", "")),
                        "source_preview": cell.get("source", "")[:100] + "..."
                        if len(cell.get("source", "")) > 100
                        else cell.get("source", ""),
                    }
                    if cell.get("cell_type") == "code":
                        cell_info["execution_count"] = cell.get("execution_count")
                        cell_info["outputs_count"] = len(cell.get("outputs", []))
                    cells_summary.append(cell_info)
            except Exception as e:
                # logger.error(f"[state] failed to iterate cells: {e}")
                pass

            self.finish(
                json.dumps(
                    {
                        "status": "success",
                        "path": path,
                        "cells_count": len(cells_summary),
                        "cells": cells_summary,
                    }
                )
            )

        except HTTPError:
            raise
        except Exception as e:
            # logger.error(f"Error getting notebook state: {e}", exc_info=True)
            raise HTTPError(500, str(e))


class GetActiveSessionsHandler(BaseToolsHandler):
    """Handler for getting active notebook sessions."""

    async def get(self):
        """Get list of active notebook sessions with kernel info."""
        try:
            sessions = []

            # Get session manager from server
            session_manager = self.settings.get("session_manager")
            if session_manager:
                session_list = await session_manager.list_sessions()
                for session in session_list:
                    sessions.append(
                        {
                            "id": session["id"],
                            "path": session.get("path"),
                            "name": session.get("name"),
                            "type": session.get("type"),
                            "kernel": {
                                "id": session.get("kernel", {}).get("id"),
                                "name": session.get("kernel", {}).get("name"),
                            },
                        }
                    )

            self.finish(json.dumps({"status": "success", "sessions": sessions}))

        except Exception as e:
            # logger.error(f"Error getting sessions: {e}", exc_info=True)
            raise HTTPError(500, str(e))


class SaveNotebookHandler(BaseToolsHandler):
    """Handler to force-save the current live YNotebook to disk."""

    async def post(self):
        try:
            data = self.get_json_body()
            path = data.get("path")
            if not path:
                raise HTTPError(400, "Missing required parameter: path")

            # Get live notebook
            notebook = await self.get_live_notebook(path)
            if not notebook:
                raise HTTPError(404, f"Notebook not found or not open: {path}")

            # Build nbformat content from live YNotebook with sanitization
            cells = []
            for _, cell in self.iter_cells(notebook):
                if not isinstance(cell, dict):
                    continue
                c = dict(cell)
                # Ensure required fields are properly typed
                if not isinstance(c.get("metadata"), dict):
                    c["metadata"] = {}
                ct = c.get("cell_type")
                if ct == "code":
                    if not isinstance(c.get("outputs"), list):
                        c["outputs"] = []
                    # execution_count can be int or None; leave as-is
                else:
                    # Non-code cells should not carry outputs
                    if "outputs" in c and c["outputs"] is None:
                        del c["outputs"]
                # attachments: ensure dict
                if c.get("attachments") is None:
                    c["attachments"] = {}
                # id: ensure present (nbformat 4.5+)
                if not c.get("id"):
                    c["id"] = str(uuid.uuid4())
                cells.append(c)

            nb_metadata = {}
            if isinstance(getattr(notebook, "metadata", None), dict):
                nb_metadata = notebook.metadata

            nb = {
                "cells": cells,
                "metadata": nb_metadata if isinstance(nb_metadata, dict) else {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }

            contents_manager = self.settings.get("contents_manager")
            if not contents_manager:
                raise HTTPError(500, "Contents manager not available")

            model = {"type": "notebook", "format": "json", "content": nb}

            # logger.info(f"[save] saving notebook: {path} (cells={len(cells)})")
            await contents_manager.save(model, path)
            # logger.info(f"[save] saved notebook: {path}")

            self.finish(
                json.dumps(
                    {
                        "status": "success",
                        "saved": True,
                        "path": path,
                        "cells": len(cells),
                    }
                )
            )
        except HTTPError:
            raise
        except Exception as e:
            # logger.error(f"Error saving notebook: {e}", exc_info=True)
            raise HTTPError(500, str(e))


# URL handlers mapping
url_handlers = [
    (r"/api/tools/insert-cell", InsertCellHandler),
    (r"/api/tools/update-cell", UpdateCellHandler),
    (r"/api/tools/delete-cell", DeleteCellHandler),
    (r"/api/tools/execute-cell", ExecuteCellHandler),
    (r"/api/tools/notebook-state", GetNotebookStateHandler),
    (r"/api/tools/sessions", GetActiveSessionsHandler),
    (r"/api/tools/save", SaveNotebookHandler),
]
