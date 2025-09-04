"""RoomProxy – minimal helper to talk to JupyterLab collaboration REST/WS API.

This helper is **internal** to the server extension.  External clients/agents should keep
using the higher level REST routes we will expose from handlers.
"""

from __future__ import annotations

import aiohttp
import asyncio
import os
from typing import Optional
from pycrdt import create_update_message, create_sync_message, Doc

# Old hardcoded logic - remove
# BASE_URL = os.getenv("JUPYTER_BASE_URL", "http://127.0.0.1:8888")
# TOKEN = os.getenv("JUPYTER_TOKEN", "")


class RoomProxy:
    """Join a collaboration session for a given notebook path.

    Usage::
        async with RoomProxy("path/to/notebook.ipynb", "http://127.0.0.1:8888") as room:
            await room.apply_yupdate(y_update_bytes)
    """

    def __init__(
        self,
        path: str,
        server_url: str,
        token: Optional[str] = None,
        xsrf_token: Optional[str] = None,
    ):
        self.path = path.lstrip("/")
        self.server_url = server_url.rstrip("/")
        self.token = token or os.getenv(
            "JUPYTER_TOKEN", ""
        )  # keep token fallback for now
        # Ensure XSRF token is string, not bytes
        if xsrf_token is not None:
            if isinstance(xsrf_token, bytes):
                self.xsrf_token = xsrf_token.decode("utf-8")
            else:
                self.xsrf_token = str(xsrf_token)
        else:
            self.xsrf_token = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.room_id: Optional[str] = None
        # local empty Y document for sync handshake
        self._doc: Doc = Doc()

    # ---------------------------------------------------------------------
    # Async context management
    # ---------------------------------------------------------------------
    async def __aenter__(self):
        # Ensure token is string, not bytes
        token_str = str(self.token) if self.token else ""
        headers = {"Authorization": f"token {token_str}"} if token_str else {}
        self._session = aiohttp.ClientSession(headers=headers)

        # Get XSRF token by making a GET request first to establish session
        if not self.xsrf_token:
            get_url = f"{self.server_url}/lab?token={token_str}"
            async with self._session.get(get_url) as resp:
                if resp.status in (
                    200,
                    405,
                ):  # 405 is Method Not Allowed but still sets cookies
                    # Extract XSRF token from cookies
                    for cookie_name, cookie in resp.cookies.items():
                        if cookie_name == "_xsrf":
                            cookie_value = cookie.value
                            # Ensure XSRF token is string, not bytes
                            if isinstance(cookie_value, bytes):
                                self.xsrf_token = cookie_value.decode("utf-8")
                            else:
                                self.xsrf_token = str(cookie_value)
                            break

        # 1. Join (or create) collaboration session for notebook path –
        #    this endpoint expects a PUT with JSON body {format, type}.
        join_url = f"{self.server_url}/api/collaboration/session/{self.path}"
        body = {"format": "json", "type": "notebook"}

        # Prepare headers with XSRF token if available
        request_headers = {}
        if self.xsrf_token:
            # Ensure XSRF token is string before adding to headers
            xsrf_str = str(self.xsrf_token)
            request_headers["X-CSRFToken"] = xsrf_str
            # Also add to body as some APIs expect it there
            body["_xsrf"] = xsrf_str

        # Debug logging to check for bytes objects
        print(f"RoomProxy DEBUG - Join URL: {join_url}")
        print(f"RoomProxy DEBUG - Request headers: {request_headers}")
        print(f"RoomProxy DEBUG - Body: {body}")

        # Validate all values are strings/JSON serializable
        import json

        try:
            json.dumps(body)
            print("RoomProxy DEBUG - Body is JSON serializable")
        except Exception as e:
            print(f"RoomProxy DEBUG - Body serialization failed: {e}")

        for key, value in request_headers.items():
            if isinstance(value, bytes):
                print(f"RoomProxy DEBUG - Header {key} is bytes: {value}")
            else:
                print(f"RoomProxy DEBUG - Header {key} is {type(value)}: {value}")

        async with self._session.put(
            join_url, json=body, headers=request_headers
        ) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(
                    f"Failed to join session – {resp.status}: {await resp.text()}"
                )
            data = await resp.json()

        # Response: {format, type, fileId, sessionId}
        fmt = data["format"]
        ftype = data["type"]
        file_id = data["fileId"]
        session_id = data["sessionId"]

        self.room_id = f"{fmt}:{ftype}:{file_id}"

        # 2. Open WebSocket connection for Y updates
        ws_base = self.server_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        ws_url = (
            f"{ws_base}/api/collaboration/room/{self.room_id}?sessionId={session_id}"
        )
        self._ws = await self._session.ws_connect(ws_url)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    async def apply_yupdate(self, update: bytes):
        """Send a binary Y-update over the collaboration websocket."""
        if self._ws is None:
            raise RuntimeError(
                "RoomProxy has no active websocket – use within 'async with'."
            )

        # 0. Send SYNC_STEP1; wait for SYNC_STEP2 reply so we know the peer is ready
        await self._ws.send_bytes(create_sync_message(self._doc))

        try:
            # Server should reply with message starting with YMessageType.SYNC (0)
            while True:
                first = await asyncio.wait_for(self._ws.receive(), timeout=5)
                # Extract bytes data from WebSocket message
                if first.type == aiohttp.WSMsgType.BINARY and first.data:
                    data = first.data
                    if isinstance(data, (bytes, bytearray)) and len(data) > 0:
                        print("RoomProxy DBG recv first-byte:", data[0])
                        # Check if message starts with YMessageType.SYNC (0) or AWARENESS (1)
                        if data[0] in (0, 1):
                            break
        except asyncio.TimeoutError:
            # No sync/awareness reply within 5 s – continue anyway
            pass

        # 1. Send the actual update payload
        message = create_update_message(update)
        await self._ws.send_bytes(message)

        # keep the connection briefly so the server can relay to other peers
        try:
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass

    async def recv(self, timeout: float | None = None):
        """Receive next message from the websocket (mainly for debugging)."""
        if self._ws is None:
            raise RuntimeError("RoomProxy has no active websocket.")
        return await asyncio.wait_for(self._ws.receive(), timeout=timeout)
