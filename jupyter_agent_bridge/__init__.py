__all__ = ["JupyterAgent", "RoomProxy"]

from importlib.metadata import version

__version__ = version(__name__) if "jupyter-agent-bridge" in __name__ else "0.0.0"

# Import the main classes for external use
from .tools import JupyterAgent
from .room_proxy import RoomProxy


def _jupyter_server_extension_points():
    return [
        {
            "module": "jupyter_agent_bridge",
        }
    ]


def _load_jupyter_server_extension(server_app):
    # Load the essential handlers that JupyterAgent needs
    from .handlers import setup_handlers
    
    setup_handlers(server_app)
    server_app.log.info("jupyter-agent-bridge extension loaded (tools + handlers)")
