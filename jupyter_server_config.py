# Jupyter Server configuration for agent tools and chat extensions
# Enable required server extensions for YDoc and agent functionality

import os

# Set logging levels separately for JupyterLab vs our components
# JupyterLab core logging level (to reduce noise from tornado, jupyter_server, etc.)
JUPYTERLAB_LOG_LEVEL = "WARNING"  # Change to WARNING or ERROR to reduce JupyterLab noise

# Our components logging level (for detailed debugging of our code)  
JUPYTERLAB_COMPONENTS_LOG_LEVEL = "DEBUG"  # Change to INFO, WARNING, or ERROR

# Set environment variables for our logging config to read
os.environ["JUPYTERLAB_LOG_LEVEL"] = JUPYTERLAB_LOG_LEVEL
os.environ["JUPYTERLAB_COMPONENTS_LOG_LEVEL"] = JUPYTERLAB_COMPONENTS_LOG_LEVEL

c = get_config()  # noqa

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
c.ServerApp.log_level = JUPYTERLAB_LOG_LEVEL

# Disable authentication for local testing (remove in production!)
c.ServerApp.token = ""
c.ServerApp.password = ""

# Explicitly pin JupyterLab dev app assets
c.LabApp.app_dir = "/Users/sanjaykarinje/git/jupyterlab/dev_mode"
c.LabApp.dev_mode = True
c.LabServerApp.app_dir = "/Users/sanjaykarinje/git/jupyterlab/dev_mode"
c.LabServerApp.dev_mode = True

print(f"🚀 JupyterLab configured:")
print(f"   JupyterLab core logging: {JUPYTERLAB_LOG_LEVEL}")
print(f"   Our components logging: {JUPYTERLAB_COMPONENTS_LOG_LEVEL}")
print("💡 To change logging levels, edit the variables in jupyter_server_config.py")
print("")
print("🚀 Start JupyterLab with proper dev mode flags:")
print("   jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py")
print("")
print("📝 To pipe logs to file:")
print("   jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py > jupyterlab_debug.log 2>&1")
