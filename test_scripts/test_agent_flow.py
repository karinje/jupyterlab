#!/usr/bin/env python3
"""
Simple agent flow test with CLI parameters
Usage: python test_agent_flow.py --token TOKEN --kernel-id KERNEL_ID [--server-url URL] [--notebook PATH]
"""

import asyncio
import argparse
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

            timeout_count = 0
            max_timeouts = 100

            while timeout_count < max_timeouts:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    msg = json.loads(message)
                    msg_type = msg.get("header", {}).get("msg_type", "")
                    parent_msg_id = msg.get("parent_header", {}).get("msg_id", "")

                    if parent_msg_id == msg_id:
                        if msg_type == "stream":
                            outputs.append(
                                {
                                    "output_type": "stream",
                                    "name": msg["content"]["name"],
                                    "text": msg["content"]["text"],
                                }
                            )
                            print(f"📄 {msg['content']['text'].strip()}")

                        elif msg_type == "execute_result":
                            outputs.append(
                                {
                                    "output_type": "execute_result",
                                    "execution_count": msg["content"][
                                        "execution_count"
                                    ],
                                    "data": msg["content"]["data"],
                                    "metadata": msg["content"].get("metadata", {}),
                                }
                            )

                        elif msg_type == "error":
                            outputs.append(
                                {
                                    "output_type": "error",
                                    "ename": msg["content"]["ename"],
                                    "evalue": msg["content"]["evalue"],
                                    "traceback": msg["content"]["traceback"],
                                }
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


async def update_cell_outputs(
    path: str,
    cell_index: int,
    outputs: list,
    execution_count: int,
    server_url: str,
    token: str,
):
    """Update outputs for a specific cell"""
    import aiohttp

    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

    update_data = {
        "path": path,
        "cell_index": cell_index,
        "outputs": outputs,
        "execution_count": execution_count,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{server_url}/api/agent/notebook/update_outputs",
            headers=headers,
            json=update_data,
        ) as resp:
            if resp.status == 200:
                print("✅ Outputs updated successfully!")
                return True
            else:
                error_text = await resp.text()
                print(f"❌ Failed to update outputs: {resp.status} - {error_text}")
                return False


async def test_agent_flow(
    server_url: str, token: str, kernel_id: str, notebook_path: str
):
    """Test the complete agent flow"""

    print("=" * 60)
    print("AGENT FLOW TEST")
    print("=" * 60)
    print(f"Server: {server_url}")
    print(f"Token: {token[:16]}...")
    print(f"Kernel: {kernel_id}")
    print(f"Notebook: {notebook_path}")

    # Test code
    test_code = """
import datetime
print(f"🚀 Agent execution at {datetime.datetime.now()}")
result = 42 * 7
print(f"📊 Result: {result}")
result
"""

    # Step 1: Insert cell
    print("\n🔸 STEP 1: Inserting cell...")
    try:
        cell_update = build_insert_cell_update(
            index=0, cell_type="code", source=test_code
        )

        async with RoomProxy(
            path=notebook_path, server_url=server_url, token=token
        ) as room:
            await room.apply_yupdate(cell_update)
            print("✅ Cell inserted successfully")
    except Exception as e:
        print(f"❌ Failed to insert cell: {e}")
        return {"error": "cell_insertion_failed"}

    # Step 2: Execute code
    print("\n🔸 STEP 2: Executing code...")
    try:
        outputs, execution_count = await execute_code_and_get_outputs(
            test_code, kernel_id, token, server_url
        )

        print(f"📋 Collected {len(outputs)} outputs")

    except Exception as e:
        print(f"❌ Failed to execute code: {e}")
        return {"error": "code_execution_failed"}

    # Step 3: Update cell outputs
    print("\n🔸 STEP 3: Updating cell outputs...")
    if outputs:
        try:
            success = await update_cell_outputs(
                notebook_path, 0, outputs, execution_count, server_url, token
            )
            if not success:
                return {"error": "output_update_failed"}
        except Exception as e:
            print(f"❌ Failed to update outputs: {e}")
            return {"error": "output_update_failed"}
    else:
        print("⚠️  No outputs to insert")

    print("\n" + "=" * 60)
    print("✅ AGENT FLOW COMPLETED SUCCESSFULLY")
    print("=" * 60)

    return {
        "success": True,
        "outputs_count": len(outputs),
        "execution_count": execution_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Test JupyterLab Agent Flow")
    parser.add_argument("--token", required=True, help="Jupyter server token")
    parser.add_argument(
        "--kernel-id", required=True, help="Kernel ID to use for execution"
    )
    parser.add_argument(
        "--server-url", default="http://127.0.0.1:8890", help="Jupyter server URL"
    )
    parser.add_argument("--notebook", default="Untitled.ipynb", help="Notebook path")

    args = parser.parse_args()

    result = asyncio.run(
        test_agent_flow(args.server_url, args.token, args.kernel_id, args.notebook)
    )

    print(f"\n🎯 Final Result: {result}")


if __name__ == "__main__":
    main()
