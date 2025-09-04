# Development Jupyter configuration to load our agent extension
c = get_config()

# Enable our extension
c.ServerApp.jpserver_extensions = {
    "jupyter_agent_ydoc": True,
    "jupyterlab": True,
    "jupyter_server_ydoc": True,
}

# Development settings
c.ServerApp.token = "test123"
c.ServerApp.disable_check_xsrf = True
c.ServerApp.allow_root = True
c.ServerApp.open_browser = False

# Enable collaboration
c.YDocExtension.collaborative = True
