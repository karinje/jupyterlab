#!/usr/bin/env python3
import asyncio
import json
import os
import subprocess
import sys

async def test_mcp_server():
    """Test the MCP server by simulating JupyterLab's communication"""
    
    # Set environment variables (same as JupyterLab settings)
    env = os.environ.copy()
    env.update({
        "SNOWFLAKE_USER": "TOTCOTTAGE",
        "SNOWFLAKE_PASSWORD": "",  # Replace with real password
        "SNOWFLAKE_ACCOUNT": "NPOVSJB-PNB00757", 
        "SNOWFLAKE_DATABASE": "SNOWFLAKE_LEARNING_DB",
        "SNOWFLAKE_WAREHOUSE": "SNOWFLAKE_LEARNING_WH"
    })
    
    # Start the MCP server process (same as JupyterLab does)
    process = subprocess.Popen(
        ["python", "mcp-snowflake-service/server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=0
    )
    
    try:
        print("🔍 Testing MCP server connection...")
        
        # Send initialization message (MCP protocol)
        init_message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        print(f"📤 Sending: {init_message}")
        process.stdin.write(json.dumps(init_message) + "\n")
        process.stdin.flush()
        
        # Read response
        response_line = process.stdout.readline()
        print(f"📥 Received: {response_line.strip()}")
        
        # Send initialized notification (required by MCP protocol)
        initialized_message = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        
        print(f"📤 Sending: {initialized_message}")
        process.stdin.write(json.dumps(initialized_message) + "\n")
        process.stdin.flush()
        
        # Wait a moment for initialization to complete
        await asyncio.sleep(0.1)
        
        # Send list tools request
        list_tools_message = {
            "jsonrpc": "2.0", 
            "id": 2,
            "method": "tools/list"
        }
        
        print(f"📤 Sending: {list_tools_message}")
        process.stdin.write(json.dumps(list_tools_message) + "\n")
        process.stdin.flush()
        
        # Read response
        response_line = process.stdout.readline()
        print(f"📥 Received: {response_line.strip()}")
        
        # Test a simple query
        query_message = {
            "jsonrpc": "2.0",
            "id": 3, 
            "method": "tools/call",
            "params": {
                "name": "execute_query",
                "arguments": {
                    "query": "SELECT 1 as test"
                }
            }
        }
        
        print(f"📤 Sending: {query_message}")
        process.stdin.write(json.dumps(query_message) + "\n")
        process.stdin.flush()
        
        # Read response
        response_line = process.stdout.readline()
        print(f"📥 Received: {response_line.strip()}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        # Clean up
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        
        if stderr:
            print(f"🔍 Server stderr: {stderr}")
            
        print("✅ Test completed")

if __name__ == "__main__":
    print("🧪 Testing MCP Snowflake server...")
    print("📝 Make sure to replace 'your_actual_password_here' with the real password!")
    asyncio.run(test_mcp_server()) 