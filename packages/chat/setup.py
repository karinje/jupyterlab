from setuptools import setup

setup(
    name="jupyterlab-chat",
    version="0.1.0",
    description="JupyterLab Chat Extension with MCP support",
    packages=["jupyterlab_chat"],
    install_requires=[
        "jupyter-server>=1.0.0",
        "openai-agents",
    ],
    entry_points={
        "jupyter_server.extension_points": [
            "jupyterlab_chat = jupyterlab_chat:_jupyter_server_extension_points"
        ]
    },
)
