# Jupyter Agent YDoc Extension

A Jupyter server extension that provides direct YDoc manipulation for agent-controlled notebook editing with <50ms real-time updates.

## Features

- **Direct YDoc Manipulation**: Insert, update, delete cells instantly
- **Real-time Synchronization**: Changes appear in all browser tabs immediately
- **Agent Integration**: OpenAI Agents SDK compatible tools
- **Progress Tracking**: Optional WebSocket for UX feedback

## Installation

1. Install the extension:
   ```bash
   pip install -e .
   ```

2. Enable the extension:
   ```bash
   jupyter server extension enable jupyter_agent_ydoc
   ```

3. Verify the extension is loaded:
   ```bash
   jupyter server extension list
   ```

## Quick Test

1. Start JupyterLab with collaborative mode:
   ```bash
   jupyter lab --collaborative --ServerApp.token=test123
   ```

2. Create or open a notebook named `test.ipynb`

3. Run the test script:
   ```bash
   python test_direct_ydoc.py
   ```

4. Watch your notebook update in real-time!

## Phase 1 Complete

This Phase 1 implementation includes:
- [x] Minimal server extension package
- [x] YDoc handlers (insert, update, delete, run)
- [x] Direct YDoc manipulation with transactions
- [x] Visual test script
- [x] Multi-tab synchronization

## Next Steps

- Phase 2: OpenAI Agent integration
- Phase 3: Progress WebSocket
- Phase 4: Complete integration testing

## Development

### Dependencies

Required:
- `jupyter_server>=2.0`
- `jupyter_collaboration>=2.0`
- `ypy>=0.6.0`

Test dependencies:
- `rich>=12.0` (for visual test script)
- `aiohttp>=3.8.0`

### API Endpoints

- `POST /api/agent/ydoc/insert` - Insert new cell
- `POST /api/agent/ydoc/update` - Update cell content
- `POST /api/agent/ydoc/delete` - Delete cell
- `POST /api/agent/ydoc/run` - Execute cell (requires kernel)

### Architecture

```
Script/Agent → REST API → YDoc Transaction → RTC Broadcast → Browser Update
```

All updates use atomic YDoc transactions for consistency and automatic CRDT synchronization.
