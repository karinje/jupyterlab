#!/usr/bin/env python3
"""
Simple test: Insert cell then immediately insert outputs to verify the mechanism
"""

import asyncio
from jupyter_agent_bridge.room_proxy import RoomProxy
from jupyter_agent_bridge import (
    build_insert_cell_update,
    build_cell_outputs_update,
)


async def test_simple_output_insert():
    """Test inserting outputs into a cell that was just created"""

    path = "Untitled.ipynb"
    server_url = "http://127.0.0.1:8890"
    token = "b5dba9f74f2d3ab186250c16f9c1d70aefff7d592a917025"

    print("=" * 50)
    print("SIMPLE OUTPUT INSERT TEST")
    print("=" * 50)

    # Step 1: Insert a cell
    print("\n🔸 STEP 1: Inserting cell...")
    test_code = "print('Hello from test cell!')\n42"

    cell_update = build_insert_cell_update(index=0, cell_type="code", source=test_code)

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(cell_update)
        print("✅ Cell inserted at index 0")

    # Step 2: Create some fake outputs
    print("\n🔸 STEP 2: Creating fake outputs...")
    fake_outputs = [
        {"output_type": "stream", "name": "stdout", "text": "Hello from test cell!\n"},
        {
            "output_type": "execute_result",
            "execution_count": 99,
            "data": {"text/plain": "42"},
            "metadata": {},
        },
    ]

    # Step 3: Insert outputs
    print("\n🔸 STEP 3: Inserting outputs...")
    output_update = build_cell_outputs_update(
        cell_index=0, outputs=fake_outputs, execution_count=99
    )

    async with RoomProxy(path=path, server_url=server_url, token=token) as room:
        await room.apply_yupdate(output_update)
        print("✅ Outputs inserted")

    print("\n" + "=" * 50)
    print("TEST COMPLETED - Check the notebook!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_simple_output_insert())
