# Jupyter Server configuration for agent tools and chat extensions
# Enable required server extensions for YDoc and agent functionality

c.ServerApp.jpserver_extensions = {
    "jupyter_server_fileid": True,
    "jupyter_server_ydoc": True,
    # NOTE: jupyter_collaboration will FAIL to load (missing entry point)
    # but the package installation is still REQUIRED for YDoc to work
    "jupyter_tools_bridge": True,
    "jupyterlab_chat": True,
}

# CRITICAL: Enable collaborative mode for YDoc document tracking
c.YDocExtension.collaborative = True

# Optional: Fix WebSocket ping configuration warnings
c.ServerApp.websocket_ping_interval = 30
c.ServerApp.websocket_ping_timeout = 25

# Log level for debugging
c.ServerApp.log_level = "INFO"

# Disable authentication for local testing (remove in production!)
c.ServerApp.token = ""
c.ServerApp.password = ""

# Explicitly pin JupyterLab dev app assets
c.LabApp.app_dir = "/Users/sanjaykarinje/git/jupyterlab/dev_mode"
c.LabApp.dev_mode = True
c.LabServerApp.app_dir = "/Users/sanjaykarinje/git/jupyterlab/dev_mode"
c.LabServerApp.dev_mode = True
