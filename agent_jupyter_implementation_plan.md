# JupyterLab Agent Extension Implementation Plan (Latest)

## Executive Summary
A single-tool-per-turn LangGraph agent drives notebook operations with strict tool protocol compliance and real-time-safe server mechanics.

- One LLM call per turn, exactly one tool call per turn: `tool_choice="any"`, `parallel_tool_calls=False`.
- All bound tools accept an optional `status_message`. The executor surfaces it to chat before running the tool.
- No StatusRouteUpdate tool. No separate validator node. Validation is integrated via a guarded self-loop in `analyze_and_decide`.
- Routing is derived from the tool name:
  - Jupyter tools (e.g., `insert_and_execute_cell`, `delete_cell`) → continue (loop to `analyze_and_decide`).
  - Snowflake MCP tools → continue.
  - `RespondToUser(intent="completion")` → END (end of this LangGraph run; conversation persists externally).
  - `CreatePlan` displays plan cards and then continues.
- Strict OpenAI tool-call protocol: if the last assistant message has `tool_calls`, we must execute them and append `ToolMessage`(s) with the exact `tool_call_id` before any further assistant/system message.
- Notebook context: fetch fresh state via `get_complete_notebook_state`, summarize via `_summarize_notebook` for LLM context. These are complementary (fresh data vs. compact prompt context).
- All hardcoded heuristics removed (e.g., any bespoke `x**2` / `x**3` logic).

---

## 🚨 CRITICAL: Dev Mode Setup & Troubleshooting Guide

### **Complete Working Setup (PROVEN)**

This section documents the exact process to get chat + WebSocket + agent working in dev mode without duplicate messages or missing functionality.

#### **1. Required JupyterLab Flags (CRITICAL)**
```bash
jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py --no-browser
```

**Why each flag is essential:**
- `--dev-mode` - Loads from dev bundles in `dev_mode/static/`
- `--extensions-in-dev-mode` - **CRITICAL**: Enables `jupyter_tools_bridge` extension for notebook operations
- `--config=jupyter_server_config.py` - Enables collaboration (`jupyter_server_ydoc`) and chat backend (`jupyterlab_chat`)
- `--port=8890` - Avoids conflicts with other instances
- `--ServerApp.log_level=DEBUG` - Shows detailed logs for debugging

**Missing `--extensions-in-dev-mode` causes:**
- Agent can send chat messages but cannot execute notebook operations
- XSRF errors when trying to insert/execute cells
- Status messages work but no actual code execution

#### **2. Backend Python Package Installation**
```bash
# Install backend packages in correct order
pip install -e jupyter_tools_bridge
pip install -e packages/chat
pip install -e packages/jupyter-agent
```

**Verification:**
```bash
jupyter server extension list | grep -E "jupyterlab_chat|jupyter_tools_bridge"
# Should show both as enabled
```

#### **3. Frontend Bundle Build Process**
```bash
# Build chat packages
cd packages/chat && jlpm build
cd ../chat-extension && jlpm build

# CRITICAL: Rebuild dev_mode bundles (this was the key missing step)
cd ../../dev_mode && npm run build
```

**Why dev_mode build is critical:**
- JupyterLab dev mode loads bundles from `dev_mode/static/`, not individual package `lib/` directories
- Without this, frontend changes never reach the browser
- This was the root cause of duplicate messages persisting

#### **4. WebSocket Duplicate Message Fix**

**Problem**: Frontend was adding assistant messages twice - once from HTTP response and once from WebSocket broadcast.

**Solution in `packages/chat/src/service.ts`:**
```typescript
async sendMessage(message: string): Promise<void> {
    // ... add user message ...

    try {
        const context = this._buildContext();
        const response = await this._llmProvider.sendMessage(message, context);

        // ✅ CRITICAL FIX: Do not add assistant message from HTTP response
        // Rely solely on WebSocket broadcast for assistant messages
        console.log('[CHAT] HTTP return ignored; waiting for WS broadcast');
    } catch (error) {
        // ... handle errors ...
    }
}
```

**Additional safeguards:**
- Client-side deduplication in `packages/chat/src/widget.tsx` (1-second window)
- Server-side deduplication in `ChatBroadcaster` (2-second window for identical content)
- WebSocket connection management with proper cleanup

#### **5. WebSocket Implementation Details**

**Backend (`packages/chat/jupyterlab_chat/__init__.py`):**
```python
class ChatBroadcaster:
    def broadcast(self, event: dict) -> None:
        # Deliver to either targeted subscribers OR global subscribers, never both
        notebook_path = event.get("notebook_path") or "*"
        if notebook_path and notebook_path != "*":
            targets = list(self._subscribers.get(notebook_path, set()))
        else:
            targets = list(self._subscribers.get("*", set()))
```

**Frontend (`packages/chat/src/service.ts`):**
```typescript
connectStream(notebookPath: string | null): void {
    const path = notebookPath || '*';
    const settings = ServerConnection.makeSettings();
    let wsUrl = URLExt.join(settings.wsUrl, 'api', 'chat', 'stream');
    const params: string[] = [`notebook_path=${encodeURIComponent(path)}`];
    if (settings.appendToken && settings.token) {
        params.push(`token=${encodeURIComponent(settings.token)}`);
    }
    wsUrl = wsUrl + `?${params.join('&')}`;

    const ws = new settings.WebSocket(wsUrl);
    this._bindWS(ws);
}
```

#### **6. Chat Extension Singleton Fix**

**Problem**: Multiple chat service instances created, leading to duplicate WebSocket connections.

**Solution in `packages/chat-extension/src/index.ts`:**
```typescript
// Hard singleton guard across potential multiple activations
const __w = (window as any);
if (__w.__JLAB_CHAT_SERVICE && __w.__JLAB_CHAT_MANAGER) {
    globalChatService = __w.__JLAB_CHAT_SERVICE as ChatService;
    globalChatManager = __w.__JLAB_CHAT_MANAGER as ChatManager;
}

const ensureChatService = async (): Promise<{chatService: ChatService; chatManager: ChatManager;}> => {
    if (!globalChatService || !globalChatManager) {
        globalChatService = new ChatService(llmProvider, cellManager);
        globalChatManager = new ChatManager(globalChatService);
        __w.__JLAB_CHAT_SERVICE = globalChatService;
        __w.__JLAB_CHAT_MANAGER = globalChatManager;

        // Connect WebSocket to active notebook
        const path = cellManager.getActiveNotebookPath?.() || null;
        globalChatService.connectStream?.(path);

        // Set up notebook change listener (once only)
        if (!__w.__JLAB_CHAT_WATCH_BOUND) {
            notebookTracker.currentChanged.connect(() => {
                const newPath = cellManager.getActiveNotebookPath?.() || null;
                globalChatService?.connectStream?.(newPath);
            });
            __w.__JLAB_CHAT_WATCH_BOUND = true;
        }
    }
    return { chatService: globalChatService, chatManager: globalChatManager };
};
```

#### **7. Agent Recursion Fix**

**Problem**: LangGraph agent hit recursion limit when user said "hi" (no tool calls generated).

**Solution in `packages/jupyter-agent/jupyter_agent_lg/agent.py`:**
```python
async def execute_tools(self, state: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing code ...

    route = "continue"
    if name == "RespondToUser":  # ✅ FIX: End on ANY RespondToUser, not just completion intent
        route = "end"
        preserved_state["final_result"] = args.get("message", "")

    preserved_state["route_after_tools"] = route
    # ... existing code ...
```

#### **8. Browser Cache Busting**

**Problem**: Browser loads stale JavaScript bundles despite rebuilds.

**Solutions:**
1. **Version bump** in `packages/chat-extension/package.json` (e.g., `4.1.0` → `4.1.3`)
2. **Hard refresh** with DevTools cache disabled (`Cmd+Shift+R` on Mac)
3. **Rebuild dev_mode** after any frontend changes: `cd dev_mode && npm run build`

#### **9. Complete Restart Procedure**

When making changes, follow this exact sequence:

```bash
# 1. Kill existing JupyterLab
pkill -f "jupyter-lab" || true

# 2. Rebuild frontend if changed
cd packages/chat && jlpm build
cd ../chat-extension && jlpm build
cd ../../dev_mode && npm run build

# 3. Reinstall backend if changed
pip install -e packages/chat

# 4. Start with correct flags
jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py --no-browser

# 5. In browser: Hard refresh with cache disabled
# 6. Test: Open notebook, open chat, send message
```

#### **10. Verification Checklist**

**✅ Backend working:**
```bash
# Check extensions loaded
grep "jupyterlab_chat.*successfully loaded" jlab.log
grep "jupyter_tools_bridge" jlab.log

# Check WebSocket broadcasts
grep "\[WS\] broadcast" jlab.log
```

**✅ Frontend working (browser console):**
```javascript
// Should see new version logs
"🌟🌟🌟 CHAT EXTENSION ACTIVATING - NEW VERSION! 🌟🌟🌟"

// Should see WebSocket logs, NOT old HTTP logs
"[CHAT] HTTP return ignored; waiting for WS broadcast"
"[WS] open path= Untitled.ipynb"

// Should NOT see old logs
❌ "About to enhance message with context..."
❌ "LLM response received:"
```

**✅ Agent working:**
```bash
# Check tool execution
grep "🛠️ \[tools\] executing name=" jlab.log

# Check notebook operations
grep "insert_and_execute_cell" jlab.log

# Should see only one assistant message per request in chat UI
```

#### **11. Common Failure Modes & Fixes**

| **Problem** | **Symptom** | **Root Cause** | **Fix** |
|-------------|-------------|----------------|---------|
| **Duplicate messages** | Two identical assistant responses | Frontend adds both HTTP + WS response | Remove HTTP response handling in `service.ts` |
| **No notebook operations** | Status messages but no code execution | Missing `--extensions-in-dev-mode` flag | Add flag and restart JupyterLab |
| **Old code running** | Console shows old logs despite changes | Stale dev_mode bundles | `cd dev_mode && npm run build` |
| **Agent recursion error** | "Recursion limit of 25 reached" | No tool calls for simple messages | Change `execute_tools` to end on any `RespondToUser` |
| **WebSocket connection fails** | No real-time updates | Token/auth issues | Check `ServerConnection.makeSettings()` token handling |
| **XSRF 403 errors** | Tools fail with auth errors | Missing collaboration extension | Ensure `--config=jupyter_server_config.py` |

#### **12. Production Deployment Notes**

For production (non-dev mode):
- Build federated extensions: `cd packages/chat-extension && jlpm build:prod`
- Install as proper extensions: `jupyter labextension install @jupyterlab/chat-extension`
- Use standard flags: `jupyter lab --port=8890 --config=jupyter_server_config.py`
- No need for `--dev-mode` or `--extensions-in-dev-mode`

---

## Philosophy & Design Principles

- **Determinism over cleverness**: One tool per turn keeps routing and execution predictable, eliminates ordering hazards, and avoids OpenAI protocol 400s.
- **Tool-first control**: Treat user-visible output and planning as tools (`RespondToUser`, `CreatePlan`) so the LLM controls UI interactions with the same mechanism as notebook edits.
- **Protocol correctness is non-negotiable**: Never issue another assistant message until all prior `tool_calls` have corresponding `ToolMessage`(s).
- **Tight feedback to the user**: Every tool can carry a `status_message` so the user sees an immediate summary of what’s happening.
- **Minimal state**: Persist only what we truly need (messages, plan when present); rely on Jupyter’s live YDoc for notebook state.
- **Separation of concerns**: Agent picks tools; `jupyter_tools_bridge` performs notebook changes; chat handlers relay UI events; MCP tools fetch external data.

---

## Architecture Overview

- **Frontend**: Chat panel (packages `chat` and `chat-extension`) collects user input, displays messages/statuses/plan cards, and (future) subscribes to live updates via WebSocket.
- **Backend Chat Service**: HTTP endpoints `/api/chat/openai`, `/api/chat/status`, `/api/chat/message` receive agent outputs and persist to notebook metadata via `ConversationManager`.
- **Agent (LangGraph)**: In `packages/jupyter-agent/jupyter_agent_lg/agent.py`: orchestrates `analyze_and_decide` and a unified tool-executor node.
- **Tools**:
  - Jupyter tools (`jupyter_tools.py`): cell CRUD, execute, save, notebook state.
  - MCP tools (`mcp_tools.py`): Snowflake and other external services via MCP.
  - System tools (`system_tools.py`): `RespondToUser`, `CreatePlan`.
- **Jupyter Server Extension**: `jupyter_tools_bridge` (handlers + YDoc), authoritative notebook operations over live shared model.

### Graph (current)
```text
User message
  |
  v
analyze_and_decide (LLM with tools)
  |  \-- if no tool_calls: prepend corrective nudge and self-loop (bounded retries)
  v
tools (execute the single tool_call; send status_message if present)
  |
  v
analyze_and_decide (continue) or END (if RespondToUser with intent="completion")
```

---

## Tool Binding & Schemas

- Bind only real tools: Jupyter, Snowflake MCP, `RespondToUser`, `CreatePlan`.
- Enforce at-most-one call per turn with `tool_choice="any"`, `parallel_tool_calls=False`.
- At runtime, augment each tool schema with optional `status_message: string`:
  - Executor extracts `status_message`, sends it to chat immediately, then removes it from args before invoking the tool.
  - This centralizes status handling and keeps tool implementations simple.

### System Tools
- `RespondToUser(message: str, intent?: "completion"|"clarification"|"status_update")`
  - Sends a user-visible message. If `intent="completion"`, the graph transitions to END.
- `CreatePlan(plan_steps: List[{ title: str, description: str }])`
  - Displays editable plan cards in the UI. The agent may then proceed with execution in subsequent turns.

### Jupyter Tools (examples)
- `insert_and_execute_cell(content: str, cell_type?: "code"|"markdown")`
- `insert_cell(...)`, `execute_cell(...)`, `update_cell(...)`, `delete_cell(...)`, `get_notebook_state(...)`, `save_notebook(...)`

### MCP Tools (examples)
- `snowflake_query(sql: str)`
- `fetch_table_schema(table: str)`, `list_databases()`

---

## Conversation & Protocol

- We use OpenAI’s tool-call protocol strictly:
  - Assistant emits `tool_calls` → we must execute each and produce a `ToolMessage` referencing the original `tool_call_id`.
  - We never call the LLM again or add other assistant/system messages until tool messages are appended.
- The agent enforces **one tool per turn**. If none: prepend a corrective nudge (system message), then retry (bounded).
- Completion is explicit: the model should call `RespondToUser(intent="completion")` when done.

---

## Execution Node

- Extract single tool call and arguments.
- If `status_message` present: send as a status and mirror as a chat bubble for immediate visibility.
- Invoke tool coroutine; capture result; append `ToolMessage` with the exact `tool_call_id`.
- Transition:
  - `RespondToUser(intent="completion")` → END.
  - Otherwise → back to `analyze_and_decide`.

---

## Chat Integration

- Backend endpoints:
  - `POST /api/chat/openai`: starts an agent run (currently non-streaming).
  - `POST /api/chat/status`: receive status events; persist to notebook metadata.
  - `POST /api/chat/message`: receive chat messages/events; persist likewise.
- `ChatHandler` (injectable) posts statuses/messages/plan-cards to these endpoints.
- Frontend renders the final `openai` response immediately; mid-run events require live push (see Real-time).

---

## Real-time Updates (mid-run visibility)

- Problem: Only the final `RespondToUser` appears today because it is returned in the HTTP response after the run completes.
- Options:
  - WebSocket push (recommended):
    - Frontend opens WS `/api/chat/stream?notebook_path|thread_id`.
    - Backend broadcasts events: `{type, notebook_path, tool_call_id?, timestamp, payload}` for `status`, `tool_started`, `tool_finished`, `RespondToUser`, `CreatePlan`.
    - UI appends live; batch-persist to metadata.
  - SSE / streaming HTTP:
    - Make `/api/chat/openai` stream events (SSE or NDJSON chunks). UI renders incrementally.
  - Jupyter events bus:
    - Emit `jupyter-events` over server WS; subscribe in frontend. Requires schema + auth wiring.
- Decision: adopt WebSockets; keep SSE as fallback.

---

## Server Mechanics (YDoc-first)

- Resolve live notebook via `YDocExtension.get_document(path, content_type="notebook", file_format="json", copy=False)`.
- CRUD and execution use `YNotebook` and kernel IOPub channels (`execute_input` authoritative for execution_count).
- Force-save serializes live YDoc to nbformat and persists via `ContentsManager.save()`.

### REST API (tools bridge)
- `POST /api/tools/insert-cell`: `{ path, index|"append", cell_type, source }` → `{ status, cell_id, index }`
- `POST /api/tools/update-cell`: `{ path, cell_id?|index?, source?, metadata? }` → `{ status, index }`
- `POST /api/tools/execute-cell`: `{ path, kernel_id, cell_id?|index?, stream? }` → `{ status, index, execution_count, outputs_count }`
- `POST /api/tools/delete-cell`: `{ path, index|"last" }` or `{ path, cell_id }` → `{ status, deleted_index, cells_remaining }`
- `POST /api/tools/notebook-state`: `{ path }` → full state snapshot
- `GET /api/tools/sessions`: kernel sessions
- `POST /api/tools/save`: persist immediately

---

## Security & Auth

- Use same-origin HTTP calls for intra-server communication.
- Include `Authorization: token=<server_token>`, `Cookie: XSRF-TOKEN=<cookie>`, `X-XSRFToken=<same_cookie_value>`, and a valid `Referer` (e.g., `/lab`).
- On 403 (XSRF), re-discover tokens/cookies and retry once; surface errors to chat if still failing.

---

## Error Handling & Recovery

- Missing tool_call: corrective nudge + bounded self-loop.
- Tool execution errors: log and send concise status; allow LLM to decide recovery next turn.
- Protocol guard: never emit assistant content before ToolMessage(s) for prior calls.
- Recursion guard: cap retries and terminate gracefully with a clear message.

---

## Logging & Observability

- Log selected tool, `tool_call_id`, normalized args (excluding secrets), `status_message`, and results.
- Log corrective nudges, retry counts, and routing decisions (e.g., completion intent).
- Persist chronological event list per run for debugging (tool start/end, statuses, messages).

---

## Configuration

- Model + parameters: model name, temperature, `tool_choice`, `parallel_tool_calls`.
- Retry caps: max self-loop retries for missing tool_call.
- Real-time: WS endpoint toggle, SSE fallback.
- Auth: token/cookie discovery and retry policy.

---

## Testing

- E2E tools (`test_scripts/test_ydoc_tools.py`): insert/update/execute/delete/save, execution_count fidelity, live YDoc sync.
- Agent behavior tests: single-tool-per-turn, status_message propagation, strict ToolMessage protocol, guarded self-loop, completion path.
- Security tests: XSRF-enabled requests to `/api/chat/status` and `/api/chat/message`.
- Load tests: multi-step prompts and chained tool turns (e.g., 10+ steps) within reasonable latency.

---

## Examples

### Multi-plot request (three turns)
1) Turn 1: `insert_and_execute_cell` with code for `x, x**2` (status: “Plotting x vs x^2”).
2) Turn 2: `insert_and_execute_cell` with code for `x, x**3` (status: “Plotting x vs x^3”).
3) Turn 3: `RespondToUser(intent="completion")` with summary of actions.

### Clarification first
- Model calls `RespondToUser(intent="clarification")` asking for dataset path. After user reply, proceeds with Jupyter tools.

### Plan then execute
- Model calls `CreatePlan` with 3–5 steps, then executes steps across subsequent turns.

---

## Open Issues / Items to Solve (Definitive)

### 1) Real-time chat updates (WebSocket implementation)
- Server (backend):
  - Add WS endpoint: `/api/chat/stream` supporting `?notebook_path` (or `thread_id`).
  - Auth: validate same-origin, require valid token; tie WS session to notebook.
  - Broadcasters: in `ChatStatusHandler` and `ChatMessageHandler`, broadcast incoming events to WS subscribers after persisting to metadata.
  - Agent: `ChatHandler` also broadcasts high-signal events (status, tool_started/finished, RespondToUser, CreatePlan) as they happen.
  - Event envelope: `{ type: "status"|"tool_started"|"tool_finished"|"message"|"plan", notebook_path, tool_call_id?, timestamp, payload }`.
- Client (frontend):
  - On NotebookPanel activation, open WS for the active notebook; auto-reconnect.
  - Render events live; de-duplicate via `tool_call_id` + timestamp; group tool_started/finished.
  - Persist is already handled server-side; UI only displays.
- Fallback: keep SSE/NDJSON as a secondary option if WS not available (not prioritized now).

#### WebSocket Implementation Plan (detailed)
- [x] Backend: Add `ChatStreamHandler` (WS) in `packages/chat/jupyterlab_chat/__init__.py`
  - Path: `/api/chat/stream`
  - Query params: `notebook_path` (required), `thread_id` (optional), `token` (optional)
  - Lifecycle: `open()` subscribes, `on_close()` unsubscribes, no `on_message`
  - Security: `check_origin` restricts to same-origin; validate token against `serverapp.token` if present
- [x] Backend: Add `ChatBroadcaster` singleton
  - Map `notebook_path -> Set[WS]`; `subscribe`, `unsubscribe`, `broadcast(event)`
  - Prune dead sockets on send errors; log with minimal PII
- [x] Backend: Wire broadcaster in existing handlers
  - `ChatStatusHandler.post`: after persist, broadcast `{type:"status", notebook_path, timestamp, payload:{status,message}}`
  - `ChatMessageHandler.post`: after persist, broadcast `{type:"message", notebook_path, timestamp, payload:{role,content}}`
  - `ChatOpenAIHandler`: optionally emit `tool_started/tool_finished` via status pathway
- [x] Backend: Register WS route in `_load_jupyter_server_extension`
- [x] Agent: Ensure `ChatHandler.send_status/send_message` include `notebook_path`; add optional `status_type: tool_started|tool_finished`
- [x] Frontend: ChatService websocket client
  - Add `connectStream(notebookPath: string)` and `disconnectStream()` in `packages/chat/src/service.ts`
  - Create WS with `ServerConnection.makeSettings().wsUrl + '/api/chat/stream?notebook_path=...'` (+ `token` when `appendToken`)
  - Handle `onmessage`: route by `event.type`
    - `message`: push as assistant/user message via existing `_messageAdded`
    - `status`: push lightweight assistant/system bubble (e.g., prefix icons) or expose a `statusReceived` signal
    - `plan`: expose `planReceived` signal with steps
  - Implement auto-reconnect with capped backoff; rebind on `notebookPath` change
- [x] Frontend: Hook to active notebook
  - In `packages/chat-extension/src/index.ts`, on activation and `notebookTracker.currentChanged`, call `chatService.connectStream(activePath)`
  - Disconnect on deactivate/`dispose()`
- [x] Frontend: UI rendering for plan/status
  - `packages/chat/src/widget.tsx`: subscribe to `planReceived` to render plan cards; consider minimal status line items
- [ ] Testing
  - Manual: Start Lab, open chat, confirm live status/messages during long tool execution
  - Automated: add lightweight integration test harness to open WS and post to `/api/chat/status`

#### Event Envelope (canonical)
```json
{
  "type": "status|tool_started|tool_finished|message|plan",
  "notebook_path": "<string>",
  "thread_id": "<string|null>",
  "tool_call_id": "<string|null>",
  "timestamp": "<ISO8601>",
  "payload": {}
}
```
- `status.payload = { "status": "working|info|error", "message": "..." }`
- `message.payload = { "role": "assistant|user|system", "content": "..." }`
- `plan.payload = { "steps": [{ "title": "...", "description": "..." }] }`

#### Acceptance Criteria
- [ ] Opening chat with an active notebook establishes WS and shows mid-run status/messages/plan
- [ ] Switching notebooks resubscribes and routes events correctly by `notebook_path`
- [ ] Invalid token on WS is rejected; HTTP endpoints continue to persist
- [ ] No crashes or memory leaks on frequent connects/disconnects

### 2) XSRF token fixes
- Standardize outbound requests from `ChatHandler` to include:
  - `Authorization: token=<server_token>`
  - `Cookie: XSRF-TOKEN=<cookie>`
  - `X-XSRFToken: <same_cookie_value>`
  - `Referer: /lab`
- Ensure same-origin URLs.
- On 403, re-discover tokens/cookies and retry once; log and send a concise status to chat on failure.
- Add tests exercising `/api/chat/status` and `/api/chat/message` with XSRF enabled.

### 3) Thread management (per-notebook threads + restore on load)
- Backend:
  - Re-enable reading conversation threads from notebook metadata (previously disabled during nbformat issues; sanitization is now in place).
  - Add endpoint to list threads for a `notebook_path` (e.g., `GET /api/chat/threads?notebook_path=...`).
  - `ConversationManager`: load the last active thread for a notebook; provide create/switch APIs.
- Frontend:
  - On notebook open/activate, fetch and render previous threads; allow switching and pinning.
  - Ensure chat panel selects the last active thread by default.

### 4) Tool coverage & integration testing
- CreatePlan: validate schema, UI rendering of plan cards, and subsequent execution turns.
- Snowflake MCP: run MCP service, validate `snowflake_query` and schema discovery flows; handle credentials via env vars/secure storage.
- End-to-end: verify statuses/messages appear live (WS), notebook changes reflect in UI, and completion intent routes to END correctly.

---

## Runbook: Install & Start

### Python deps (from repo root)
```bash
python -m pip install -U pip setuptools wheel
pip install editables
pip install -e ./jupyter_tools_bridge
pip install -e ./packages/jupyter-agent
pip install -e ./packages/chat
```

### Start JupyterLab (dev) with logs
```bash
# optional: rotate any existing log
mv jlab.log jlab.$(date +%Y%m%d-%H%M%S).log 2>/dev/null || true

# start lab
nohup jupyter lab \
  --dev-mode \
  --extensions-in-dev-mode \
  --ServerApp.log_level=DEBUG \
  --port=8890 \
  --config=jupyter_server_config.py \
  > jlab.log 2>&1 &
```

### Stop (if needed)
```bash
pkill -f "jupyter-lab" || true
```

---

## Future Work (Focused)
- Implement WS-based real-time streaming end-to-end (backend + frontend) per the envelope above.
- Harden XSRF handling on internal calls and add tests.
- Re-enable per-notebook thread loading from metadata and UI thread management.
- Complete coverage tests for `CreatePlan` and Snowflake MCP flows to ensure chat ↔ tools ↔ agent integration is flawless.

## CreatePlan Tool - Complete Workflow & Requirements

### **🎯 Overview**
The CreatePlan tool enables interactive, multi-step analysis planning where users can review, edit, and approve plans before execution. This creates a collaborative workflow between the LLM agent and user for complex tasks.

### **🔧 When to Use CreatePlan**

#### **ALWAYS Use CreatePlan When:**
1. **Multi-step requests** requiring 3+ distinct operations
2. **Complex analysis** involving multiple data sources, transformations, or visualizations
3. **Ambiguous requests** where user input would improve the approach
4. **High-stakes operations** where user review prevents costly mistakes
5. **Exploratory analysis** where the path isn't immediately clear

#### **Examples Requiring CreatePlan:**
```
User: "Analyze the sales data and create a comprehensive report"
→ CreatePlan: [Data loading, EDA, trend analysis, visualization, summary]

User: "Build a machine learning model to predict customer churn"
→ CreatePlan: [Data prep, feature engineering, model selection, training, evaluation]

User: "Compare Q1 vs Q2 performance across all regions"
→ CreatePlan: [Data extraction, regional grouping, metric calculation, comparison charts]
```

#### **DON'T Use CreatePlan For:**
- **Single-step tasks**: "Plot x vs y" → Direct execution
- **Simple queries**: "Show first 5 rows" → Direct execution
- **Clarification requests**: Use RespondToUser instead

### **🏗️ Plan Card Architecture**

#### **Plan Card Format in Conversation**
When CreatePlan is called, plan steps are stored in conversation history as:
```
[CARD:title|description]
[CARD:title|description]
[CARD:title|description]
```

#### **Plan Card Lifecycle**
1. **Agent Creates Plan**: `CreatePlan(plan_steps=[...])` → Cards displayed in UI
2. **Plan Stored**: Assistant message with `[CARD:...]` format added to conversation
3. **User Reviews**: User can edit card titles/descriptions directly in UI
4. **Plan Updated**: Edited cards update the assistant message in conversation history
5. **User Proceeds**: User sends message like "proceed", "go ahead", "implement this"
6. **Agent Executes**: Agent sees updated cards in conversation and implements them

#### **Critical Understanding: Plan Precedence Rules**

**Rule 1: Latest Plan Supersedes Earlier Requests**
```
Conversation Flow:
1. User: "Create a sales dashboard"
2. Assistant: [CARD:Load data|...] [CARD:Create charts|...] [CARD:Build dashboard|...]
3. User edits cards to: [CARD:Load Q4 data only|...] [CARD:Focus on regional breakdown|...]
4. User: "proceed"
5. Agent: Must implement EDITED cards, not original "sales dashboard" request
```

**Rule 2: New Requests Can Invalidate Plans**
```
Conversation Flow:
1. User: "Analyze customer data"
2. Assistant: [CARD:Load customers|...] [CARD:Segment analysis|...]
3. User: "Actually, forget that. I want to analyze product sales instead"
4. Agent: Should create NEW plan for product sales, ignoring customer plan
```

**Rule 3: Plan Context Boundaries**
- **Plans override**: All user messages BEFORE the plan in conversation
- **Plans don't override**: User messages AFTER the plan
- **Multiple plans**: Each plan creates a new context boundary

### **🧠 Agent Decision Logic for Plans**

#### **Plan Detection Algorithm**
```python
def analyze_conversation_for_plans(conversation_history):
    """
    Agent should mentally process conversation to understand plan context
    """
    plans = []
    current_context = []

    for message in conversation_history:
        if message.role == "assistant" and "[CARD:" in message.content:
            # Found a plan - this creates a context boundary
            plan = extract_cards_from_message(message.content)
            plans.append({
                "plan": plan,
                "supersedes": current_context,  # This plan overrides these messages
                "position": len(conversation_history)
            })
            current_context = []  # Reset context after plan
        elif message.role == "user":
            current_context.append(message)

    return plans, current_context  # Latest plan + messages after last plan
```

#### **Decision Matrix for Agent**

| Conversation State | Agent Action | Reasoning |
|-------------------|--------------|-----------|
| No plans exist | Evaluate if task needs CreatePlan | Simple → Execute, Complex → CreatePlan |
| Plan exists, user says "proceed" | Execute latest plan cards | Plan cards are the authoritative instruction |
| Plan exists, user gives new instruction | Determine if new instruction invalidates plan | If related → modify plan, If unrelated → new plan |
| Multiple plans exist | Use latest plan + messages after it | Each plan creates context boundary |
| Plan exists, user edits cards | Execute edited cards when user proceeds | Edited cards supersede original request |

#### **Example Decision Scenarios**

**Scenario 1: Plan Modification**
```
1. User: "Analyze sales data"
2. Assistant: [CARD:Load data|...] [CARD:Create charts|...]
3. User: "Also include customer segmentation in the analysis"
4. Agent Decision: Modify existing plan to include segmentation
   → CreatePlan with updated steps including segmentation
```

**Scenario 2: Plan Invalidation**
```
1. User: "Analyze sales data"
2. Assistant: [CARD:Load sales|...] [CARD:Sales charts|...]
3. User: "Never mind, I want to work on inventory analysis instead"
4. Agent Decision: Completely new request, ignore sales plan
   → CreatePlan for inventory analysis OR direct execution if simple
```

**Scenario 3: Plan Execution**
```
1. User: "Create ML model for predictions"
2. Assistant: [CARD:Data prep|...] [CARD:Feature engineering|...] [CARD:Model training|...]
3. User edits cards: [CARD:Data prep with outlier removal|...] [CARD:Advanced feature engineering|...]
4. User: "looks good, proceed"
5. Agent Decision: Execute the EDITED cards, not original request
   → Start with "Data prep with outlier removal" step
```

### **💬 Conversation History & Context Integration**

#### **How Plans Are Stored**
Plans are stored as assistant messages in conversation metadata:
```json
{
  "role": "assistant",
  "content": "Here's my plan:\n\n[CARD:Load data|Import and validate the dataset]\n[CARD:Explore data|Perform EDA and identify patterns]\n[CARD:Create visualizations|Generate charts and graphs]",
  "metadata": {"messageType": "plan"},
  "timestamp": "2025-01-02T10:30:00Z"
}
```

#### **Plan Updates in Conversation**
When user edits cards:
1. **Frontend**: User edits cards in UI
2. **Backend**: `_handle_plan_update_sync()` updates the assistant message content
3. **Conversation**: The same assistant message gets updated with new card content
4. **Agent Context**: Agent sees updated cards in conversation history

**Important**: There's only ONE plan message per plan - it gets updated in place, not duplicated.

#### **Context Building for Agent**
```python
def build_agent_context(conversation_history):
    """
    Agent receives full conversation history including:
    - Original user requests
    - Plan cards (potentially edited)
    - User feedback on plans
    - Subsequent user messages
    """
    context_messages = []

    for message in conversation_history:
        if message.metadata.get("messageType") == "plan":
            # This is a plan message - contains current card state
            context_messages.append({
                "role": "assistant",
                "content": message.content  # Contains [CARD:...] format
            })
        else:
            # Regular user/assistant message
            context_messages.append(message)

    return context_messages
```

### **🎨 User Experience Flow**

#### **Complete Plan Workflow**
```
1. User Request: "Build a comprehensive sales analysis"

2. Agent Analysis:
   - Complex multi-step task → Use CreatePlan
   - CreatePlan(plan_steps=[
       {"title": "Data Loading", "description": "Import sales data from database"},
       {"title": "Data Cleaning", "description": "Handle missing values and outliers"},
       {"title": "Trend Analysis", "description": "Analyze sales trends over time"},
       {"title": "Regional Breakdown", "description": "Compare performance by region"},
       {"title": "Visualization", "description": "Create charts and dashboard"}
     ])

3. UI Display: Cards appear as editable elements in chat

4. User Review: User edits cards:
   - Changes "Data Loading" → "Load Q4 2024 sales data only"
   - Changes "Regional Breakdown" → "Focus on top 5 regions by revenue"

5. Plan Update: Backend updates conversation history with edited cards

6. User Approval: "This looks perfect, please proceed"

7. Agent Execution:
   - Sees edited cards in conversation
   - Executes: "Load Q4 2024 sales data only" (not generic data loading)
   - Continues with other edited steps
```

#### **Plan Abandonment Flow**
```
1. User: "Analyze customer behavior"
2. Agent: CreatePlan([customer data loading, behavior analysis, segmentation])
3. User: "Actually, I changed my mind. Can you help me with inventory management instead?"
4. Agent Analysis:
   - New request is unrelated to customer behavior
   - Previous plan should be ignored
   - New request is complex → CreatePlan for inventory
5. Agent: CreatePlan([inventory data loading, stock analysis, reorder recommendations])
```

### **🔧 Implementation Requirements**

#### **System Prompt Enhancements**
The agent needs enhanced instructions about plan handling:

```
PLAN CARD WORKFLOW (CRITICAL):

1. WHEN TO CREATE PLANS:
   - Multi-step tasks (3+ operations)
   - Complex analysis requiring user input
   - Ambiguous requests needing clarification
   - High-stakes operations requiring approval

2. PLAN PRECEDENCE RULES:
   - Latest plan cards supersede ALL earlier user requests before the plan
   - User messages AFTER a plan can modify or invalidate it
   - If user edits cards, implement EDITED version, not original request
   - Multiple plans: each creates a new context boundary

3. PLAN EXECUTION TRIGGERS:
   - User says: "proceed", "go ahead", "implement this", "looks good"
   - User provides implementation feedback: "start with step 1"
   - User asks execution questions: "how will you do step 2?"

4. PLAN INVALIDATION SIGNALS:
   - User requests completely different task: "forget that, do X instead"
   - User says: "never mind", "cancel that", "ignore the plan"
   - User provides contradictory requirements

5. CONVERSATION ANALYSIS:
   - Read conversation chronologically
   - Identify plan boundaries (assistant messages with [CARD:title|description])
   - Determine what the user CURRENTLY wants (latest plan + subsequent messages)
   - Ignore superseded requests (messages before latest active plan)
```

#### **Tool Schema Improvements**
Enhanced tool descriptions with specific use cases and expected outputs:

```python
# In system_tools.py
CreatePlan.description = """
Create interactive plan cards for multi-step tasks. Use when:
- Task requires 3+ distinct operations
- User input would improve the approach
- Complex analysis needs user review
- Ambiguous requests need clarification

Each plan step should be:
- Specific and actionable
- 1-2 sentences maximum
- Clear about expected outcome
- Ordered logically

The user can edit these cards before you proceed.
"""

RespondToUser.description = """
Send a message to the user. Use for:
- Asking clarifying questions
- Providing status updates
- Completing tasks (intent="completion")
- Explaining results or next steps

Always include a descriptive thread_title summarizing the conversation topic.
"""
```

### **🧪 Testing Scenarios**

#### **Test Case 1: Plan Creation & Execution**
```
Input: "Create a machine learning model to predict house prices"
Expected: CreatePlan with steps for data prep, feature engineering, model training, evaluation
User edits: Changes "basic features" to "advanced feature engineering with polynomial terms"
User: "proceed"
Expected: Agent implements advanced feature engineering, not basic
```

#### **Test Case 2: Plan Invalidation**
```
Input: "Analyze customer churn data"
Agent: CreatePlan for churn analysis
User: "Actually, I want to analyze product sales instead"
Expected: Agent ignores churn plan, creates new plan for sales analysis
```

#### **Test Case 3: Plan Modification**
```
Input: "Create quarterly report"
Agent: CreatePlan for Q4 report
User: "Make it for Q1-Q3 instead, and add competitor analysis"
Expected: Agent modifies plan to cover Q1-Q3 and include competitor analysis
```

### **🚨 Critical Implementation Notes**

1. **Conversation Storage**: Plans are stored as assistant messages with `[CARD:title|description]` format
2. **Plan Updates**: When user edits cards, the same assistant message is updated in place
3. **Context Boundaries**: Each plan creates a boundary - messages before it are superseded
4. **Agent Memory**: Agent must analyze full conversation to understand current context
5. **UI Integration**: Cards are editable in frontend, changes sync to backend conversation storage

This architecture ensures that the agent can handle complex, iterative planning workflows while maintaining clear context boundaries and user control over the execution plan.

## System Instructions - Enhanced Tool Guidance

### **🎯 Core Tool-Calling Principles**

The agent must understand each tool's purpose, expected inputs, outputs, and when to use them. Here's the comprehensive guidance:

#### **Tool Selection Decision Tree**
```
User Request Analysis:
├── Single operation (plot, query, simple task)
│   └── Use appropriate direct tool (insert_and_execute_cell, query_snowflake)
├── Multi-step task (3+ operations)
│   └── Use CreatePlan first, then execute steps
├── Need user clarification
│   └── Use RespondToUser with intent="clarification"
└── Task complete
    └── Use RespondToUser with intent="completion"
```

### **📋 Detailed Tool Instructions**

#### **1. insert_and_execute_cell**
**Purpose**: Execute Python code in Jupyter notebook
**When to use**:
- Data analysis, visualization, computation
- Installing packages, importing libraries
- Any Python operation that produces output
- Building on previous notebook work

**Expected outputs**:
- `execution_count`: Shows cell execution order
- `outputs`: Can include text, DataFrames, plots, errors
- Real-time cell appears in notebook UI

**Usage patterns**:
```python
# Data loading and exploration
insert_and_execute_cell(
    code="import pandas as pd\ndf = pd.read_csv('data.csv')\ndf.head()",
    status_message="Loading and previewing dataset"
)

# Visualization
insert_and_execute_cell(
    code="plt.figure(figsize=(10,6))\nplt.plot(df['x'], df['y'])\nplt.title('X vs Y Analysis')",
    status_message="Creating visualization"
)

# Complex analysis
insert_and_execute_cell(
    code="from sklearn.model_selection import train_test_split\nX_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)",
    status_message="Preparing data for machine learning"
)
```

**Key considerations**:
- Check notebook state first - don't repeat existing work
- Build incrementally on previous cells
- Use meaningful variable names that persist across cells
- Include error handling for data operations

#### **2. delete_cell**
**Purpose**: Remove cells from notebook
**When to use**:
- Cleaning up failed experiments
- Removing duplicate or obsolete code
- Correcting mistakes in cell sequence

**Usage patterns**:
```python
# Remove last cell if it had errors
delete_cell(cell_index=-1, status_message="Removing failed cell")

# Clean up specific problematic cell
delete_cell(cell_index=3, status_message="Removing outdated analysis")
```

**Key considerations**:
- Use sparingly - prefer creating new cells over deleting
- Check cell index carefully to avoid deleting wrong content
- Consider if cell deletion affects variable dependencies

#### **3. RespondToUser**
**Purpose**: Communicate with user
**When to use**:
- Task completion announcements
- Asking clarifying questions
- Providing explanations or status updates
- Error reporting and next steps

**Intent types**:
- `"completion"`: Task is finished, ends conversation turn
- `"clarification"`: Need user input to proceed
- `"status_update"`: Progress report, conversation continues

**Usage patterns**:
```python
# Task completion
RespondToUser(
    message="I've completed the sales analysis. The notebook now contains data loading, trend analysis, and visualizations showing Q4 performance increased 15% over Q3.",
    intent="completion",
    thread_title="Sales Analysis Report",
    status_message="Finalizing analysis summary"
)

# Clarification request
RespondToUser(
    message="I need to clarify the date range for your analysis. Should I focus on the last 12 months, or do you have a specific period in mind?",
    intent="clarification",
    thread_title="Data Analysis Planning",
    status_message="Requesting analysis parameters"
)

# Status update
RespondToUser(
    message="I've loaded the dataset (1.2M rows) and completed initial cleaning. Next, I'll perform the trend analysis you requested.",
    intent="status_update",
    thread_title="Large Dataset Analysis",
    status_message="Providing progress update"
)
```

**Thread title guidelines**:
- 3-8 words describing conversation topic
- Examples: "Sales Data Analysis", "ML Model Training", "Database Query Help"
- Be specific but concise

#### **4. CreatePlan**
**Purpose**: Create interactive, editable analysis plans
**When to use**:
- Multi-step tasks requiring 3+ operations
- Complex analysis where user input improves approach
- Ambiguous requests needing structure
- High-stakes operations requiring approval

**Plan step guidelines**:
- Each step should be specific and actionable
- 1-2 sentences maximum per description
- Clear about expected outcome
- Logically ordered sequence
- 3-7 steps optimal (not too granular, not too broad)

**Usage patterns**:
```python
# Comprehensive analysis plan
CreatePlan(
    plan_steps=[
        PlanStepOutput(
            title="Data Loading & Validation",
            description="Import dataset, check for missing values, validate data types and ranges"
        ),
        PlanStepOutput(
            title="Exploratory Data Analysis",
            description="Generate summary statistics, identify patterns, detect outliers"
        ),
        PlanStepOutput(
            title="Feature Engineering",
            description="Create derived features, handle categorical variables, scale numerical data"
        ),
        PlanStepOutput(
            title="Model Development",
            description="Train multiple algorithms, perform cross-validation, select best model"
        ),
        PlanStepOutput(
            title="Results & Visualization",
            description="Evaluate model performance, create prediction visualizations, summarize findings"
        )
    ],
    status_message="Creating machine learning analysis plan"
)

# Simpler analysis plan
CreatePlan(
    plan_steps=[
        PlanStepOutput(
            title="Load Q4 Sales Data",
            description="Import sales data for October-December 2024"
        ),
        PlanStepOutput(
            title="Regional Performance Analysis",
            description="Compare sales performance across different regions"
        ),
        PlanStepOutput(
            title="Trend Visualization",
            description="Create charts showing monthly trends and growth patterns"
        )
    ],
    status_message="Planning quarterly sales analysis"
)
```

**Plan execution workflow**:
1. Agent creates plan → Cards displayed to user
2. User can edit card titles/descriptions
3. User says "proceed" or similar → Agent executes edited cards
4. Agent implements steps based on CURRENT card content, not original request

#### **5. Snowflake Tools (MCP)**
**Purpose**: Query external databases via Model Context Protocol
**When to use**: Only when user explicitly mentions databases, SQL, or data warehouses

**Available tools**:
- `query_snowflake`: Execute SQL queries
- `list_snowflake_tables`: Discover available tables
- `get_table_schema`: Understand table structure
- `get_database_info`: Explore database metadata

**Usage patterns**:
```python
# Discover available data
list_snowflake_tables(
    database="SALES_DB",
    schema_name="PUBLIC",
    status_message="Exploring available sales tables"
)

# Understand table structure
get_table_schema(
    table_name="CUSTOMER_ORDERS",
    database="SALES_DB",
    status_message="Analyzing customer orders table schema"
)

# Execute analysis query
query_snowflake(
    query="SELECT region, SUM(revenue) as total_revenue FROM sales_data WHERE date >= '2024-01-01' GROUP BY region ORDER BY total_revenue DESC",
    database="SALES_DB",
    status_message="Calculating regional revenue totals"
)
```

**Integration with Jupyter**:
- Query Snowflake to get data
- Use insert_and_execute_cell to analyze results in Python
- Combine database insights with notebook visualizations

### **🧠 Enhanced System Prompt**

```python
def _create_system_instructions(self) -> str:
    return """You are a data analysis agent working in JupyterLab. Decide what to do next and EXPRESS your decision via TOOL CALLS ONLY.

TOOL-CALLING CONTRACT (STRICT):
- Produce exactly ONE tool call per turn
- Include a short status_message in tool args, summarizing the step you are about to perform
- Never emit plain-text answers unless using RespondToUser
- If task is complete, call RespondToUser(intent="completion")

AVAILABLE TOOLS & USAGE:

🔧 JUPYTER TOOLS:
- insert_and_execute_cell(code, cell_type="code", position="end")
  USE FOR: Python code execution, data analysis, visualization, computation
  OUTPUTS: execution_count, text/DataFrame/plot outputs, real-time cell in UI
  CONTEXT: Check notebook state first, build on existing work, use meaningful variables

- delete_cell(cell_index)
  USE FOR: Removing failed/duplicate/obsolete cells (use sparingly)
  CONTEXT: Verify index, consider variable dependencies

💬 COMMUNICATION TOOLS:
- RespondToUser(message, intent, thread_title)
  USE FOR: User communication, task completion, clarification requests
  INTENTS: "completion" (ends turn), "clarification" (needs input), "status_update" (continues)
  THREAD_TITLE: 3-8 words describing conversation topic

📋 PLANNING TOOLS:
- CreatePlan(plan_steps)
  USE FOR: Multi-step tasks (3+ operations), complex analysis, ambiguous requests
  STEPS: Specific, actionable, 1-2 sentences, logically ordered, 3-7 steps optimal
  WORKFLOW: Create plan → User edits cards → User says "proceed" → Execute edited cards

🗄️ DATABASE TOOLS (only when user mentions databases/SQL):
- query_snowflake(query, database, schema_name)
- list_snowflake_tables(database, schema_name)
- get_table_schema(table_name, database)
- get_database_info()

PLAN CARD WORKFLOW (CRITICAL):

WHEN TO CREATE PLANS:
- Multi-step tasks requiring 3+ distinct operations
- Complex analysis where user input would improve approach
- Ambiguous requests needing clarification structure
- High-stakes operations requiring user approval

PLAN PRECEDENCE RULES:
- Latest plan cards supersede ALL user requests before the plan
- User messages AFTER a plan can modify or invalidate it
- If user edits cards, implement EDITED version, not original request
- Each plan creates a context boundary in conversation

PLAN EXECUTION TRIGGERS:
- User says: "proceed", "go ahead", "implement this", "looks good", "start"
- User provides implementation feedback: "begin with step 1"
- User asks execution questions: "how will you do step 2?"

PLAN INVALIDATION SIGNALS:
- User requests completely different task: "forget that, do X instead"
- User says: "never mind", "cancel that", "ignore the plan"
- User provides contradictory requirements

CONVERSATION ANALYSIS:
- Read conversation chronologically to understand context
- Identify plan boundaries (assistant messages with [CARD:title|description])
- Determine current user intent (latest plan + subsequent messages)
- Ignore superseded requests (messages before latest active plan)
- If plan cards were edited, implement EDITED content, not original request

DECISION EXAMPLES:

Simple Request: "Plot sales over time"
→ insert_and_execute_cell(code="plt.plot(df['date'], df['sales'])", status_message="Creating sales timeline plot")

Complex Request: "Build comprehensive sales analysis with predictions"
→ CreatePlan([Data loading, EDA, trend analysis, forecasting model, visualization])

Clarification Needed: "Analyze the data" (no specifics)
→ RespondToUser(message="I'd be happy to analyze your data. Could you specify what type of analysis you're looking for?", intent="clarification")

Plan Execution: User edited cards and said "proceed"
→ Execute first edited card step with insert_and_execute_cell

Task Complete: Analysis finished with results
→ RespondToUser(message="Analysis complete. Results show...", intent="completion")

The conversation history shows you everything - read it naturally and respond appropriately to the user's current intent."""
```

This enhanced system provides the agent with comprehensive understanding of:
1. **When to use each tool** based on task complexity and user intent
2. **Expected outputs** from each tool to set proper expectations
3. **Plan workflow mechanics** including precedence rules and execution triggers
4. **Context analysis** to understand conversation boundaries and current user intent
5. **Practical examples** showing decision-making patterns

The agent can now make informed decisions about tool selection and understand the complete lifecycle of plan-based workflows.
