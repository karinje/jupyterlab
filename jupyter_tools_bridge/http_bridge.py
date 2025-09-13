"""
HTTP Bridge for JupyterAgent Tools
Exposes JupyterAgent methods via HTTP API for LangGraph integration
"""

import json
import logging
from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.application import ExtensionApp
from .tools import JupyterAgent

logger = logging.getLogger(__name__)


class JupyterAgentHandler(APIHandler):
    """HTTP handler for JupyterAgent method calls"""

    def initialize(self):
        """Initialize the handler"""
        self.jupyter_agent = None

    def check_xsrf_cookie(self):
        """Disable XSRF check for this endpoint"""
        pass

    async def post(self, method):
        """Handle POST requests to /api/jupyter_agent/{method}"""
        try:
            # Parse request body
            body = json.loads(self.request.body)

            # Initialize JupyterAgent if needed
            if not self.jupyter_agent:
                server_url = f"http://127.0.0.1:{self.serverapp.port}"
                token = self._get_server_token()
                self.jupyter_agent = JupyterAgent(server_url, token)

            # Call the appropriate method
            result = await self._call_agent_method(method, body)

            self.write(result)

        except Exception as e:
            logger.error(f"Error in JupyterAgent HTTP bridge: {e}")
            self.set_status(500)
            self.write({"error": str(e)})

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

    async def _call_agent_method(self, method: str, params: dict):
        """Call JupyterAgent method with parameters"""
        if method == "insert_code_and_execute":
            return await self.jupyter_agent.insert_code_and_execute(
                notebook_path=params.get("notebook_path", "Untitled.ipynb"),
                code=params.get("code", ""),
                cell_type=params.get("cell_type", "code"),
                position=params.get("position", "end"),
                kernel_id=params.get("kernel_id"),
            )

        elif method == "insert_cell":
            return {
                "cell_id": await self.jupyter_agent.insert_cell(
                    notebook_path=params.get("notebook_path", "Untitled.ipynb"),
                    source=params.get("source", ""),
                    cell_type=params.get("cell_type", "code"),
                    position=params.get("position", "end"),
                )
            }

        elif method == "execute_cell":
            return await self.jupyter_agent.execute_cell(
                notebook_path=params.get("notebook_path", "Untitled.ipynb"),
                cell_id=params.get("cell_id"),
                content=params.get("content"),
                kernel_id=params.get("kernel_id"),
            )

        elif method == "get_cell_content":
            return await self.jupyter_agent.get_cell_content(
                notebook_path=params.get("notebook_path", "Untitled.ipynb"),
                cell_id=params.get("cell_id"),
            )

        elif method == "insert_markdown":
            return {
                "cell_id": await self.jupyter_agent.insert_markdown(
                    notebook_path=params.get("notebook_path", "Untitled.ipynb"),
                    markdown=params.get("markdown", ""),
                    position=params.get("position", "end"),
                )
            }

        elif method == "update_cell_outputs":
            success = await self.jupyter_agent.update_cell_outputs(
                notebook_path=params.get("notebook_path", "Untitled.ipynb"),
                cell_id=params.get("cell_id"),
                outputs=params.get("outputs", []),
                execution_count=params.get("execution_count"),
            )
            return {"success": success}

        else:
            raise ValueError(f"Unknown method: {method}")


class JupyterAgentBridgeExtension(ExtensionApp):
    """JupyterLab extension for JupyterAgent HTTP bridge"""

    name = "jupyter_agent_http_bridge"

    def initialize_handlers(self):
        """Initialize the handlers"""
        self.handlers.extend(
            [
                (r"/api/jupyter_agent/([^/]+)", JupyterAgentHandler),
            ]
        )


# Register the extension
def _jupyter_server_extension_points():
    """Entry point for jupyter server extension"""
    return [
        {
            "module": "jupyter_agent_bridge.http_bridge",
            "app": JupyterAgentBridgeExtension,
        }
    ]
