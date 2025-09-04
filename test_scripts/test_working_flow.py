#!/usr/bin/env python3
"""
Working complete flow test using the proven approach
"""

import asyncio
import json
import uuid
import websockets
from jupyter_agent_bridge.room_proxy import RoomProxy
from jupyter_agent_bridge.handlers import build_insert_cell_update


async def execute_code_and_get_outputs(
    code: str, kernel_id: str, token: str, server_url: str
):
    """Execute code in kernel and return the outputs"""
    from urllib.parse import urlparse

    parsed = urlparse(server_url)
    ws_url = f"ws://{parsed.netloc}/api/kernels/{kernel_id}/channels?token={token}"

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
                    "username": "agent",
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

            timeout_count = 0
            max_timeouts = 100  # 10 seconds total

            while timeout_count < max_timeouts:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    msg = json.loads(message)
                    msg_type = msg.get("header", {}).get("msg_type", "")
                    parent_msg_id = msg.get("parent_header", {}).get("msg_id", "")

                    # Only process messages related to our execution
                    if parent_msg_id == msg_id:
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
                    timeout_count += 1
                    continue

    except Exception as e:
        print(f"❌ Error during execution: {e}")
        return [], None

    return outputs, execution_count


async def test_working_flow():
    """Test the complete flow using known working methods"""

    print("=" * 60)
    print("WORKING COMPLETE FLOW TEST")
    print("=" * 60)

    # Use current working parameters from the running server
    server_url = "http://127.0.0.1:8890"
    token = "01832d646d7715316bd90727b3ac14aa4c1eceb1425df2c1"
    notebook_path = "Untitled.ipynb"

    print(f"✅ Server: {server_url}")
    print(f"✅ Token: {token[:16]}...")
    print(f"✅ Notebook: {notebook_path}")

    # Check if we can find an existing kernel from the logs
    # From the logs, I can see kernel IDs being used
    # Let's try to get one dynamically but fall back to creating new one

    # For now, let's create a new kernel by starting with a simple approach
    # We'll use the working RoomProxy approach for cell insertion

    # Code to execute
    test_code = """
import datetime
import random

print(f"🚀 Agent test execution at {datetime.datetime.now()}")
print("🔢 Performing calculations...")

# Generate some data
data = [random.randint(1, 100) for _ in range(3)]
print(f"📊 Generated data: {data}")

total = sum(data)
print(f"📈 Total: {total}")

# This creates an execute_result output
{"timestamp": str(datetime.datetime.now()), "data": data, "total": total}
"""

    # Step 1: Insert the cell using RoomProxy (this works)
    print("\n🔸 STEP 1: Inserting cell using RoomProxy...")
    try:
        cell_update = build_insert_cell_update(
            index=0, cell_type="code", source=test_code
        )

        async with RoomProxy(
            path=notebook_path, server_url=server_url, token=token
        ) as room:
            await room.apply_yupdate(cell_update)
            print("✅ Cell inserted successfully via RoomProxy")
    except Exception as e:
        print(f"❌ Failed to insert cell: {e}")
        return {"error": "cell_insertion_failed"}

    # Step 2: For kernel execution, we need a kernel ID
    # Let's try to create a new kernel using a direct WebSocket approach
    # or use a known kernel ID from the process

    # From the server logs, I can see kernel IDs like:
    # Let's try to use the InsertCellHandler with execute=True instead
    print("\n🔸 STEP 2: Using InsertCellHandler with execution...")

    try:
        import aiohttp

        # Get XSRF token first
        jar = aiohttp.CookieJar()
        async with aiohttp.ClientSession(cookie_jar=jar) as session:
            # Establish session
            async with session.get(f"{server_url}/lab?token={token}") as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to establish session: {resp.status}")

                # Get XSRF token
                xsrf_token = None
                for cookie_name, cookie in resp.cookies.items():
                    if cookie_name == "_xsrf":
                        xsrf_token = cookie.value
                        break

                if not xsrf_token:
                    raise Exception("No XSRF token found")

                print(f"✅ Got XSRF token: {xsrf_token[:16]}...")

            # Try the insert endpoint with execute=True
            insert_data = {
                "path": notebook_path,
                "source": test_code,
                "cell_type": "code",
                "index": 1,  # Insert as second cell
                "execute": True,
                "_xsrf": xsrf_token,
            }

            headers = {"Content-Type": "application/json", "X-CSRFToken": xsrf_token}

            async with session.post(
                f"{server_url}/api/agent/notebook/insert?token={token}",
                json=insert_data,
                headers=headers,
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print("✅ Cell inserted and executed successfully!")
                    print(f"📋 Result: {result}")

                    if "execution" in result:
                        execution = result["execution"]
                        if execution.get("status") == "ok":
                            outputs = execution.get("outputs", [])
                            execution_count = execution.get("execution_count")

                            print(f"📊 Got {len(outputs)} outputs:")
                            for i, output in enumerate(outputs):
                                print(f"  {i + 1}. {output['output_type']}")

                            # The outputs should already be in the notebook via the handler
                            print(
                                "✅ Complete flow successful - cell inserted and executed with outputs!"
                            )

                            return {
                                "success": True,
                                "method": "InsertCellHandler_with_execute",
                                "outputs_count": len(outputs),
                                "execution_count": execution_count,
                            }
                        else:
                            print(f"⚠️ Execution had issues: {execution}")

                else:
                    error_text = await resp.text()
                    print(f"❌ Insert endpoint failed: {resp.status} - {error_text}")

                    # Fall back to manual execution approach
                    return await manual_execution_fallback(
                        test_code, notebook_path, server_url, token
                    )

    except Exception as e:
        print(f"❌ InsertCellHandler approach failed: {e}")
        return await manual_execution_fallback(
            test_code, notebook_path, server_url, token
        )


async def manual_execution_fallback(test_code, notebook_path, server_url, token):
    """Fallback to manual kernel execution"""
    print("\n🔸 FALLBACK: Manual kernel execution...")

    # Try to find or create a kernel
    # This is a simplified approach - in a real implementation,
    # we'd have better kernel management

    # For now, let's assume we have a kernel and try with a known ID
    # You would need to get this dynamically in a real implementation

    print("⚠️ Manual kernel execution would require a valid kernel ID")
    print("   In a production system, you would:")
    print("   1. Query /api/kernels to find existing kernels")
    print("   2. Create a new kernel if none exist")
    print("   3. Execute code via WebSocket")
    print("   4. Update cell outputs via the UpdateCellOutputsHandler")

    return {
        "partial_success": True,
        "cell_inserted": True,
        "execution_attempted": False,
        "note": "Cell inserted successfully, manual execution would require kernel management",
    }


if __name__ == "__main__":
    result = asyncio.run(test_working_flow())
    print(f"\n🎯 Final Result: {result}")
