# Backend YDoc Agent for Real-Time Notebook Control (JupyterLab 4+)

**Goal:** Implement a backend-only agent (Python) that can **insert/update/delete cells**, **execute code**, and **attach outputs** in a live JupyterLab notebook with **real-time** UI sync. No front-end scripting is required; changes appear instantly in the open notebook via JupyterLab’s **Real-Time Collaboration (RTC)**.

---

## 1) Scope & Assumptions

- Target: **Latest JupyterLab 4.x** with RTC enabled (local use first; keep code portable).
- Agent runs **server-side** (as a Jupyter Server extension or a co-located backend service within the same process), not in the browser.
- The agent edits the live **YDoc shared model** for the notebook and uses **Jupyter kernel** APIs to execute code and consume IOPub outputs.

---

## 2) Install & Enable Real-Time Collaboration

```bash
# Recommended packages
pip install jupyter-collaboration jupyter-server-ydoc jupyter_ydoc jupyter-client nbformat
# or conda-forge channels where applicable
```

- **Enable RTC**: JupyterLab 4 supports RTC by installing/activating **`jupyter-collaboration`** (server + lab extension providing Y documents and collaboration UI).
- **What it provides**: A server extension (**`jupyter_server_ydoc`**) that **manages YDocuments tied to files** and **exposes WebSocket endpoints for real-time updates** (the browser is a Yjs client).
- **Design intent**: These **collaborative shared models** are used for **real-time collaboration _and server-side execution of notebooks_**—this is the official path you’ll build on.

**References**
- JupyterLab RTC user docs: https://jupyterlab.readthedocs.io/en/latest/user/rtc.html
- Jupyter Real-Time Collaboration repo: https://github.com/jupyterlab/jupyter-collaboration
- `jupyter-server-ydoc` (PyPI): https://pypi.org/project/jupyter-server-ydoc/
- Jupyter YDoc docs (Python/JS APIs): https://jupyter-ydoc.readthedocs.io/

---

## 3) Architecture (high level)

```
[Your Agent (server-side)]
    ├─ Uses jupyter_server_ydoc to access the live YNotebook (shared model)
    ├─ Mutates cells/outputs on YNotebook
    └─ Uses jupyter_client to execute code in the notebook's kernel

[Jupyter Server + jupyter_server_ydoc]
    ├─ Hosts YDocuments (YNotebook) for notebooks
    └─ Relays Yjs updates to clients (WebSocket) and persists to disk

[JupyterLab Frontend (browser)]
    └─ Yjs client for the notebook; reflects edits/outputs in real time
```

- Server-side **YNotebook** schema (simplified): each cell has `id`, `cell_type`, `source`, `metadata`, `execution_state`, `execution_count`, `outputs`, `attachments`.
- UI live-updates because the browser is a Yjs peer connected to the same shared model.

**References**
- Jupyter YDoc docs (YNotebook schema/API): https://jupyter-ydoc.readthedocs.io/

---

## 4) Agent Tool API (to expose to your planner/agent)

| Tool | Signature | Behavior |
|---|---|---|
| `insert_cell` | `(index: int \| 'append', type: Literal['code','markdown'], source: str, id?: str)` | Create a valid nbformat cell and insert into **YNotebook**. |
| `update_cell_source` | `(id_or_index, source: str)` | Update `source` field of a cell in YNotebook. |
| `delete_cell` | `(id_or_index)` | Remove a cell from YNotebook. |
| `execute_cell` | `(id_or_index, stream: bool = True)` | Resolve code, send `execute_request` via **jupyter_client**, map IOPub stream/result/display/error messages to **nbformat outputs**, update the same cell’s `outputs` + `execution_count` in YNotebook (incrementally if `stream=True`). |
| `get_snapshot` | `()` | Return structured notebook state (cells: id/type/source_len/execution_count/outputs summary) for planning/logging. |

Useful references:
- Jupyter Client API overview (kernel channels): https://jupyter-client.readthedocs.io/en/latest/api/jupyter_client.html
- nbformat spec (output types and fields): https://nbformat.readthedocs.io/en/latest/format_description.html

---

## 5) Implementation Steps (server-side)

### 5.1 Bind to the **live** YNotebook
Implement this as a **Jupyter Server extension** (recommended) so you can access the server’s collaboration manager and bind to the live shared model for a given notebook path/session.

- Author a basic server extension and get access to the `ServerApp` instance.
- From the extension, **retrieve the YDocument/YNotebook corresponding to a notebook path**. The collaboration layer maintains YDocuments for open files and exposes real-time endpoints; your code should **operate on the live model**, not a detached copy.

> Notes for implementers
> • The **Python shared model class** you will manipulate is `jupyter_ydoc.ynotebook.YNotebook` (append/get/set cells, observe, etc.).
> • The `jupyter_ydoc` package registers available doc types (including `"notebook"`) via entry points—useful if you construct docs programmatically.

Docs:
- Jupyter YDoc Python API: https://jupyter-ydoc.readthedocs.io/en/latest/python_api.html

### 5.2 Insert & Update Cells (YNotebook API)

- **Required fields** when creating a code cell (nbformat 4.5+): `id` (string, unique), `cell_type: "code"`, `source: str`, plus optional `metadata`, and initial `execution_state`, `execution_count`, `outputs`.

**Skeleton (conceptual):**
```python
from jupyter_ydoc import YNotebook

def insert_cell(ynb: YNotebook, index: int | str, cell_type: str, source: str, cell_id: str | None = None):
    cell = {
        "id": cell_id or gen_uuid(),         # ensure uniqueness
        "cell_type": cell_type,              # "code" or "markdown"
        "source": source,
        "metadata": {},
        "execution_state": "idle",
        "execution_count": None,
        "outputs": [] if cell_type == "code" else None,
        "attachments": None
    }
    if index == 'append':
        ynb.append_cell(cell)                # ← shared model edit (real-time)
    else:
        ycell = ynb.create_ycell(cell)
        ynb.set_ycell(index, ycell)          # insert/replace at index
```

Also useful: `get_cell(index)`, `set_cell(index, cell_dict)` for updating in place.

### 5.3 Execute Code via **jupyter_client**

- Locate the notebook’s **kernel** (via Jupyter Server’s session/kernel managers) and create a `KernelClient`. Send `execute_request(code)` on the **shell** channel and read results from **IOPub**.

**Skeleton (conceptual):**
```python
from jupyter_client import BlockingKernelClient

def execute_and_stream(kclient: BlockingKernelClient, code: str):
    # Send execute request
    msg_id = kclient.execute(code, store_history=True, allow_stdin=False, stop_on_error=False)

    outputs = []
    while True:
        msg = kclient.get_iopub_msg()  # loop until status: 'idle'
        mtype = msg['header']['msg_type']
        content = msg['content']

        if mtype in ('stream', 'display_data', 'execute_result', 'error'):
            outputs.append(map_to_nbformat_output(mtype, content))
            yield ('output', outputs[-1])  # streaming hook
        elif mtype == 'status' and content.get('execution_state') == 'idle':
            break
```

### 5.4 Map Kernel Messages → **nbformat** Outputs

- **execute_result** (has `execution_count`), **display_data**, **stream**, **error** → nbformat-compatible dicts.

**Example mappers (conceptual):**
```python
def map_to_nbformat_output(mtype, content):
    if mtype == 'stream':
        return {"output_type": "stream", "name": content["name"], "text": content["text"]}
    if mtype == 'display_data':
        return {"output_type": "display_data", "data": content["data"], "metadata": content.get("metadata", {})}
    if mtype == 'execute_result':
        return {"output_type": "execute_result", "execution_count": content["execution_count"],
                "data": content["data"], "metadata": content.get("metadata", {})}
    if mtype == 'error':
        return {"output_type": "error", "ename": content["ename"], "evalue": content["evalue"], "traceback": content["traceback"]}
    raise ValueError(f"Unsupported msg_type: {mtype}")
```

References:
- Jupyter Client API: https://jupyter-client.readthedocs.io/en/latest/api/jupyter_client.html
- nbformat outputs spec: https://nbformat.readthedocs.io/en/latest/format_description.html

### 5.5 Attach Outputs Back to **the Same Cell** (Real-Time)

- After each message (or at the end), **write updated outputs** (and final `execution_count`) into that cell in the **YNotebook**. The browser will reflect the change **immediately**.

**Skeleton (conceptual):**
```python
def update_cell_outputs(ynb: YNotebook, index: int, outputs: list, exec_count: int | None):
    cell = ynb.get_cell(index)
    cell["outputs"] = outputs
    cell["execution_count"] = exec_count
    ynb.set_cell(index, cell)  # ← shared model edit (real-time push)
```

### 5.6 Persistence & Autosave

- The collab stack integrates the YDoc with Jupyter’s file system; updates from your agent will be **saved automatically** by the server’s save loop.

---

## 6) Real-Time Behavior & UX

- With **RTC enabled**, **any** edit to the shared model (cell structure, `source`, **`outputs`**) propagates to the browser instantly via WebSockets; users watch the agent’s actions unfold live (like another collaborator).
- Works for **single-user** too—the browser is simply a Yjs peer.

---

## 7) Versioning & Compatibility

- Keep `jupyter-collaboration`, `jupyter-server-ydoc`, and `jupyter_ydoc` versions compatible with your JupyterLab 4.x. These are actively maintained.
- The **`jupyter-server-ydoc`** project description explicitly lists **“server-side execution of notebooks”** as a supported use case—validating this backend-agent pattern.

References:
- https://github.com/jupyterlab/jupyter-collaboration
- https://pypi.org/project/jupyter-server-ydoc/

---

## 8) Testing Strategy

1. **Unit**: function-level tests for mapping IOPub → nbformat outputs; ID generation; YNotebook cell mutations (use a synthetic YNotebook where possible).
2. **Integration**: spin up JupyterLab with **RTC enabled**, open a test notebook in the browser, run the agent’s `insert_cell` → `execute_cell` flow; verify live updates.
3. **Resilience**: kernel restarts/interrupts; malformed code; large outputs; streaming backpressure. (Check `status: idle`/`busy` and `execute_reply` handling.)

---

## 9) Security & Permissions

- The agent runs with the **same privileges** as the Jupyter Server; secure access exactly as you secure Jupyter (tokens, auth, local-only).
- If you expose any agent endpoints, guard them with the server’s auth and CSRF protections.

References:
- Jupyter Server docs: https://jupyter-server.readthedocs.io/

---

## 10) FAQ — Addressing “No Official Way”

| Claim | What’s actually true | Actionable guidance |
|---|---|---|
| “No official documented way to insert cells server-side with real-time sync.” | The **collaboration stack** (server+lab) is the official path. Its project description states models are used for **real-time collaboration and server-side execution of notebooks**. | Build on **`jupyter-server-ydoc` + `jupyter_ydoc`** and manipulate **YNotebook** directly. |
| “YDoc access is read-only / unsafe to modify.” | The **live shared model** is designed to be edited; that’s how collaboration works. The **YNotebook** Python API exposes `append_cell`, `set_cell`, etc., including **outputs** and `execution_count`. | Make sure you bind to the **live** YNotebook (not a detached copy). |
| “Architecture is frontend-only; server just relays.” | The server **manages YDocuments**, integrates CRDTs with files/kernels, and serves **WebSocket RTC**. It supports server-side manipulation. | Keep control on the backend: edit **YNotebook** + drive kernel with **jupyter_client**. |
| “Server extensions should expose REST, not modify YDocs.” | The collaboration server extension **exists to manage YDocs** and is the supported integration point. | Implement as a server extension; avoid UI scripting unless for cosmetic focus/scroll. |

---

## 11) Minimal End-to-End Pseudocode (Wire-up)

```python
# 0) Resolve notebook path -> live YNotebook + KernelClient (impl-specific bindings)
ynb = get_live_ynotebook("/path/to.ipynb")              # bind to shared model (RTC)
kclient = get_kernel_client_for_path("/path/to.ipynb")  # jupyter_client KernelClient

# 1) Insert a code cell
cid = gen_uuid()
insert_cell(ynb, index='append', cell_type='code', source="print('hello')", cell_id=cid)

# 2) Execute + stream outputs back into the same cell
outputs, exec_count = [], None
for kind, payload in execute_and_stream(kclient, "print('hello')"):  # see §5.3
    if kind == 'output':
        outputs.append(payload)
        update_cell_outputs(ynb, index=-1, outputs=outputs, exec_count=exec_count)

# 3) On finalize, set execution_count
exec_count = get_final_execution_count(kclient)  # e.g., from execute_reply / execute_result
update_cell_outputs(ynb, index=-1, outputs=outputs, exec_count=exec_count)
# -> UI shows cell + outputs in real-time (RTC)
```

References:
- Jupyter Client (execute_request & IOPub): https://jupyter-client.readthedocs.io/en/latest/api/jupyter_client.html
- nbformat output schema: https://nbformat.readthedocs.io/en/latest/format_description.html
- Jupyter YDoc (YNotebook): https://jupyter-ydoc.readthedocs.io/
- JupyterLab RTC docs: https://jupyterlab.readthedocs.io/en/latest/user/rtc.html

---

### End

This spec contains the **complete pieces** your coding agent needs: how to bind to the live shared model, mutate it, execute code and translate kernel messages to nbformat outputs, and leverage RTC for **real-time** UI updates.
