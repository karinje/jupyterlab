#!/usr/bin/env python3
"""
LangGraph Agent Setup Verification Script

Run this script to verify that your LangGraph agent setup is correct.
"""

import os
import sys
import json
from pathlib import Path


def check_python_dependencies():
    """Check if required Python dependencies are installed"""
    print("🔍 Checking Python dependencies...")

    required_packages = [
        "langgraph",
        "langchain",
        "langchain_openai",
        "openai",
        "anthropic",
        "pydantic",
        "aiohttp",
    ]

    missing_packages = []

    for package in required_packages:
        try:
            if package == "langchain_openai":
                import langchain_openai
            else:
                __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package}")
            missing_packages.append(package)

    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Install with: pip install " + " ".join(missing_packages))
        return False
    else:
        print("✅ All Python dependencies installed!")
        return True


def check_langgraph_agent():
    """Check if LangGraph agent modules can be imported"""
    print("\n🔍 Checking LangGraph agent modules...")

    try:
        # Add packages directory to Python path
        packages_dir = Path(__file__).parent / "packages" / "jupyter-agent"
        if packages_dir.exists():
            sys.path.insert(0, str(packages_dir))

        from jupyter_agent_lg.agent import DataAnalysisAgent
        from jupyter_agent_lg.state import StateManager, PlanStep
        from jupyter_agent_lg.llm import LLMRouter, OpenAILLM
        from jupyter_agent_lg.context import NotebookStateManager

        print("  ✅ DataAnalysisAgent")
        print("  ✅ StateManager")
        print("  ✅ LLMRouter")
        print("  ✅ NotebookStateManager")
        print("✅ LangGraph agent modules importable!")
        return True

    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        print("❌ LangGraph agent modules not importable!")
        return False


def check_api_key():
    """Check if OpenAI API key is configured"""
    print("\n🔍 Checking OpenAI API key configuration...")

    # Check environment variable
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        print("  ✅ Found in environment variable")
        return True

    # Check JupyterLab settings
    try:
        from jupyter_core.paths import jupyter_config_dir

        config_dir = jupyter_config_dir()
        settings_file = (
            Path(config_dir)
            / "lab"
            / "user-settings"
            / "@jupyterlab"
            / "chat-extension"
            / "plugin.jupyterlab-settings"
        )

        if settings_file.exists():
            with open(settings_file, "r") as f:
                settings_data = json.load(f)
                api_key = settings_data.get("openaiApiKey", "").strip()
                if api_key:
                    print("  ✅ Found in JupyterLab settings")
                    return True
                else:
                    print("  ⚠️ Settings file exists but no API key found")
        else:
            print("  ⚠️ JupyterLab settings file not found")

    except Exception as e:
        print(f"  ⚠️ Error checking JupyterLab settings: {e}")

    print("❌ No OpenAI API key found!")
    print("Configure via:")
    print("  1. JupyterLab Settings → Chat Extension")
    print("  2. Or: export OPENAI_API_KEY='your-key'")
    return False


def check_jupyter_agent_bridge():
    """Check if jupyter_agent_bridge is available"""
    print("\n🔍 Checking jupyter_agent_bridge...")

    try:
        from jupyter_agent_bridge.tools import JupyterAgent

        print("  ✅ JupyterAgent tools available")
        return True
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        print("❌ jupyter_agent_bridge not available!")
        print("Make sure the core agent tools are set up.")
        return False


def check_project_structure():
    """Check if project structure is correct"""
    print("\n🔍 Checking project structure...")

    base_path = Path(__file__).parent
    required_paths = [
        "packages/jupyter-agent/jupyter_agent_lg/__init__.py",
        "packages/jupyter-agent/jupyter_agent_lg/agent.py",
        "packages/jupyter-agent/jupyter_agent_lg/state.py",
        "packages/jupyter-agent/jupyter_agent_lg/llm.py",
        "packages/jupyter-agent/jupyter_agent_lg/context.py",
        "packages/chat/src/widget.tsx",
        "packages/chat/src/llm.ts",
        "packages/chat/jupyterlab_chat/__init__.py",
        "dev_mode/package.json",
    ]

    all_good = True
    for path_str in required_paths:
        path = base_path / path_str
        if path.exists():
            print(f"  ✅ {path_str}")
        else:
            print(f"  ❌ {path_str}")
            all_good = False

    if all_good:
        print("✅ Project structure looks good!")
    else:
        print("❌ Some files are missing!")

    return all_good


def main():
    """Run all setup checks"""
    print("🤖 LangGraph Agent Setup Verification")
    print("=" * 50)

    checks = [
        ("Python Dependencies", check_python_dependencies),
        ("Project Structure", check_project_structure),
        ("LangGraph Agent Modules", check_langgraph_agent),
        ("Jupyter Agent Bridge", check_jupyter_agent_bridge),
        ("OpenAI API Key", check_api_key),
    ]

    results = {}
    for name, check_func in checks:
        results[name] = check_func()

    print("\n" + "=" * 50)
    print("📊 SETUP VERIFICATION SUMMARY")
    print("=" * 50)

    all_good = True
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
        if not result:
            all_good = False

    print("\n" + "=" * 50)
    if all_good:
        print("🎉 ALL CHECKS PASSED!")
        print("\nYou're ready to use the LangGraph agent!")
        print("\nNext steps:")
        print("1. jupyter lab --dev-mode --extensions-in-dev-mode --port=8890")
        print("2. cd dev_mode && npm run watch  (in separate terminal)")
        print("3. Open chat and select LangGraph mode")
    else:
        print("❌ SOME CHECKS FAILED!")
        print("\nPlease fix the issues above before using the LangGraph agent.")
        print("\nSee DEV_MODE_SETUP.md for detailed setup instructions.")

    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
