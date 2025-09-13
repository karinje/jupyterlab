"""
Jupyter Server configuration for ensuring proper extension loading order.
"""

c = get_config()  # noqa

# Ensure collaboration extensions load first
c.ServerApp.jpserver_extensions = {
    "jupyter_server_fileid": True,
    "jupyter_server_ydoc": True,
    "jupyter_collaboration": True,
    "jupyter_tools_bridge": True,  # Our extension loads after collaboration
}

# Enable collaborative mode
c.YDocExtension.collaborative = True

# Log level for debugging
c.ServerApp.log_level = "INFO"

# Disable authentication for local testing (remove in production!)
c.ServerApp.token = ""
c.ServerApp.password = ""
