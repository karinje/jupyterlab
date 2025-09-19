"""
HTTP Handlers for LangGraph Agent Integration

Provides REST API endpoints for the LangGraph agent to integrate with
the JupyterLab chat system and handle agent requests.
"""

import json
import logging
import asyncio
from typing import Optional
from jupyter_server.base.handlers import APIHandler
import tornado.web

from .agent import DataAnalysisAgent

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


class LangGraphHandler(APIHandler):
    """Main handler for LangGraph agent requests"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._agent: Optional[DataAnalysisAgent] = None

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    def get_agent(self) -> DataAnalysisAgent:
        """Get or create DataAnalysisAgent instance"""
        if self._agent is None:
            # Get server configuration
            server_url = f"http://127.0.0.1:{self.serverapp.port}"
            token = self._get_server_token()

            # Get API keys from settings
            openai_api_key = self._get_openai_api_key()
            anthropic_api_key = self._get_anthropic_api_key()

            # Create agent
            self._agent = DataAnalysisAgent(
                server_url=server_url,
                token=token,
                openai_api_key=openai_api_key,
                anthropic_api_key=anthropic_api_key,
            )

            logger.info("🤖 Created new DataAnalysisAgent instance")

        return self._agent

    @tornado.web.authenticated
    async def post(self):
        """Handle LangGraph agent requests"""
        try:
            # Parse request
            request_data = self.get_json_body()
            message = request_data.get("message", "")
            notebook_path = request_data.get("notebook_path", "Untitled.ipynb")
            conversation_history = request_data.get("conversation_history", [])  # Use actual conversation history
            model = request_data.get("model", "gpt-4o")
            provider = request_data.get("provider", "openai")
            mcp_servers = request_data.get("mcp_servers", {})

            logger.info(
                f"🚀 LangGraph request: {message[:100]}... (model: {model}, provider: {provider})"
            )

            # Get agent and process request
            agent = self.get_agent()

            # Run agent in background to avoid timeout
            result = await asyncio.wait_for(
                agent.process_request(
                    request=message,
                    notebook_path=notebook_path,
                    conversation_history=conversation_history,
                    model=model,
                    provider=provider,
                    mcp_servers=mcp_servers,
                ),
                timeout=300.0,  # 5 minute timeout
            )

            # Return response
            self.write(
                {
                    "status": "success",
                    "result": result,
                    "agent_type": "langgraph",
                    "provider": provider,
                    "model": model,
                }
            )

            logger.info("✅ LangGraph request completed successfully")

        except asyncio.TimeoutError:
            logger.error("❌ LangGraph request timed out")
            self.set_status(408)
            self.write(
                {
                    "status": "error",
                    "error": "Request timed out",
                    "agent_type": "langgraph",
                }
            )

        except Exception as e:
            logger.error(f"❌ LangGraph request failed: {e}")
            import traceback

            logger.error(f"❌ Full traceback: {traceback.format_exc()}")

            self.set_status(500)
            self.write({"status": "error", "error": str(e), "agent_type": "langgraph"})

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

    def _get_openai_api_key(self) -> Optional[str]:
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
            return None

        except Exception as e:
            logger.warning(f"Could not get OpenAI API key: {e}")
            return None

    def _get_anthropic_api_key(self) -> Optional[str]:
        """Get Anthropic API key from environment or settings"""
        try:
            import os

            # Try environment variable
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                return api_key

            # Could extend to read from JupyterLab settings in the future
            return None

        except Exception as e:
            logger.warning(f"Could not get Anthropic API key: {e}")
            return None


class LangGraphStatusHandler(APIHandler):
    """Handler for LangGraph agent status updates"""

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    @tornado.web.authenticated
    async def get(self):
        """Get agent status"""
        try:
            # For now, just return basic status
            # In the future, could track active agent sessions

            self.write(
                {
                    "status": "ready",
                    "available_providers": ["openai", "anthropic"],
                    "default_model": "gpt-4o",
                }
            )

        except Exception as e:
            logger.error(f"❌ Status check failed: {e}")
            self.set_status(500)
            self.write({"status": "error", "error": str(e)})

    @tornado.web.authenticated
    async def post(self):
        """Receive status updates from agent"""
        try:
            status_data = self.get_json_body()
            logger.info(f"📊 Agent Status: {status_data}")

            # For now, just log status updates
            # In the future, could broadcast to connected WebSocket clients

            self.write({"status": "received"})

        except Exception as e:
            logger.error(f"❌ Status update failed: {e}")
            self.set_status(500)
            self.write({"error": str(e)})


class LangGraphModelsHandler(APIHandler):
    """Handler for getting available models and providers"""

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    @tornado.web.authenticated
    async def get(self):
        """Get available models and providers"""
        try:
            models_info = {
                "providers": {
                    "openai": {
                        "name": "OpenAI",
                        "models": [
                            {
                                "id": "gpt-4o",
                                "name": "GPT-4o",
                                "description": "Most capable model",
                            },
                            {
                                "id": "gpt-4o-mini",
                                "name": "GPT-4o Mini",
                                "description": "Fast and efficient",
                            },
                            {
                                "id": "o1-preview",
                                "name": "o1 Preview",
                                "description": "Advanced reasoning",
                            },
                            {
                                "id": "o1-mini",
                                "name": "o1 Mini",
                                "description": "Efficient reasoning",
                            },
                            {
                                "id": "gpt-4-turbo",
                                "name": "GPT-4 Turbo",
                                "description": "Previous generation",
                            },
                            {
                                "id": "gpt-3.5-turbo",
                                "name": "GPT-3.5 Turbo",
                                "description": "Fast and cost-effective",
                            },
                        ],
                        "default_model": "gpt-4o",
                    },
                    "anthropic": {
                        "name": "Anthropic",
                        "models": [
                            {
                                "id": "claude-3-5-sonnet-20241022",
                                "name": "Claude 3.5 Sonnet",
                                "description": "Most capable Claude model",
                            },
                            {
                                "id": "claude-3-opus-20240229",
                                "name": "Claude 3 Opus",
                                "description": "Powerful reasoning",
                            },
                            {
                                "id": "claude-3-sonnet-20240229",
                                "name": "Claude 3 Sonnet",
                                "description": "Balanced performance",
                            },
                            {
                                "id": "claude-3-haiku-20240307",
                                "name": "Claude 3 Haiku",
                                "description": "Fast and efficient",
                            },
                        ],
                        "default_model": "claude-3-5-sonnet-20241022",
                    },
                    "google": {
                        "name": "Google",
                        "models": [
                            {
                                "id": "gemini-1.5-pro",
                                "name": "Gemini 1.5 Pro",
                                "description": "Most capable Gemini",
                            },
                            {
                                "id": "gemini-1.5-flash",
                                "name": "Gemini 1.5 Flash",
                                "description": "Fast inference",
                            },
                            {
                                "id": "gemini-pro",
                                "name": "Gemini Pro",
                                "description": "Previous generation",
                            },
                        ],
                        "default_model": "gemini-1.5-pro",
                        "available": False,  # Not yet implemented
                        "note": "Coming soon",
                    },
                },
                "default_provider": "openai",
                "default_model": "gpt-4o",
            }

            self.write(models_info)

        except Exception as e:
            logger.error(f"❌ Models info failed: {e}")
            self.set_status(500)
            self.write({"error": str(e)})


# Handler registration for JupyterLab extension
def get_handlers():
    """Get handlers for registration with JupyterLab"""
    return [
        (r"/api/langgraph/process", LangGraphHandler),
        (r"/api/langgraph/status", LangGraphStatusHandler),
        (r"/api/langgraph/models", LangGraphModelsHandler),
    ]
