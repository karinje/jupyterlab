# JupyterLab AI Assistant - Complete Technical Specification

> **Purpose**: This document captures the complete technical implementation of a ~21,000 line AI-powered JupyterLab extension. It is designed to be comprehensive enough that an AI coding assistant can recreate the entire system from scratch.

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Component 1: Chat System](#3-component-1-chat-system)
4. [Component 2: LangGraph Agent](#4-component-2-langgraph-agent)
5. [Component 3: Jupyter Tools Bridge](#5-component-3-jupyter-tools-bridge)
6. [Component 4: Chat Extension (JupyterLab Plugin)](#6-component-4-chat-extension)
7. [Critical Lessons Learned](#7-critical-lessons-learned)
8. [API Reference](#8-api-reference)
9. [Build & Development Workflow](#9-build--development-workflow)
10. [Testing](#10-testing)

---

## 1. Executive Summary

### What We Built
A fully integrated AI chat assistant for JupyterLab that can:
- Chat with users about their notebooks
- Execute code in notebooks in real-time
- Manipulate cells (insert, update, delete, execute)
- Support multiple LLM providers (OpenAI GPT-4o, Anthropic Claude, etc.)
- Maintain conversation threads per notebook
- Create and edit interactive analysis plans

### Key Statistics
- **Total Lines of Code**: ~21,000 (excluding auto-generated lock files)
- **Custom Commits**: 32
- **Main Components**: 4 packages + 1 server extension
- **API Endpoints**: 14
- **Languages**: TypeScript (frontend), Python (backend)

### Package Structure
```
jupyterlab/
├── packages/
│   ├── chat/                    # Chat UI + Python backend (6,555 lines)
│   │   ├── src/                 # TypeScript frontend
│   │   │   ├── widget.tsx       # Main chat UI (1,254 lines)
│   │   │   ├── service.ts       # Chat service (1,195 lines)
│   │   │   ├── cellmanager.ts   # Notebook integration (384 lines)
│   │   │   ├── llm.ts           # LLM providers (234 lines)
│   │   │   ├── models.ts        # Model configuration (109 lines)
│   │   │   └── tokens.ts        # Interfaces (224 lines)
│   │   └── jupyterlab_chat/     # Python backend
│   │       └── __init__.py      # All handlers (2,200 lines)
│   │
│   ├── chat-extension/          # JupyterLab plugin (536 lines)
│   │   └── src/index.ts         # Plugin registration (296 lines)
│   │
│   └── jupyter-agent/           # LangGraph agent (3,444 lines)
│       └── jupyter_agent_lg/
│           ├── agent.py         # Main agent (1,361 lines)
│           ├── state.py         # State management (286 lines)
│           ├── context.py       # Notebook context (307 lines)
│           └── tools/           # Tool implementations
│               ├── jupyter_tools.py  (302 lines)
│               ├── system_tools.py   (103 lines)
│               └── mcp_tools.py      (215 lines)
│
├── jupyter_tools_bridge/        # Server extension (1,724 lines)
│   ├── handlers.py              # REST API handlers (847 lines)
│   ├── tools.py                 # JupyterTools client (498 lines)
│   ├── logging_config.py        # Centralized logging (142 lines)
│   └── __init__.py              # Extension registration (57 lines)
│
└── mcp-snowflake-service/       # MCP integration (optional)
    └── server.py                # Snowflake MCP server
```

---

## 2. Architecture Overview

### Data Flow Diagram
```
┌─────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ ChatManager (widget.tsx)                                           │ │
│  │ • Floating dialog with drag/resize                                 │ │
│  │ • Thread history panel                                             │ │
│  │ • Model selector dropdown                                          │ │
│  │ • Message display with card rendering                              │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ User sends message
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND SERVICES                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │   ChatService    │  │   CellManager    │  │   LLMProvider    │      │
│  │   (service.ts)   │  │ (cellmanager.ts) │  │    (llm.ts)      │      │
│  │                  │  │                  │  │                  │      │
│  │ • WebSocket mgmt │  │ • Active nb path │  │ • Routes to      │      │
│  │ • Thread state   │  │ • Cell context   │  │   backend        │      │
│  │ • Request cancel │  │ • Scrolling      │  │ • Multi-provider │      │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘      │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ POST /api/chat/openai
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PYTHON BACKEND HANDLERS                               │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ ChatAgentHandler (jupyterlab_chat/__init__.py)                     │ │
│  │ • Receives message + context (notebook_path, thread_id)            │ │
│  │ • Loads conversation history from notebook metadata                │ │
│  │ • Routes to JupyterAgent for processing                            │ │
│  │ • Saves user message to thread                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  Other Handlers: ChatThreadsHandler, ChatStatusHandler, ChatMessageHandler │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ agent.process_request()
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LANGGRAPH AGENT                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ JupyterAgent (jupyter_agent_lg/agent.py)                           │ │
│  │                                                                    │ │
│  │  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐       │ │
│  │  │  START       │────▶│analyze_and_  │────▶│  Tool        │       │ │
│  │  │              │     │  decide      │     │  Execution   │       │ │
│  │  └──────────────┘     │  (LLM call)  │     └──────┬───────┘       │ │
│  │                       └──────────────┘            │               │ │
│  │                              ▲                    │               │ │
│  │                              └────────────────────┘               │ │
│  │                                (loop until RespondToUser)         │ │
│  │                                                                    │ │
│  │  Available Tools:                                                  │ │
│  │  • insert_and_execute_cell  - Insert code and run it              │ │
│  │  • update_and_execute_cell  - Modify existing cell and run        │ │
│  │  • delete_cell              - Remove a cell                        │ │
│  │  • RespondToUser            - Send message to chat UI             │ │
│  │  • CreatePlan               - Generate interactive plan cards     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ Tool calls (e.g., insert_and_execute_cell)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   JUPYTER TOOLS BRIDGE                                   │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ JupyterTools (jupyter_tools_bridge/tools.py)                       │ │
│  │ • HTTP client to /api/tools/* endpoints                            │ │
│  │ • XSRF token management (CRITICAL!)                                │ │
│  │ • Kernel discovery and caching                                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ REST Handlers (jupyter_tools_bridge/handlers.py)                   │ │
│  │ • InsertCellHandler:  /api/tools/insert-cell                       │ │
│  │ • ExecuteCellHandler: /api/tools/execute-cell                      │ │
│  │ • UpdateCellHandler:  /api/tools/update-cell                       │ │
│  │ • DeleteCellHandler:  /api/tools/delete-cell                       │ │
│  │ • SaveHandler:        /api/tools/save                              │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ YDoc operations
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      JUPYTERLAB CORE                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │   YNotebook      │  │   Kernel         │  │   Contents       │      │
│  │   (YDoc)         │  │   Manager        │  │   Manager        │      │
│  │                  │  │                  │  │                  │      │
│  │ • Real-time sync │  │ • Code execution │  │ • File I/O       │      │
│  │ • Cell CRUD      │  │ • Output capture │  │ • Persistence    │      │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Frontend-Driven Thread Management**: Frontend owns all thread IDs. Backend never creates thread IDs - it only uses what frontend provides.

2. **YDoc for Real-time Updates**: All cell manipulations go through YDoc (not Contents API) so changes appear instantly in the browser.

3. **Single Tool Per Turn**: Agent executes one tool at a time with `parallel_tool_calls=False` to ensure predictable state.

4. **WebSocket for Live Updates**: Status messages and assistant responses stream via WebSocket, not HTTP polling.

5. **Conversation Persistence in Notebook Metadata**: Threads stored in notebook's `metadata.chat_conversations` - travels with the notebook.

---

## 3. Component 1: Chat System

### 3.1 Frontend Widget (`packages/chat/src/widget.tsx`)

The chat UI is a pure DOM-based floating dialog (not React) for simplicity and direct control.

#### Key Structure

```typescript
export class ChatManager {
  private _isVisible: boolean = false;
  private _chatService: IChatService;
  private _dialogElement: HTMLDivElement | null = null;
  private _currentThreadId: string | null = null;
  private _availableThreads: any[] = [];

  constructor(chatService: IChatService) {
    this._chatService = chatService;
    // Expose globally for card interactions
    (window as any).chatManager = this;
    
    // Subscribe to plan events for card rendering
    if ((this._chatService as any).planReceived) {
      (this._chatService as any).planReceived.connect((_, payload) => {
        // Convert plan steps to [CARD:title|description] format
        const content = payload.steps
          .map((s: any) => `[CARD:${s.title}|${s.description}]`)
          .join('\n');
        this._addMessageToDisplay('assistant', content, new Date(), {
          messageType: 'plan'
        });
      });
    }
  }
}
```

#### Dialog HTML Structure

```typescript
private async _createDialog(): Promise<void> {
  this._dialogElement = document.createElement('div');
  this._dialogElement.style.cssText = `
    position: fixed;
    top: 50px; right: 50px;
    width: 350px; height: 500px;
    background: white;
    border: 1px solid #c0c0c0;
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
    z-index: 2000;
    display: none;
    flex-direction: column;
  `;

  this._dialogElement.innerHTML = `
    <div id="chat-header">...</div>
    <div id="thread-history-panel">...</div>
    <div id="chat-messages" class="jp-ChatDialog-messages"></div>
    <div><!-- Input area -->
      <textarea id="chat-input"></textarea>
      <button id="chat-send-btn">➤</button>
      <select id="chat-model">
        <option value="gpt-4o">GPT-4o</option>
        <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
        ...
      </select>
      <button id="thread-history-btn">🕐</button>
      <button id="new-thread-btn">+</button>
      <button id="clear-debug-btn">🧹</button>
    </div>
  `;
  
  // Make draggable and resizable
  this._makeDraggable(this._dialogElement, header);
  this._makeResizable(this._dialogElement);
}
```

#### Message Display with Card Detection

```typescript
private _addMessageToDisplay(
  role: 'user' | 'assistant',
  content: string,
  timestamp?: Date,
  metadata?: any
): void {
  const messageType = metadata?.messageType;
  const isStatusMessage = messageType === 'status';
  const isPlanMessage = messageType === 'plan';
  
  // Extract cards from content
  const cards = this._extractCardsFromContent(content);
  const hasCards = cards.length > 0;
  
  if (isStatusMessage) {
    // Subtle status card styling
    // ...
  } else if (hasCards || isPlanMessage) {
    // Render interactive cards
    messageDiv.innerHTML = this._renderCards(cards);
  } else {
    // Normal chat bubble
    // ...
  }
}

private _extractCardsFromContent(content: string): any[] {
  const cards: any[] = [];
  // Pattern: [CARD:title|description]
  const cardPattern = /\[CARD:([^|]+)\|([^\]]+)\]/g;
  let match;
  while ((match = cardPattern.exec(content)) !== null) {
    cards.push({
      id: `card-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      title: match[1].trim(),
      description: match[2].trim()
    });
  }
  return cards;
}
```

### 3.2 Chat Service (`packages/chat/src/service.ts`)

#### Core Service Implementation

```typescript
export class ChatService implements IChatService {
  private _llmProvider: ILLMProvider;
  private _cellManager: ICellManager;
  private _messages: IChatMessage[] = [];
  private _messageAdded = new Signal<this, IChatMessage>(this);
  private _ws: WebSocket | null = null;
  private _selectedThreadId: string | null = null;
  private _currentAbortController: AbortController | null = null;

  async sendMessage(message: string): Promise<void> {
    // Cancel any current request (ChatGPT-like behavior)
    await this._cancelCurrentRequest('interrupt');

    // Add user message to UI
    const userMessage: IChatMessage = {
      id: UUID.uuid4(),
      role: 'user',
      content: message,
      timestamp: new Date()
    };
    this._messages.push(userMessage);
    this._messageAdded.emit(userMessage);

    try {
      const context = await this._buildContext();
      this._currentAbortController = new AbortController();
      
      await this._llmProvider.sendMessage(
        message,
        context,
        this._currentAbortController.signal
      );
    } catch (error) {
      if (error?.name === 'AbortError') {
        // Show interruption message
        this._messageAdded.emit({
          id: UUID.uuid4(),
          role: 'assistant',
          content: 'Interrupting agent execution...',
          timestamp: new Date(),
          metadata: { messageType: 'interruption' }
        });
      }
    }
  }
}
```

#### Context Building (CRITICAL)

```typescript
private async _buildContext(): Promise<any> {
  const notebookPath = this._cellManager.getActiveNotebookPath?.() || null;

  // ALWAYS generate thread ID if missing
  if (!this._selectedThreadId) {
    this._selectedThreadId = UUID.uuid4();
  }

  // Collect plan cards for synchronous backend processing
  const currentPlan = this._collectCurrentPlanCards();

  return {
    notebook_path: notebookPath,
    thread_id: this._selectedThreadId,
    plan_cards: currentPlan?.length > 0 ? currentPlan : undefined
  };
}
```

#### WebSocket Connection for Live Updates

```typescript
connectStream(notebookPath: string | null): void {
  const settings = ServerConnection.makeSettings();
  let wsUrl = URLExt.join(settings.wsUrl, 'api', 'chat', 'stream');
  wsUrl += `?notebook_path=${encodeURIComponent(notebookPath || '*')}`;
  if (settings.token) {
    wsUrl += `&token=${encodeURIComponent(settings.token)}`;
  }

  const ws = new settings.WebSocket(wsUrl);
  this._ws = ws;
  
  ws.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    const type = data?.type;
    const payload = data?.payload || {};

    if (type === 'message') {
      // Assistant message from agent
      this._messages.push({
        id: UUID.uuid4(),
        role: 'assistant',
        content: payload.content,
        timestamp: new Date()
      });
      this._messageAdded.emit(/* ... */);
    } else if (type === 'status') {
      // Status update (e.g., "Executing code...")
      // ...
    } else if (type === 'plan_cards') {
      // Interactive plan from CreatePlan tool
      this._planReceived.emit({
        steps: payload.plan_steps,
        timestamp: payload.timestamp
      });
    } else if (type === 'scroll_to_cell') {
      // Scroll notebook to cell
      this._scrollToNotebookCell(payload.cell_index);
    }
  };
}
```

### 3.3 Python Backend (`packages/chat/jupyterlab_chat/__init__.py`)

#### Main Chat Handler

```python
class ChatAgentHandler(APIHandler):
    """Handler for agent chat requests with multi-LLM provider support"""
    
    _shared_agent = None  # Class-level agent for cancellation support

    async def post(self):
        body = json.loads(self.request.body)
        message = body.get("message", "")
        model = body.get("model", "gpt-4o-mini")
        provider = body.get("provider", "openai")
        context = body.get("context", {})
        notebook_path = context.get("notebook_path")
        thread_id = context.get("thread_id")

        # Load conversation history
        conversations = await self.conversation_manager.load_conversation_history(
            notebook_path
        )

        # Build conversation context for agent
        if thread_id and thread_id in conversations.get("threads", {}):
            thread_messages = conversations["threads"][thread_id].get("messages", [])
            # Filter out status messages
            conversation_context = [
                msg for msg in thread_messages
                if msg.get("metadata", {}).get("messageType") != "status"
            ][-100:]  # Last 100 messages

        # Save user message
        await self.conversation_manager.save_conversation_message(
            notebook_path, {"role": "user", "content": message}, thread_id
        )

        # Run LangGraph agent
        result = await self._run_langgraph_agent(
            message,
            notebook_path,
            conversation_context + [{"role": "user", "content": message}],
            model,
            provider,
            thread_id
        )

        self.write({
            "response": str(result),
            "thread_id": thread_id,
            "notebook_path": notebook_path
        })
```

#### Conversation Manager

```python
class ConversationManager:
    """Manages chat conversation threads in notebook metadata"""

    async def save_conversation_message(
        self,
        notebook_path: str,
        message: Dict,
        thread_id: Optional[str] = None,
        thread_title: Optional[str] = None,
    ) -> str:
        conversations = await self.load_conversation_history(notebook_path)

        # Create thread if it doesn't exist
        if not thread_id:
            thread_id = str(uuid.uuid4())

        if thread_id not in conversations["threads"]:
            conversations["threads"][thread_id] = {
                "created": datetime.utcnow().isoformat() + "Z",
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "title": thread_title or self._generate_thread_title(message.get("content", "")),
                "messages": [],
            }
            conversations["thread_order"].insert(0, thread_id)

        # Add message to thread
        conversations["threads"][thread_id]["messages"].append({
            **message,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        conversations["active_thread"] = thread_id

        # Save to notebook metadata via Contents API
        await self._save_conversations_to_notebook(notebook_path, conversations)
        return thread_id
```

#### WebSocket Broadcaster

```python
class ChatBroadcaster:
    """Simple in-process broadcaster keyed by notebook_path."""

    def __init__(self):
        self._subscribers: DefaultDict[str, Set[WebSocketHandler]] = defaultdict(set)
        self._recent_messages: Dict[tuple, float] = {}  # Dedup cache

    def broadcast(self, event: dict) -> None:
        notebook_path = event.get("notebook_path") or "*"
        payload = json.dumps(event)

        # Deduplicate assistant messages (2 second window)
        if event.get("type") == "message":
            content = event.get("payload", {}).get("content", "")
            key = (notebook_path, str(content))
            now = time.time() * 1000.0
            if now - self._recent_messages.get(key, 0) < 2000:
                return  # Skip duplicate
            self._recent_messages[key] = now

        # Deliver to targeted subscribers
        targets = list(self._subscribers.get(notebook_path, set()))
        for ws in targets:
            try:
                ws.write_message(payload)
            except Exception:
                # Prune dead connections
                self._subscribers[notebook_path].discard(ws)
```

---

## 4. Component 2: LangGraph Agent

### 4.1 Agent Class (`packages/jupyter-agent/jupyter_agent_lg/agent.py`)

#### Initialization

```python
class JupyterAgent:
    """LangGraph-based agent for Jupyter notebook tasks"""

    def __init__(
        self,
        server_url: str,
        token: str,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_notebook_path: str = "analysis.ipynb",
    ):
        self.server_url = server_url
        self.token = token
        self.current_task = None  # For cancellation

        # Initialize LLMs
        self.openai_llm = ChatOpenAI(
            api_key=openai_api_key, 
            model="gpt-4o", 
            temperature=0.2
        ) if openai_api_key else None
        
        self.claude_llm = ChatAnthropic(
            api_key=anthropic_api_key,
            model="claude-3-5-sonnet-20241022",
            temperature=0.2
        ) if anthropic_api_key else None

        # Create tools
        self.jupyter_tools_client = JupyterTools(server_url, token)
        self.jupyter_tools = create_jupyter_tools(
            self.jupyter_tools_client, 
            default_notebook_path
        )
        self.system_tools = create_system_tools(self.chat_handler)

        # Bind tools to LLMs (CRITICAL: parallel_tool_calls=False)
        all_tools = self.system_tools + self.jupyter_tools
        self.openai_llm_with_tools = self.openai_llm.bind_tools(
            all_tools, 
            parallel_tool_calls=False, 
            tool_choice="any"
        )

        # Build LangGraph workflow
        self.workflow = self._build_graph()
```

#### Graph Construction

```python
def _build_graph(self):
    """Build the LangGraph workflow."""
    workflow = StateGraph(AnalysisState)
    
    # Add nodes
    workflow.add_node("analyze_and_decide", self.analyze_and_decide)
    
    # Set entry point
    workflow.set_entry_point("analyze_and_decide")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "analyze_and_decide",
        self._route_after_decision,
        {
            "continue": "analyze_and_decide",  # Loop back for more tool calls
            "end": END,                         # Stop when RespondToUser called
        }
    )
    
    return workflow.compile()

def _route_after_decision(self, state: AnalysisState) -> str:
    """Route based on last tool call."""
    last_tool = state.get("last_tool_name")
    
    # RespondToUser ends the conversation turn
    if last_tool == "RespondToUser":
        return "end"
    
    # Check iteration limit
    if state.get("iteration_count", 0) >= 10:
        return "end"
    
    return "continue"
```

#### Core Decision Node

```python
async def analyze_and_decide(self, state: AnalysisState) -> AnalysisState:
    """Main LLM decision node with tool calling."""
    
    # Select LLM based on provider
    provider = state.get("provider", "openai")
    if provider == "anthropic" and self.claude_llm_with_tools:
        llm = self.claude_llm_with_tools
    else:
        llm = self.openai_llm_with_tools

    # Build messages for LLM
    messages = self._build_messages(state)

    # Invoke LLM
    response = await llm.ainvoke(messages)

    # Process tool calls
    if hasattr(response, 'tool_calls') and response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_name = tool_call['name']
        tool_args = tool_call['args']

        # Send status message if provided
        if 'status_message' in tool_args:
            await self.chat_handler.send_status(tool_args['status_message'])

        # Execute the tool
        tool_result = await self._execute_tool(tool_name, tool_args, state)

        # Update state
        state["last_tool_name"] = tool_name
        state["last_tool_result"] = tool_result
        state["messages"].append({
            "role": "assistant",
            "content": "",
            "tool_calls": [tool_call]
        })
        state["messages"].append({
            "role": "tool",
            "content": str(tool_result),
            "tool_call_id": tool_call['id']
        })

    state = increment_iteration(state)
    return state
```

### 4.2 Tools Implementation

#### Jupyter Tools (`jupyter_agent_lg/tools/jupyter_tools.py`)

```python
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

class InsertAndExecuteCellInput(BaseModel):
    code: str = Field(description="Python code to insert and execute")
    cell_type: str = Field(default="code", description="Cell type: 'code' or 'markdown'")
    position: str = Field(default="end", description="Where to insert: 'end' or index")

def create_jupyter_tools(jupyter_client: JupyterTools, default_notebook_path: str):
    """Create LangChain tools for Jupyter operations."""
    
    async def insert_and_execute_cell(
        code: str,
        cell_type: str = "code",
        position: str = "end",
    ) -> str:
        """Insert code into notebook and execute it."""
        try:
            # Insert the cell
            result = await jupyter_client.insert_cell(
                default_notebook_path,
                code,
                cell_type=cell_type,
                cell_index=position
            )
            cell_id = result.get("cell_id")
            index = result.get("index")

            if cell_type == "code":
                # Get kernel and execute
                kernel_id = await jupyter_client.get_kernel_for_notebook(
                    default_notebook_path
                )
                exec_result = await jupyter_client.execute_cell(
                    default_notebook_path,
                    kernel_id,
                    index=index,
                    scroll_to_cell=True
                )
                
                execution_count = exec_result.get("execution_count")
                outputs_count = exec_result.get("outputs_count", 0)
                
                return f"Code executed successfully. execution_count={execution_count}, outputs={outputs_count}"
            
            return f"Markdown cell inserted at index {index}"
            
        except Exception as e:
            return f"Error: {str(e)}"

    return [
        StructuredTool.from_function(
            func=insert_and_execute_cell,
            name="insert_and_execute_cell",
            description="Insert and execute Python code in the notebook",
            args_schema=InsertAndExecuteCellInput,
            coroutine=insert_and_execute_cell,
        ),
        # ... more tools
    ]
```

#### System Tools (`jupyter_agent_lg/tools/system_tools.py`)

```python
class RespondToUserInput(BaseModel):
    message: str = Field(description="Message to send to the user")
    intent: str = Field(
        default="inform",
        description="Intent: 'inform', 'ask_clarification', 'report_error', 'complete'"
    )

def create_system_tools(chat_handler: ChatHandler):
    """Create system tools for chat interaction."""
    
    async def respond_to_user(message: str, intent: str = "inform") -> str:
        """Send a response message to the user through the chat interface."""
        await chat_handler.send_message(
            message,
            thread_id=chat_handler.current_thread_id
        )
        return f"responded: intent={intent}"

    async def create_plan(steps: List[Dict[str, str]]) -> str:
        """Create an interactive plan with editable cards."""
        await chat_handler.display_plan_cards(
            steps,
            thread_id=chat_handler.current_thread_id
        )
        return f"Plan created with {len(steps)} steps"

    return [
        StructuredTool.from_function(
            func=respond_to_user,
            name="RespondToUser",
            description="Send a message to the user. USE THIS to communicate results.",
            args_schema=RespondToUserInput,
            coroutine=respond_to_user,
        ),
        StructuredTool.from_function(
            func=create_plan,
            name="CreatePlan",
            description="Create an interactive analysis plan with editable steps",
            coroutine=create_plan,
        ),
    ]
```

---

## 5. Component 3: Jupyter Tools Bridge

### 5.1 REST API Handlers (`jupyter_tools_bridge/handlers.py`)

#### Base Handler with YDoc Access

```python
class BaseToolsHandler(APIHandler):
    """Base handler with common functionality."""

    async def get_live_notebook(self, path: str) -> Optional[YNotebook]:
        """
        Get the live YNotebook for a given path.
        
        CRITICAL: This is the key to real-time updates!
        """
        try:
            # Get YDoc extension from settings
            ydoc_ext = self.settings.get("jupyter_server_ydoc")
            
            if not ydoc_ext:
                self.log.error("YDocExtension not found in settings")
                return None

            # Get live document (requires jupyter-collaboration package!)
            ydoc = await ydoc_ext.get_document(
                path=path,
                content_type="notebook",
                file_format="json",
                copy=False  # Get the LIVE document, not a copy
            )
            
            if not isinstance(ydoc, YNotebook):
                self.log.error(f"Document is not YNotebook: {type(ydoc)}")
                return None

            return ydoc

        except Exception as e:
            self.log.error(f"Failed to get live notebook: {e}")
            return None
```

#### Insert Cell Handler

```python
class InsertCellHandler(BaseToolsHandler):
    """Handler for inserting cells into a notebook."""

    async def post(self):
        data = self.get_json_body()
        
        path = data.get("path")
        index = data.get("index", "append")
        cell_type = data.get("cell_type", "code")
        source = data.get("source", "")
        cell_id = data.get("cell_id", str(uuid.uuid4()))

        # Get the LIVE notebook (via YDoc)
        notebook = await self.get_live_notebook(path)
        if not notebook:
            raise HTTPError(404, f"Notebook not open: {path}")

        # Create cell in nbformat structure
        cell = {
            "id": cell_id,
            "cell_type": cell_type,
            "source": source,
            "metadata": {},
            "execution_state": "idle",
            "execution_count": None,
            "outputs": [] if cell_type == "code" else None,
        }

        # Insert via YNotebook API (triggers real-time sync!)
        if index == "append":
            pre_count = len(notebook.ycells)
            notebook.append_cell(cell)
            actual_index = pre_count
        else:
            idx = int(index)
            ycell = notebook.create_ycell(cell)
            notebook.set_ycell(idx, ycell)
            actual_index = idx

        self.finish(json.dumps({
            "status": "success",
            "cell_id": cell_id,
            "index": actual_index
        }))
```

#### Execute Cell Handler

```python
class ExecuteCellHandler(BaseToolsHandler):
    """Handler for executing cells."""

    async def post(self):
        data = self.get_json_body()
        
        path = data.get("path")
        kernel_id = data.get("kernel_id")
        cell_id = data.get("cell_id")
        index = data.get("index")
        scroll_to_cell = data.get("scroll_to_cell", True)

        # Get notebook and find target cell
        notebook = await self.get_live_notebook(path)
        if not notebook:
            raise HTTPError(404, f"Notebook not open: {path}")

        target_index = self._find_cell_index(notebook, cell_id, index)
        cell = notebook.get_cell(target_index)
        source = cell.get("source", "")

        # Get kernel client
        kernel = self.kernel_manager.get_kernel(kernel_id)
        client = kernel.client()
        client.start_channels()

        try:
            # Execute code
            msg_id = client.execute(source)
            
            # Collect outputs from IOPub
            outputs = []
            execution_count = None
            
            while True:
                try:
                    msg = client.get_iopub_msg(timeout=30)
                    msg_type = msg["msg_type"]
                    content = msg["content"]
                    parent_msg_id = msg.get("parent_header", {}).get("msg_id")
                    
                    if parent_msg_id != msg_id:
                        continue
                    
                    if msg_type == "execute_input":
                        execution_count = content.get("execution_count")
                    elif msg_type in ("stream", "display_data", "execute_result", "error"):
                        output = self.map_to_nbformat_output(msg_type, content)
                        if output:
                            outputs.append(output)
                    elif msg_type == "status" and content.get("execution_state") == "idle":
                        break
                        
                except Exception:
                    break

            # Update cell in YDoc with outputs
            cell["execution_count"] = execution_count
            cell["outputs"] = outputs
            notebook.set_cell(target_index, cell)

            # Broadcast scroll command if requested
            if scroll_to_cell:
                await self._broadcast_scroll(path, target_index)

            self.finish(json.dumps({
                "status": "success",
                "execution_count": execution_count,
                "outputs_count": len(outputs),
                "outputs_attached": True,
                "scrolled": scroll_to_cell
            }))

        finally:
            client.stop_channels()
```

### 5.2 JupyterTools Client (`jupyter_tools_bridge/tools.py`)

```python
class JupyterTools:
    """High-level tools interface for notebook manipulation."""

    def __init__(self, base_url: str, token: str = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = None
        self._kernel_cache = {}
        self._xsrf_token: Optional[str] = None

    async def _ensure_xsrf_cookie(self):
        """
        CRITICAL: Get XSRF token before any POST request!
        
        Without this, all POST requests fail with 403 Forbidden.
        """
        if self._xsrf_token:
            return
            
        await self._ensure_session()
        
        # Visit /lab to get the cookie
        async with self.session.get(
            f"{self.base_url}/lab",
            headers=self._get_headers()
        ) as resp:
            xsrf_cookie = resp.cookies.get("_xsrf")
            if xsrf_cookie and xsrf_cookie.value:
                self._xsrf_token = xsrf_cookie.value
                logger.info(f"Got XSRF token: {self._xsrf_token[:10]}...")

    async def insert_cell(
        self,
        notebook_path: str,
        content: str,
        cell_type: str = "code",
        cell_index: Union[int, str] = "append",
    ) -> Dict[str, Any]:
        """Insert a cell with XSRF handling."""
        await self._ensure_xsrf_cookie()

        url = f"{self.base_url}/api/tools/insert-cell"
        data = {
            "path": notebook_path,
            "source": content,
            "cell_type": cell_type,
            "index": cell_index,
        }

        # MUST send both cookie AND header!
        headers = self._get_headers(xsrf=self._xsrf_token)
        cookies = {'_xsrf': self._xsrf_token} if self._xsrf_token else {}

        async with self.session.post(
            url, json=data, headers=headers, cookies=cookies
        ) as response:
            if response.status != 200:
                error = await response.text()
                raise Exception(f"Insert failed: {error}")
            return await response.json()

    async def get_kernel_for_notebook(self, notebook_path: str) -> str:
        """Get or discover kernel ID for a notebook."""
        if notebook_path in self._kernel_cache:
            return self._kernel_cache[notebook_path]

        # Query sessions API
        async with self.session.get(
            f"{self.base_url}/api/sessions",
            headers=self._get_headers()
        ) as resp:
            sessions = await resp.json()
            
            for session in sessions:
                if session.get("path") == notebook_path:
                    kernel_id = session.get("kernel", {}).get("id")
                    if kernel_id:
                        self._kernel_cache[notebook_path] = kernel_id
                        return kernel_id
        
        raise Exception(f"No kernel found for {notebook_path}")
```

---

## 6. Component 4: Chat Extension

### 6.1 Plugin Registration (`packages/chat-extension/src/index.ts`)

```typescript
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { INotebookTracker } from '@jupyterlab/notebook';
import { ChatService, ChatManager, CellManager, OpenAIProvider } from '@jupyterlab/chat';

const chatExtension: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/chat-extension:plugin',
  autoStart: true,
  requires: [INotebookTracker],
  activate: (app: JupyterFrontEnd, notebookTracker: INotebookTracker) => {
    console.log('Chat extension activating...');

    // Create cell manager with notebook tracker
    const cellManager = new CellManager(notebookTracker);
    
    // Create LLM provider
    const llmProvider = new OpenAIProvider();
    
    // Create chat service
    const chatService = new ChatService(llmProvider, cellManager);
    
    // Create chat manager (UI)
    const chatManager = new ChatManager(chatService);

    // Register command to toggle chat
    app.commands.addCommand('chat:toggle', {
      label: 'Toggle Chat',
      execute: () => chatManager.toggle()
    });

    // Add keyboard shortcut
    app.commands.addKeyBinding({
      command: 'chat:toggle',
      keys: ['Accel Shift C'],
      selector: 'body'
    });

    // CRITICAL: Handle notebook switching
    notebookTracker.currentChanged.connect(async (_, notebook) => {
      if (notebook) {
        const path = notebook.context.path;
        console.log(`Notebook changed to: ${path}`);
        
        // Update WebSocket connection
        chatService.connectStream(path);
        
        // Load conversation history for new notebook
        await chatService.loadConversationHistory(path, true);
      }
    });

    // Connect WebSocket on startup
    const currentPath = notebookTracker.currentWidget?.context.path || null;
    chatService.connectStream(currentPath);

    console.log('Chat extension activated!');
  }
};

export default chatExtension;
```

---

## 7. Critical Lessons Learned

> **⚠️ This section captures bugs that took hours/days to fix. Pay close attention!**

### 7.1 XSRF Token Handling

**Problem**: All POST requests to Jupyter APIs fail with `403 Forbidden: XSRF cookie does not match POST argument`

**Root Cause**: Jupyter requires both:
1. `_xsrf` cookie in the request
2. `X-XSRFToken` header with same value

**Solution**:
```python
async def _ensure_xsrf_cookie(self):
    """MUST call before any POST request!"""
    url = f"{self.base_url}/lab"
    async with self.session.get(url, headers=self._get_headers()) as resp:
        xsrf_cookie = resp.cookies.get("_xsrf")
        if xsrf_cookie:
            self._xsrf_token = xsrf_cookie.value

async def insert_cell(self, ...):
    await self._ensure_xsrf_cookie()
    
    # Send BOTH cookie AND header
    headers = {"X-XSRFToken": self._xsrf_token}
    cookies = {"_xsrf": self._xsrf_token}
    
    async with self.session.post(url, json=data, headers=headers, cookies=cookies):
        ...
```

### 7.2 YDoc/Collaboration Package Paradox

**Problem**: `YDocExtension.get_document()` returns `None` even though notebooks are open.

**Root Cause**: The `jupyter-collaboration` package MUST be installed, even though its server extension fails to load!

**Why**: The package provides dependencies that enable YDoc document tracking. Without it, `get_document()` doesn't work.

**Solution**:
```bash
pip install jupyter-collaboration  # Required even though it shows loading error!
```

**Expected startup logs**:
```
[I] jupyter_server_ydoc | extension was successfully loaded.
[W] jupyter_collaboration | extension failed loading  # THIS IS OK!
```

### 7.3 dev_mode Webpack Build

**Problem**: TypeScript changes in `packages/*/src/` don't appear in the browser.

**Root Cause**: JupyterLab dev mode loads bundles from `dev_mode/static/`, not individual package `lib/` directories.

**Wrong Approaches**:
- ❌ Hard refresh browser
- ❌ Restart JupyterLab only
- ❌ Run `npm run watch` in individual packages

**Correct Solution**:
```bash
# MUST run webpack watch in dev_mode
cd dev_mode && npm run watch

# In separate terminal, run JupyterLab
jupyter lab --dev-mode --extensions-in-dev-mode
```

### 7.4 Thread ID Management

**Problem**: User and assistant messages were being saved to different threads.

**Root Cause**: Backend was generating thread IDs independently of frontend.

**Solution**: Frontend-driven thread management:

```typescript
// Frontend ALWAYS provides thread_id
private async _buildContext(): Promise<any> {
  if (!this._selectedThreadId) {
    this._selectedThreadId = UUID.uuid4();  // Frontend generates
  }
  return {
    notebook_path: notebookPath,
    thread_id: this._selectedThreadId  // ALWAYS send
  };
}
```

```python
# Backend NEVER generates thread_id
async def post(self):
    thread_id = context.get("thread_id")  # Use frontend's ID
    # Never do: thread_id = thread_id or str(uuid.uuid4())
```

### 7.5 WebSocket Message Deduplication

**Problem**: Assistant messages appeared twice in chat UI.

**Root Cause**: Messages broadcast via WebSocket AND returned via HTTP response.

**Solution**: Only display messages from WebSocket, ignore HTTP response:

```typescript
// service.ts
async sendMessage(message: string): Promise<void> {
  const response = await this._llmProvider.sendMessage(message, context);
  
  // Do NOT add assistant message from HTTP response
  // It will come via WebSocket broadcast
  console.log('[CHAT] HTTP return ignored; waiting for WS broadcast');
}
```

### 7.6 Notebook Path Targeting

**Problem**: Chat was sending messages to wrong notebook (e.g., "Untitled.ipynb" instead of active notebook).

**Root Cause**: `getActiveNotebookPath()` was returning stale cached value.

**Solution**: Always get fresh path from notebookTracker:

```typescript
// cellmanager.ts
getActiveNotebookPath(): string | null {
  // Get from tracker, not cache
  const panel = this._notebookTracker.currentWidget;
  const currentPath = panel?.context?.path || null;

  // Cache for fallback only
  if (currentPath) {
    this._lastNotebookPath = currentPath;
  }

  return currentPath || this._lastNotebookPath;
}
```

### 7.7 Status Messages Polluting Threads

**Problem**: Every status message ("Executing code...") created its own thread.

**Root Cause**: `ChatStatusHandler` was saving status messages to conversation history.

**Solution**: Status messages are broadcast-only, never saved:

```python
class ChatStatusHandler(APIHandler):
    async def post(self):
        # DO NOT save to conversation history
        # Status messages should only be broadcast for real-time display
        chat_broadcaster.broadcast({
            "type": "status",
            "notebook_path": notebook_path,
            "payload": {"message": msg_text}
        })
        # NO: await conv.save_conversation_message(...)
```

### 7.8 Contents API vs YDoc Race Condition

**Problem**: Agent-inserted cells disappeared after chat saved conversation.

**Root Cause**: 
1. Agent inserts cells via YDoc (live state)
2. Chat saves metadata via Contents API (reads from disk)
3. Contents API write overwrites YDoc changes

**Solution**: Chat must also use YDoc for metadata:

```python
async def _save_conversations_to_notebook(self, notebook_path, conversations):
    # WRONG: Contents API
    # notebook = await contents_manager.get(notebook_path)
    # notebook["metadata"]["chat_conversations"] = conversations
    # await contents_manager.save(notebook, notebook_path)
    
    # RIGHT: YDoc (same live state as agent tools)
    ydoc = await ydoc_ext.get_document(notebook_path, ...)
    current_notebook = ydoc.get()
    current_notebook["metadata"]["chat_conversations"] = conversations
    ydoc.set(current_notebook)
```

---

## 8. API Reference

### Chat Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/openai` | POST | Send message to agent |
| `/api/chat/stream` | WebSocket | Real-time updates |
| `/api/chat/threads` | GET | Get conversation threads |
| `/api/chat/thread-title` | POST | Save thread title |
| `/api/chat/cancel` | POST | Cancel running agent |
| `/api/chat/status` | POST | Send status update |
| `/api/chat/message` | POST | Send assistant message |
| `/api/chat/conversations` | POST/PUT/DELETE | Thread management |
| `/api/chat/plan_cards` | POST | Display plan cards |
| `/api/chat/scroll` | POST | Scroll notebook to cell |

### Tools Bridge Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tools/insert-cell` | POST | Insert new cell |
| `/api/tools/update-cell` | POST | Update cell content |
| `/api/tools/delete-cell` | POST | Delete cell |
| `/api/tools/execute-cell` | POST | Execute cell |
| `/api/tools/save` | POST | Force save notebook |

---

## 9. Build & Development Workflow

### Initial Setup

```bash
# 1. Install JupyterLab distribution
cd /path/to/jupyterlab
pip install -e .

# 2. Install backend packages
pip install backports.tarfile  # Fix setuptools issue
pip install -e jupyter_tools_bridge
pip install -e packages/chat
pip install -e packages/jupyter-agent

# 3. Install collaboration package (REQUIRED!)
pip install jupyter-collaboration

# 4. Build frontend
cd packages/chat && jlpm build
cd ../chat-extension && jlpm build

# 5. Build dev_mode bundle (CRITICAL!)
cd ../../dev_mode && npm run build
```

### Development Mode

Terminal 1:
```bash
cd dev_mode && npm run watch
```

Terminal 2:
```bash
jupyter lab --dev-mode --extensions-in-dev-mode \
  --ServerApp.log_level=DEBUG \
  --port=8890 \
  --config=jupyter_server_config.py
```

### Configuration (`jupyter_server_config.py`)

```python
c.ServerApp.jpserver_extensions = {
    "jupyter_server_fileid": True,
    "jupyter_server_ydoc": True,
    "jupyter_tools_bridge": True,
    "jupyterlab_chat": True,
}

c.YDocExtension.collaborative = True

c.ServerApp.websocket_ping_interval = 30
c.ServerApp.websocket_ping_timeout = 25
```

---

## 10. Testing

### Manual Testing Flow

1. Open notebook in JupyterLab
2. Press `Cmd+Shift+C` to open chat
3. Send: "create a simple matplotlib plot"
4. Verify:
   - Code cell appears in notebook
   - Plot renders inline
   - Assistant responds in chat

### Test Scripts

```bash
# Test YDoc tools
python test_scripts/test_ydoc_tools.py

# Test notebook isolation
python test_notebook_isolation.py

# Check environment
python test_scripts/tools_env_check.py
```

### Key Test Cases

1. **Thread Isolation**: Messages in Notebook A don't appear in Notebook B
2. **Cancellation**: Sending new message cancels previous agent execution
3. **Notebook Switching**: Chat context switches when changing notebooks
4. **Real-time Updates**: Code cells appear instantly without refresh
5. **Output Capture**: Matplotlib plots render in notebook cells

---

## Appendix: File Size Reference

| File | Lines | Description |
|------|-------|-------------|
| `jupyterlab_chat/__init__.py` | 2,200 | All Python backend handlers |
| `widget.tsx` | 1,254 | Chat UI implementation |
| `agent.py` | 1,361 | LangGraph agent |
| `service.ts` | 1,195 | Chat service |
| `handlers.py` (tools) | 847 | YDoc REST handlers |
| `tools.py` (bridge) | 498 | JupyterTools client |
| `cellmanager.ts` | 384 | Notebook integration |
| `index.ts` (extension) | 296 | Plugin registration |
| `state.py` | 286 | Agent state |
| `llm.ts` | 234 | LLM providers |
| `tokens.ts` | 224 | TypeScript interfaces |

---

*Document generated: December 2024*
*Total implementation effort: ~21,000 lines across 32 commits*

