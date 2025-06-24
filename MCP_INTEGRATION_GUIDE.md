# JupyterLab MCP Integration Guide

## Overview

This guide explains how **Model Context Protocol (MCP)** integration works in JupyterLab using the **OpenAI Agents SDK**. This implementation allows LLMs in JupyterLab chat to access and use tools from MCP servers like Snowflake, filesystem, databases, and more.

## Current Architecture

The MCP integration is implemented directly in the JupyterLab server extension, bypassing any Python bridge:

```
JupyterLab Chat UI (TypeScript)
       ↓ HTTP POST /api/chat/openai
JupyterLab Server Extension (Python)
       ↓ OpenAI Agents SDK
MCP Servers (STDIO)
```

## How It Works

### 1. **Frontend Request**
- Chat UI sends HTTP POST to `/api/chat/openai`
- Includes message, model, and MCP server configurations
- All handled in `packages/chat/src/llm.ts`

### 2. **Server Extension Processing**
- `ChatOpenAIHandler` in `packages/chat/jupyterlab_chat/__init__.py` receives request
- Loads OpenAI API key from JupyterLab settings
- Uses OpenAI Agents SDK to create agent with MCP servers
- Agent automatically decides when to use MCP tools

### 3. **MCP Server Communication**
- MCP servers launched via STDIO (same as Cursor/Claude Desktop)
- OpenAI Agents SDK handles all JSON-RPC 2.0 protocol details
- Tools are discovered and executed automatically

## Setup Instructions

### 1. Install Python Dependencies

The server extension requires the OpenAI Agents SDK:

```bash
# From workspace root
pip install agents openai mcp
```

### 2. Set OpenAI API Key

Configure in JupyterLab Settings (not environment variable):
1. Open JupyterLab
2. Go to `Settings` → `Settings Editor` → `Chat`
3. Set your OpenAI API key in the "OpenAI API Key" field

### 3. Build and Start JupyterLab

```bash
# From workspace root
npm run build
jupyter lab --dev-mode
```

### 4. Configure MCP Servers

In JupyterLab Settings → Chat → "MCP Servers" section:

```json
{
  "mcpServers": {
    "snowflake": {
      "command": "python",
      "args": ["path/to/snowflake-mcp-server.py"],
      "env": {
        "SNOWFLAKE_USER": "your_username@company.com",
        "SNOWFLAKE_PASSWORD": "your_password",
        "SNOWFLAKE_ACCOUNT": "your_account.snowflakecomputing.com",
        "SNOWFLAKE_WAREHOUSE": "COMPUTE_WH",
        "SNOWFLAKE_DATABASE": "YOUR_DB",
        "SNOWFLAKE_SCHEMA": "PUBLIC"
      }
    }
  }
}
```

## Configuration Examples

### Filesystem MCP Server

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/your/files"],
      "env": {}
    }
  }
}
```

### PostgreSQL Database

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": {
        "DATABASE_URL": "postgresql://user:password@localhost:5432/dbname"
      }
    }
  }
}
```

### SQLite Database

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sqlite", "path/to/database.db"],
      "env": {}
    }
  }
}
```

## File Structure

```
packages/chat/
├── jupyterlab_chat/
│   └── __init__.py              # Main server extension with MCP integration
├── src/
│   ├── llm.ts                   # Frontend provider that calls server extension
│   ├── service.ts               # Chat service
│   ├── tokens.ts                # TypeScript interfaces
│   └── ...
├── python/                      # (NOT USED - legacy files)
│   ├── openai_agents_bridge.py  # Unused Python bridge
│   └── ...
└── ...

packages/chat-extension/
├── schema/
│   └── plugin.json              # Configuration schema for settings
└── src/
    └── index.ts                 # Extension entry point
```

## Key Components

### Server Extension (`jupyterlab_chat/__init__.py`)
- **`ChatOpenAIHandler`**: Handles `/api/chat/openai` requests
- **MCP Integration**: Uses OpenAI Agents SDK directly
- **Settings Loading**: Reads API key and MCP configs from JupyterLab settings
- **Error Handling**: Comprehensive timeout and cleanup logic

### Frontend Provider (`llm.ts`)
- **`OpenAIProvider`**: Makes HTTP calls to server extension
- **Security**: No API keys stored in browser
- **MCP Configuration**: Passes MCP server configs to backend

### Configuration Schema (`plugin.json`)
- **API Key Settings**: Secure storage in JupyterLab settings
- **MCP Server Configuration**: Command, args, and environment variables
- **Model Selection**: Supports OpenAI models with tool calling

## Performance Characteristics

Based on actual usage logs, typical request timing:
- **Request parsing**: ~0.001s
- **Settings loading**: ~0.002s
- **SDK import**: ~0.003s
- **MCP server connection**: ~0.5-2s per server
- **Agent creation**: ~0.001s
- **LLM execution**: 3-10s (multiple LLM calls for complex queries)
- **MCP cleanup**: ~0.001s

**Total typical request time**: 5-15 seconds for queries requiring MCP tools

## Usage Examples

### Database Queries
```
"Show me the top 10 customers by profit from the sales data"
```
→ Agent automatically connects to Snowflake MCP server and executes queries

### File Operations
```
"List all Python files in the project and show me their sizes"
```
→ Agent uses filesystem MCP server to browse and analyze files

### Data Analysis
```
"Calculate the average profit margin across all products"
```
→ Agent queries database via MCP, performs calculations

## Troubleshooting

### Python Dependencies
```bash
pip install agents openai mcp
```

### MCP Server Connection Issues
- Check command paths in settings
- Verify environment variables are set correctly
- Look for connection timeouts in JupyterLab logs

### API Key Issues
- Set OpenAI API key in JupyterLab Settings → Chat
- Supported models: `gpt-4o`, `gpt-4o-mini`, `o1-preview`, `o1-mini`

### Build Issues
```bash
npm run clean
npm run build
jupyter lab build
```

### Common Errors

**"OpenAI Agents SDK not installed"**
```bash
pip install agents
```

**"MCP server connection timeout"**
- Check server command is correct
- Verify required environment variables
- Test MCP server independently

**"Error cleaning up server: Attempted to exit cancel scope"**
- This is a harmless asyncio cleanup warning in the MCP SDK
- Does not affect functionality

## Supported MCP Servers

- **@modelcontextprotocol/server-filesystem** - File operations
- **@modelcontextprotocol/server-postgres** - PostgreSQL database
- **@modelcontextprotocol/server-sqlite** - SQLite database
- **Custom Snowflake servers** - Data warehouse access
- **Any STDIO-compatible MCP server** following the MCP specification

## Security Notes

- **API keys never sent to browser** - stored securely in JupyterLab settings
- **MCP servers run in separate processes** with limited environment access
- **Database credentials** passed via environment variables to MCP servers
- **No persistent connections** - MCP servers created and cleaned up per request

## Development Notes

### Adding New MCP Servers
1. Install the MCP server package or create custom server
2. Add configuration to JupyterLab Settings → Chat → MCP Servers
3. Test connection independently before using in chat

### Debugging
- Check JupyterLab terminal output for detailed timing logs
- Browser console shows frontend request/response flow
- MCP server logs appear in JupyterLab terminal

### Performance Optimization
- **MCP server startup time** is the main bottleneck
- Consider keeping long-running MCP servers if startup is slow
- Database connection pooling in MCP servers can help

---

This implementation provides production-ready MCP integration that follows the same STDIO-based patterns used by Cursor and Claude Desktop, ensuring broad compatibility with the MCP ecosystem.
