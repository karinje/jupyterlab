# JupyterLab LangGraph Agent

A sophisticated LLM-driven data analysis agent for JupyterLab using LangGraph for workflow orchestration.

## Features

- **Pure LLM-Driven**: Every decision made by LLM with complete context awareness
- **Dynamic Planning**: Interactive plan creation and modification
- **Multi-Step Analysis**: Iterative workflow with context building
- **Real-Time Updates**: Status updates streamed to chat UI
- **Multi-LLM Support**: OpenAI, Anthropic Claude, Google Gemini (coming soon)
- **Cross-Cell Targeting**: Precise notebook manipulation with UUID-based cell identification

## Architecture

The LangGraph agent uses a state machine approach where:

1. **Analyze & Decide** - LLM analyzes current context and chooses next action
2. **Action Nodes** - Execute specific capabilities:
   - Create analysis plans
   - Execute code in notebooks
   - Query external data sources
   - Create visualizations
   - Handle user feedback
3. **State Management** - Maintains complete context across iterations
4. **Real-Time Communication** - Updates chat UI with progress

## Installation

```bash
# Install Python dependencies
cd packages/jupyter-agent
pip install -e .

# Install TypeScript package (for interfaces)
npm install
npm run build
```

## Configuration

Set your API keys:

```bash
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"  # Optional
```

Or configure through JupyterLab settings for OpenAI.

## Usage

The agent integrates with the JupyterLab chat extension. Select:

- **Provider**: OpenAI, Anthropic, or Google
- **Model**: Specific model (GPT-4o, Claude 3.5 Sonnet, etc.)
- **Mode**: LangGraph for complex analysis tasks

### Example Workflow

1. User: "Analyze customer churn patterns"
2. Agent creates analysis plan with steps
3. Agent loads data from external sources
4. Agent explores data structure and patterns
5. Agent creates visualizations
6. Agent summarizes findings
7. User can provide feedback at any point

## Components

### Core Classes

- **`DataAnalysisAgent`** - Main LangGraph workflow orchestrator
- **`StateManager`** - Manages analysis state and transitions
- **`NotebookStateManager`** - Efficient notebook context retrieval
- **`LLMRouter`** - Multi-provider LLM abstraction
- **`ChatHandler`** - Real-time communication with UI

### State Schema

The agent maintains comprehensive state including:

- Original user request and conversation history
- Complete notebook state with intelligent output summarization
- Analysis plan with step tracking
- Execution history and error handling
- Available data sources and resources

## Integration

The agent integrates with existing JupyterLab infrastructure:

- **JupyterAgent Tools** - Uses proven cell insertion and execution
- **MCP Servers** - Connects to external data sources
- **Chat Extension** - Seamless UI integration
- **Y-Document Sync** - Real-time notebook updates

## Development

### Adding New Providers

1. Implement `LLMProvider` interface
2. Add to `LLMRouter` registration
3. Update UI dropdown options

### Adding New Capabilities

1. Create new node function in `DataAnalysisAgent`
2. Add to workflow graph with routing
3. Update decision prompt with new action

### Testing

```bash
# Run agent tests
python -m pytest tests/

# Test with real notebook
python -m jupyter_agent_lg.test_agent
```

## Architecture Decisions

- **LangGraph over hardcoded logic** - Enables pure LLM decision making
- **Comprehensive state** - LLM needs complete context for good decisions
- **Real-time updates** - Users need visibility into agent progress
- **Provider abstraction** - Support multiple LLM providers seamlessly
- **Integration over replacement** - Build on proven JupyterAgent foundation

## Future Enhancements

- Multi-notebook orchestration
- Agent memory and learning
- Custom tool integration
- Advanced error recovery
- Performance optimization
- Export and reporting features
