__all__ = ["room_proxy"]

from importlib.metadata import version

__version__ = version(__name__) if "jupyter-agent-bridge" in __name__ else "0.0.0"


def _jupyter_server_extension_points():
    return [
        {
            "module": "jupyter_agent_bridge",
        }
    ]


def _load_jupyter_server_extension(server_app):
    from .handlers import setup_handlers

    setup_handlers(server_app)
    server_app.log.info("jupyter-agent-bridge extension loaded (placeholder)")
