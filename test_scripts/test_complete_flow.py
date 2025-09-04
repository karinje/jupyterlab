#!/usr/bin/env python3
"""
Complete flow test: Insert cell + Execute + Insert outputs
"""

import asyncio
import json
import uuid
from jupyter_agent_bridge.room_proxy import RoomProxy
import websockets
import pycrdt


def build_cell_output_update(
    cell_index: int, outputs: list, execution_count: int = None
):
    """
    Build a Y-update to insert outputs into a specific cell

    Args:
        cell_index: Index of the cell to update
        outputs: List of output objects (from kernel execution)
        execution_count: Execution count to set on the cell
    """
    # Create a Y document to build the update
    doc = pycrdt.Doc()

    # Create the notebook structure
    notebook = doc.get_map("notebook")
    cells = doc.get_array("cells")

    # We need to create a partial structure to update the specific cell
    # In Yjs, we target the specific cell by its index and update its outputs

    # Create the update for cell outputs
    update_data = {"cell_index": cell_index, "outputs": outputs}

    if execution_count is not None:
        update_data["execution_count"] = execution_count

    # For now, let's create a simpler approach - we'll build a Y-update
    # that targets the cell's outputs array directly

    # This is a simplified approach - in reality we'd need to:
    # 1. Navigate to the specific cell by index
    # 2. Update its outputs array
    # 3. Set execution_count if provided

    # Create the Y-update bytes
    with doc.transaction() as txn:
        # Add a marker to track this update
        update_marker = doc.get_map("cell_output_update")
        update_marker.set("cell_index", cell_index)
        update_marker.set("outputs", json.dumps(outputs))
        if execution_count is not None:
            update_marker.set("execution_count", execution_count)

    return doc.get_update()


async def execute_code_and_get_outputs(
    code: str, kernel_id: str, token: str, server_url: str
):
    """Execute code in kernel and return the outputs"""
    ws_url = f"ws://127.0.0.1:8890/api/kernels/{kernel_id}/channels?token={token}"

    outputs = []
    execution_count = None

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected to kernel WebSocket")

            # Create execution request
            msg_id = str(uuid.uuid4())
            execute_msg = {
                "header": {
                    "msg_id": msg_id,
                    "msg_type": "execute_request",
                    "username": "test",
                    "session": str(uuid.uuid4()),
                    "date": "",
                    "version": "5.3",
                },
                "parent_header": {},
                "metadata": {},
                "content": {
                    "code": code,
                    "silent": False,
                    "store_history": True,
                    "user_expressions": {},
                    "allow_stdin": False,
                    "stop_on_error": True,
                },
                "buffers": [],
                "channel": "shell",
            }

            print("📤 Sending execution request...")
            await websocket.send(json.dumps(execute_msg))

            print("📥 Listening for responses...")

            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    msg = json.loads(message)
                    msg_type = msg.get("header", {}).get("msg_type", "")

                    print(f"📨 Received: {msg_type}")

                    # Collect outputs
                    if msg_type == "stream":
                        output = {
                            "output_type": "stream",
                            "name": msg["content"]["name"],
                            "text": msg["content"]["text"],
                        }
                        outputs.append(output)
                        print(f"📄 Stream output: {msg['content']['text'].strip()}")

                    elif msg_type == "execute_result":
                        output = {
                            "output_type": "execute_result",
                            "execution_count": msg["content"]["execution_count"],
                            "data": msg["content"]["data"],
                            "metadata": msg["content"].get("metadata", {}),
                        }
                        outputs.append(output)
                        print(f"📄 Execute result: {msg['content']['data']}")

                    elif msg_type == "display_data":
                        output = {
                            "output_type": "display_data",
                            "data": msg["content"]["data"],
                            "metadata": msg["content"].get("metadata", {}),
                        }
                        outputs.append(output)
                        print(f"📄 Display data: {msg['content']['data']}")

                    elif msg_type == "error":
                        output = {
                            "output_type": "error",
                            "ename": msg["content"]["ename"],
                            "evalue": msg["content"]["evalue"],
                            "traceback": msg["content"]["traceback"],
                        }
                        outputs.append(output)
                        print(
                            f"📄 Error: {msg['content']['ename']}: {msg['content']['evalue']}"
                        )

                    elif msg_type == "execute_reply":
                        execution_count = msg["content"]["execution_count"]
                        status = msg["content"]["status"]
                        print(
                            f"✅ Execution completed: status={status}, count={execution_count}"
                        )
                        break

                except asyncio.TimeoutError:
                    print("⏰ Timeout waiting for more messages")
                    break

    except Exception as e:
        print(f"❌ Error during execution: {e}")
        return [], None

    return outputs, execution_count


async def get_current_token_and_kernel():
    """Get the current JupyterLab token and kernel ID dynamically"""
    import aiohttp
    import re

    # Get the token from the main page
    async with aiohttp.ClientSession() as session:
        async with session.get("http://127.0.0.1:8890") as resp:
            if resp.status == 302:
                # Follow redirect to get token from URL
                location = resp.headers.get("Location", "")
                token_match = re.search(r"token=([a-f0-9]+)", location)
                if token_match:
                    token = token_match.group(1)
                else:
                    raise Exception("Could not extract token from redirect")
            elif resp.status == 200:
                # Check if page contains token in HTML
                html = await resp.text()
                token_match = re.search(r'data-jupyter-api-token="([a-f0-9]+)"', html)
                if token_match:
                    token = token_match.group(1)
                else:
                    raise Exception("Could not extract token from HTML")
            else:
                raise Exception(f"Unexpected status: {resp.status}")

        # Get available kernels
        headers = {"Authorization": f"token {token}"}
        async with session.get(
            "http://127.0.0.1:8890/api/kernels", headers=headers
        ) as resp:
            if resp.status == 200:
                kernels = await resp.json()
                if kernels:
                    kernel_id = kernels[0]["id"]
                else:
                    # Start a new kernel if none exist
                    async with session.post(
                        "http://127.0.0.1:8890/api/kernels",
                        headers=headers,
                        json={"name": "python3"},
                    ) as resp:
                        kernel_data = await resp.json()
                        kernel_id = kernel_data["id"]
            else:
                raise Exception(f"Failed to get kernels: {resp.status}")

    return token, kernel_id


async def test_multiple_cell_targeting():
    """Test multiple cell targeting scenarios to verify our approach works"""

    # Configuration
    path = "Untitled.ipynb"
    server_url = "http://127.0.0.1:8890"

    # Use current values from the fresh server restart
    token = "d0e4b88278aa22aef04a73accbe7deafd8484a042a5830a2"  # New token from dev mode restart
    kernel_id = "NEED_TO_CREATE"  # Will create new kernel
    print(f"✅ Token: {token[:16]}...")

    # Create a new kernel first
    print("🔸 Creating new kernel...")
    import aiohttp

    headers = {"Authorization": f"token {token}"}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server_url}/api/kernels", headers=headers, json={"name": "python3"}
        ) as resp:
            if resp.status == 201:
                kernel_data = await resp.json()
                kernel_id = kernel_data["id"]
                print(f"✅ Created kernel: {kernel_id}")
            else:
                raise Exception(f"Failed to create kernel: {resp.status}")

    # Code to execute (with matplotlib plot to test rich outputs)
    test_code = """
import matplotlib.pyplot as plt
import numpy as np
import datetime

print(f"🚀 Starting execution at {datetime.datetime.now()}")
print("🔢 Creating a plot...")

# Create a simple plot
x = np.linspace(0, 10, 100)
y = np.sin(x)

plt.figure(figsize=(6, 4))
plt.plot(x, y, 'b-', linewidth=2)
plt.title('Agent Test Plot')
plt.xlabel('X')
plt.ylabel('Sin(X)')
plt.grid(True)
plt.show()

print("✨ Plot completed!")
"Agent execution successful"  # This will create an execute_result output
"""

    print("=" * 60)
    print("CELL TARGETING TEST: Multiple scenarios")
    print("=" * 60)

    # Step 1: Insert the cell and track its ID
    print("\n🔸 STEP 1: Inserting cell...")

    # Generate a unique cell ID that we can track
    cell_id = str(uuid.uuid4())

    # Build cell update with our specific cell ID
    from pycrdt import Doc, Map, Array, Text

    ydoc = Doc()
    cells = ydoc["cells"] = Array()

    cell_map = {
        "id": cell_id,  # Use our tracked cell ID
        "cell_type": "code",
        "source": Text(test_code),
        "metadata": Map({}),
        "execution_count": None,
        "outputs": Array(),
    }
    cell = Map(cell_map)

    with ydoc.transaction():
        cells.insert(0, cell)  # Insert at beginning

    cell_update = ydoc.get_update()

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(cell_update)
        print(f"✅ Cell inserted successfully with ID: {cell_id}")

        # Kernel ID is already obtained above

    # Step 2: Execute the code
    print("\n🔸 STEP 2: Executing code...")
    outputs, execution_count = await execute_code_and_get_outputs(
        test_code, kernel_id, token, server_url
    )

    print(f"📋 Collected {len(outputs)} outputs:")
    for i, output in enumerate(outputs):
        print(f"  {i + 1}. {output['output_type']}: {str(output)[:100]}...")

    # Step 3: Insert outputs back into the notebook
    print("\n🔸 STEP 3: Inserting outputs into notebook...")
    if outputs:
        print("📝 Inserting outputs into the cell...")

        # Use the working UpdateCellOutputsHandler directly
        print("🔍 Checking notebook state...")

        # Get the cell ID from the notebook
        import aiohttp

        headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            # Get the notebook and find our specific cell by ID
            async with session.get(
                f"{server_url}/api/contents/{path}", headers=headers
            ) as resp:
                notebook_data = await resp.json()
                cells = notebook_data["content"]["cells"]

                # Find our cell by ID
                target_cell_index = None
                for i, cell in enumerate(cells):
                    if cell.get("id") == cell_id:
                        target_cell_index = i
                        break

                if target_cell_index is None:
                    raise Exception(f"Could not find cell with ID {cell_id}")

                print(f"🎯 Found our cell at index {target_cell_index}")

            # Call the working handler directly with the correct index
            update_data = {
                "path": path,
                "cell_index": target_cell_index,
                "outputs": outputs,
                "execution_count": execution_count,
            }

            async with session.post(
                f"{server_url}/api/agent/notebook/update_outputs",
                headers=headers,
                json=update_data,
            ) as resp:
                if resp.status == 200:
                    print("✅ Outputs inserted successfully!")
                else:
                    error_text = await resp.text()
                    print(f"❌ Failed to insert outputs: {resp.status} - {error_text}")

        print(f"📊 Inserted {len(outputs)} outputs:")
        for i, output in enumerate(outputs):
            print(f"  {i + 1}. {output['output_type']}")

    else:
        print("⚠️  No outputs to insert")

    # SCENARIO 2: Insert code in CELL A, execute CELL B, put outputs in CELL C
    print("\n" + "=" * 40)
    print("🔸 SCENARIO 2: Cross-cell targeting test")
    print("Agent control: Insert→A, Execute→B, Outputs→C")
    print("=" * 40)

    # Create CELL A (code storage only)
    cell_a_id = str(uuid.uuid4())
    code_a = 'x = 100\ny = 200\nprint("Variables set in Cell A")'

    ydoc_a = Doc()
    cells_a = ydoc_a["cells"] = Array()
    cell_a = Map(
        {
            "id": cell_a_id,
            "cell_type": "code",
            "source": Text(code_a),
            "metadata": Map({}),
            "execution_count": None,
            "outputs": Array(),
        }
    )

    with ydoc_a.transaction():
        cells_a.append(cell_a)

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(ydoc_a.get_update())
        print(f"✅ CELL A inserted (code storage): {cell_a_id[:8]}...")

    # Create CELL B (different code to execute)
    cell_b_id = str(uuid.uuid4())
    code_b = 'result = x + y\nprint(f"Sum from Cell B: {result}")\nresult'

    ydoc_b = Doc()
    cells_b = ydoc_b["cells"] = Array()
    cell_b = Map(
        {
            "id": cell_b_id,
            "cell_type": "code",
            "source": Text(code_b),
            "metadata": Map({}),
            "execution_count": None,
            "outputs": Array(),
        }
    )

    with ydoc_b.transaction():
        cells_b.append(cell_b)

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(ydoc_b.get_update())
        print(f"✅ CELL B inserted (execution target): {cell_b_id[:8]}...")

    # Create CELL C (output destination only)
    cell_c_id = str(uuid.uuid4())
    code_c = "# This cell will receive outputs from Cell B execution"

    ydoc_c = Doc()
    cells_c = ydoc_c["cells"] = Array()
    cell_c = Map(
        {
            "id": cell_c_id,
            "cell_type": "code",
            "source": Text(code_c),
            "metadata": Map({}),
            "execution_count": None,
            "outputs": Array(),
        }
    )

    with ydoc_c.transaction():
        cells_c.append(cell_c)

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(ydoc_c.get_update())
        print(f"✅ CELL C inserted (output destination): {cell_c_id[:8]}...")

    # Execute CELL A first (setup variables)
    print("🔸 Executing CELL A (setup)...")
    outputs_a, exec_count_a = await execute_code_and_get_outputs(
        code_a, kernel_id, token, server_url
    )

    # Execute CELL B (main computation)
    print("🔸 Executing CELL B (computation)...")
    outputs_b, exec_count_b = await execute_code_and_get_outputs(
        code_b, kernel_id, token, server_url
    )

    # Put CELL B's outputs into CELL C
    print("🔸 Putting CELL B outputs into CELL C...")
    if outputs_b:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{server_url}/api/contents/{path}", headers=headers
            ) as resp:
                notebook_data = await resp.json()
                cells = notebook_data["content"]["cells"]

                # Find CELL C by ID
                cell_c_index = None
                for i, cell in enumerate(cells):
                    if cell.get("id") == cell_c_id:
                        cell_c_index = i
                        break

                print(f"🎯 Found CELL C at index {cell_c_index}")

            update_data = {
                "path": path,
                "cell_index": cell_c_index,
                "outputs": outputs_b,  # CELL B's outputs
                "execution_count": exec_count_b,
            }

            async with session.post(
                f"{server_url}/api/agent/notebook/update_outputs",
                headers=headers,
                json=update_data,
            ) as resp:
                if resp.status == 200:
                    print("✅ CELL B outputs successfully inserted into CELL C!")
                else:
                    print(f"❌ Failed: {resp.status}")

    # SCENARIO 3: Verify the cross-cell targeting worked
    print("\n" + "=" * 40)
    print("🔸 SCENARIO 3: Verify cross-cell targeting")
    print("=" * 40)

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{server_url}/api/contents/{path}", headers=headers
        ) as resp:
            notebook_data = await resp.json()
            cells = notebook_data["content"]["cells"]

            print(f"📋 Notebook now has {len(cells)} cells:")
            for i, cell in enumerate(cells):
                cell_id_found = cell.get("id", "NO_ID")
                has_outputs = len(cell.get("outputs", [])) > 0
                exec_count = cell.get("execution_count", "None")
                source_preview = cell.get("source", "")[:30].replace("\n", " ")
                print(
                    f"  Cell {i}: ID={cell_id_found[:8]}... outputs={has_outputs} exec_count={exec_count}"
                )
                print(f"         Source: {source_preview}...")

                # Verify our specific cells
                if cell_id_found == cell_id:
                    print(
                        f"    ✅ Original cell: {len(cell.get('outputs', []))} outputs"
                    )
                elif cell_id_found == cell_a_id:
                    print(
                        f"    📝 CELL A (storage): {len(cell.get('outputs', []))} outputs"
                    )
                elif cell_id_found == cell_b_id:
                    print(
                        f"    🔧 CELL B (executed): {len(cell.get('outputs', []))} outputs"
                    )
                elif cell_id_found == cell_c_id:
                    print(
                        f"    📤 CELL C (received outputs): {len(cell.get('outputs', []))} outputs"
                    )

            print("\n🎯 Agent Control Test Results:")
            print("   - CELL A: Contains setup code")
            print("   - CELL B: Contains computation code")
            print("   - CELL C: Should have CELL B's execution outputs")

            # Find CELL C and verify it has the right outputs
            for cell in cells:
                if cell.get("id") == cell_c_id:
                    c_outputs = cell.get("outputs", [])
                    if c_outputs:
                        print(
                            f"   ✅ SUCCESS: CELL C has {len(c_outputs)} outputs from CELL B execution!"
                        )
                        for j, output in enumerate(c_outputs):
                            print(
                                f"      Output {j + 1}: {output.get('output_type', 'unknown')}"
                            )
                    else:
                        print("   ❌ FAILED: CELL C has no outputs")
                    break

    print("\n" + "=" * 60)
    print("✅ CELL TARGETING TESTS COMPLETED")
    print("=" * 60)

    return {
        "original_cell": {"cell_id": cell_id, "outputs_count": len(outputs)},
        "cell_a": {"cell_id": cell_a_id, "purpose": "code_storage"},
        "cell_b": {"cell_id": cell_b_id, "purpose": "execution_target"},
        "cell_c": {
            "cell_id": cell_c_id,
            "purpose": "output_destination",
            "outputs_count": len(outputs_b),
        },
        "total_cells_created": 4,
        "agent_control_test": "cross_cell_targeting",
    }


if __name__ == "__main__":
    result = asyncio.run(test_multiple_cell_targeting())
    print(f"\n🎯 Final Result: {result}")
