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
    web_app.settings["serverapp"] = server_app  # Store server app reference

    # Try to get YDocExtension instance and store it in settings
    try:
        from jupyter_server_ydoc import YDocExtension

        # YDocExtension should already be loaded at this point
        ydoc_ext = YDocExtension.instance()
        if ydoc_ext:
            web_app.settings["ydoc_extension"] = ydoc_ext
            server_app.log.info("Stored YDocExtension instance in settings")
        else:
            server_app.log.warning("YDocExtension.instance() returned None")
    except Exception as e:
        server_app.log.error(f"Failed to get YDocExtension: {e}")

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
    This is where we can access the collaboration infrastructure.
    """
    web_app = server_app.web_app

    # The YDocExtension stores collaboration infrastructure in web_app.settings
    # We need: file_loaders, ywebsocket_server, file_id_manager

    required_components = ["file_loaders", "ywebsocket_server", "file_id_manager"]
    missing_components = []

    for component in required_components:
        if component not in web_app.settings:
            missing_components.append(component)
        else:
            server_app.log.info(
                f"✅ Found {component}: {type(web_app.settings[component])}"
            )

    if missing_components:
        server_app.log.error(
            f"❌ Missing collaboration components: {missing_components}"
        )
        server_app.log.error("Real-time features will not work!")
    else:
        server_app.log.info(
            "✅ All collaboration components found - real-time features ready!"
        )
        # The components exist in web_app.settings, but handlers access self.settings
        # So we don't need to do anything extra - they're already accessible


# For backward compatibility
load_jupyter_server_extension = _load_jupyter_server_extension
