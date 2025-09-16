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
