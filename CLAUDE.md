# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a fork of JupyterLab with custom AI agent integration. It extends JupyterLab with real-time notebook manipulation via LangGraph agents, OpenAI Agents SDK, and direct YDoc manipulation for <50ms cell updates.

The project adds:
- **LangGraph-based data analysis agent** (`packages/jupyter-agent/`)
- **Chat UI extension** (`packages/chat/` and `packages/chat-extension/`)
- **YDoc-based notebook tools bridge** (`jupyter_tools_bridge/`)

## Common Commands

### Development

```bash
# Start JupyterLab in development mode
jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py

# Alternative: Use the start script
python start_dev_jupyterlab.py

# Build everything (utils, builder, packages, dev mode)
npm run build:dev

# Build just the dev mode app
cd dev_mode && npm run build

# Clean and rebuild from scratch
npm run clean:slate
```

### Testing

```bash
# Run all tests (excluding galata and template packages)
npm run test

# Run tests for a specific package scope
npm run test:scope --scope "@jupyterlab/chat"

# Run Galata end-to-end tests
npm run test:galata
```

### Linting and Formatting

```bash
# Run all linters (prettier, eslint, stylelint)
npm run lint

# Check formatting without fixing
npm run lint:check

# Fix TypeScript/JavaScript files
npm run eslint

# Fix CSS files
npm run stylelint
```

### Python Development

```bash
# Install in development mode
pip install -e .

# Install agent package
pip install -e packages/jupyter-agent

# Install tools bridge
pip install -e jupyter_tools_bridge

# Check Python setup
python check_setup.py
```

### Package Management

```bash
# Install all dependencies
jlpm

# Deduplicate yarn dependencies
npm run deduplicate

# Build all packages
npm run build:all

# Build specific package
cd packages/chat && jlpm build
```

## Architecture

### Extension Structure

The codebase follows JupyterLab's standard extension pattern with four types of packages:

1. **Python Server Extensions** (backend only)
   - `jupyter_tools_bridge/` - YDoc manipulation and notebook tools
   - Located at repository root

2. **TypeScript Library Packages** (frontend logic)
   - `packages/chat/` - Chat UI components and services
   - Not loaded directly by JupyterLab, but consumed by extension packages

3. **JupyterLab Extension Packages** (plugin registration)
   - `packages/chat-extension/` - Registers chat plugin with JupyterLab
   - Contains plugin activation, settings, commands

4. **Python Agent Package** (AI agent logic)
   - `packages/jupyter-agent/jupyter_agent_lg/` - LangGraph agent implementation
   - Uses LangChain, LangGraph, OpenAI/Anthropic APIs

### Key Components

**Agent System (`packages/jupyter-agent/jupyter_agent_lg/`):**
- `agent.py` - Main LangGraph agent with state management
- `context.py` - Notebook state tracking and context management
- `tools/jupyter_tools.py` - LangChain-wrapped notebook manipulation tools
- `state.py` - LangGraph state definitions
- `handlers.py` - HTTP endpoints for agent operations

**Chat UI (`packages/chat/src/`):**
- `widget.tsx` - Main React chat widget component
- `service.ts` - Chat service with WebSocket communication
- `cellmanager.ts` - Manages cell references and notebook context
- `llm.ts` - LLM provider abstraction

**Tools Bridge (`jupyter_tools_bridge/`):**
- `tools.py` - `JupyterTools` class with direct YDoc manipulation
- `handlers.py` - REST API endpoints for notebook operations
- `http_bridge.py` - HTTP client for tools
- `logging_config.py` - Centralized logging configuration

### Data Flow

```
Chat UI (TypeScript)
  → WebSocket/REST API
  → LangGraph Agent (Python)
  → JupyterTools (YDoc manipulation)
  → Real-time notebook updates (<50ms)
```

### Monorepo Structure

- **Root `package.json`**: Workspace coordinator using Lerna
- **`packages/`**: All TypeScript packages (100+ packages)
- **`dev_mode/`**: Development mode JupyterLab build
- **`builder/`**: Custom build utilities
- **`buildutils/`**: Build scripts and tooling
- **`galata/`**: End-to-end testing framework
- **`jupyterlab/`**: Core JupyterLab Python package

## Important Configuration

### Server Configuration (`jupyter_server_config.py`)

This file is critical for enabling the agent features:
- Enables collaborative mode for YDoc (`c.YDocExtension.collaborative = True`)
- Loads required extensions (`jupyter_server_ydoc`, `jupyter_tools_bridge`, `jupyterlab_chat`)
- Sets up LangSmith tracing for agent debugging
- Configures dev mode paths

**Do not modify this file unless you understand the YDoc requirements.**

### Environment Variables

Set in `jupyter_server_config.py` or shell:
- `JLAB_AGENT_ENABLE_TRACING` - Enable LangSmith tracing (default: "true")
- `JLAB_AGENT_DEBUG_LLMS` - Debug LLM calls (default: "false")
- `JLAB_AGENT_LOG_OPENAI_PAYLOADS` - Log OpenAI payloads to disk (default: "true")
- `LANGCHAIN_API_KEY` - LangSmith API key for tracing
- `OPENAI_API_KEY` - Required for agent operations
- `ANTHROPIC_API_KEY` - Required for Claude model usage

## Development Workflow

### Making Changes to Chat Extension

1. Edit TypeScript files in `packages/chat/src/` or `packages/chat-extension/src/`
2. Rebuild: `cd packages/chat && jlpm build && cd ../chat-extension && jlpm build`
3. Restart JupyterLab (no rebuild needed if using `--dev-mode --extensions-in-dev-mode`)

### Making Changes to Agent

1. Edit Python files in `packages/jupyter-agent/jupyter_agent_lg/`
2. No rebuild needed - Python reloads automatically
3. Restart JupyterLab to pick up changes

### Making Changes to Tools Bridge

1. Edit Python files in `jupyter_tools_bridge/`
2. No rebuild needed - installed with `pip install -e`
3. Restart JupyterLab to reload extension

### Building Core JupyterLab

Only needed if changing core JupyterLab packages (not agent/chat):

```bash
npm run build:core
```

## Testing Strategy

### Unit Tests

Each package has its own test suite:
```bash
# Run all package tests
npm run test

# Run specific package test
cd packages/chat && jlpm test
```

### Integration Tests

Test scripts in `test_scripts/`:
- `test_complete_flow.py` - End-to-end agent workflow test
- `test_notebook_isolation.py` - Multi-notebook context isolation test

### Manual Testing

Start JupyterLab and verify:
1. Chat widget appears in sidebar
2. Can send messages and get responses
3. Code cells appear in notebook in real-time
4. Outputs render correctly (text, images, dataframes)

## Common Issues

### "Module not found" errors in browser

The extension wasn't built or dev mode isn't configured correctly. Run:
```bash
cd dev_mode && npm run build
```

### Agent can't find notebook

Ensure collaborative mode is enabled in `jupyter_server_config.py`:
```python
c.YDocExtension.collaborative = True
```

### 403 XSRF errors in tools

The tools need proper authentication. Verify `jupyter_tools_bridge` is loaded:
```bash
jupyter server extension list
```

### Changes not appearing

For TypeScript: Rebuild package with `jlpm build`
For Python: Restart JupyterLab server

### Build failures

Try cleaning first:
```bash
npm run clean
jlpm
npm run build:all
```

## LLM Provider Configuration

The agent supports multiple LLM providers via LangChain:

**OpenAI (default):**
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4", temperature=0)
```

**Anthropic:**
```python
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-3-5-sonnet-20241022")
```

Provider is selected in `packages/jupyter-agent/jupyter_agent_lg/agent.py` in the `JupyterAgent` class initialization.

## Key Files to Know

- `jupyter_server_config.py` - Server configuration (agent, tracing, logging)
- `packages/jupyter-agent/jupyter_agent_lg/agent.py` - Main agent logic
- `jupyter_tools_bridge/tools.py` - Core notebook manipulation tools
- `packages/chat/src/widget.tsx` - Chat UI implementation
- `package.json` (root) - Build scripts and workspace configuration
- `dev_mode/` - Development build output (gitignored)

## Git Workflow Notes

This repository uses standard JupyterLab git workflow but has pre-commit hooks that may modify files (prettier, eslint). Use `--no-verify` if you need to bypass hooks, but prefer fixing issues when possible.
