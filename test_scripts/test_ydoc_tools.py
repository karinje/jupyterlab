#!/usr/bin/env python3
"""
Test script for YDoc-based Jupyter Tools Bridge.

This script tests the real-time notebook manipulation capabilities
using the correct YDocExtension approach.
"""

import asyncio
import sys
import aiohttp


class JupyterToolsTester:
    """Test client for Jupyter Tools Bridge API."""

    def __init__(self, base_url="http://localhost:8890", token=None):
        self.base_url = base_url
        self.token = token
        self.session = None
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"token {token}"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        # Get XSRF token
        await self._get_xsrf_token()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get_xsrf_token(self):
        """Get XSRF token from the server."""
        try:
            async with self.session.get(
                f"{self.base_url}/lab", headers=self.headers
            ) as resp:
                if "_xsrf" in resp.cookies:
                    self.headers["X-XSRFToken"] = resp.cookies["_xsrf"].value
        except Exception as e:
            print(f"Warning: Could not get XSRF token: {e}")

    async def get_sessions(self):
        """Get list of active notebook sessions."""
        url = f"{self.base_url}/api/tools/sessions"
        async with self.session.get(url, headers=self.headers) as resp:
            return await resp.json()

    async def get_notebook_state(self, path):
        """Get current state of a notebook."""
        url = f"{self.base_url}/api/tools/notebook-state"
        data = {"path": path}
        async with self.session.post(url, json=data, headers=self.headers) as resp:
            return await resp.json()

    async def insert_cell(
        self, path, index="append", cell_type="code", source="", cell_id=None
    ):
        """Insert a new cell into the notebook."""
        url = f"{self.base_url}/api/tools/insert-cell"
        data = {"path": path, "index": index, "cell_type": cell_type, "source": source}
        if cell_id:
            data["cell_id"] = cell_id

        async with self.session.post(url, json=data, headers=self.headers) as resp:
            return await resp.json()

    async def update_cell(
        self, path, cell_id=None, index=None, source=None, metadata=None
    ):
        """Update a cell's content."""
        url = f"{self.base_url}/api/tools/update-cell"
        data = {"path": path}

        if cell_id:
            data["cell_id"] = cell_id
        if index is not None:
            data["index"] = index
        if source is not None:
            data["source"] = source
        if metadata is not None:
            data["metadata"] = metadata

        async with self.session.post(url, json=data, headers=self.headers) as resp:
            return await resp.json()

    async def delete_cell(self, path, cell_id=None, index=None):
        """Delete a cell from the notebook."""
        url = f"{self.base_url}/api/tools/delete-cell"
        data = {"path": path}

        if cell_id:
            data["cell_id"] = cell_id
        if index is not None:
            data["index"] = index

        async with self.session.post(url, json=data, headers=self.headers) as resp:
            return await resp.json()

    async def execute_cell(
        self, path, kernel_id, cell_id=None, index=None, stream=True
    ):
        """Execute a cell and get outputs."""
        url = f"{self.base_url}/api/tools/execute-cell"
        data = {"path": path, "kernel_id": kernel_id, "stream": stream}

        if cell_id:
            data["cell_id"] = cell_id
        if index is not None:
            data["index"] = index

        async with self.session.post(url, json=data, headers=self.headers) as resp:
            return await resp.json()


async def run_tests():
    """Run comprehensive tests of the agent API."""

    print("=" * 60)
    print("YDoc-based Jupyter Tools Bridge Test Suite")
    print("=" * 60)

    # You may need to adjust these based on your setup
    BASE_URL = "http://localhost:8890"
    TOKEN = None  # Set if using token authentication
    TEST_NOTEBOOK = "test_tools.ipynb"  # Make sure this notebook is open!

    async with JupyterToolsTester(BASE_URL, TOKEN) as tester:
        # Test 1: Get active sessions
        print("\n📋 Test 1: Getting active sessions...")
        sessions = await tester.get_sessions()
        print(f"Found {len(sessions.get('sessions', []))} active sessions")

        if not sessions.get("sessions"):
            print("❌ No active sessions found. Please open a notebook first!")
            return

        # Find our test notebook
        kernel_id = None
        for session in sessions["sessions"]:
            print(f"  - {session['path']} (kernel: {session['kernel']['id']})")
            if session["path"] == TEST_NOTEBOOK:
                kernel_id = session["kernel"]["id"]

        if not kernel_id:
            print(
                f"❌ Test notebook '{TEST_NOTEBOOK}' not found. Please open it first!"
            )
            return

        print(f"✅ Found test notebook with kernel ID: {kernel_id}")

        # Test 2: Get initial notebook state
        print("\n📊 Test 2: Getting notebook state...")
        state = await tester.get_notebook_state(TEST_NOTEBOOK)
        print(f"Notebook state: {state}")
        initial_cell_count = state.get("cells_count", 0)
        print(f"Notebook has {initial_cell_count} cells")

        # ---------------------------
        # Index-based flow (original)
        # ---------------------------
        print("\n=== INDEX-BASED FLOW ===")

        # Insert markdown (index-based)
        idx_md = await tester.insert_cell(
            TEST_NOTEBOOK,
            index="append",
            cell_type="markdown",
            source="# Index Flow Markdown\n\nInserted via index-based test.",
        )
        print(f"[index] inserted md: {idx_md}")
        idx_md_index = idx_md.get("index")
        await asyncio.sleep(0.3)

        # Insert code (index-based)
        idx_code = await tester.insert_cell(
            TEST_NOTEBOOK,
            index="append",
            cell_type="code",
            source="print('Index flow hello')\n3 + 7",
        )
        print(f"[index] inserted code: {idx_code}")
        idx_code_index = idx_code.get("index")
        await asyncio.sleep(0.3)

        # Execute by index
        idx_exec = await tester.execute_cell(
            TEST_NOTEBOOK, kernel_id, index=idx_code_index, stream=True
        )
        print(f"[index] execute result: {idx_exec}")
        await asyncio.sleep(0.3)

        # Update by index
        idx_upd = await tester.update_cell(
            TEST_NOTEBOOK, index=idx_code_index, source="# Index flow updated\n21 * 2"
        )
        print(f"[index] update result: {idx_upd}")
        await asyncio.sleep(0.3)

        # Re-execute by index
        idx_exec2 = await tester.execute_cell(
            TEST_NOTEBOOK, kernel_id, index=idx_code_index, stream=True
        )
        print(f"[index] execute2 result: {idx_exec2}")
        await asyncio.sleep(0.3)

        # Delete last by index
        idx_del = await tester.delete_cell(TEST_NOTEBOOK, index="last")
        print(f"[index] delete last result: {idx_del}")
        await asyncio.sleep(0.3)

        # ---------------------------
        # ID-based flow (additional)
        # ---------------------------
        print("\n=== ID-BASED FLOW ===")

        # Test 3: Insert markdown cell
        print("\n📝 Test 3: Inserting markdown cell...")
        result = await tester.insert_cell(
            TEST_NOTEBOOK,
            index="append",
            cell_type="markdown",
            source="# Test Markdown Cell\n\nThis cell was inserted by the tools!",
        )
        print(f"Inserted markdown cell: {result}")
        md_cell_id = result.get("cell_id")

        # Small delay to let UI update
        await asyncio.sleep(0.5)

        # Test 4: Insert code cell
        print("\n💻 Test 4: Inserting code cell...")
        result = await tester.insert_cell(
            TEST_NOTEBOOK,
            index="append",
            cell_type="code",
            source="import time\nprint('Hello from tools!')\ntime.sleep(1)\nprint('Done!')\n2 + 2",
        )
        print(f"Inserted code cell: {result}")
        code_cell_id = result.get("cell_id")

        await asyncio.sleep(0.5)

        # Test 5: Execute the code cell by cell_id
        print("\n🚀 Test 5: Executing code cell...")
        result = await tester.execute_cell(
            TEST_NOTEBOOK, kernel_id, cell_id=code_cell_id, stream=True
        )
        print(f"Execution result: {result}")

        await asyncio.sleep(0.5)

        # Test 6: Update cell source by cell_id
        print("\n✏️ Test 6: Updating cell source...")
        result = await tester.update_cell(
            TEST_NOTEBOOK,
            cell_id=code_cell_id,
            source="# Updated code\nprint('This code was updated!')\n10 * 10",
        )
        print(f"Update result: {result}")

        await asyncio.sleep(0.5)

        # Test 7: Execute updated cell by cell_id
        print("\n🔄 Test 7: Executing updated cell...")
        result = await tester.execute_cell(
            TEST_NOTEBOOK, kernel_id, cell_id=code_cell_id, stream=True
        )
        print(f"Execution result: {result}")

        await asyncio.sleep(0.5)

        # Test 8: Insert cell with complex output
        print("\n📊 Test 8: Testing rich outputs...")
        result = await tester.insert_cell(
            TEST_NOTEBOOK,
            index="append",
            cell_type="code",
            source="""import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 2*np.pi, 100)
y = np.sin(x)
plt.figure(figsize=(8, 4))
plt.plot(x, y)
plt.title('Sine Wave')
plt.xlabel('x')
plt.ylabel('sin(x)')
plt.grid(True)
plt.show()""",
        )
        rich_cell_id = result.get("cell_id")

        result = await tester.execute_cell(
            TEST_NOTEBOOK, kernel_id, cell_id=rich_cell_id, stream=True
        )
        print(f"Rich output execution: {result}")

        await asyncio.sleep(0.5)

        # Test 9: Error handling
        print("\n⚠️ Test 9: Testing error output...")
        result = await tester.insert_cell(
            TEST_NOTEBOOK,
            index="append",
            cell_type="code",
            source="raise ValueError('This is a test error')",
        )
        error_cell_id = result.get("cell_id")

        result = await tester.execute_cell(
            TEST_NOTEBOOK, kernel_id, cell_id=error_cell_id, stream=True
        )
        print(f"Error execution: {result}")

        await asyncio.sleep(0.5)

        # Test 10: Get final state
        print("\n📊 Test 10: Getting final notebook state...")
        state = await tester.get_notebook_state(TEST_NOTEBOOK)
        final_cell_count = state.get("cells_count", 0)
        print(
            f"Final cell count: {final_cell_count} (added {final_cell_count - initial_cell_count} cells)"
        )

        # Test 11: Delete by cell_id
        print("\n🗑️ Test 11: Deleting a cell by id...")
        result = await tester.delete_cell(TEST_NOTEBOOK, cell_id=md_cell_id)
        print(f"Delete result: {result}")

        # Allow autosave to persist RTC changes
        await asyncio.sleep(2.0)

        # Force save to disk
        print("\n💾 Forcing save...")
        url = f"{tester.base_url}/api/tools/save"
        async with tester.session.post(
            url, json={"path": TEST_NOTEBOOK}, headers=tester.headers
        ) as resp:
            save_result = await resp.json()
        print(f"Save result: {save_result}")

        # Final state check
        state = await tester.get_notebook_state(TEST_NOTEBOOK)
        print(f"\nFinal notebook has {state.get('cells_count', 0)} cells")

        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("Check your notebook to see the real-time updates!")
        print("=" * 60)


def main():
    """Main entry point."""
    print("\n⚠️  Prerequisites:")
    print("1. Make sure JupyterLab is running (jupyter lab)")
    print("2. Open a notebook named 'test_tools.ipynb'")
    print("3. Make sure the notebook has an active kernel")
    print("\nPress Enter to continue or Ctrl+C to abort...")

    try:
        input()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)

    # Run the async tests
    asyncio.run(run_tests())


if __name__ == "__main__":
    main()
