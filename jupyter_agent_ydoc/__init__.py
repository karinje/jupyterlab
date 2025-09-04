def _jupyter_server_extension_points():
    return [{"module": "jupyter_agent_ydoc"}]


def _load_jupyter_server_extension(server_app):
    from .handlers import setup_handlers

    setup_handlers(server_app)
    server_app.log.info("Agent YDoc extension loaded")
