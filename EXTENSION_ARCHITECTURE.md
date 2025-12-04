# JupyterLab AI Workbench - Extension Architecture & Modularization Plan

> **Purpose**: This document defines the architecture for converting the current ~21,000 line monolithic implementation into modular, distributable JupyterLab extensions. It also outlines the extensibility framework for future features.

---

## Table of Contents

1. [Vision & Goals](#1-vision--goals)
2. [JupyterLab Extension System Explained](#2-jupyterlab-extension-system-explained)
3. [Current Codebase → Extension Mapping](#3-current-codebase--extension-mapping)
4. [Extension Specifications](#4-extension-specifications)
5. [Inter-Extension Communication](#5-inter-extension-communication)
6. [Build & Packaging Workflow](#6-build--packaging-workflow)
7. [Migration Plan](#7-migration-plan)
8. [Future Extensions Roadmap](#8-future-extensions-roadmap)
9. [Distribution Strategy](#9-distribution-strategy)

---

## 1. Vision & Goals

### Product Vision

Create "DataLab" - an AI-native analytics workbench for data professionals, similar to how Cursor forked VS Code for developers. The platform will:

- Tightly integrate databases, dashboards, spreadsheets
- Connect upstream sources (Snowflake, BigQuery, APIs)
- Connect downstream destinations (CRM, ad systems, reports)
- Provide AI chat with tools for analytics, modeling, dashboarding
- Deliver everything in one seamless application

### Architecture Goals

| Goal | Approach |
|------|----------|
| **Modularity** | Each feature is a separate extension |
| **Extensibility** | Plugin system for future features |
| **Portability** | Extensions work on vanilla JupyterLab |
| **Maintainability** | Clear boundaries, independent versioning |
| **Bundleability** | Can package everything as single product |

### Development Strategy

```
Phase 1: Development
────────────────────
Build features as independent extensions
Test on vanilla JupyterLab
Each extension has own repo/versioning

Phase 2: Distribution  
─────────────────────
Bundle extensions with JupyterLab
Create branded "DataLab" distribution
Single install experience

Phase 3: Product
────────────────
Desktop app (Electron wrapper)
Cloud-hosted version
Enterprise features
```

---

## 2. JupyterLab Extension System Explained

### 2.1 Extension Types

JupyterLab has TWO types of extensions that work together:

#### Frontend Extension (TypeScript/JavaScript)

Runs in the browser, provides UI components.

```typescript
// src/index.ts
import { JupyterFrontEndPlugin } from '@jupyterlab/application';

const plugin: JupyterFrontEndPlugin<void> = {
  id: '@org/my-extension:plugin',
  autoStart: true,
  requires: [INotebookTracker],
  activate: (app, tracker) => {
    // Register commands, widgets, etc.
  }
};

export default plugin;
```

Declared in `package.json`:
```json
{
  "jupyterlab": {
    "extension": true
  }
}
```

#### Server Extension (Python)

Runs on the server, provides REST/WebSocket endpoints.

```python
# __init__.py
def _jupyter_server_extension_points():
    return [{"module": "my_extension"}]

def _load_jupyter_server_extension(server_app):
    # Register handlers
    server_app.web_app.add_handlers(".*$", handlers)
```

Declared in `pyproject.toml`:
```toml
[project.entry-points."jupyter_server.extension.v1"]
my_extension = "my_extension"
```

### 2.2 Combined Frontend + Backend Extension

A single Python package can contain BOTH frontend and backend:

```
my-extension/
├── pyproject.toml              ← Python package definition
├── package.json                ← npm package definition
├── my_extension/               ← Python backend
│   ├── __init__.py             ← Server extension entry
│   ├── handlers.py             ← REST endpoints
│   └── labextension/           ← Pre-built frontend (generated)
│       ├── package.json
│       └── static/*.js
├── src/                        ← TypeScript frontend source
│   └── index.ts
└── style/
    └── index.css
```

### 2.3 How Installation Works

```
DEVELOPER (builds the extension)
────────────────────────────────
src/*.ts ──jlpm build──► lib/*.js ──jupyter labextension build──► labextension/

pyproject.toml + labextension/ ──python -m build──► dist/*.whl


USER (installs the extension)
─────────────────────────────
pip install my-extension
    │
    ├──► site-packages/my_extension/        (Python code)
    ├──► share/jupyter/labextensions/@org/  (Pre-built JS)
    └──► etc/jupyter/jupyter_server_config.d/ (Auto-enable)


USER (runs JupyterLab)
──────────────────────
jupyter lab
    │
    ├──► Loads server extension (Python)
    └──► Loads frontend extension (pre-built JS)
    
NO npm/yarn needed on user machine!
```

### 2.4 Extension Dependencies

Extensions CAN depend on other extensions:

**Python dependencies** (pyproject.toml):
```toml
[project]
dependencies = [
    "jupyterlab-notebook-tools>=0.1.0",  # Another extension!
    "langchain>=0.1.0",
]
```

**Frontend dependencies** (package.json):
```json
{
  "dependencies": {
    "@org/notebook-tools": "^0.1.0"
  },
  "jupyterlab": {
    "sharedPackages": {
      "@org/notebook-tools": {
        "bundled": false,
        "singleton": true
      }
    }
  }
}
```

### 2.5 Key Files Explained

| File | Purpose | Auto-generated? |
|------|---------|-----------------|
| `package.json` | npm dependencies, build scripts | No - you write it |
| `yarn.lock` | Locked npm versions | Yes - by yarn |
| `package-lock.json` | npm's lock file | Yes - DELETE if using yarn |
| `pyproject.toml` | Python package config | No - you write it |
| `labextension/` | Pre-built frontend | Yes - by build process |

---

## 3. Current Codebase → Extension Mapping

### 3.1 Current Structure (Monolithic)

```
jupyterlab/ (fork)
├── packages/
│   ├── chat/                        ← Frontend library + Python backend
│   │   ├── src/*.ts                 ← TypeScript (6 files, ~3,400 lines)
│   │   ├── jupyterlab_chat/         ← Python (1 file, ~2,200 lines)
│   │   ├── package.json             ← "extension": false (library only)
│   │   └── setup.py                 ← Server extension registration
│   │
│   ├── chat-extension/              ← Frontend plugin
│   │   ├── src/index.ts             ← JupyterFrontEndPlugin (~300 lines)
│   │   └── package.json             ← "extension": true
│   │
│   └── jupyter-agent/               ← Python only
│       └── jupyter_agent_lg/        ← LangGraph agent (~3,400 lines)
│
├── jupyter_tools_bridge/            ← Python server extension (~1,700 lines)
│   ├── pyproject.toml
│   ├── __init__.py
│   ├── handlers.py
│   └── tools.py
│
└── mcp-snowflake-service/           ← Standalone MCP server
    └── server.py
```

### 3.2 Target Structure (Modular Extensions)

```
STANDALONE REPOSITORIES
───────────────────────

jupyterlab-notebook-tools/           ← Extension 1 (backend only)
├── pyproject.toml
└── jupyter_notebook_tools/
    ├── __init__.py
    ├── handlers.py                  ← FROM: jupyter_tools_bridge/handlers.py
    ├── ydoc.py                      ← FROM: jupyter_tools_bridge/handlers.py (extracted)
    └── client.py                    ← FROM: jupyter_tools_bridge/tools.py

jupyterlab-ai-agent/                 ← Extension 2 (backend only)
├── pyproject.toml
└── jupyter_ai_agent/
    ├── __init__.py
    ├── agent.py                     ← FROM: jupyter_agent_lg/agent.py
    ├── state.py                     ← FROM: jupyter_agent_lg/state.py
    ├── context.py                   ← FROM: jupyter_agent_lg/context.py
    └── tools/
        ├── jupyter.py               ← FROM: jupyter_agent_lg/tools/jupyter_tools.py
        ├── system.py                ← FROM: jupyter_agent_lg/tools/system_tools.py
        └── base.py                  ← New: tool registration system

jupyterlab-ai-chat/                  ← Extension 3 (frontend + backend)
├── pyproject.toml
├── package.json
├── jupyter_ai_chat/
│   ├── __init__.py
│   ├── handlers/
│   │   ├── chat.py                  ← FROM: jupyterlab_chat/__init__.py (ChatAgentHandler)
│   │   ├── threads.py               ← FROM: jupyterlab_chat/__init__.py (ChatThreadsHandler)
│   │   ├── status.py                ← FROM: jupyterlab_chat/__init__.py (ChatStatusHandler)
│   │   └── websocket.py             ← FROM: jupyterlab_chat/__init__.py (ChatStreamHandler)
│   ├── core/
│   │   ├── conversation.py          ← FROM: jupyterlab_chat/__init__.py (ConversationManager)
│   │   ├── broadcaster.py           ← FROM: jupyterlab_chat/__init__.py (ChatBroadcaster)
│   │   └── agent_client.py          ← New: calls jupyterlab-ai-agent
│   └── labextension/                ← Generated during build
├── src/
│   ├── index.ts                     ← FROM: chat-extension/src/index.ts
│   ├── widget.tsx                   ← FROM: chat/src/widget.tsx
│   ├── service.ts                   ← FROM: chat/src/service.ts
│   ├── cellmanager.ts               ← FROM: chat/src/cellmanager.ts
│   ├── llm.ts                       ← FROM: chat/src/llm.ts
│   └── tokens.ts                    ← FROM: chat/src/tokens.ts
└── style/
    └── index.css

jupyterlab-mcp-connectors/           ← Extension 4 (backend + optional frontend)
├── pyproject.toml
├── package.json                     ← Optional: config UI
└── jupyter_mcp_connectors/
    ├── __init__.py
    ├── base.py                      ← Base MCP connector class
    ├── snowflake.py                 ← FROM: mcp-snowflake-service/server.py
    └── registry.py                  ← Connector discovery/registration
```

### 3.3 Line Count Migration

| Current File | Lines | Target Extension | Target File |
|--------------|-------|------------------|-------------|
| `jupyterlab_chat/__init__.py` | 2,200 | jupyterlab-ai-chat | Split into handlers/, core/ |
| `chat/src/widget.tsx` | 1,254 | jupyterlab-ai-chat | src/widget.tsx |
| `chat/src/service.ts` | 1,195 | jupyterlab-ai-chat | src/service.ts |
| `jupyter_agent_lg/agent.py` | 1,361 | jupyterlab-ai-agent | agent.py |
| `jupyter_tools_bridge/handlers.py` | 847 | jupyterlab-notebook-tools | handlers.py |
| `jupyter_tools_bridge/tools.py` | 498 | jupyterlab-notebook-tools | client.py |
| `chat/src/cellmanager.ts` | 384 | jupyterlab-ai-chat | src/cellmanager.ts |
| `chat-extension/src/index.ts` | 296 | jupyterlab-ai-chat | src/index.ts |
| `jupyter_agent_lg/state.py` | 286 | jupyterlab-ai-agent | state.py |
| `chat/src/llm.ts` | 234 | jupyterlab-ai-chat | src/llm.ts |
| `chat/src/tokens.ts` | 224 | jupyterlab-ai-chat | src/tokens.ts |

---

## 4. Extension Specifications

### 4.1 jupyterlab-notebook-tools

**Purpose**: Programmatic notebook manipulation via YDoc

**Type**: Backend only (no frontend)

**Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/notebook-tools/insert-cell` | POST | Insert new cell |
| `/api/notebook-tools/update-cell` | POST | Update cell content |
| `/api/notebook-tools/delete-cell` | POST | Delete cell |
| `/api/notebook-tools/execute-cell` | POST | Execute cell |
| `/api/notebook-tools/save` | POST | Force save notebook |

**Dependencies**:
```toml
[project]
dependencies = [
    "jupyter-server>=2.0",
    "jupyter-server-ydoc>=2.0",
    "jupyter-ydoc>=3.0",
]
```

**Exports** (for other extensions):
```python
# Other extensions can import:
from jupyter_notebook_tools import NotebookToolsClient

client = NotebookToolsClient(base_url, token)
await client.insert_cell(path, code)
await client.execute_cell(path, index)
```

---

### 4.2 jupyterlab-ai-agent

**Purpose**: LangGraph-based AI agent for notebook tasks

**Type**: Backend only (no frontend)

**Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/invoke` | POST | Process message with agent |
| `/api/agent/cancel` | POST | Cancel running agent |
| `/api/agent/tools` | GET | List available tools |

**Dependencies**:
```toml
[project]
dependencies = [
    "jupyter-server>=2.0",
    "jupyterlab-notebook-tools>=0.1.0",  # Extension dependency!
    "langchain>=0.1.0",
    "langgraph>=0.1.0",
    "langchain-openai>=0.1.0",
    "langchain-anthropic>=0.1.0",
]
```

**Plugin System** (for tool providers):
```python
# pyproject.toml of a tool provider extension
[project.entry-points."jupyter_ai_agent.tools"]
my_tools = "my_extension:get_tools"

# my_extension/__init__.py
def get_tools():
    return [MyCustomTool1(), MyCustomTool2()]
```

**Agent discovers tools at runtime**:
```python
# jupyter_ai_agent/agent.py
from importlib.metadata import entry_points

def _discover_tools(self):
    tools = []
    for ep in entry_points(group='jupyter_ai_agent.tools'):
        provider = ep.load()
        tools.extend(provider())
    return tools
```

---

### 4.3 jupyterlab-ai-chat

**Purpose**: Chat UI and conversation management

**Type**: Frontend + Backend (combined)

**Frontend Components**:
- Floating chat dialog (draggable, resizable)
- Thread history panel
- Model selector dropdown
- Plan card rendering
- Message display with code formatting

**Backend Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/message` | POST | Send message (routes to agent) |
| `/api/chat/stream` | WebSocket | Real-time updates |
| `/api/chat/threads` | GET | List conversation threads |
| `/api/chat/threads` | POST | Create new thread |
| `/api/chat/threads/<id>` | DELETE | Delete thread |
| `/api/chat/status` | POST | Broadcast status message |

**Dependencies**:
```toml
# pyproject.toml
[project]
dependencies = [
    "jupyter-server>=2.0",
    "jupyterlab-ai-agent>=0.1.0",  # Optional but recommended
]

[project.optional-dependencies]
agent = ["jupyterlab-ai-agent>=0.1.0"]
```

```json
// package.json
{
  "dependencies": {
    "@jupyterlab/application": "^4.0.0",
    "@jupyterlab/notebook": "^4.0.0"
  }
}
```

**Owns**:
- Thread/conversation state
- Notebook metadata persistence (chat_conversations)
- WebSocket broadcasting
- Request cancellation
- UI state

**Does NOT own**:
- LLM orchestration (delegates to agent)
- Cell manipulation (delegates to notebook-tools)

---

### 4.4 jupyterlab-mcp-connectors

**Purpose**: Data source connectors via Model Context Protocol

**Type**: Backend + optional frontend

**Connectors** (initial):
- Snowflake
- PostgreSQL (future)
- BigQuery (future)

**Plugin System** (for connector providers):
```python
# pyproject.toml of a connector extension
[project.entry-points."jupyter_mcp.connectors"]
salesforce = "my_crm_extension:SalesforceConnector"

# Automatically discovered by jupyterlab-mcp-connectors
```

**Configuration** (via JupyterLab settings):
```json
{
  "jupyterlab-mcp-connectors": {
    "connectors": {
      "snowflake": {
        "account": "xxx",
        "warehouse": "COMPUTE_WH"
      }
    }
  }
}
```

---

## 5. Inter-Extension Communication

### 5.1 Communication Patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      EXTENSION COMMUNICATION                                 │
└─────────────────────────────────────────────────────────────────────────────┘

Pattern 1: REST API Calls
─────────────────────────
jupyterlab-ai-chat                    jupyterlab-ai-agent
       │                                     │
       │  POST /api/agent/invoke             │
       │  {message, history, notebook_path}  │
       │ ──────────────────────────────────► │
       │                                     │
       │  {response, tool_calls}             │
       │ ◄────────────────────────────────── │
       │                                     │


Pattern 2: Shared Settings
──────────────────────────
web_app.settings["jupyter_server_ydoc"]  ← Set by jupyter-server-ydoc
web_app.settings["kernel_manager"]       ← Set by jupyter-server

All extensions can access these shared resources.


Pattern 3: Entry Points (Plugin Discovery)
──────────────────────────────────────────
jupyterlab-ai-agent discovers tools:

  entry_points(group='jupyter_ai_agent.tools')
       │
       ├── jupyterlab-notebook-tools:get_jupyter_tools
       ├── jupyterlab-mcp-connectors:get_mcp_tools  
       └── my-custom-extension:get_custom_tools


Pattern 4: Python Imports
─────────────────────────
# Direct import (tight coupling)
from jupyter_notebook_tools import NotebookToolsClient

client = NotebookToolsClient(base_url, token)
```

### 5.2 Chat → Agent → Tools Flow

```
User: "Create a plot of sales data"
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ jupyterlab-ai-chat                                               │
│                                                                  │
│  1. ChatMessageHandler receives request                         │
│  2. Saves user message to thread (ConversationManager)          │
│  3. Calls AgentClient.invoke()                                  │
│         │                                                        │
│         │ POST /api/agent/invoke                                │
│         │ {                                                      │
│         │   "message": "Create a plot of sales data",           │
│         │   "conversation_history": [...],                      │
│         │   "notebook_path": "analysis.ipynb",                  │
│         │   "model": "gpt-4o",                                  │
│         │   "status_callback_url": "/api/chat/status"           │
│         │ }                                                      │
└─────────┼───────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ jupyterlab-ai-agent                                              │
│                                                                  │
│  1. AgentInvokeHandler receives request                         │
│  2. Loads tools from entry points                               │
│  3. Runs LangGraph workflow                                     │
│  4. LLM decides: call insert_and_execute_cell                   │
│  5. Sends status: POST /api/chat/status                         │
│         │                                                        │
│         │ Tool calls NotebookToolsClient                        │
│         │                                                        │
└─────────┼───────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ jupyterlab-notebook-tools                                        │
│                                                                  │
│  1. InsertCellHandler receives request                          │
│  2. Gets YNotebook via YDocExtension                            │
│  3. notebook.append_cell(code)  ← Real-time update!            │
│  4. ExecuteCellHandler runs code                                │
│  5. Returns {cell_id, outputs}                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
          │
          │ (result bubbles back up)
          ▼
┌─────────────────────────────────────────────────────────────────┐
│ jupyterlab-ai-chat                                               │
│                                                                  │
│  1. Receives agent response                                     │
│  2. Saves assistant message to thread                           │
│  3. Broadcasts via WebSocket                                    │
│  4. Frontend displays message                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Status Message Flow

```python
# jupyterlab-ai-agent/agent.py

class JupyterAgent:
    def __init__(self, status_callback_url: str = None):
        self.status_callback_url = status_callback_url
    
    async def _send_status(self, message: str):
        """Send status to chat extension for display."""
        if self.status_callback_url:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    self.status_callback_url,
                    json={"message": message, "type": "status"}
                )
    
    async def analyze_and_decide(self, state):
        # Before tool execution
        tool_args = response.tool_calls[0]['args']
        if 'status_message' in tool_args:
            await self._send_status(tool_args['status_message'])
        
        # Execute tool...
```

---

## 6. Build & Packaging Workflow

### 6.1 Extension pyproject.toml Template

```toml
[build-system]
requires = ["hatchling>=1.5.0", "jupyterlab>=4.0.0", "hatch-jupyter-builder>=0.8.0"]
build-backend = "hatchling.build"

[project]
name = "jupyterlab-ai-chat"
version = "0.1.0"
description = "AI Chat extension for JupyterLab"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.8"
dependencies = [
    "jupyter-server>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "build",
    "pytest",
]

# Server extension registration
[project.entry-points."jupyter_server.extension.v1"]
jupyterlab_ai_chat = "jupyter_ai_chat"

# Wheel configuration
[tool.hatch.build.targets.wheel.shared-data]
"jupyter_ai_chat/labextension" = "share/jupyter/labextensions/@org/jupyterlab-ai-chat"
"install.json" = "share/jupyter/labextensions/@org/jupyterlab-ai-chat/install.json"

# Auto-enable server extension
[tool.hatch.build.hooks.jupyter-builder]
dependencies = ["hatch-jupyter-builder>=0.8.0"]
build-function = "hatch_jupyter_builder.npm_builder"
ensured-targets = [
    "jupyter_ai_chat/labextension/static/style.js",
    "jupyter_ai_chat/labextension/package.json",
]
skip-if-exists = ["jupyter_ai_chat/labextension/static/style.js"]

[tool.hatch.build.hooks.jupyter-builder.build-kwargs]
build_cmd = "build:prod"
npm = ["jlpm"]

[tool.hatch.build.hooks.jupyter-builder.editable-build-kwargs]
build_cmd = "build"
npm = ["jlpm"]
source_dir = "src"
build_dir = "jupyter_ai_chat/labextension"
```

### 6.2 Extension package.json Template

```json
{
  "name": "@org/jupyterlab-ai-chat",
  "version": "0.1.0",
  "description": "AI Chat extension for JupyterLab",
  "license": "BSD-3-Clause",
  "main": "lib/index.js",
  "types": "lib/index.d.ts",
  "style": "style/index.css",
  "files": [
    "lib/**/*.{d.ts,js,js.map}",
    "style/**/*.css",
    "schema/*.json"
  ],
  "scripts": {
    "build": "jlpm build:lib && jlpm build:labextension:dev",
    "build:prod": "jlpm clean && jlpm build:lib && jlpm build:labextension",
    "build:lib": "tsc",
    "build:labextension": "jupyter labextension build .",
    "build:labextension:dev": "jupyter labextension build --development True .",
    "clean": "jlpm clean:lib && jlpm clean:labextension",
    "clean:lib": "rimraf lib tsconfig.tsbuildinfo",
    "clean:labextension": "rimraf jupyter_ai_chat/labextension",
    "watch": "run-p watch:src watch:labextension",
    "watch:src": "tsc -w",
    "watch:labextension": "jupyter labextension watch ."
  },
  "dependencies": {
    "@jupyterlab/application": "^4.0.0",
    "@jupyterlab/apputils": "^4.0.0",
    "@jupyterlab/notebook": "^4.0.0",
    "@jupyterlab/services": "^7.0.0",
    "@lumino/widgets": "^2.0.0"
  },
  "devDependencies": {
    "@jupyterlab/builder": "^4.0.0",
    "npm-run-all": "^4.1.5",
    "rimraf": "^5.0.0",
    "typescript": "~5.0.0"
  },
  "jupyterlab": {
    "extension": true,
    "outputDir": "jupyter_ai_chat/labextension",
    "schemaDir": "schema"
  }
}
```

### 6.3 Development Workflow

```bash
# Initial setup (one time)
git clone https://github.com/org/jupyterlab-ai-chat
cd jupyterlab-ai-chat
pip install -e ".[dev]"
jlpm install

# Development (daily)
jlpm watch                    # Terminal 1: Watch TypeScript
jupyter lab --autoreload      # Terminal 2: Run JupyterLab

# Testing
pytest
jlpm test

# Building for distribution
python -m build               # Creates dist/*.whl

# Publishing
twine upload dist/*           # Upload to PyPI
```

### 6.4 Backend-Only Extension (Simpler)

For extensions without frontend (like `jupyterlab-ai-agent`):

```toml
# pyproject.toml (much simpler!)
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "jupyterlab-ai-agent"
version = "0.1.0"
dependencies = [
    "jupyter-server>=2.0",
    "jupyterlab-notebook-tools>=0.1.0",
    "langchain>=0.1.0",
    "langgraph>=0.1.0",
]

[project.entry-points."jupyter_server.extension.v1"]
jupyter_ai_agent = "jupyter_ai_agent"

[tool.hatch.build.targets.wheel]
packages = ["jupyter_ai_agent"]
```

No package.json, no TypeScript, no build hooks needed!

---

## 7. Migration Plan

### 7.1 Phase 1: Extract jupyterlab-notebook-tools (Week 1)

**Why first**: No dependencies on other custom code, most reusable.

```bash
# Create new repo
mkdir jupyterlab-notebook-tools
cd jupyterlab-notebook-tools

# Copy code
cp -r ../jupyterlab/jupyter_tools_bridge/* jupyter_notebook_tools/

# Rename and adjust imports
mv jupyter_notebook_tools/__init__.py jupyter_notebook_tools/__init__.py
# Update: "jupyter_tools_bridge" → "jupyter_notebook_tools"

# Create pyproject.toml (use template from Section 6.4)
# Test independently
pip install -e .
jupyter lab  # Verify /api/notebook-tools/* endpoints work
```

**Verification**:
- [ ] `pip install -e .` succeeds
- [ ] `jupyter server extension list` shows extension
- [ ] `/api/notebook-tools/insert-cell` works
- [ ] `/api/notebook-tools/execute-cell` works

### 7.2 Phase 2: Extract jupyterlab-ai-agent (Week 2)

**Depends on**: jupyterlab-notebook-tools

```bash
mkdir jupyterlab-ai-agent
cd jupyterlab-ai-agent

# Copy code
cp -r ../jupyterlab/packages/jupyter-agent/jupyter_agent_lg/* jupyter_ai_agent/

# Update imports
# FROM: from jupyter_tools_bridge.tools import JupyterTools
# TO:   from jupyter_notebook_tools import NotebookToolsClient

# Add dependency in pyproject.toml
# dependencies = ["jupyterlab-notebook-tools>=0.1.0", ...]

# Add REST endpoint
# Create jupyter_ai_agent/handlers.py with AgentInvokeHandler
```

**Verification**:
- [ ] `pip install -e .` succeeds
- [ ] `/api/agent/invoke` endpoint works
- [ ] Agent can call notebook-tools extension

### 7.3 Phase 3: Extract jupyterlab-ai-chat (Week 3-4)

**Depends on**: jupyterlab-ai-agent (optional)

```bash
mkdir jupyterlab-ai-chat
cd jupyterlab-ai-chat

# Copy Python backend
mkdir -p jupyter_ai_chat/handlers
cp ../jupyterlab/packages/chat/jupyterlab_chat/__init__.py jupyter_ai_chat/handlers/

# Split __init__.py into:
# - handlers/chat.py (ChatAgentHandler)
# - handlers/threads.py (ChatThreadsHandler, ChatConversationsHandler)
# - handlers/status.py (ChatStatusHandler, ChatMessageHandler)
# - handlers/websocket.py (ChatStreamHandler)
# - core/conversation.py (ConversationManager)
# - core/broadcaster.py (ChatBroadcaster)

# Copy TypeScript frontend
mkdir src
cp ../jupyterlab/packages/chat/src/*.ts src/
cp ../jupyterlab/packages/chat/src/*.tsx src/
cp ../jupyterlab/packages/chat-extension/src/index.ts src/

# Merge index.ts from chat-extension into main index.ts

# Create pyproject.toml and package.json (use templates)
# Build and test
jlpm install
jlpm build
pip install -e .
```

**Verification**:
- [ ] Frontend builds without errors
- [ ] Chat UI appears in JupyterLab
- [ ] Messages send and receive
- [ ] Thread management works
- [ ] Works WITH agent extension installed
- [ ] Works WITHOUT agent extension (basic mode)

### 7.4 Phase 4: Extract jupyterlab-mcp-connectors (Week 5)

```bash
mkdir jupyterlab-mcp-connectors
cd jupyterlab-mcp-connectors

# Copy Snowflake MCP
mkdir jupyter_mcp_connectors
cp ../jupyterlab/mcp-snowflake-service/server.py jupyter_mcp_connectors/snowflake.py

# Create base connector class
# Create connector registry
# Create entry point for agent to discover
```

### 7.5 Phase 5: Create Distribution Bundle (Week 6)

```bash
mkdir datalab
cd datalab

# Create meta-package
cat > pyproject.toml << EOF
[project]
name = "datalab"
version = "0.1.0"
dependencies = [
    "jupyterlab>=4.0.0",
    "jupyterlab-ai-chat>=0.1.0",
    "jupyterlab-ai-agent>=0.1.0",
    "jupyterlab-notebook-tools>=0.1.0",
    "jupyterlab-mcp-connectors>=0.1.0",
]
EOF

# User installs everything with:
# pip install datalab
```

---

## 8. Future Extensions Roadmap

### 8.1 jupyterlab-ai-memory

**Purpose**: Long-term context and memory for AI agent

**Features**:
- Vector store for semantic search
- Conversation summarization
- Cross-notebook memory
- User preference learning

**Architecture**:
```
jupyterlab-ai-memory/
├── jupyter_ai_memory/
│   ├── backends/
│   │   ├── chroma.py         # Local vector DB
│   │   ├── pinecone.py       # Cloud vector DB
│   │   └── sqlite_fts.py     # Simple full-text search
│   ├── memory.py             # MemoryManager
│   └── handlers.py           # REST API
└── src/
    └── memory-panel.tsx      # UI to browse/search
```

**Integration with agent**:
```python
# Agent queries memory before responding
memories = await memory_client.search(user_message, top_k=5)
context = f"Relevant context:\n{memories}\n\nUser: {user_message}"
```

### 8.2 jupyterlab-ai-skills

**Purpose**: Reusable analysis workflows

**Features**:
- Pre-built skills (data cleaning, visualization, ML pipeline)
- User-defined custom skills
- Skill sharing/marketplace

**Architecture**:
```
jupyterlab-ai-skills/
├── jupyter_ai_skills/
│   ├── library/
│   │   ├── data_cleaning.py
│   │   ├── exploratory_analysis.py
│   │   └── ml_pipeline.py
│   ├── custom/               # User skills stored here
│   └── skill_manager.py
└── src/
    └── skill-browser.tsx     # UI to browse/create skills
```

**Skill definition**:
```python
class DataCleaningSkill:
    name = "data_cleaning"
    description = "Clean and preprocess a dataset"
    
    steps = [
        {"action": "load_data", "description": "Load the dataset"},
        {"action": "check_missing", "description": "Check for missing values"},
        {"action": "handle_missing", "description": "Handle missing values"},
        {"action": "check_duplicates", "description": "Check for duplicates"},
        {"action": "standardize_types", "description": "Standardize data types"},
    ]
    
    async def execute(self, agent, context):
        for step in self.steps:
            await agent.execute_step(step, context)
```

### 8.3 jupyterlab-dashboard-export

**Purpose**: Export notebooks to dashboards

**Features**:
- Export to Streamlit
- Export to Dash
- Export to static HTML
- Export to Observable

**Architecture**:
```
jupyterlab-dashboard-export/
├── jupyter_dashboard_export/
│   ├── exporters/
│   │   ├── streamlit.py
│   │   ├── dash.py
│   │   └── html.py
│   └── handlers.py
└── src/
    └── export-dialog.tsx     # Export configuration UI
```

### 8.4 jupyterlab-spreadsheet

**Purpose**: Spreadsheet integration

**Features**:
- Google Sheets connector
- Excel file support
- Two-way sync
- Embedded spreadsheet view

### 8.5 Additional MCP Connectors

Each as a separate extension:
- `jupyterlab-mcp-bigquery`
- `jupyterlab-mcp-postgres`
- `jupyterlab-mcp-salesforce`
- `jupyterlab-mcp-hubspot`
- `jupyterlab-mcp-google-ads`
- `jupyterlab-mcp-stripe`

---

## 9. Distribution Strategy

### 9.1 Open Source Extensions (Free)

```
jupyterlab-notebook-tools      ← Core infrastructure
jupyterlab-ai-chat             ← Basic chat (BYOK - bring your own key)
jupyterlab-ai-agent            ← Basic agent
jupyterlab-mcp-connectors      ← Base framework
```

### 9.2 Premium Extensions (Paid/Enterprise)

```
jupyterlab-ai-memory           ← Enterprise feature
jupyterlab-ai-skills           ← Enterprise feature  
jupyterlab-dashboard-export    ← Pro feature
Enterprise MCP connectors      ← Per-connector pricing
```

### 9.3 DataLab Distribution

```bash
# Free tier
pip install datalab-free
# Includes: notebook-tools, ai-chat, ai-agent, mcp-connectors

# Pro tier
pip install datalab-pro
# Includes: Free + dashboard-export + skills

# Enterprise tier
pip install datalab-enterprise
# Includes: Pro + memory + all MCP connectors + support
```

### 9.4 Desktop App (Future)

```
DataLab.app (Electron)
├── Bundled JupyterLab
├── All extensions pre-installed
├── Native OS integration
├── Auto-updates
└── Offline support
```

---

## Appendix A: Quick Reference

### Extension Type Decision Tree

```
Need frontend UI?
├── Yes → Need backend too?
│         ├── Yes → Combined extension (frontend + backend)
│         └── No  → Frontend-only extension
└── No  → Backend-only extension
```

### File Checklist for New Extension

**Backend-only**:
- [ ] `pyproject.toml` with `jupyter_server.extension.v1` entry point
- [ ] `__init__.py` with `_jupyter_server_extension_points()` and `_load_jupyter_server_extension()`
- [ ] `handlers.py` with Tornado request handlers

**Frontend-only**:
- [ ] `package.json` with `"jupyterlab": {"extension": true}`
- [ ] `src/index.ts` with `JupyterFrontEndPlugin`
- [ ] `tsconfig.json`

**Combined**:
- [ ] All of the above
- [ ] `hatch-jupyter-builder` config in pyproject.toml
- [ ] `labextension/` output directory

### Common Commands

```bash
# Development
jlpm install          # Install npm dependencies
jlpm build            # Build TypeScript
pip install -e .      # Install Python package in dev mode
jupyter lab           # Run JupyterLab

# Debugging
jupyter server extension list    # List server extensions
jupyter labextension list        # List lab extensions

# Building
python -m build       # Build wheel
twine upload dist/*   # Publish to PyPI
```

---

*Document created: December 2024*
*Covers: Modularization of ~21,000 lines into 4 core extensions + future roadmap*

