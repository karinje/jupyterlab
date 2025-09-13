# Dev Mode Setup Guide

## 🚀 **Quick Dev Mode Setup (No Package Installation Required)**

When using JupyterLab's dev mode flags, you **don't need to install packages**. The extensions are loaded directly from source!

### **1. Install Python Dependencies Only**

The LangGraph agent needs Python dependencies, but you don't need to install the package itself:

```bash
# Install only the Python dependencies
pip install langgraph>=0.2.0 langchain>=0.3.0 langchain-openai>=0.2.0 anthropic>=0.34.0 openai>=1.50.0 pydantic>=2.0.0 aiohttp>=3.9.0
```

Or use the requirements file:
```bash
cd packages/jupyter-agent
pip install -r requirements.txt
```

### **2. Build TypeScript (Optional)**

You can build the TypeScript for better performance, but it's not required in dev mode:

```bash
cd packages/jupyter-agent
npm install
npm run build  # Optional - dev mode can work without this
```

### **3. Start JupyterLab in Dev Mode**

```bash
# This loads extensions from source directories
jupyter lab --dev-mode --extensions-in-dev-mode --port=8890
```

### **4. Enable Frontend Hot Reloading (CRITICAL)**

In a **separate terminal**, run webpack watch for frontend changes:

```bash
cd dev_mode
npm run watch
```

**Without this, TypeScript changes won't appear in the browser!**

## ⚙️ **API Key Configuration**

### **Method 1: JupyterLab Settings (Recommended)**

1. Open JupyterLab Settings → Chat Extension
2. Enter your OpenAI API key in the settings
3. The LangGraph agent will automatically read from there

### **Method 2: Environment Variable (Fallback)**

```bash
export OPENAI_API_KEY="your-openai-key-here"
export ANTHROPIC_API_KEY="your-anthropic-key-here"  # Optional
```

## 📁 **Project Structure in Dev Mode**

```
jupyterlab/
├── packages/jupyter-agent/           # LangGraph agent (no install needed)
│   ├── jupyter_agent_lg/            # Python code (loaded directly)
│   └── src/                         # TypeScript (loaded directly)
├── packages/chat/                   # Chat extension (already working)
├── packages/chat-extension/         # Chat extension plugin
└── dev_mode/                        # Webpack bundler
    └── npm run watch                # MUST run this for frontend changes
```

## 🔧 **How Dev Mode Works**

1. **`--dev-mode`** - Loads extensions from source directories
2. **`--extensions-in-dev-mode`** - Includes local workspace extensions
3. **`dev_mode/npm run watch`** - Bundles TypeScript changes in real-time
4. **Python modules** - Loaded directly from `packages/*/jupyter_*_lg/` directories

## ✅ **Verification Steps**

1. Start JupyterLab with dev flags
2. Start webpack watch in separate terminal
3. Open chat, select LangGraph mode
4. Check logs for: "✅ Using OpenAI API key from JupyterLab settings"
5. Test with a simple request like "create a simple plot"

## 🐛 **Troubleshooting**

### **"Module not found" errors**
```bash
# Install missing Python dependencies
pip install langgraph langchain langchain-openai openai anthropic pydantic
```

### **"API key not found" errors**
- Check JupyterLab Settings → Chat Extension
- Or set `OPENAI_API_KEY` environment variable
- Look for logs: "✅ Using OpenAI API key from..."

### **Frontend changes not appearing**
```bash
# MUST run webpack watch
cd dev_mode && npm run watch
```

### **Import errors in Python**
```bash
# The jupyter_agent_lg module should be importable directly
python -c "from jupyter_agent_lg.agent import DataAnalysisAgent; print('✅ Import works')"
```

## 🎯 **Ready to Use**

Once you have:
- ✅ Python dependencies installed
- ✅ API key configured in JupyterLab settings
- ✅ JupyterLab running with dev flags
- ✅ Webpack watch running

You can immediately use the LangGraph agent without any package installations! 🚀
