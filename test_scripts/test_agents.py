#!/usr/bin/env python3
import json


def test_imports():
    try:
        from agents import Agent, run
        from agents.mcp import MCPServerStdio

        return {"success": True, "message": "All imports successful"}
    except ImportError as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = test_imports()
    print(json.dumps(result))
