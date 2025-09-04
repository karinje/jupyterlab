#!/usr/bin/env python3
"""
Test script to execute code in a Jupyter kernel using WebSocket
"""

import asyncio
import websockets
import json
import uuid


async def test_kernel_execution():
    # Configuration
    base_url = "http://127.0.0.1:8890"
    token = "b5dba9f74f2d3ab186250c16f9c1d70aefff7d592a917025"
    kernel_id = "74744e83-76bb-480c-8cce-1df8e07c59c1"

    # WebSocket URL for kernel
    ws_url = f"ws://127.0.0.1:8890/api/kernels/{kernel_id}/channels?token={token}"

    print(f"Connecting to kernel WebSocket: {ws_url}")

    try:
        async with websockets.connect(ws_url) as websocket:
            print("✅ Connected to kernel WebSocket")

            # Create execution request message
            msg_id = str(uuid.uuid4())
            execute_msg = {
                "header": {
                    "msg_id": msg_id,
                    "msg_type": "execute_request",
                    "username": "test_user",
                    "session": str(uuid.uuid4()),
                    "date": "",
                    "version": "5.3",
                },
                "parent_header": {},
                "metadata": {},
                "content": {
                    "code": "print('Hello from WebSocket execution!')\nresult = 5 * 7\nprint(f'5 * 7 = {result}')",
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

            # Listen for responses
            outputs = []
            execution_count = None

            print("📥 Listening for responses...")
            timeout_count = 0
            max_timeout = 50  # 5 seconds

            while timeout_count < max_timeout:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    msg_data = json.loads(message)

                    msg_type = msg_data.get("header", {}).get("msg_type")
                    parent_msg_id = msg_data.get("parent_header", {}).get("msg_id")

                    print(f"📨 Received: {msg_type}")

                    # Only process messages related to our execution
                    if parent_msg_id == msg_id:
                        if msg_type == "execute_reply":
                            execution_count = msg_data.get("content", {}).get(
                                "execution_count"
                            )
                            status = msg_data.get("content", {}).get("status")
                            print(
                                f"✅ Execution completed: status={status}, count={execution_count}"
                            )

                        elif msg_type == "stream":
                            output_text = msg_data.get("content", {}).get("text", "")
                            outputs.append(
                                {"output_type": "stream", "text": output_text}
                            )
                            print(f"📄 Output: {output_text.strip()}")

                        elif msg_type == "execute_result":
                            data = msg_data.get("content", {}).get("data", {})
                            outputs.append(
                                {"output_type": "execute_result", "data": data}
                            )
                            print(f"📊 Result: {data}")

                        elif msg_type == "error":
                            error_info = msg_data.get("content", {})
                            outputs.append(
                                {"output_type": "error", "error": error_info}
                            )
                            print(f"❌ Error: {error_info}")

                    # Check if execution is done
                    if msg_type == "execute_reply" and parent_msg_id == msg_id:
                        break

                except asyncio.TimeoutError:
                    timeout_count += 1
                    continue

            print("\n🎉 Execution Summary:")
            print(f"   Message ID: {msg_id}")
            print(f"   Execution Count: {execution_count}")
            print(f"   Outputs: {len(outputs)} items")

            for i, output in enumerate(outputs):
                print(f"   Output {i + 1}: {output['output_type']}")
                if "text" in output:
                    print(f"      Text: {repr(output['text'])}")

            return {
                "status": "ok",
                "execution_count": execution_count,
                "outputs": outputs,
                "msg_id": msg_id,
            }

    except Exception as e:
        print(f"❌ Error: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    result = asyncio.run(test_kernel_execution())
    print(f"\nFinal result: {result}")
