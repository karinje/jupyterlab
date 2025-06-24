#!/bin/bash
# Complete installation script for JupyterLab Chat MCP integration

echo "🚀 Installing JupyterLab Chat MCP Integration..."

# Get the current directory
CHAT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "📍 Working in: $CHAT_DIR"

# 1. Install Python dependencies
echo "📦 Installing Python dependencies..."
cd "$CHAT_DIR/python"
pip3 install -r requirements.txt

# 2. Install the Jupyter server extension
echo "🔧 Installing Jupyter server extension..."
cd "$CHAT_DIR"
pip3 install -e .

# 3. Enable the server extension
echo "✅ Enabling server extension..."
jupyter server extension enable jupyter_server_extension

# 4. Build the frontend (if not already built)
echo "🏗️  Building frontend..."
cd "$CHAT_DIR/../.."
npm run build

echo ""
echo "🎉 Installation complete!"
echo ""
echo "📝 Next steps:"
echo "1. Set your OpenAI API key: export OPENAI_API_KEY='your-key'"
echo "2. Restart JupyterLab: jupyter lab"
echo "3. Configure MCP servers in Settings > Chat"
echo "4. Use Ctrl+Shift+Space to open chat"
echo ""
echo "🔍 To test the server extension:"
echo "curl -X POST http://localhost:8888/api/chat/mcp \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"config\":{\"openai_api_key\":\"your-key\"},\"message\":\"Hello\"}'"
