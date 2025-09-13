# Test Scripts - Jupyter Tools Bridge

This folder contains tests for the server-side notebook manipulation tools.

## Main Tests

### `test_ydoc_tools.py`
- Purpose: End-to-end validation of live YDoc notebook manipulation
- Covers:
  - Insert (markdown/code), update, execute (with execution_count), rich outputs, error handling
  - Delete by index and by cell_id
  - Force save to persist changes to disk
- Usage:
  ```bash
  python test_scripts/test_ydoc_tools.py
  ```

### `test_mcp.py`
- Purpose: MCP integration testing (kept for future use)

### `tools_env_check.py`
- Purpose: Environment sanity check (extensions, packages, and server status)
- Usage:
  ```bash
  python test_scripts/tools_env_check.py
  ```

## Prerequisites
- JupyterLab running:
  ```bash
  jupyter lab --dev-mode --extensions-in-dev-mode --ServerApp.log_level=DEBUG --port=8890
  ```
- Open `test_tools.ipynb` with an active kernel before running tests

## Notes
- Tests operate on the live YDoc (RTC) model; changes appear instantly in the UI.
- The save endpoint is called at the end of the test to ensure persistence across restarts.
