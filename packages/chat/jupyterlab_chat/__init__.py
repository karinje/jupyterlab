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

# Set up proper logging using simplified config
try:
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
except ImportError:
    # Fallback if centralized logging not available
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger("jupyterlab")

# Module-level debug to confirm our code is loaded
logger.info("🔥🔥🔥 JUPYTERLAB CHAT MODULE IMPORTED - NEW VERSION! 🔥🔥🔥")

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
                        logger.debug(f"WS dedup drop MESSAGE path={notebook_path}")
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

# Removed BOOT_CLEAR_DONE - no need to clear chat history on restart

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

    async def clear_all_conversations(self, notebook_path: str) -> bool:
        """Clear all conversations for a notebook and save to disk"""
        try:
            logger.info(f"🧹 Clearing all conversations for notebook: {notebook_path}")
            
            # Create empty conversation structure
            empty_conversations = {
                "threads": {},
                "active_thread": None,
                "thread_order": []
            }
            
            # Save empty structure to notebook (this will persist to disk)
            await self._save_conversations_to_notebook(notebook_path, empty_conversations)
            
            logger.info(f"✅ Successfully cleared all conversations for {notebook_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing conversations: {e}")
            return False

    async def _save_conversations_to_notebook(
        self, notebook_path: str, conversations: Dict
    ):
        """Save conversations back to notebook metadata using YDoc to avoid file/live state conflicts"""
        try:
            # Get YDoc extension from web_app settings (jupyter_server_ydoc)
            ydoc_ext = self.serverapp.web_app.settings.get("jupyter_server_ydoc")
            if ydoc_ext:
                logger.info("✅ Found YDoc extension in web_app.settings")
            else:
                logger.error("❌ YDoc extension not found - jupyter_server_ydoc may not be loaded")
                logger.error(f"Available settings keys: {list(self.serverapp.web_app.settings.keys())}")
                return

            # Get live YDoc document (this is the authoritative live state)
            try:
                ydoc = await ydoc_ext.get_document(
                    path=notebook_path,
                    content_type="notebook",
                    file_format="json",
                    copy=False  # Get reference to live document, not a copy
                )
            except Exception as e:
                logger.error(f"Failed to get YDoc for {notebook_path}: {e}")
                return

            # Get current notebook state from YDoc
            current_notebook = ydoc.get()
            if not current_notebook or not isinstance(current_notebook, dict):
                logger.error(f"Invalid notebook state in YDoc for {notebook_path}")
                return

            # Update ONLY metadata, leave cells untouched
            if "metadata" not in current_notebook:
                current_notebook["metadata"] = {}

            current_notebook["metadata"]["chat_conversations"] = conversations

            # Update YDoc live state (this preserves all cells and only updates metadata)
            ydoc.set(current_notebook)

            logger.info(f"💾 Saved conversation metadata to YDoc live state: {notebook_path}")
            logger.info(f"📝 Conversation threads: {list(conversations.keys()) if isinstance(conversations, dict) else 'N/A'}")

        except Exception as e:
            logger.error(f"Error saving conversations to YDoc: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")


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
                        # Resolve notebook path from active sessions
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
                                        if isinstance(sessions, list) and len(sessions) > 0:
                                            notebook_path = sessions[0].get("path")
                    if notebook_path and msg_text:
                        # Status messages should only be broadcast for real-time display,
                        # NOT saved to conversation history (they were creating separate threads)
                        logger.info(f"📊 Broadcasting status message: {msg_text} (not saving to conversation)")
                        # Broadcast live status event
                        try:
                            targets = []
                            key = notebook_path or "*"
                            if key and key != "*":
                                targets = list(chat_broadcaster._subscribers.get(key, set()))
                            else:
                                targets = list(chat_broadcaster._subscribers.get("*", set()))
                            logger.debug(f"WS about to broadcast STATUS to recipients={len(targets)} path={key}")
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
                    thread_id = item.get("thread_id")  # Extract thread_id from request
                    if not notebook_path:
                        # Resolve notebook path from active sessions
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
                                        if isinstance(sessions, list) and len(sessions) > 0:
                                            notebook_path = sessions[0].get("path")
                    if notebook_path and message_text:
                        # Save assistant message to YDoc metadata (fixed race condition)
                        conv = ConversationManager(self.serverapp)
                        await conv.save_conversation_message(
                            notebook_path,
                            {"role": "assistant", "content": message_text},
                            thread_id,  # Pass thread_id to save to same thread as user message
                        )

                        # Broadcast live assistant message
                        try:
                            targets = []
                            key = notebook_path or "*"
                            if key and key != "*":
                                targets = list(chat_broadcaster._subscribers.get(key, set()))
                            else:
                                targets = list(chat_broadcaster._subscribers.get("*", set()))
                            logger.debug(f"WS about to broadcast MESSAGE to recipients={len(targets)} path={key}")
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


class ChatThreadsHandler(APIHandler):
    """Handler for getting conversation threads"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversation_manager = ConversationManager(self.serverapp)
    
    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass
    
    @tornado.web.authenticated
    async def get(self):
        """Get conversation threads for a notebook with centralized thread selection logic"""
        try:
            notebook_path = self.get_argument('notebook_path', None)
            if not notebook_path:
                self.set_status(400)
                self.finish({"error": "notebook_path parameter required"})
                return
            
            conversations = await self.conversation_manager.load_conversation_history(notebook_path)
            all_threads = conversations.get("threads", {})
            
            # Build thread summaries with centralized logic
            thread_summaries = []
            most_recent_thread_id = None
            most_recent_time = 0
            
            for thread_id, thread_data in all_threads.items():
                # Filter out status messages for accurate message count
                messages = thread_data.get("messages", [])
                conversation_messages = []
                for msg in messages:
                    content = msg.get("content", "")
                    if content and not content.startswith("[status]") and not content.startswith("⏳"):
                        conversation_messages.append(msg)
                
                # Get thread metadata
                title = thread_data.get("title", "Untitled")
                last_updated = thread_data.get("last_updated", thread_data.get("created", ""))
                created = thread_data.get("created", "")
                
                # Calculate most recent thread
                if last_updated:
                    try:
                        update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00')).timestamp()
                        if update_time > most_recent_time:
                            most_recent_time = update_time
                            most_recent_thread_id = thread_id
                    except Exception:
                        pass
                
                thread_summaries.append({
                    "id": thread_id,
                    "title": title,
                    "message_count": len(conversation_messages),
                    "last_updated": last_updated,
                    "created": created,
                    "messages": conversation_messages  # Filtered messages for frontend
                })
            
            # Sort threads by last_updated (most recent first)
            thread_summaries.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
            
            # Use most recent thread if no active thread specified
            selected_thread_id = most_recent_thread_id or conversations.get("active_thread")
            
            response = {
                "threads": thread_summaries,
                "selected_thread_id": selected_thread_id,
                "total_threads": len(thread_summaries)
            }
            
            logger.info(f"📚 Returning {len(thread_summaries)} threads for {notebook_path}, selected: {selected_thread_id}")
            self.finish(response)
            
        except Exception as e:
            logger.error(f"Error getting conversation threads: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class ChatThreadTitleHandler(APIHandler):
    """Handler for saving thread titles"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversation_manager = ConversationManager(self.serverapp)

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    @tornado.web.authenticated
    async def post(self):
        """Save thread title to conversation metadata"""
        try:
            body = self.get_json_body()
            title = body.get("title")
            notebook_path = body.get("notebook_path")
            thread_id = body.get("thread_id")

            if not title or not notebook_path:
                self.set_status(400)
                self.finish({"error": "title and notebook_path are required"})
                return

            logger.info(f"💾 Saving thread title: '{title}' for notebook: {notebook_path}, thread: {thread_id}")

            # Load current conversations
            conversations = await self.conversation_manager.load_conversation_history(notebook_path)
            
            # Find the thread to update (use most recent if no thread_id specified)
            target_thread_id = thread_id
            if not target_thread_id:
                # Find most recent thread
                all_threads = conversations.get("threads", {})
                most_recent_time = 0
                for tid, thread_data in all_threads.items():
                    last_updated = thread_data.get("last_updated", "")
                    if last_updated:
                        try:
                            update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00')).timestamp()
                            if update_time > most_recent_time:
                                most_recent_time = update_time
                                target_thread_id = tid
                        except Exception:
                            pass

            if target_thread_id and target_thread_id in conversations.get("threads", {}):
                # Update thread title
                conversations["threads"][target_thread_id]["title"] = title
                conversations["threads"][target_thread_id]["last_updated"] = datetime.utcnow().isoformat()
                
                # Save updated conversations
                await self.conversation_manager._save_conversations_to_notebook(notebook_path, conversations)
                
                logger.info(f"✅ Thread title saved: '{title}' for thread {target_thread_id}")
                self.finish({"status": "success", "thread_id": target_thread_id, "title": title})
            else:
                logger.warning(f"Thread not found: {target_thread_id}")
                self.set_status(404)
                self.finish({"error": "Thread not found"})

        except Exception as e:
            logger.error(f"Error saving thread title: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class ChatDebugHandler(APIHandler):
    """Handler for debug operations like clearing conversation history"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conversation_manager = ConversationManager(self.serverapp)

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    @tornado.web.authenticated
    async def post(self):
        """Handle debug operations"""
        try:
            body = self.get_json_body()
            action = body.get("action")
            notebook_path = body.get("notebook_path")

            if not action or not notebook_path:
                self.set_status(400)
                self.finish({"error": "action and notebook_path are required"})
                return

            if action == "clear_conversations":
                success = await self.conversation_manager.clear_all_conversations(notebook_path)
                
                if success:
                    self.finish({"status": "success", "message": f"Cleared conversations for {notebook_path}"})
                else:
                    self.set_status(500)
                    self.finish({"error": "Failed to clear conversations"})
            else:
                self.set_status(400)
                self.finish({"error": f"Unknown action: {action}"})

        except Exception as e:
            logger.error(f"Error in debug handler: {e}")
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
        logger.info("🚨🚨🚨 CHAT HANDLER CALLED - VERSION 4 - TESTING PYTHON RELOAD! 🚨🚨🚨")
        logger.info("🔍 IMMEDIATE NEXT LINE AFTER CHAT HANDLER CALLED")
        logger.info("🔍 ENTERING POST METHOD")
        request_start = time.time()
        logger.info(f"🚀 Request started at {request_start}")
        logger.info("🔍 ABOUT TO ENTER TRY BLOCK")

        try:
            # Parse request body
            parse_start = time.time()
            logger.debug(f"RAW REQUEST BODY: {self.request.body}")
            logger.debug(f"Raw body bytes: {len(self.request.body) if self.request.body else 0}")
            body = json.loads(self.request.body)
            logger.debug("PARSED BODY SUCCESS")
            message = body.get("message", "")
            model = body.get("model", "gpt-4o-mini")
            provider = body.get("provider", "openai")
            mcp_servers_config = body.get("mcpServers", {})
            context = body.get("context", {})
            notebook_path = context.get("notebook_path")
            logger.info(f"notebook_path (from frontend context): {notebook_path}")
            thread_id = body.get("thread_id")

            # TRUST FRONTEND: Only fall back to sessions if frontend sends null/empty
            if not notebook_path:
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
                                if len(sessions) >= 1:
                                    notebook_path = sessions[0].get("path")
                                    logger.info(f"🧭 Fallback: resolved notebook_path from sessions: {notebook_path} (from {len(sessions)} sessions)")
                                else:
                                    logger.warning("🧭 No active sessions found, using Untitled.ipynb as last resort")
                                    notebook_path = "Untitled.ipynb"
                except Exception as e:
                    logger.warning(f"Failed to resolve notebook path from sessions: {e}")
                    notebook_path = "Untitled.ipynb"  # Only fallback to Untitled as last resort

            # Removed cold start clearing - conversations should persist across restarts
            chat_mode = body.get("chat_mode", "auto")  # auto, langgraph, openai_agents
            parse_time = time.time() - parse_start
            logger.info(f"⚡ Request parsing took {parse_time:.3f}s")
            logger.info(f"🎯 USING MODEL: {model}, PROVIDER: {provider}, MODE: {chat_mode}")
            logger.debug(f"FULL REQUEST BODY: {json.dumps(body, indent=2)}")
            logger.info(f"🎯 FINAL notebook_path: {notebook_path} (frontend should provide active notebook, not random session)")

            # Load conversation history
            history_start = time.time()
            conversation_context = []
            active_thread_id = None
            # Always load conversation history (no more boot clearing)
            conversations = (
                await self.conversation_manager.load_conversation_history(
                    notebook_path
                )
            )
            
            # Log all available threads for debugging
            all_threads = conversations.get("threads", {})
            thread_count = len(all_threads)
            logger.info(f"📚 Found {thread_count} conversation threads in {notebook_path}")
            
            if thread_count > 0:
                for tid, thread_data in all_threads.items():
                    message_count = len(thread_data.get("messages", []))
                    created = thread_data.get("created_at", "unknown")
                    logger.info(f"  📝 Thread {tid[:8]}... has {message_count} messages (created: {created})")
            
            # Use selected thread ID from frontend context - respect explicit null for new threads
            selected_thread_id = context.get("selected_thread_id")
            all_threads = conversations.get("threads", {})
            
            # If specific thread selected, use it
            if selected_thread_id and selected_thread_id in all_threads:
                active_thread_id = selected_thread_id
                logger.info(f"🎯 Using selected thread ID: {active_thread_id}")
            # If frontend explicitly wants new thread (selected_thread_id is None), don't auto-select
            elif "selected_thread_id" in context and context["selected_thread_id"] is None:
                active_thread_id = None  # Force new thread creation
                logger.info(f"🆕 Frontend requested new thread, not auto-selecting existing thread")
            else:
                # Find most recent thread based on last_updated timestamp
                most_recent_thread_id = suggested_thread_id
                most_recent_time = 0
                
                for tid, thread_data in all_threads.items():
                    last_updated = thread_data.get("last_updated")
                    if last_updated:
                        try:
                            update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00')).timestamp()
                            if update_time > most_recent_time:
                                most_recent_time = update_time
                                most_recent_thread_id = tid
                        except Exception:
                            pass
                
                active_thread_id = most_recent_thread_id
                logger.info(f"🎯 Using most recent thread ID: {active_thread_id} (was suggested: {suggested_thread_id})")
            
            if active_thread_id and active_thread_id in conversations.get("threads", {}):
                thread_messages = conversations["threads"][active_thread_id].get("messages", [])
                
                # Filter out status messages - only use real conversation messages for context
                filtered_messages = []
                for msg in thread_messages:
                    content = msg.get("content", "")
                    if content and not content.startswith("[status]") and not content.startswith("⏳"):
                        filtered_messages.append(msg)
                    else:
                        logger.debug(f"Filtering out status message: {content[:50]}...")
                
                conversation_context = filtered_messages[-10:]
                logger.info(f"✅ Loaded {len(thread_messages)} total messages, filtered to {len(filtered_messages)} conversation messages, using last {len(conversation_context)} for context")
                
                # Log first and last conversation messages for verification
                if len(filtered_messages) > 0:
                    first_msg = filtered_messages[0]
                    last_msg = filtered_messages[-1]
                    logger.info(f"  📖 First conversation message: {first_msg.get('role', 'unknown')} - {first_msg.get('content', '')[:100]}...")
                    if len(filtered_messages) > 1:
                        logger.info(f"  📖 Last conversation message: {last_msg.get('role', 'unknown')} - {last_msg.get('content', '')[:100]}...")
            else:
                logger.info(f"❌ No active thread found or thread {active_thread_id} doesn't exist - starting fresh conversation")

            history_time = time.time() - history_start
            logger.info(f"⚡ History handling took {history_time:.3f}s")

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

            # ALWAYS USE LANGGRAPH AGENT - NO FILTERING, NO FALLBACKS!
            logger.info("🤖 ALWAYS USING LANGGRAPH AGENT (no stupid filtering)")
            # Pass conversation context to agent for continuity
            logger.info(f"📚 Passing {len(conversation_context)} messages as conversation context")
            response = await self._run_langgraph_agent(
                message,
                notebook_path,
                conversation_context,  # Pass actual conversation context
                model,
                mcp_servers_config,
                provider,
                active_thread_id,  # Pass thread_id to agent
            )

            # Note: Assistant message is already saved by RespondToUser tool via ChatMessageHandler
            # No need to save again here to avoid duplicates

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

    # REMOVED: _should_use_langgraph - stupid filtering logic removed
    # ALL messages go to LangGraph agent, no exceptions!

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
        thread_id: str = None,
    ) -> str:
        """Run LangGraph agent workflow"""
        try:
            logger.info("🚀 STEP 1: CALLING LANGGRAPH AGENT")

            # Add the jupyter-agent package to Python path for dev mode
            logger.info("🚀 STEP 2: IMPORTING MODULES")
            import sys
            import os
            import asyncio

            logger.info("🚀 STEP 3: SETTING UP PYTHON PATH")
            # Get the absolute path to the jupyter-agent package
            current_dir = os.path.dirname(os.path.abspath(__file__))
            jupyter_agent_path = os.path.join(current_dir, "..", "..", "jupyter-agent")
            jupyter_agent_path = os.path.abspath(jupyter_agent_path)
            logger.info(f"🐍 Jupyter agent path: {jupyter_agent_path}")

            if jupyter_agent_path not in sys.path:
                sys.path.insert(0, jupyter_agent_path)
                logger.info("🐍 Added LangGraph agent path to sys.path")
            else:
                logger.info("🐍 Path already in sys.path")

            logger.info("🚀 STEP 4: IMPORTING LANGGRAPH AGENT")
            # Import LangGraph agent
            from jupyter_agent_lg.agent import DataAnalysisAgent

            logger.info("✅ DataAnalysisAgent imported successfully")

            logger.info("🚀 STEP 5: GETTING SERVER CONFIG")
            # Get server configuration
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            logger.info(f"🌐 Server URL: {server_url}")

            logger.info("🚀 STEP 6: GETTING SERVER TOKEN")
            token = self._get_server_token()
            logger.info(f"🔑 Token length: {len(token) if token else 0}")

            logger.info("🚀 STEP 7: GETTING API KEYS")
            # Get API keys
            openai_api_key = self._get_openai_api_key()
            anthropic_api_key = self._get_anthropic_api_key()
            logger.info(
                f"🔑 OpenAI key length: {len(openai_api_key) if openai_api_key else 0}"
            )
            logger.info(
                f"🔑 Anthropic key length: {len(anthropic_api_key) if anthropic_api_key else 0}"
            )

            logger.info("🚀 STEP 8: CREATING AGENT")
            # Create agent
            agent = DataAnalysisAgent(
                server_url=server_url,
                token=token,
                openai_api_key=openai_api_key,
                anthropic_api_key=anthropic_api_key,
            )
            logger.info("✅ DataAnalysisAgent created successfully")

            logger.info("🚀 STEP 9: PROCESSING REQUEST")
            logger.info(f"📝 Message: '{message}'")
            logger.info(f"📝 Model: {model}")
            logger.info(f"📝 Provider: {provider}")
            logger.info(f"📝 Notebook path: {notebook_path}")
            logger.info(
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
                    thread_id=thread_id,  # Pass thread_id to agent
                ),
                timeout=300.0,  # 5 minute timeout
            )
            logger.info(f"✅ LANGGRAPH AGENT RETURNED: {result[:200]}...")
            logger.info("🚀 STEP 10: AGENT PROCESS REQUEST COMPLETED")
            logger.info(f"✅ RESULT TYPE: {type(result)}")
            logger.info(f"✅ RESULT LENGTH: {len(str(result))}")

            return result

        except Exception as e:
            import traceback

            full_traceback = traceback.format_exc()
            logger.error(f"❌ LangGraph agent execution failed: {e}")
            logger.error(f"❌ FULL TRACEBACK:\n{full_traceback}")
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
            (r"/api/chat/threads", ChatThreadsHandler),
            (r"/api/chat/thread-title", ChatThreadTitleHandler),
            (r"/api/chat/debug", ChatDebugHandler),
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
        (r"/api/chat/threads", ChatThreadsHandler),
        (r"/api/chat/thread-title", ChatThreadTitleHandler),
        (r"/api/chat/debug", ChatDebugHandler),
    ]
    server_app.web_app.add_handlers(".*$", handlers)
    server_app.log.info("JupyterLab Chat extension loaded with status endpoints")
    logger.info("extension loaded: handlers registered /api/chat/*")
