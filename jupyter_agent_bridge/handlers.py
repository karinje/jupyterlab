"""REST handlers that will wrap Collaboration API – WIP placeholder."""

import uuid
import json
from tornado import web
from jupyter_server.base.handlers import APIHandler
from pycrdt import Doc, Map, Array, Text


class NotImplementedHandler(APIHandler):
    async def get(self):
        self.set_status(501)
        self.finish({"error": "Not implemented"})

    post = get


def build_insert_cell_update(index: int = 0, cell_type: str = "code", source: str = ""):
    """Build a Y-update for inserting a new cell."""
    ydoc = Doc()
    cells = ydoc["cells"] = Array()

    cell_map = {
        "id": str(uuid.uuid4()),
        "cell_type": cell_type,
        "source": Text(source),
        "metadata": Map({}),
    }
    if cell_type == "code":
        cell_map.update(
            {
                "execution_count": None,
                "outputs": Array(),
            }
        )

    cell = Map(cell_map)

    with ydoc.transaction():
        cells.insert(index, cell)

    return ydoc.get_update()


class UpdateCellOutputsHandler(APIHandler):
    @web.authenticated
    async def post(self):
        try:
            data = self.get_json_body()
            path = data["path"]
            cell_index = data["cell_index"]
            outputs = data["outputs"]
            execution_count = data.get("execution_count")

            self.log.info(f"Updating outputs for cell at index {cell_index} in {path}")

            # Get the cell ID from the notebook
            import aiohttp

            # Extract token from request or use server token
            req_token = self.get_argument("token", default=None)
            if not req_token:
                # Check Authorization header
                auth_header = self.request.headers.get("Authorization", "")
                if auth_header.lower().startswith("token "):
                    req_token = auth_header.split()[1]

            # If still missing, use the server's token
            if not req_token:
                req_token = getattr(self.serverapp.identity_provider, "token", "")

            headers = {
                "Authorization": f"token {req_token}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                # Get the notebook to find the cell ID
                server_url = f"http://127.0.0.1:{self.serverapp.port}"
                async with session.get(
                    f"{server_url}/api/contents/{path}", headers=headers
                ) as resp:
                    if resp.status != 200:
                        raise Exception(f"Failed to get notebook: {resp.status}")

                    notebook_data = await resp.json()
                    cells = notebook_data["content"]["cells"]

                    if cell_index >= len(cells):
                        raise Exception(f"Cell index {cell_index} out of range")

                    # Update the cell directly in the notebook content
                    target_cell = cells[cell_index]
                    target_cell["outputs"] = outputs
                    if execution_count is not None:
                        target_cell["execution_count"] = execution_count

                    # Save the notebook back
                    save_data = {
                        "type": "notebook",
                        "content": notebook_data["content"],
                    }

                    async with session.put(
                        f"{server_url}/api/contents/{path}",
                        headers=headers,
                        json=save_data,
                    ) as save_resp:
                        if save_resp.status != 200:
                            error_text = await save_resp.text()
                            raise Exception(
                                f"Failed to save notebook: {save_resp.status} - {error_text}"
                            )


            self.finish({"success": True, "message": "Outputs updated"})

        except Exception as e:
            self.log.error(f"Error in UpdateCellOutputsHandler: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class InsertCellHandler(APIHandler):
    """POST /api/agent/notebook/insert – insert a new cell via RoomProxy, optionally execute it"""

    async def post(self):
        body = self.get_json_body()
        required = {"path", "source"}
        missing = required - body.keys()
        if missing:
            raise web.HTTPError(400, reason=f"Missing fields: {', '.join(missing)}")

        path: str = body["path"]
        index: int = int(body.get("index", 0))
        cell_type: str = str(body.get("cell_type", "code"))
        source: str = str(body["source"])
        execute: bool = bool(body.get("execute", False))

        # Build Y-update
        update_bytes = build_insert_cell_update(
            index=index, cell_type=cell_type, source=source
        )

        # Apply via RoomProxy
        from .room_proxy import RoomProxy

        try:
            # Dynamically determine server_url to avoid hardcoded ports.
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            xsrf_token = self.xsrf_token
            if xsrf_token is not None:
                if isinstance(xsrf_token, bytes):
                    xsrf_token = xsrf_token.decode("utf-8")
                else:
                    xsrf_token = str(xsrf_token)

            # Extract Jupyter server authentication token. Prefer explicit token in
            # request (e.g. because client called the handler with ?token=...),
            # otherwise fall back to the server's own token so that the internal
            # RoomProxy calls are always authenticated.
            req_token = self.get_argument("token", default=None)
            if not req_token:
                # Tornado converts headers to lower-case keys
                auth_header = self.request.headers.get("Authorization", "")
                if auth_header.lower().startswith("token "):
                    req_token = auth_header.split()[1]

            # If still missing, use the server's token so that we can authenticate
            # internal requests even when the outer request was already trusted via
            # cookies.
            if not req_token:
                # identity_provider is always present in Jupyter Server >=2
                req_token = getattr(self.serverapp.identity_provider, "token", "")

            async with RoomProxy(
                path=path, server_url=server_url, token=req_token, xsrf_token=xsrf_token
            ) as room:
                await room.apply_yupdate(update_bytes)

            result = {"status": "ok", "cell_inserted": True}

            # Execute the cell if requested
            if execute and cell_type == "code":
                try:
                    execution_result = await self._execute_cell(path, source, req_token)
                    result["execution"] = execution_result
                except Exception as exec_error:
                    self.log.error(f"Cell execution failed: {exec_error}")
                    result["execution"] = {"status": "error", "error": str(exec_error)}

            self.finish(result)

        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            self.log.error(f"Error applying update: {exc}")
            self.log.error(f"Traceback: {tb}")
            # Return more detailed error info for debugging
            raise web.HTTPError(500, reason=f"Failed to apply update: {str(exc)[:200]}")

    async def _execute_cell(self, path: str, source: str, token: str):
        """Execute code using Jupyter's kernel WebSocket API"""
        import asyncio
        import uuid
        import websockets
        from urllib.parse import urlparse

        # Find the kernel for this notebook
        kernel_id = await self._get_kernel_for_notebook(path, token)
        if not kernel_id:
            raise Exception("No kernel found for notebook")

        # Build WebSocket URL
        server_url = f"http://127.0.0.1:{self.serverapp.port}"
        parsed = urlparse(server_url)
        ws_url = f"ws://{parsed.netloc}/api/kernels/{kernel_id}/channels?token={token}"

        try:
            async with websockets.connect(ws_url) as websocket:
                # Create execution request message
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
                        "code": source,
                        "silent": False,
                        "store_history": True,
                        "user_expressions": {},
                        "allow_stdin": False,
                        "stop_on_error": True,
                    },
                    "buffers": [],
                    "channel": "shell",
                }

                # Send execution request
                await websocket.send(json.dumps(execute_msg))

                # Collect responses
                outputs = []
                execution_count = None
                timeout_count = 0
                max_timeout = 100  # 10 seconds

                while timeout_count < max_timeout:
                    try:
                        # Wait for message with timeout
                        message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        msg_data = json.loads(message)

                        msg_type = msg_data.get("header", {}).get("msg_type")
                        parent_msg_id = msg_data.get("parent_header", {}).get("msg_id")

                        # Only process messages related to our execution
                        if parent_msg_id == msg_id:
                            if msg_type == "execute_reply":
                                execution_count = msg_data.get("content", {}).get(
                                    "execution_count"
                                )
                                status = msg_data.get("content", {}).get("status")
                                if status == "ok":
                                    break
                                elif status == "error":
                                    error_info = msg_data.get("content", {})
                                    outputs.append(
                                        {
                                            "output_type": "error",
                                            "ename": error_info.get("ename", "Unknown"),
                                            "evalue": error_info.get("evalue", ""),
                                            "traceback": error_info.get(
                                                "traceback", []
                                            ),
                                        }
                                    )
                                    break

                            elif msg_type == "stream":
                                output_text = msg_data.get("content", {}).get(
                                    "text", ""
                                )
                                outputs.append(
                                    {
                                        "output_type": "stream",
                                        "name": msg_data.get("content", {}).get(
                                            "name", "stdout"
                                        ),
                                        "text": output_text,
                                    }
                                )

                            elif msg_type == "execute_result":
                                data = msg_data.get("content", {}).get("data", {})
                                outputs.append(
                                    {
                                        "output_type": "execute_result",
                                        "data": data,
                                        "execution_count": msg_data.get(
                                            "content", {}
                                        ).get("execution_count"),
                                    }
                                )

                            elif msg_type == "display_data":
                                data = msg_data.get("content", {}).get("data", {})
                                outputs.append(
                                    {
                                        "output_type": "display_data",
                                        "data": data,
                                        "metadata": msg_data.get("content", {}).get(
                                            "metadata", {}
                                        ),
                                    }
                                )

                    except asyncio.TimeoutError:
                        timeout_count += 1
                        continue

                return {
                    "status": "ok",
                    "execution_count": execution_count,
                    "outputs": outputs,
                    "msg_id": msg_id,
                }

        except Exception as e:
            return {"status": "error", "error": str(e), "outputs": []}

    async def _get_kernel_for_notebook(self, path: str, token: str):
        """Find the kernel ID for a given notebook"""
        import aiohttp

        server_url = f"http://127.0.0.1:{self.serverapp.port}"
        headers = {"Authorization": f"token {token}"}

        async with aiohttp.ClientSession(headers=headers) as session:
            # Get all active kernels
            async with session.get(f"{server_url}/api/kernels") as resp:
                if resp.status != 200:
                    return None
                kernels = await resp.json()

            # Get all active sessions to match notebook path to kernel
            async with session.get(f"{server_url}/api/sessions") as resp:
                if resp.status != 200:
                    return None
                sessions = await resp.json()

            # Find session for our notebook
            for session in sessions:
                if session.get("path") == path:
                    return session.get("kernel", {}).get("id")

            # If no session found, return the first available kernel
            if kernels:
                return kernels[0]["id"]

        return None


def setup_handlers(server_app):
    base_url = server_app.web_app.settings["base_url"]
    host_pattern = r".*$"
    routes = [
        (f"{base_url}api/agent/notebook/insert", InsertCellHandler),
        (f"{base_url}api/agent/notebook/update_outputs", UpdateCellOutputsHandler),
        (f"{base_url}api/agent/notebook/.*", NotImplementedHandler),
    ]
    server_app.web_app.add_handlers(host_pattern, routes)
