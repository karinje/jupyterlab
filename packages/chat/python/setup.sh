#!/bin/bash
# Setup script for JupyterLab Chat MCP Python Bridge

echo "🐍 Setting up Python environment for JupyterLab Chat MCP integration..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed. Please install Python 3.8 or later."
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "📍 Found Python $python_version"

# Install requirements
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Verify installation
echo "🔍 Verifying installation..."
python3 -c "
try:
    from agents import Agent, Runner
    from agents.mcp.server import MCPServerStdio
    from agents.models import OpenAIChatCompletionsModel
    print('✅ OpenAI Agents SDK installed successfully')
except ImportError as e:
    print('❌ Failed to import OpenAI Agents SDK:', e)
    exit(1)
"

echo "🎉 Setup complete! JupyterLab Chat MCP integration is ready."
echo ""
echo "📝 Next steps:"
echo "1. Set your OPENAI_API_KEY environment variable"
echo "2. Configure MCP servers in JupyterLab Settings > Chat"
echo "3. Restart JupyterLab to use the new MCP integration"
