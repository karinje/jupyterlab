import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Dict, Optional, Set, DefaultDict

from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.application import ExtensionApp
import tornado.web
import tornado.websocket
from collections import defaultdict

# Import our JupyterAgent tools
from jupyter_tools_bridge.tools import JupyterTools

# Set up logger first
logger = logging.getLogger(__name__)

# Module-level debug to confirm our code is loaded
logger.info("🔥🔥🔥 JUPYTERLAB CHAT MODULE IMPORTED - NEW VERSION! 🔥🔥🔥")
print("[chat-backend] module import: JUPYTERLAB CHAT MODULE IMPORTED - NEW VERSION!")

class ChatBroadcaster:
    """Simple in-process broadcaster keyed by notebook_path."""

    def __init__(self):
        self._subscribers: DefaultDict[str, Set[tornado.websocket.WebSocketHandler]] = defaultdict(set)
        # Recent assistant messages to deduplicate bursts (notebook_path, content) -> last_ms
        self._recent_messages: Dict[tuple, float] = {}

    def subscribe(self, notebook_path: str, ws: tornado.websocket.WebSocketHandler) -> None:
        key = notebook_path or "*"
        self._subscribers[key].add(ws)

    def unsubscribe(self, notebook_path: str, ws: tornado.websocket.WebSocketHandler) -> None:
        key = notebook_path or "*"
        bucket = self._subscribers.get(key)
        if bucket and ws in bucket:
            bucket.remove(ws)
        if bucket and not bucket:
            self._subscribers.pop(key, None)

    def broadcast(self, event: dict) -> None:
        try:
            import json as _json
            import time as _time

            notebook_path = event.get("notebook_path") or "*"
            etype = event.get("type") or "unknown"
            payload = _json.dumps(event)

            # Deduplicate assistant messages for 2 seconds window per notebook/content
            if etype == "message":
                try:
                    content = (event.get("payload") or {}).get("content", "")
                    key = (notebook_path, str(content))
                    now = _time.time() * 1000.0
                    last = self._recent_messages.get(key, 0)
                    if now - last < 2000:
                        print(f"[WS] dedup drop MESSAGE path={notebook_path}")
                        return
                    self._recent_messages[key] = now
                except Exception:
                    pass

            # Deliver to targeted subscribers if a concrete notebook_path is provided;
            # only deliver to global ('*') subscribers when notebook_path is '*'. Never both.
            if notebook_path and notebook_path != "*":
                targets = list(self._subscribers.get(notebook_path, set()))
            else:
                targets = list(self._subscribers.get("*", set()))

            try:
                logger.info(
                    f"WS broadcast type={etype} notebook_path={notebook_path} recipients={len(targets)}"
                )
                print(
                    f"[WS] broadcast type={etype} recipients={len(targets)} path={notebook_path}"
                )
            except Exception:
                pass

            for ws in list(targets):
                try:
                    if not ws.ws_connection or ws.ws_connection.is_closing():
                        # prune silently
                        for key, bucket in list(self._subscribers.items()):
                            if ws in bucket:
                                bucket.discard(ws)
                                if not bucket:
                                    self._subscribers.pop(key, None)
                        continue
                    ws.write_message(payload)
                except Exception as _e:
                    logger.debug(f"WS send failed; pruning: {_e}")
                    for key, bucket in list(self._subscribers.items()):
                        if ws in bucket:
                            bucket.discard(ws)
                            if not bucket:
                                self._subscribers.pop(key, None)
        except Exception as e:
            logger.warning(f"Broadcast error: {e}")


# Module-level broadcaster
chat_broadcaster = ChatBroadcaster()


class ChatStreamHandler(tornado.websocket.WebSocketHandler):
    """WebSocket stream for live chat events."""

    def check_origin(self, origin: str) -> bool:
        try:
            from urllib.parse import urlparse

            if not origin:
                return False
            o = urlparse(origin)
            # Allow same host (http or https) and localhost
            host = self.request.host.split(":")[0]
            return o.hostname in {host, "127.0.0.1", "localhost"}
        except Exception:
            return False

    def _get_server_token(self) -> str:
        try:
            # Try to extract server_app from settings
            server_app = (
                self.settings.get("serverapp")
                or self.settings.get("server_app")
                or (getattr(self.application, "settings", {}) or {}).get("serverapp")
                or (getattr(self.application, "settings", {}) or {}).get("server_app")
            )
            token = None
            if server_app is not None:
                if hasattr(server_app, "identity_provider") and hasattr(
                    server_app.identity_provider, "token"
                ):
                    token = server_app.identity_provider.token
                if not token and hasattr(server_app, "token"):
                    token = server_app.token
            return token or ""
        except Exception:
            return ""

    def open(self):
        try:
            # Validate token if server has one
            token = self.get_query_argument("token", default=None)
            server_token = self._get_server_token()

            if server_token:
                if not token or token != server_token:
                    logger.warning("WS auth failed: invalid/missing token")
                    self.close(code=4003, reason="Forbidden")
                    return

            self._notebook_path = self.get_query_argument("notebook_path", default="*")
            self._thread_id = self.get_query_argument("thread_id", default=None)
            chat_broadcaster.subscribe(self._notebook_path, self)
            logger.info(f"WS open for notebook_path={self._notebook_path}")
        except Exception as e:
            logger.error(f"WS open error: {e}")
            self.close(code=1011, reason="Server error")

    def on_close(self):
        try:
            chat_broadcaster.unsubscribe(getattr(self, "_notebook_path", "*"), self)
        except Exception:
            pass

    def on_message(self, message):
        # Read-only stream; ignore incoming messages
        pass


# LangGraph agent is TypeScript-based, runs in frontend
# Backend just needs to signal that it should be used
LANGGRAPH_AVAILABLE = True  # Always available since it's frontend TypeScript
logger.info("🚀 LangGraph agent available (TypeScript frontend)")

# Cold-start flag: clear chat history in notebook metadata on first request after restart
BOOT_CLEAR_DONE = False

# Import function_tool decorator for OpenAI Agents SDK
try:
    from agents import function_tool
except ImportError:
    # Fallback if agents package not available
    def function_tool(func):
        return func


class ConversationManager:
    """Manages chat conversation threads in notebook metadata"""

    def __init__(self, serverapp):
        self.serverapp = serverapp
        self._xsrf_token = None

    async def load_conversation_history(self, notebook_path: str) -> Dict:
        """Load conversation threads from notebook metadata"""
        try:
            # Get notebook content via Contents API
            import aiohttp

            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            token = self._get_server_token()
            headers = {"Authorization": f"token {token}"}

            async with aiohttp.ClientSession() as session:
                # Ensure XSRF token for subsequent PUT
                try:
                    async with session.get(f"{server_url}/lab", headers=headers) as r:
                        xsrf = r.cookies.get("_xsrf")
                        if xsrf and xsrf.value:
                            self._xsrf_token = xsrf.value
                except Exception:
                    self._xsrf_token = None
                async with session.get(
                    f"{server_url}/api/contents/{notebook_path}", headers=headers
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"Failed to load notebook {notebook_path}: {resp.status}"
                        )
                        return self._create_empty_conversations()

                    notebook_data = await resp.json()
                    metadata = notebook_data.get("content", {}).get("metadata", {})
                    return metadata.get(
                        "chat_conversations", self._create_empty_conversations()
                    )

        except Exception as e:
            logger.error(f"Error loading conversation history: {e}")
            return self._create_empty_conversations()

    async def save_conversation_message(
        self, notebook_path: str, message: Dict, thread_id: Optional[str] = None
    ) -> str:
        """Save a message to conversation thread and return thread_id"""
        try:
            # Load current conversations
            conversations = await self.load_conversation_history(notebook_path)

            # Create new thread if needed
            if not thread_id:
                thread_id = str(uuid.uuid4())
                conversations["threads"][thread_id] = {
                    "created": datetime.utcnow().isoformat(),
                    "last_updated": datetime.utcnow().isoformat(),
                    "title": self._generate_thread_title(message.get("content", "")),
                    "messages": [],
                }
                conversations["active_thread"] = thread_id
                conversations["thread_order"].insert(0, thread_id)

            # Add message to thread
            if thread_id in conversations["threads"]:
                conversations["threads"][thread_id]["messages"].append(
                    {**message, "timestamp": datetime.utcnow().isoformat()}
                )
                conversations["threads"][thread_id]["last_updated"] = (
                    datetime.utcnow().isoformat()
                )
                conversations["active_thread"] = thread_id

                # Update thread order (move to front)
                if thread_id in conversations["thread_order"]:
                    conversations["thread_order"].remove(thread_id)
                conversations["thread_order"].insert(0, thread_id)

            # Save back to notebook
            await self._save_conversations_to_notebook(notebook_path, conversations)
            return thread_id

        except Exception as e:
            logger.error(f"Error saving conversation message: {e}")
            return thread_id or str(uuid.uuid4())

    def _create_empty_conversations(self) -> Dict:
        """Create empty conversation structure"""
        return {"threads": {}, "active_thread": None, "thread_order": []}

    def _generate_thread_title(self, first_message: str) -> str:
        """Generate thread title from first user message"""
        if not first_message:
            return f"Chat {datetime.utcnow().strftime('%H:%M')}"

        # Take first 50 chars, clean up
        title = first_message[:50].strip()
        if len(first_message) > 50:
            title += "..."
        return title

    def _get_server_token(self) -> Optional[str]:
        """Get server token for API calls"""
        if hasattr(self.serverapp, "identity_provider") and hasattr(
            self.serverapp.identity_provider, "token"
        ):
            return self.serverapp.identity_provider.token
        if hasattr(self.serverapp, "token"):
            return self.serverapp.token
        return None

    async def _save_conversations_to_notebook(
        self, notebook_path: str, conversations: Dict
    ):
        """Save conversations back to notebook metadata"""
        try:
            import aiohttp

            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            token = self._get_server_token()
            headers = {"Authorization": f"token {token}"}

            async with aiohttp.ClientSession() as session:
                # Get current notebook
                async with session.get(
                    f"{server_url}/api/contents/{notebook_path}", headers=headers
                ) as resp:
                    if resp.status != 200:
                        logger.error(
                            f"Failed to load notebook for saving: {resp.status}"
                        )
                        return

                    notebook_data = await resp.json()

                # Update metadata
                if "metadata" not in notebook_data["content"]:
                    notebook_data["content"]["metadata"] = {}
                notebook_data["content"]["metadata"]["chat_conversations"] = (
                    conversations
                )

                # Sanitize cells to avoid nbformat save errors (attachments None, outputs type)
                try:
                    cells = notebook_data["content"].get("cells", [])
                    for c in cells:
                        if not isinstance(c.get("metadata"), dict):
                            c["metadata"] = {}
                        if c.get("attachments") is None:
                            c["attachments"] = {}
                        ct = c.get("cell_type")
                        if ct == "code":
                            if not isinstance(c.get("outputs"), list):
                                c["outputs"] = []
                        else:
                            if "outputs" in c and c["outputs"] is None:
                                del c["outputs"]
                except Exception as _e:
                    logger.warning(f"conversation save sanitation failed: {_e}")

                # Save notebook
                save_data = {"type": "notebook", "content": notebook_data["content"]}

                put_headers = dict(headers)
                if self._xsrf_token:
                    put_headers["X-XSRFToken"] = self._xsrf_token
                async with session.put(
                    f"{server_url}/api/contents/{notebook_path}",
                    headers=put_headers,
                    json=save_data,
                ) as resp:
                    if resp.status != 200:
                        logger.error(
                            f"Failed to save notebook conversations: {resp.status}"
                        )
                    else:
                        logger.info(f"💾 Saved conversation to {notebook_path}")

        except Exception as e:
            logger.error(f"Error saving conversations to notebook: {e}")


class ChatStatusHandler(APIHandler):
    """Handler for status updates from LangGraph agent"""

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    @tornado.web.authenticated
    async def post(self):
        """Handle status updates from LangGraph agent"""
        try:
            data = self.get_json_body()
            items = data if isinstance(data, list) else [data]
            logger.info(f"📊 Agent Status Update: batch={len(items)}")
            # Persist status as an assistant message so chat UI can render it
            try:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    msg_text = item.get("message") or item.get("content") or ""
                    notebook_path = item.get("notebook_path")
                    if not notebook_path:
                        # Fallback to active session if single
                        import aiohttp

                        server_url = f"http://127.0.0.1:{self.serverapp.port}"
                        token = ChatOpenAIHandler._get_server_token(
                            self
                        )  # reuse helper
                        headers = {"Authorization": f"token {token}"}
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                f"{server_url}/api/sessions", headers=headers
                            ) as resp:
                                if resp.status == 200:
                                    data_sess = await resp.json()
                                    if isinstance(data_sess, dict):
                                        sessions = data_sess.get("sessions", [])
                                        if (
                                            isinstance(sessions, list)
                                            and len(sessions) == 1
                                        ):
                                            notebook_path = sessions[0].get("path")
                    if notebook_path and msg_text:
                        conv = ConversationManager(self.serverapp)
                        await conv.save_conversation_message(
                            notebook_path,
                            {"role": "assistant", "content": f"[status] {msg_text}"},
                        )
                        # Broadcast live status event
                        try:
                            targets = []
                            key = notebook_path or "*"
                            if key and key != "*":
                                targets = list(chat_broadcaster._subscribers.get(key, set()))
                            else:
                                targets = list(chat_broadcaster._subscribers.get("*", set()))
                            print(f"[WS] about to broadcast STATUS to recipients={len(targets)} path={key}")
                            chat_broadcaster.broadcast(
                                {
                                    "type": item.get("type") or "status",
                                    "notebook_path": notebook_path,
                                    "thread_id": item.get("thread_id"),
                                    "tool_call_id": item.get("tool_call_id"),
                                    "timestamp": item.get("timestamp")
                                    or datetime.utcnow().isoformat(),
                                    "payload": {
                                        "status": item.get("status")
                                        or "working",
                                        "message": msg_text,
                                    },
                                }
                            )
                        except Exception as _be:
                            logger.debug(f"status broadcast failed: {_be}")
            except Exception as _e:
                logger.warning(f"status persist failed: {_e}")

            self.set_status(200)
            self.finish({"status": "received"})

        except Exception as e:
            logger.error(f"❌ Status update failed: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class ChatMessageHandler(APIHandler):
    """Handler for messages from LangGraph agent"""

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    @tornado.web.authenticated
    async def post(self):
        """Handle messages from LangGraph agent"""
        try:
            data = self.get_json_body()
            items = data if isinstance(data, list) else [data]
            logger.info(f"💬 Agent Message batch: {len(items)}")
            # Persist assistant message so chat UI can render it
            try:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    notebook_path = item.get("notebook_path")
                    message_text = item.get("content") or item.get("message") or ""
                    if not notebook_path:
                        # Fallback to active session if single
                        import aiohttp

                        server_url = f"http://127.0.0.1:{self.serverapp.port}"
                        token = ChatOpenAIHandler._get_server_token(self)
                        headers = {"Authorization": f"token {token}"}
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                f"{server_url}/api/sessions", headers=headers
                            ) as resp:
                                if resp.status == 200:
                                    data_sess = await resp.json()
                                    if isinstance(data_sess, dict):
                                        sessions = data_sess.get("sessions", [])
                                        if (
                                            isinstance(sessions, list)
                                            and len(sessions) == 1
                                        ):
                                            notebook_path = sessions[0].get("path")
                    if notebook_path and message_text:
                        conv = ConversationManager(self.serverapp)
                        await conv.save_conversation_message(
                            notebook_path,
                            {"role": "assistant", "content": message_text},
                        )
                        # Broadcast live assistant message
                        try:
                            targets = []
                            key = notebook_path or "*"
                            if key and key != "*":
                                targets = list(chat_broadcaster._subscribers.get(key, set()))
                            else:
                                targets = list(chat_broadcaster._subscribers.get("*", set()))
                            print(f"[WS] about to broadcast MESSAGE to recipients={len(targets)} path={key}")
                            chat_broadcaster.broadcast(
                                {
                                    "type": "message",
                                    "notebook_path": notebook_path,
                                    "thread_id": item.get("thread_id"),
                                    "tool_call_id": item.get("tool_call_id"),
                                    "timestamp": item.get("timestamp")
                                    or datetime.utcnow().isoformat(),
                                    "payload": {
                                        "role": "assistant",
                                        "content": message_text,
                                    },
                                }
                            )
                        except Exception as _be:
                            logger.debug(f"message broadcast failed: {_be}")
            except Exception as _e:
                logger.warning(f"message persist failed: {_e}")

            self.set_status(200)
            self.finish({"status": "received"})

        except Exception as e:
            logger.error(f"❌ Message handling failed: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class ChatOpenAIHandler(APIHandler):
    """Handler for OpenAI chat requests with MCP server support"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mcp_servers = {}
        self.conversation_manager = ConversationManager(self.serverapp)

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    async def post(self):
        """Handle POST requests to /api/chat/openai"""
        self.log.info(
            "🚨🚨🚨 CHAT HANDLER CALLED - VERSION 4 - TESTING PYTHON RELOAD! 🚨🚨🚨"
        )
        print("[chat-backend] ChatOpenAIHandler.post: entered")
        self.log.info("🔍 IMMEDIATE NEXT LINE AFTER CHAT HANDLER CALLED")
        self.log.info("🔍 ENTERING POST METHOD")
        request_start = time.time()
        self.log.info(f"🚀 Request started at {request_start}")
        self.log.info("🔍 ABOUT TO ENTER TRY BLOCK")

        try:
            # Parse request body
            parse_start = time.time()
            self.log.info(f"🔍 RAW REQUEST BODY: {self.request.body}")
            print(
                f"[chat-backend] raw body bytes: {len(self.request.body) if self.request.body else 0}"
            )
            body = json.loads(self.request.body)
            self.log.info("🔍 PARSED BODY SUCCESS")
            message = body.get("message", "")
            model = body.get("model", "gpt-4o-mini")
            provider = body.get("provider", "openai")
            mcp_servers_config = body.get("mcpServers", {})
            context = body.get("context", {})
            notebook_path = context.get("notebook_path", "Untitled.ipynb")
            print(f"[chat-backend] notebook_path (from context): {notebook_path}")
            thread_id = body.get("thread_id")

            # SERVER-SIDE FALLBACK: derive path from active sessions if needed
            if not notebook_path or notebook_path == "Untitled.ipynb":
                try:
                    import aiohttp

                    server_url = f"http://127.0.0.1:{self.serverapp.port}"
                    token = self._get_server_token()
                    headers = {"Authorization": f"token {token}"}
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{server_url}/api/sessions", headers=headers
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                sessions = data.get("sessions", [])
                                if len(sessions) == 1:
                                    notebook_path = sessions[0].get(
                                        "path", notebook_path
                                    )
                                    self.log.info(
                                        f"🧭 Fallback notebook_path from sessions: {notebook_path}"
                                    )
                                    print(
                                        f"[chat-backend] notebook_path (fallback from sessions): {notebook_path}"
                                    )
                                else:
                                    self.log.info(
                                        f"🧭 Fallback skipped; session count={len(sessions)}"
                                    )
                except Exception as e:
                    self.log.warning(f"Fallback to sessions failed: {e}")

            # Cold start clearing: on the first request after server restart, clear chat history
            global BOOT_CLEAR_DONE
            if not BOOT_CLEAR_DONE and notebook_path:
                try:
                    self.log.warning(
                        f"❄️ Cold start: clearing chat_conversations for {notebook_path}"
                    )
                    # Prime XSRF by loading once, then save empty conversations
                    await self.conversation_manager.load_conversation_history(
                        notebook_path
                    )
                    empty_conv = self.conversation_manager._create_empty_conversations()
                    await self.conversation_manager._save_conversations_to_notebook(
                        notebook_path, empty_conv
                    )
                    BOOT_CLEAR_DONE = True
                except Exception as e:
                    self.log.warning(f"Cold start clear failed: {e}")

            # Continue as before
            chat_mode = body.get("chat_mode", "auto")  # auto, langgraph, openai_agents
            parse_time = time.time() - parse_start
            self.log.info(f"⚡ Request parsing took {parse_time:.3f}s")
            self.log.info(
                f"🎯 USING MODEL: {model}, PROVIDER: {provider}, MODE: {chat_mode}"
            )
            self.log.info(f"🔍 FULL REQUEST BODY: {json.dumps(body, indent=2)}")
            print(f"[chat-backend] proceeding with notebook_path: {notebook_path}")

            # Load conversation history
            history_start = time.time()
            conversation_context = []
            active_thread_id = None
            if BOOT_CLEAR_DONE:
                conversations = (
                    await self.conversation_manager.load_conversation_history(
                        notebook_path
                    )
                )
                active_thread_id = thread_id or conversations.get("active_thread")
                if active_thread_id and active_thread_id in conversations.get(
                    "threads", {}
                ):
                    thread_messages = conversations["threads"][active_thread_id].get(
                        "messages", []
                    )
                    conversation_context = thread_messages[-10:]
            else:
                self.log.warning(
                    "❄️ Cold start: skipping history load; starting with empty conversation_context"
                )
                BOOT_CLEAR_DONE = True

            history_time = time.time() - history_start
            logger.info(
                f"⚡ History handling took {history_time:.3f}s (BOOT_CLEAR_DONE={BOOT_CLEAR_DONE})"
            )

            # Save user message to conversation history
            save_user_start = time.time()
            user_message = {"role": "user", "content": message}
            active_thread_id = (
                await self.conversation_manager.save_conversation_message(
                    notebook_path, user_message, active_thread_id
                )
            )
            save_user_time = time.time() - save_user_start
            logger.info(f"⚡ User message saving took {save_user_time:.3f}s")

            # ALWAYS USE LANGGRAPH AGENT - NO FALLBACKS!
            self.log.info("🤖 ALWAYS USING LANGGRAPH AGENT")
            # Force empty conversation_context for now to avoid stale history
            if conversation_context:
                self.log.warning(
                    f"❄️ Forcing empty conversation_context (dropping {len(conversation_context)} messages)"
                )
            response = await self._run_langgraph_agent(
                message,
                notebook_path,
                [],  # FORCE COLD CONTEXT
                model,
                mcp_servers_config,
                provider,
            )
            # Skip saving assistant to metadata for now to avoid reintroducing history
            logger.warning(
                "💾 Skipping assistant message save to notebook metadata (temp)"
            )

            # Return response
            response_data = {
                "response": str(response),
                "thread_id": active_thread_id,
                "notebook_path": notebook_path,
                "agent_type": "langgraph",
            }

            total_time = time.time() - request_start
            logger.info(f"🏁 Total request time: {total_time:.3f}s")

            self.write(response_data)

        except Exception as e:
            total_time = time.time() - request_start
            logger.error(f"❌ Error in ChatOpenAIHandler after {total_time:.3f}s: {e}")
            import traceback

            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            self.set_status(500)
            self.write({"error": str(e)})

    def _should_use_langgraph(self, message: str) -> bool:
        """Determine if message should use LangGraph agent"""
        # Use LangGraph for complex analysis tasks
        analysis_keywords = [
            "analyze",
            "analysis",
            "pattern",
            "trend",
            "correlation",
            "visualize",
            "plot",
            "chart",
            "graph",
            "dashboard",
            "explore",
            "investigate",
            "examine",
            "study",
            "compare",
            "contrast",
            "relationship",
            "insight",
            "data",
            "dataset",
            "statistics",
            "metrics",
        ]

        message_lower = message.lower()
        return any(keyword in message_lower for keyword in analysis_keywords)

    def _get_server_token(self) -> str:
        """Get server token for authentication"""
        token = None
        if hasattr(self.serverapp, "identity_provider") and hasattr(
            self.serverapp.identity_provider, "token"
        ):
            token = self.serverapp.identity_provider.token
        if not token and hasattr(self.serverapp, "token"):
            token = self.serverapp.token
        return token or ""

    async def _run_openai_agent(
        self,
        message: str,
        notebook_path: str,
        conversation_context: list,
        model: str,
        mcp_servers_config: dict,
    ) -> str:
        """Run existing OpenAI Agents SDK workflow"""
        try:
            # Get settings from JupyterLab
            settings_dir = self.settings.get(
                "jupyter_config_dir", os.path.expanduser("~/.jupyter")
            )
            lab_settings_dir = os.path.join(settings_dir, "lab", "user-settings")
            chat_settings_file = os.path.join(
                lab_settings_dir,
                "@jupyterlab",
                "chat-extension",
                "plugin.jupyterlab-settings",
            )

            api_key = ""
            settings_mcp_servers = {}

            if os.path.exists(chat_settings_file):
                with open(chat_settings_file) as f:
                    settings_data = json.load(f)
                    api_key = settings_data.get("openaiApiKey", "")
                    settings_mcp_servers = settings_data.get("mcpServers", {})

            # Use MCP servers from settings if not provided in request
            if not mcp_servers_config and settings_mcp_servers:
                mcp_servers_config = settings_mcp_servers

            if not api_key:
                return "OpenAI API key not configured in JupyterLab Chat settings"

            # Import OpenAI Agents SDK
            from agents import Agent, Runner, set_default_openai_key
            from agents.mcp import MCPServerStdio
            from agents.mcp.server import MCPServerStdioParams

            # Set OpenAI API key
            set_default_openai_key(api_key)

            # Create JupyterTools instance
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            token = self._get_server_token()
            jupyter_tools = JupyterTools(server_url, token)

            # Create function tools from JupyterTools methods
            @function_tool
            async def insert_code_and_execute(
                code: str,
                notebook_path: str = "Untitled.ipynb",
                cell_type: str = "code",
                position: str = "end",
                kernel_id: str = None,
            ):
                """Insert code into a notebook cell, execute it, and capture outputs (PRIMARY TOOL)"""
                return await jupyter_tools.insert_code_and_execute(
                    notebook_path, code, cell_type, position, kernel_id
                )

            @function_tool
            async def insert_cell(
                source: str,
                notebook_path: str = "Untitled.ipynb",
                cell_type: str = "code",
                position: str = "end",
            ):
                """Insert a new cell with specified content"""
                return await jupyter_tools.insert_cell(
                    notebook_path, source, cell_type, position
                )

            @function_tool
            async def execute_cell(
                notebook_path: str = "Untitled.ipynb",
                cell_id: str = None,
                content: str = None,
                kernel_id: str = None,
            ):
                """Execute code in a specified cell or provided content and get its outputs"""
                return await jupyter_tools.execute_cell(
                    notebook_path, cell_id, content, kernel_id
                )

            @function_tool
            async def get_cell_content(
                notebook_path: str = "Untitled.ipynb", cell_id: str = None
            ):
                """Get cell content by UUID or all cells in the notebook"""
                return await jupyter_tools.get_cell_content(notebook_path, cell_id)

            @function_tool
            async def insert_markdown(
                markdown: str,
                notebook_path: str = "Untitled.ipynb",
                position: str = "end",
            ):
                """Insert markdown cells for documentation and explanations"""
                return await jupyter_tools.insert_markdown(
                    notebook_path, markdown, position
                )

            jupyter_tools = [
                insert_code_and_execute,
                insert_cell,
                execute_cell,
                get_cell_content,
                insert_markdown,
            ]

            # Set up MCP servers
            mcp_server_instances = []
            for server_name, config in mcp_servers_config.items():
                try:
                    params = MCPServerStdioParams(
                        command=config.get("command"),
                        args=config.get("args", []),
                        env=config.get("env", {}),
                    )
                    mcp_server = MCPServerStdio(params, name=server_name)
                    await asyncio.wait_for(mcp_server.connect(), timeout=10.0)
                    mcp_server_instances.append(mcp_server)
                except Exception as e:
                    logger.error(
                        f"❌ Failed to connect to MCP server {server_name}: {e}"
                    )

            # Create agent
            agent = Agent(
                name="JupyterLab Chat Assistant",
                model=model,
                tools=jupyter_tools,
                mcp_servers=mcp_server_instances,
                instructions="""You are a helpful JupyterLab assistant with access to notebook manipulation and external data tools.""",
            )

            # Run agent
            response = await asyncio.wait_for(Runner.run(agent, message), timeout=60.0)

            # Clean up MCP servers
            for server in mcp_server_instances:
                try:
                    if hasattr(server, "disconnect"):
                        await server.disconnect()
                except Exception as e:
                    logger.warning(f"Error cleaning up MCP server: {e}")

            return (
                str(response.final_output) if response.final_output else str(response)
            )

        except Exception as e:
            logger.error(f"❌ OpenAI Agents execution failed: {e}")
            return f"Error: {e}"

    async def _run_langgraph_agent(
        self,
        message: str,
        notebook_path: str,
        conversation_context: list,
        model: str,
        mcp_servers_config: dict,
        provider: str = "openai",
    ) -> str:
        """Run LangGraph agent workflow"""
        try:
            self.log.info("🚀 STEP 1: CALLING LANGGRAPH AGENT")

            # Add the jupyter-agent package to Python path for dev mode
            self.log.info("🚀 STEP 2: IMPORTING MODULES")
            import sys
            import os
            import asyncio

            self.log.info("🚀 STEP 3: SETTING UP PYTHON PATH")
            # Get the absolute path to the jupyter-agent package
            current_dir = os.path.dirname(os.path.abspath(__file__))
            jupyter_agent_path = os.path.join(current_dir, "..", "..", "jupyter-agent")
            jupyter_agent_path = os.path.abspath(jupyter_agent_path)
            self.log.info(f"🐍 Jupyter agent path: {jupyter_agent_path}")

            if jupyter_agent_path not in sys.path:
                sys.path.insert(0, jupyter_agent_path)
                self.log.info("🐍 Added LangGraph agent path to sys.path")
            else:
                self.log.info("🐍 Path already in sys.path")

            self.log.info("🚀 STEP 4: IMPORTING LANGGRAPH AGENT")
            # Import LangGraph agent
            from jupyter_agent_lg.agent import DataAnalysisAgent

            self.log.info("✅ DataAnalysisAgent imported successfully")

            self.log.info("🚀 STEP 5: GETTING SERVER CONFIG")
            # Get server configuration
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            self.log.info(f"🌐 Server URL: {server_url}")

            self.log.info("🚀 STEP 6: GETTING SERVER TOKEN")
            token = self._get_server_token()
            self.log.info(f"🔑 Token length: {len(token) if token else 0}")

            self.log.info("🚀 STEP 7: GETTING API KEYS")
            # Get API keys
            openai_api_key = self._get_openai_api_key()
            anthropic_api_key = self._get_anthropic_api_key()
            self.log.info(
                f"🔑 OpenAI key length: {len(openai_api_key) if openai_api_key else 0}"
            )
            self.log.info(
                f"🔑 Anthropic key length: {len(anthropic_api_key) if anthropic_api_key else 0}"
            )

            self.log.info("🚀 STEP 8: CREATING AGENT")
            # Create agent
            agent = DataAnalysisAgent(
                server_url=server_url,
                token=token,
                openai_api_key=openai_api_key,
                anthropic_api_key=anthropic_api_key,
            )
            self.log.info("✅ DataAnalysisAgent created successfully")

            self.log.info("🚀 STEP 9: PROCESSING REQUEST")
            self.log.info(f"📝 Message: '{message}'")
            self.log.info(f"📝 Model: {model}")
            self.log.info(f"📝 Provider: {provider}")
            self.log.info(f"📝 Notebook path: {notebook_path}")
            self.log.info(
                f"📝 Conversation context length: {len(conversation_context)}"
            )

            # Process request
            result = await asyncio.wait_for(
                agent.process_request(
                    request=message,
                    notebook_path=notebook_path,
                    conversation_history=conversation_context,
                    model=model,
                    provider=provider,
                    mcp_servers=mcp_servers_config,
                ),
                timeout=300.0,  # 5 minute timeout
            )
            self.log.info(f"✅ LANGGRAPH AGENT RETURNED: {result[:200]}...")
            self.log.info("🚀 STEP 10: AGENT PROCESS REQUEST COMPLETED")
            self.log.info(f"✅ RESULT TYPE: {type(result)}")
            self.log.info(f"✅ RESULT LENGTH: {len(str(result))}")

            return result

        except Exception as e:
            import traceback

            full_traceback = traceback.format_exc()
            self.log.error(f"❌ LangGraph agent execution failed: {e}")
            self.log.error(f"❌ FULL TRACEBACK:\n{full_traceback}")
            return f"LangGraph agent error: {e}"

    def _get_openai_api_key(self) -> str:
        """Get OpenAI API key from JupyterLab settings or environment"""
        try:
            import os
            from jupyter_core.paths import jupyter_config_dir

            # First try JupyterLab settings (preferred method)
            try:
                config_dir = jupyter_config_dir()
                lab_settings_dir = os.path.join(config_dir, "lab", "user-settings")
                chat_settings_file = os.path.join(
                    lab_settings_dir,
                    "@jupyterlab",
                    "chat-extension",
                    "plugin.jupyterlab-settings",
                )

                if os.path.exists(chat_settings_file):
                    with open(chat_settings_file, "r") as f:
                        settings_data = json.load(f)
                        api_key = settings_data.get("openaiApiKey", "")
                        if api_key and api_key.strip():
                            logger.info(
                                "✅ Using OpenAI API key from JupyterLab settings"
                            )
                            return api_key.strip()

            except Exception as e:
                logger.warning(f"Could not read JupyterLab settings: {e}")

            # Fallback to environment variable
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if api_key:
                logger.info("✅ Using OpenAI API key from environment variable")
                return api_key

            logger.warning("❌ No OpenAI API key found in settings or environment")
            return ""

        except Exception as e:
            logger.error(f"Error getting OpenAI API key: {e}")
            return ""

    def _get_anthropic_api_key(self) -> str:
        """Get Anthropic API key from environment"""
        try:
            import os

            return os.getenv("ANTHROPIC_API_KEY", "")
        except Exception as e:
            logger.warning(f"Could not get Anthropic API key: {e}")
            return ""


class ChatExtension(ExtensionApp):
    """JupyterLab Chat Extension Server"""

    name = "jupyterlab_chat"

    def initialize_handlers(self):
        """Initialize the extension's handlers"""
        handlers = [
            (r"/api/chat/openai", ChatOpenAIHandler),
        ]
        self.handlers.extend(handlers)


def _jupyter_server_extension_points():
    """Entry point for the server extension"""
    return [{"module": "jupyterlab_chat"}]


def _load_jupyter_server_extension(server_app):
    """Load the extension"""
    handlers = [
        (r"/api/chat/openai", ChatOpenAIHandler),
        (r"/api/chat/status", ChatStatusHandler),
        (r"/api/chat/message", ChatMessageHandler),
        (r"/api/chat/stream", ChatStreamHandler),
    ]
    server_app.web_app.add_handlers(".*$", handlers)
    server_app.log.info("JupyterLab Chat extension loaded with status endpoints")
    print("[chat-backend] extension loaded: handlers registered /api/chat/*")
