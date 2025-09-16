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
