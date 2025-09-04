#!/usr/bin/env python
"""Demonstrate realtime insertion of a code cell into an open notebook
using only the public collaboration API (no private imports).

Prerequisites:
  • `pip install y_py aiohttp`
  • JupyterLab running with `--collaborative` and TOKEN env set:
        JUPYTER_TOKEN=abc123 jupyter lab --collaborative

Usage:
    python examples/insert_cell_demo.py my_notebook.ipynb

Open the notebook in a browser first – the new cell should appear at
the top instantly.
"""

from __future__ import annotations

import sys
import asyncio
import uuid
from y_py import YDoc, YMap, YArray, YText
from y_py import encode_state_as_update  # type: ignore
import os

from jupyter_agent_bridge.room_proxy import RoomProxy


def build_insert_cell_update(index: int = 0, source: str = "print('hi')") -> bytes:
    """Return a Y-update that inserts a simple code cell at *index*."""
    ydoc = YDoc()
    cells: YArray = ydoc.get_array("cells")

    cell = YMap(
        {
            "id": str(uuid.uuid4()),
            "cell_type": "code",
            "source": YText(source),
            "metadata": YMap({}),
            "execution_count": None,
            "outputs": YArray(),
        }
    )

    with ydoc.begin_transaction() as txn:
        cells.insert(txn, index, cell)

    update = encode_state_as_update(ydoc)
    return update


async def main():
    if len(sys.argv) < 2:
        print("Usage: insert_cell_demo.py NOTEBOOK_PATH.ipynb [SOURCE_CODE]")
        sys.exit(1)

    path = sys.argv[1]
    source_code = sys.argv[2] if len(sys.argv) > 2 else "print('hi')"

    base_url = os.getenv("JUPYTER_BASE_URL", "http://127.0.0.1:8888")
    token = os.getenv("JUPYTER_TOKEN", "<empty>")

    print(f"Base URL: {base_url}\nToken: {token}\nNotebook: {path}")

    update_bytes = build_insert_cell_update(source=source_code)

    async with RoomProxy(path) as room:
        await room.apply_yupdate(update_bytes)
        print("✔ cell inserted – check browser!")
        # keep connection a bit to ensure sync
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
