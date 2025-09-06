# JupyterLab LangGraph Agent

LangGraph-based intelligent data analysis agent for JupyterLab notebooks.

## Overview

This package provides a sophisticated AI agent that uses LangGraph workflows to perform iterative data analysis in JupyterLab notebooks. The agent makes intelligent decisions about what actions to take next based on complete notebook context and user requests.

## Architecture

### Core Components

- **DataAnalysisAgent** - Main LangGraph workflow orchestrator
- **AnalysisNodes** - Individual workflow nodes (analyze, plan, execute, etc.)
- **LLMRouter** - Multi-LLM support and decision making
- **JupyterBridge** - Integration with existing jupyter_agent_bridge tools
- **MCPConnector** - Integration with MCP services (Snowflake, etc.)
- **ChatHandler** - Real-time communication with chat extension
- **NotebookStateManager** - Efficient notebook state management

### Workflow Nodes

1. **analyze_and_decide** - Core decision-making node (LLM-driven)
2. **create_plan** - Generate interactive analysis plans
3. **execute_code** - Run code in notebook cells
4. **query_snowflake** - Load data from external sources
5. **create_visualization** - Generate charts and plots
6. **handle_feedback** - Process user input and adapt
7. **complete_analysis** - Finalize and summarize results

## Key Features

### 🧠 **Pure LLM-Driven Decisions**
- Every action determined by LLM with complete context
- No hardcoded logic or predetermined workflows
- Dynamic adaptation based on notebook state

### 📋 **Interactive Planning**
- LLM creates detailed analysis plans
- Plans displayed as editable cards in chat UI
- Users can modify plans in real-time

### 🔄 **Real-time Updates**
- Status updates streamed to chat UI
- Cells appear instantly via Y-document collaboration
- Progress tracking throughout workflow

### 🎯 **Context Awareness**
- Complete notebook state analysis
- Smart output summarization to avoid token limits
- Execution history tracking

### 🛠 **Multi-LLM Support**
- Router supports OpenAI, Anthropic, local models
- Easy switching between providers
- Cost and performance optimization

## Integration Points

### Existing Components
- **jupyter_agent_bridge** - Core notebook manipulation tools
- **jupyter_agent_ydoc** - Y-document collaboration
- **packages/chat** - Chat UI components
- **packages/chat-extension** - JupyterLab extension
- **mcp-snowflake-service** - External data access

### Data Flow
```
Chat Extension → LangGraph Agent → JupyterBridge → Notebook
                      ↓
              MCPConnector → External Data
                      ↓
              ChatHandler → Real-time Updates
```

## Usage

### Basic Usage
```typescript
import { DataAnalysisAgent } from '@jupyterlab/jupyter_agent_lg';

const agent = new DataAnalysisAgent({
  serverUrl: 'http://localhost:8890',
  token: 'your-token',
  llmProvider: 'openai',
  llmModel: 'gpt-4',
  maxSteps: 20,
  enableMCP: true,
  mcpServices: ['snowflake']
});

// Start analysis
const result = await agent.startAnalysis(
  'Analyze customer churn patterns',
  'analysis.ipynb',
  conversationHistory
);
```

### Integration with Chat Extension
The agent is designed to be called from the existing chat extension:

```typescript
// In chat extension
import { DataAnalysisAgent } from '@jupyterlab/jupyter_agent_lg';

const agent = new DataAnalysisAgent(config);
await agent.startAnalysis(userMessage, notebookPath, history);
```

## Development

### Building
```bash
npm run build
```

### Watching
```bash
npm run watch
```

### Testing
```bash
npm test
```

## Configuration

### Agent Config
```typescript
interface AgentConfig {
  serverUrl: string;           // JupyterLab server URL
  token: string;               // Authentication token
  defaultNotebook?: string;    // Default notebook path
  llmProvider: 'openai' | 'anthropic' | 'local';
  llmModel: string;            // Model name
  maxSteps: number;            // Max workflow steps
  enableMCP: boolean;          // Enable MCP services
  mcpServices: string[];       // MCP service names
}
```

## Workflow Example

```
User: "Analyze sales trends by region"

1. analyze_and_decide → No plan exists, empty notebook
   Decision: create_plan

2. create_plan → Generate 5-step analysis plan
   Display: Interactive plan cards in chat

3. analyze_and_decide → Plan exists, no data
   Decision: query_snowflake

4. query_snowflake → Load sales data into notebook
   Result: df variable with 10K rows

5. analyze_and_decide → Data loaded, no exploration
   Decision: execute_code

6. execute_code → Run df.describe(), df.info()
   Result: Data exploration outputs

7. analyze_and_decide → Basic analysis done, no viz
   Decision: create_visualization

8. create_visualization → Generate regional sales charts
   Result: Matplotlib plots in notebook

9. analyze_and_decide → Analysis complete
   Decision: complete_analysis

10. complete_analysis → Generate summary markdown
    Result: Final analysis report
```

## Status

- ✅ Core architecture implemented
- ✅ All workflow nodes defined
- ✅ Integration points established
- 🚧 LLM integration (Phase 2)
- 🚧 Real LangGraph implementation (Phase 2)
- 🚧 Interactive plan cards UI (Phase 2)
- 🚧 Multi-LLM router (Phase 3)

## Next Steps

1. **LLM Integration** - Connect to actual LLM providers
2. **LangGraph Implementation** - Replace mock workflow with real LangGraph
3. **Chat UI Integration** - Implement plan cards and status updates
4. **Testing** - Comprehensive test suite
5. **Documentation** - Usage examples and API docs

## Dependencies

- **LangGraph** - Workflow orchestration
- **LangChain** - LLM integration
- **@jupyterlab/chat** - Chat components
- **@jupyterlab/services** - Jupyter API access

---

This package represents the "intelligence layer" that orchestrates the existing JupyterLab agent infrastructure to provide sophisticated, LLM-driven data analysis workflows. 