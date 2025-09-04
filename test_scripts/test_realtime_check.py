#!/usr/bin/env python3
"""
Simple test to check real-time Y-document updates
"""

import asyncio
import uuid
from jupyter_agent_bridge.room_proxy import RoomProxy
from pycrdt import Doc, Map, Array, Text


async def test_realtime_update():
    """Test if Y-document updates appear in real-time"""

    # Configuration
    path = "Untitled.ipynb"
    server_url = "http://127.0.0.1:8890"
    token = "083227b4643dfce99c6b60de6982a36131137501f6635538"

    print("🔄 Testing Real-Time Y-Document Updates")
    print("=" * 50)
    print("📝 Watch your JupyterLab notebook for real-time changes...")
    print("   (Should appear WITHOUT refreshing!)")

    # Test 1: Insert a simple markdown cell
    print("\n🔸 TEST 1: Inserting markdown cell...")

    cell_id = str(uuid.uuid4())
    ydoc = Doc()
    cells = ydoc["cells"] = Array()

    cell = Map(
        {
            "id": cell_id,
            "cell_type": "markdown",
            "source": Text(
                f"# Real-Time Test {cell_id[:8]}\n\nThis cell should appear **immediately** without refresh!"
            ),
            "metadata": Map({}),
        }
    )

    with ydoc.transaction():
        cells.insert(0, cell)

    cell_update = ydoc.get_update()

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(cell_update)
        print(f"✅ Markdown cell inserted: {cell_id[:8]}...")

    print("⏳ Waiting 3 seconds for you to check if it appeared...")
    await asyncio.sleep(3)

    # Test 2: Insert a code cell
    print("\n🔸 TEST 2: Inserting code cell...")

    cell_id_2 = str(uuid.uuid4())
    ydoc_2 = Doc()
    cells_2 = ydoc_2["cells"] = Array()

    cell_2 = Map(
        {
            "id": cell_id_2,
            "cell_type": "code",
            "source": Text(f'print("Real-time code cell {cell_id_2[:8]}")'),
            "metadata": Map({}),
            "execution_count": None,
            "outputs": Array(),
        }
    )

    with ydoc_2.transaction():
        cells_2.insert(0, cell_2)

    cell_update_2 = ydoc_2.get_update()

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(cell_update_2)
        print(f"✅ Code cell inserted: {cell_id_2[:8]}...")

    print("⏳ Waiting 3 seconds for you to check if it appeared...")
    await asyncio.sleep(3)

    print("\n" + "=" * 50)
    print("✅ Real-time update test completed!")
    print("📋 Check your notebook - you should see 2 new cells")
    print("   - 1 markdown cell with heading")
    print("   - 1 code cell with print statement")
    print("   - Both should have appeared WITHOUT refreshing!")


if __name__ == "__main__":
    asyncio.run(test_realtime_update())
