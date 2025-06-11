# Testing the JupyterLab Chat Interface

## ✅ Fixed Setup and Build Steps

1. **Install dependencies:**
   ```bash
   cd /Users/sanjaykarinje/git/jupyterlab
   pip install -e .
   jlpm install  # This updates the lockfile for new packages
   ```

2. **Build all packages:**
   ```bash
   jlpm build:all  # This builds all packages including extensions
   ```

3. **Build JupyterLab in development mode:**
   ```bash
   cd dev_mode
   jlpm build
   ```

## Testing the Chat Interface

### 1. Launch JupyterLab
```bash
jupyter lab --dev-mode
```

### 2. Configure API Keys

**Option A: Via Settings UI**
- Go to Settings → Settings Editor
- Find "Chat" in the left panel
- Add your API keys:
  - OpenAI API Key: `sk-...` 
  - Claude API Key: `sk-ant-...`
  - Choose your preferred provider

**Option B: Via Settings File**
Create `~/.jupyter/lab/user-settings/@jupyterlab/chat-extension/plugin.jupyterlab-settings`:
```json
{
  "provider": "openai",
  "openaiApiKey": "sk-your-openai-key-here",
  "openaiModel": "gpt-3.5-turbo"
}
```

### 3. Open Chat Interface

**Method 1: Command Palette**
- Press `Cmd/Ctrl + Shift + C` → Search "Open Chat" → Execute

**Method 2: Via Console**
```javascript
// In browser console
app.commands.execute('chat:open');
```

## ✅ Ready to Test!

The build completed successfully with only warnings (which are normal). Your chat interface should now be available in JupyterLab.

## Testing Scenarios

### Basic Chat Functionality

1. **Simple conversation:**
   - Type: "Hello! Can you help me with Python?"
   - Verify: Assistant responds appropriately

2. **Code assistance:**
   - Type: "Write a function to calculate fibonacci numbers"
   - Verify: Assistant provides code example

### Cell Interaction Features

1. **Reading cells:**
   ```
   User: "What's in cell 0?"
   Expected: Assistant describes the content of the first cell
   ```

2. **Cell manipulation:**
   ```
   User: "Add a cell with print('Hello World')"
   Expected: New code cell is inserted with the content
   ```

3. **Cell execution:**
   ```
   User: "Execute cell 0"  
   Expected: The first cell runs and shows output
   ```

4. **Cell modification:**
   ```
   User: "Modify cell 1 with: import pandas as pd"
   Expected: Cell 1 content is updated
   ```

### Testing Different LLM Providers

**OpenAI Testing:**
```json
{
  "provider": "openai",
  "openaiApiKey": "sk-...",
  "openaiModel": "gpt-3.5-turbo"
}
```

**Claude Testing:**
```json
{
  "provider": "claude", 
  "claudeApiKey": "sk-ant-...",
  "claudeModel": "claude-3-sonnet-20240229"
}
```

**Local Model Testing (Ollama):**
```json
{
  "provider": "local",
  "localUrl": "http://localhost:11434",
  "localModel": "llama2"
}
```

## Debugging

### Check Browser Console
```javascript
// Check if extension loaded
console.log(app.commands.hasCommand('chat:open'));
```

### Common Issues

1. **Chat panel not opening:**
   - Check browser console for errors
   - Try: `app.commands.execute('chat:open')`

2. **API key errors:**
   - Verify API key format in settings
   - Check network requests in DevTools

3. **Cell operations not working:**
   - Ensure a notebook is open and active
   - Check that cells exist at the referenced indices

## 🎉 You're Ready!

The chat interface is now built and ready for testing. Launch JupyterLab with `jupyter lab --dev-mode` and start chatting! 