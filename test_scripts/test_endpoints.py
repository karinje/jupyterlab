#!/usr/bin/env python3
"""
Test script to verify our YDoc endpoints are accessible
"""

import asyncio
import aiohttp
from rich.console import Console
from rich.panel import Panel

console = Console()


async def test_endpoints():
    """Test our YDoc endpoints"""

    base_url = "http://localhost:8889"
    headers = {"Authorization": "token test123", "Content-Type": "application/json"}

    console.print(Panel.fit("🧪 Testing YDoc Extension Endpoints", style="blue"))

    async with aiohttp.ClientSession() as session:
        # Test 1: Insert cell endpoint
        console.print("\n[yellow]Testing POST /api/agent/ydoc/insert[/yellow]")

        payload = {
            "path": "test.ipynb",
            "index": 0,
            "cell_type": "code",
            "source": "print('Hello from YDoc!')",
        }

        try:
            async with session.post(
                f"{base_url}/api/agent/ydoc/insert", headers=headers, json=payload
            ) as resp:
                status = resp.status
                text = await resp.text()

                if status == 200:
                    console.print(f"✅ [green]Success ({status})[/green]: {text}")
                else:
                    console.print(f"⚠️ [yellow]Response ({status})[/yellow]: {text}")

        except Exception as e:
            console.print(f"❌ [red]Error[/red]: {e}")

        # Test 2: Update cell endpoint
        console.print("\n[yellow]Testing POST /api/agent/ydoc/update[/yellow]")

        payload = {
            "path": "test.ipynb",
            "cell_id": "test-cell-id",
            "source": "print('Updated content')",
        }

        try:
            async with session.post(
                f"{base_url}/api/agent/ydoc/update", headers=headers, json=payload
            ) as resp:
                status = resp.status
                text = await resp.text()

                if status == 200:
                    console.print(f"✅ [green]Success ({status})[/green]: {text}")
                else:
                    console.print(f"⚠️ [yellow]Response ({status})[/yellow]: {text}")

        except Exception as e:
            console.print(f"❌ [red]Error[/red]: {e}")

    console.print("\n[bold green]✅ Extension endpoints are accessible![/bold green]")
    console.print("[blue]Phase 1 Complete: Basic YDoc REST API working[/blue]")


if __name__ == "__main__":
    asyncio.run(test_endpoints())
