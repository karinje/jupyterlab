"""
Jupyter Tools Bridge - Server extension for notebook manipulation tools.
"""

from jupyter_server.utils import url_path_join
from .handlers import url_handlers


def _jupyter_server_extension_points():
    """
    Entry point for Jupyter Server extension.
    """
    return [{"module": "jupyter_tools_bridge"}]


def _load_jupyter_server_extension(server_app):
    """
    Load the Jupyter server extension.

    Args:
        server_app: The Jupyter server application instance
    """
    web_app = server_app.web_app

    # Store references in settings for handlers to access
    web_app.settings["kernel_manager"] = server_app.kernel_manager
    web_app.settings["session_manager"] = server_app.session_manager
    web_app.settings["contents_manager"] = server_app.contents_manager
    # Store server app reference for handlers
    web_app.settings["serverapp"] = server_app

    # Store contents_manager in settings for handlers to access
    web_app.settings["contents_manager"] = server_app.contents_manager
    
    # Note: YDoc extension is automatically available in web_app.settings["jupyter_server_ydoc"]
    # This is set by the jupyter_server_ydoc extension framework automatically
    
    # Register handlers
    base_url = web_app.settings["base_url"]
    for pattern, handler in url_handlers:
        full_pattern = url_path_join(base_url, pattern)
        web_app.add_handlers(".*$", [(full_pattern, handler)])
        server_app.log.info(f"Registered tools handler: {full_pattern}")
    
    server_app.log.info("Jupyter Tools Bridge extension loaded successfully")


async def _start_jupyter_server_extension(server_app):
    """
    Called after all extensions are loaded and the server is running.
    Extension initialization is complete - no additional setup needed.
    """
    server_app.log.info("✅ Jupyter Tools Bridge startup complete - YDoc tools ready")


# For backward compatibility
load_jupyter_server_extension = _load_jupyter_server_extension
