# Real-Time YDoc Updates for JupyterLab Agent

## Overview

This implementation provides real-time cell insertion and output updates for JupyterLab notebooks using the YDoc collaboration protocol. Instead of using file-based updates (which have delays), we directly connect to the YDoc WebSocket and send CRDT updates that immediately sync with all connected clients.

## Key Features

1. **Real-time Cell Insertion**: Insert code or markdown cells that appear instantly in the browser
2. **Real-time Output Updates**: Execute code and update cell outputs without delay
3. **Complete Workflow**: Insert cell → Execute code → Update outputs → Validate completion
4. **Kernel Management**: Reuses existing notebook kernels instead of creating new ones

## Architecture

```
Agent (Python) → HTTP API → YDoc WebSocket → JupyterLab Frontend
                     ↓
              handlers.py
                     ↓
            YDoc CRDT Updates
                     ↓
            Real-time Sync
```

## Files

- `jupyter_agent_bridge/handlers.py` - REST API handlers that connect to YDoc WebSocket
- `jupyter_agent_bridge/tools.py` - High-level Python API for agents
- `test_scripts/test_realtime_updates.py` - Test script to verify functionality

## How to Test

### 1. Start JupyterLab

```bash
# Start JupyterLab (make sure collaboration is enabled)
jupyter lab --collaborative
```

### 2. Create/Open a Test Notebook

1. Open JupyterLab in your browser (http://localhost:8888)
2. Create a new notebook or open an existing one (e.g., `test.ipynb`)
3. **IMPORTANT**: Keep the notebook open in your browser to see real-time updates

### 3. Get Your Authentication Token (if needed)

```bash
# List running servers and their tokens
jupyter server list
```

### 4. Run the Test Script

```bash
# Basic test (no auth token)
python test_scripts/test_realtime_updates.py test.ipynb

# With authentication token
python test_scripts/test_realtime_updates.py test.ipynb --token YOUR_TOKEN_HERE

# Custom server URL
python test_scripts/test_realtime_updates.py test.ipynb --url http://localhost:8890
```

### 5. Watch the Magic! ✨

As the test runs, you should see in your browser:
- Cells appearing instantly (no refresh needed)
- Code being inserted in real-time
- Outputs appearing immediately after execution
- Everything syncing without any delay

## What the Test Does

1. **Cell Insertion Test**
   - Inserts a markdown cell at the beginning
   - Inserts a code cell at the end
   - Both should appear instantly in your browser

2. **Code Execution Test**
   - Executes simple print statements
   - Executes code with plots (matplotlib)
   - Captures all output types

3. **Complete Workflow Test**
   - Inserts a code cell
   - Executes the code
   - Updates outputs
   - Validates everything is attached

4. **Output Update Test**
   - Updates outputs of an existing cell
   - Shows real-time synchronization

## Implementation Details

### YDoc Protocol

We use the YJS/YDoc binary protocol for real-time collaboration:

1. **Connect to WebSocket**: `/api/collaboration/room/json:notebook:{path}`
2. **Sync Protocol**:
   - Send sync step 1 (request current state)
   - Receive current YDoc state
   - Apply our changes to the YDoc
   - Send update (diff) back
3. **CRDT Operations**:
   - For cell insertion: `cells.append(new_cell)` or `cells.insert(index, new_cell)`
   - For output updates: `cell["outputs"].clear()` then `cell["outputs"].append(output)`

### Cell Structure (nbformat v4)

```python
{
    "id": "unique-cell-id",
    "cell_type": "code" | "markdown",
    "source": "cell content",
    "metadata": {},
    "outputs": [  # Only for code cells
        {
            "output_type": "stream" | "execute_result" | "display_data" | "error",
            "name": "stdout",  # For stream
            "text": "output text",  # For stream
            "data": {},  # For execute_result/display_data
            "ename": "ErrorName",  # For error
            "evalue": "Error value",  # For error
            "traceback": []  # For error
        }
    ],
    "execution_count": 1  # Only for code cells
}
```

## Troubleshooting

### Cells not appearing in real-time?

1. Make sure the notebook is open in your browser
2. Verify JupyterLab was started with `--collaborative` flag
3. Check the browser console for WebSocket errors
4. Ensure you're using the correct notebook path

### Authentication errors?

1. Get your token: `jupyter server list`
2. Pass it to the test: `--token YOUR_TOKEN`
3. Or disable authentication in Jupyter config

### WebSocket connection failed?

1. Check if JupyterLab is running
2. Verify the server URL (default: http://localhost:8888)
3. Check firewall/proxy settings
4. Look at JupyterLab server logs

## Next Steps

This implementation can be extended to:
1. Support more complex cell operations (move, delete, duplicate)
2. Handle collaborative editing conflicts
3. Add cell metadata updates
4. Support widget outputs
5. Integrate with LangGraph agents

## Technical Notes

- Uses `pycrdt` for CRDT operations
- WebSocket communication via `websockets` library
- Follows YJS sync protocol (compatible with JupyterLab 4.x)
- All updates are real-time (no file watching delays)
- Properly handles all nbformat v4 output types
