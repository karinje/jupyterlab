#!/usr/bin/env python3
"""
Test script to show what the logger output actually looks like from different modules.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_from_this_file():
    """Show logging from this test file"""
    print("=" * 60)
    print("1. LOGGING FROM THIS TEST FILE:")
    print("=" * 60)
    
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
    
    logger.info("This message comes from test_actual_logging_output.py")
    logger.warning("This warning comes from test_actual_logging_output.py")
    logger.error("This error comes from test_actual_logging_output.py")

def test_by_creating_jupyter_tools():
    """Show logging by actually using JupyterTools"""
    print("\n" + "=" * 60)
    print("2. LOGGING FROM ACTUAL JUPYTER TOOLS:")
    print("=" * 60)
    
    try:
        # Create a JupyterTools instance which will log from tools.py
        from jupyter_tools_bridge.tools import JupyterTools
        
        # This will trigger logging from tools.py during initialization
        tools = JupyterTools("http://localhost:8888", "fake-token")
        print("✅ JupyterTools created (check logs above for tools.py messages)")
        
    except Exception as e:
        print(f"❌ Failed to create JupyterTools: {e}")

def test_by_importing_agent():
    """Show logging by importing agent components"""
    print("\n" + "=" * 60) 
    print("3. LOGGING FROM AGENT COMPONENTS:")
    print("=" * 60)
    
    try:
        # Add agent path
        agent_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packages", "jupyter-agent")
        if os.path.exists(agent_path):
            sys.path.insert(0, agent_path)
        
        # Import agent components - this should trigger any module-level logging
        from jupyter_agent_lg import agent
        from jupyter_agent_lg.tools import jupyter_tools
        
        print("✅ Agent components imported (check logs above for any agent messages)")
        
    except Exception as e:
        print(f"❌ Failed to import agent: {e}")

def show_format_explanation():
    """Explain what the log format means"""
    print("\n" + "=" * 60)
    print("4. LOG FORMAT EXPLANATION:")
    print("=" * 60)
    print("Format: [timestamp] [filename:line] LEVEL: message")
    print("")
    print("Example: [2025-09-17 19:45:05] [tools.py:123] INFO: Connection successful")
    print("         │                    │            │      │")
    print("         │                    │            │      └─ Your log message")
    print("         │                    │            └─ Log level (INFO/WARNING/ERROR/DEBUG)")
    print("         │                    └─ Filename and line number where log was called")
    print("         └─ Timestamp when the log was generated")
    print("")
    print("🎯 The key benefit: You can see EXACTLY which file and line generated each log!")

if __name__ == "__main__":
    print("🧪 Actual Logging Output Test")
    print("This shows what the logger output looks like from different files")
    
    test_from_this_file()
    test_by_creating_jupyter_tools()
    test_by_importing_agent()
    show_format_explanation()
    
    print("\n" + "=" * 60)
    print("✅ Test completed!")
    print("Notice how each log message shows:")
    print("- The exact filename where it was logged")
    print("- The line number in that file")
    print("- This makes debugging much easier!")
    print("=" * 60) 