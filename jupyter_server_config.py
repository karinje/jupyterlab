# Jupyter Server configuration for agent tools and chat extensions
# Enable required server extensions for YDoc and agent functionality

import os

# Set logging levels separately for JupyterLab vs our components
# JupyterLab core logging level (to reduce noise from tornado, jupyter_server, etc.)
JUPYTERLAB_LOG_LEVEL = (
    "WARNING"  # Change to WARNING or ERROR to reduce JupyterLab noise
)

# Our components logging level (for detailed debugging of our code)
JUPYTERLAB_COMPONENTS_LOG_LEVEL = "DEBUG"  # Change to INFO, WARNING, or ERROR

# Set environment variables for our logging config to read
os.environ["JUPYTERLAB_LOG_LEVEL"] = JUPYTERLAB_LOG_LEVEL
os.environ["JUPYTERLAB_COMPONENTS_LOG_LEVEL"] = JUPYTERLAB_COMPONENTS_LOG_LEVEL

# Optional LangSmith/LangGraph tracing defaults.
# Respect any explicit env the user already set; otherwise seed sensible defaults so
# the agent can pick up tracing/logging without extra manual exports.
os.environ.setdefault("JLAB_AGENT_ENABLE_TRACING", "true")
os.environ.setdefault("JLAB_AGENT_DEBUG_LLMS", "false")
os.environ.setdefault("JLAB_AGENT_LOG_OPENAI_PAYLOADS", "true")

# Only backfill the API key if the user hasn't provided one via env already.
langsmith_key = (
    os.environ.get("LANGCHAIN_API_KEY")
    or os.environ.get("LANGSMITH_API_KEY")
    or os.environ.get("LANGGRAPH_API_KEY")
)
if langsmith_key:
    os.environ.setdefault("LANGGRAPH_API_KEY", langsmith_key)
# else: Set LANGCHAIN_API_KEY in your environment or .env file

# Provide a default project name if the caller hasn't already chosen one.
os.environ.setdefault("LANGCHAIN_PROJECT", "jupyterlab-agent")

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
c.LabApp.app_dir = "/Users/sanjaykarinje/git/jupyterlab_v1/dev_mode"
c.LabApp.dev_mode = True
c.LabServerApp.app_dir = "/Users/sanjaykarinje/git/jupyterlab_v1/dev_mode"
c.LabServerApp.dev_mode = True

print("🚀 JupyterLab configured:")
print(f"   JupyterLab core logging: {JUPYTERLAB_LOG_LEVEL}")
print(f"   Our components logging: {JUPYTERLAB_COMPONENTS_LOG_LEVEL}")
print("💡 To change logging levels, edit the variables in jupyter_server_config.py")
print("")
print("🚀 Start JupyterLab with proper dev mode flags:")
print(
    "   jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py"
)
print("")
print("📝 To pipe logs to file:")
print(
    "   jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py > jupyterlab_debug.log 2>&1"
)
