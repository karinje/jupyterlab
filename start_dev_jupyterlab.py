#!/usr/bin/env python3
"""
Development startup script for JupyterLab with our YDoc extension
Uses the local development version of JupyterLab, not system install
"""

import sys
import os
import logging
from pathlib import Path

# Add current directory to Python path so we can import our extension
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Start development JupyterLab with our extension"""

    # Import from local development JupyterLab
    try:
        from jupyterlab.labapp import LabApp

        logger.info(
            "✓ Using development JupyterLab from: %s",
            Path(__file__).parent / "jupyterlab",
        )
    except ImportError:
        logger.error(
            "✗ Could not import development JupyterLab. Make sure you're in the jupyterlab repo directory."
        )
        return 1

    # Create LabApp instance
    app = LabApp()

    # Configure for development and collaboration
    app.allow_root = True
    app.token = "test123"
    app.disable_check_xsrf = True
    app.open_browser = True
    app.collaborative = True  # Enable collaborative mode for YDoc

    # Manually load our extension before starting
    try:
        logger.info("Loading jupyter_agent_bridge extension...")
        from jupyter_agent_bridge import _load_jupyter_server_extension

        _load_jupyter_server_extension(app)
        logger.info("✓ Agent bridge extension loaded successfully!")

        # Show available endpoints
        logger.info("Available endpoints:")
        logger.info("  JupyterAgent with consistent YDoc handlers:")
        logger.info("    - Cell insertion: YDoc handler (proper auth + real-time)")
        logger.info("    - Output updates: YDoc handler (proper auth + real-time)")
        logger.info("    - Code execution: Kernel WebSocket")
        logger.info("  POST /api/agent/notebook/insert - YDoc cell insertion")
        logger.info("  POST /api/agent/notebook/update_outputs - YDoc output updates")

    except Exception as e:
        logger.error("✗ Failed to load YDoc extension: %s", e)
        logger.info("Continuing without YDoc extension...")

    # Start the application
    logger.info("🚀 Starting development JupyterLab...")
    logger.info("📍 URL: http://localhost:8888/?token=test123")
    logger.info("🔑 Token: test123")
    logger.info("📁 Root: %s", os.getcwd())

    try:
        app.start()
    except KeyboardInterrupt:
        logger.info("🛑 JupyterLab stopped")
        return 0
    except Exception as e:
        logger.error("💥 Error starting JupyterLab: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
