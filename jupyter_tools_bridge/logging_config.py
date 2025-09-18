"""
Simplified logging configuration for JupyterLab components.

This module sets up a single, well-formatted logger for all components.
"""

import logging
import sys
import os
from typing import Optional


class JupyterLabFormatter(logging.Formatter):
    """Custom formatter that shows clean folder structure instead of full paths"""
    
    def format(self, record):
        # Get the pathname and make it relative to the project root
        pathname = record.pathname
        
        # Try to make path relative to the jupyterlab project root
        try:
            # Find the jupyterlab directory in the path
            if 'jupyterlab' in pathname:
                parts = pathname.split(os.sep)
                if 'jupyterlab' in parts:
                    # Get everything after 'jupyterlab'
                    jupyterlab_index = parts.index('jupyterlab')
                    relative_parts = parts[jupyterlab_index + 1:]
                    if relative_parts:
                        clean_path = '/'.join(relative_parts)
                    else:
                        clean_path = parts[-1]  # Just filename if at jupyterlab root
                else:
                    clean_path = os.path.basename(pathname)
            else:
                clean_path = os.path.basename(pathname)
        except:
            # Fallback to just filename if path processing fails
            clean_path = os.path.basename(pathname)
        
        # Create the log record with clean path
        record.clean_pathname = clean_path
        
        # Use the parent format method
        return super().format(record)


def setup_jupyterlab_logging(
    level: str = None, 
    our_components_level: str = None,
    format_string: Optional[str] = None,
    force_setup: bool = False
) -> None:
    """
    Set up simplified logging for all JupyterLab components.
    
    Args:
        level: General logging level for JupyterLab (INFO, WARNING, ERROR)
        our_components_level: Logging level for our components (DEBUG, INFO, WARNING, ERROR)
        format_string: Custom format string for log messages
        force_setup: Force setup even if already configured
    """
    # Get log levels from environment if not specified
    if level is None:
        level = os.getenv("JUPYTERLAB_LOG_LEVEL", "INFO")
    if our_components_level is None:
        our_components_level = os.getenv("JUPYTERLAB_COMPONENTS_LOG_LEVEL", "DEBUG")
    
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Check if already configured (unless forced)
    if not force_setup and root_logger.handlers:
        return
    
    # Set up the format with clean folder structure
    if format_string is None:
        format_string = '[%(asctime)s] [%(clean_pathname)s:%(lineno)d] %(levelname)s: %(message)s'
    
    formatter = JupyterLabFormatter(format_string, datefmt='%Y-%m-%d %H:%M:%S')
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)  # Handler accepts all levels
    console_handler.setFormatter(formatter)
    
    # Configure root logger to accept all levels
    root_logger.setLevel(logging.DEBUG)
    
    # Only add handler if not already present
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        root_logger.addHandler(console_handler)
    
    # MUCH BETTER APPROACH: Use a custom filter instead of listing every component
    class ComponentLevelFilter(logging.Filter):
        """Filter that sets different log levels based on logger name patterns"""
        
        def filter(self, record):
            logger_name = record.name
            
            # Our components get detailed logging (DEBUG level)
            our_patterns = [
                'jupyterlab',  # Our single logger
                'packages.chat.',
                'packages.jupyter-agent.',
                'jupyter_tools_bridge',
                'jupyter_agent_lg',
            ]
            
            # Check if this is one of our components
            is_our_component = any(logger_name.startswith(pattern) for pattern in our_patterns)
            
            if is_our_component:
                # Our components: allow if level >= our_components_level (DEBUG)
                return record.levelno >= getattr(logging, our_components_level.upper())
            else:
                # Everything else: allow if level >= general level (INFO/WARNING/ERROR)
                return record.levelno >= getattr(logging, level.upper())
    
    # Apply the filter to our handler
    console_handler.addFilter(ComponentLevelFilter())


def get_logger(name: str = "jupyterlab") -> logging.Logger:
    """
    Get the configured logger.
    
    Args:
        name: Logger name (defaults to "jupyterlab")
        
    Returns:
        Configured logger instance
    """
    # Ensure logging is set up
    setup_jupyterlab_logging()
    
    # Return the single logger
    return logging.getLogger("jupyterlab")


# Auto-setup when module is imported
setup_jupyterlab_logging() 