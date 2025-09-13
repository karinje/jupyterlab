# Jupyter Tools Bridge (Server-side, RTC YDoc)

Server extension providing backend-only tools to manipulate open Jupyter notebooks in real time via the live YDoc shared model (RTC). No frontend scripting required; the browser updates instantly.

- Extension module: `jupyter_tools_bridge`
- Handlers: `jupyter_tools_bridge/handlers.py`
- Live model resolution: per request via `YDocExtension.get_document(path, copy=False)`

## Endpoints (JSON)
Base URL: `http://localhost:8890`

All POSTs require XSRF header (`X-XSRFToken`); in dev the token is disabled but supported.

### Insert cell
POST `/api/tools/insert-cell`
Body:
```json
{
  "path": "test_tools.ipynb",
  "index": "append",  // or integer
  "cell_type": "code", // "markdown" | "raw"
  "source": "print('hello')"
}
```
Response: `{ status, cell_id, index }`

### Update cell
POST `/api/tools/update-cell`
Body (one of index or cell_id):
```json
{
  "path": "test_tools.ipynb",
  "cell_id": "<uuid>",
  "source": "# Updated...",
  "metadata": { "tags": ["foo"] }
}
```
Response: `{ status, index }`

### Execute cell
POST `/api/tools/execute-cell`
```json
{
  "path": "test_tools.ipynb",
  "kernel_id": "<kernel-id>",
  "cell_id": "<uuid>", // or index
  "stream": true
}
```
- execution_count is set from IOPub `execute_input` (authoritative), with fallback to `execute_result` if needed.
Response: `{ status, index, execution_count, outputs_count }`

### Delete cell
POST `/api/tools/delete-cell`
```json
{
  "path": "test_tools.ipynb",
  "index": "last" // or integer; or use "cell_id"
}
```
- Uses the YArray directly (e.g., `ycells.pop(index)`), which updates RTC immediately.
Response: `{ status, deleted_index, cells_remaining }`

### Notebook state (snapshot)
POST `/api/tools/notebook-state`
```json
{ "path": "test_tools.ipynb" }
```
Response: `{ status, path, cells_count, cells: [{ index, id, type, source_length, execution_count?, outputs_count? }] }`

### Active sessions (get kernel_id)
GET `/api/tools/sessions`
Response: `{ status, sessions: [{ id, path, name, type, kernel: { id, name } }] }`

### Force save (persist RTC → disk)
POST `/api/tools/save`
```json
{ "path": "test_tools.ipynb" }
```
- Serializes the current live YNotebook to nbformat and calls `ContentsManager.save`. Guarantees durability before restarts.
Response: `{ status, saved, path, cells }`

## How it’s wired
- On load (`jupyter_tools_bridge/__init__.py`), the server stores in `web_app.settings`:
  - `kernel_manager`, `session_manager`, `serverapp`, and the `YDocExtension` service
- Each handler resolves the live YNotebook by calling `ydoc_ext.get_document(path, copy=False)`
- Cell ops use the YNotebook live API: `append_cell`, `create_ycell`+`set_ycell`, `get_cell`/`set_cell`, `ycells.pop`, and kernel execution via `jupyter_client`

## Auth/XSRF
- Dev: token may be blank; production should set `ServerApp.token` and require `Authorization: token <...>`
- XSRF: POSTs require `X-XSRFToken` header; clients obtain `_xsrf` cookie from `/lab`

## Running (dev)
Start Jupyter:
```bash
jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890 --config=jupyter_server_config.py
```
- `jupyter_server_config.py` enables: `jupyter_server_fileid`, `jupyter_server_ydoc`, `jupyter_collaboration`, `jupyter_tools_bridge`
- Open `test_tools.ipynb` in the browser (ensures a live session/kernel)

Run tools tests:
```bash
python test_scripts/test_ydoc_tools.py
```
- Exercises index- and id-based flows and calls `/api/tools/save` to persist

Env sanity check:
```bash
python test_scripts/tools_env_check.py
```

## Integration flow (Agent/Chat)
1) Call `/api/tools/sessions` and pick your notebook’s `path` and `kernel_id`
2) Insert/Update/Execute/Delete via endpoints (by index or `cell_id`)
3) Call `/api/tools/save` to persist before restart/handoff

## Notes
- All changes operate on the live RTC model; the UI updates instantly
- For persistence across restarts use autosave (wait) or call the save endpoint 