#!/usr/bin/env python3
"""
Test script for JupyterAgent tools

This script tests the high-level agent tools to ensure they work
before integrating with LLM agents.
"""

import asyncio
from jupyter_agent_bridge.tools import JupyterAgent


async def test_agent_tools():
    """Test the JupyterAgent tools"""

    print("🤖 Testing JupyterAgent Tools")
    print("=" * 50)

    # Configuration
    server_url = "http://127.0.0.1:8890"
    token = "d0e4b88278aa22aef04a73accbe7deafd8484a042a5830a2"  # Current token from dev mode JupyterLab
    notebook_path = "Untitled.ipynb"

    # Create agent
    agent = JupyterAgent(server_url, token)

    # Test 1: Primary tool - insert_code_and_execute
    print("\n🔥 TEST 1: insert_code_and_execute (Primary Tool)")
    print("-" * 40)

    test_code = """
import numpy as np
import matplotlib.pyplot as plt

# Create sample data
x = np.linspace(0, 2*np.pi, 100)
y = np.sin(x)

# Create plot
plt.figure(figsize=(8, 6))
plt.plot(x, y, 'b-', linewidth=2, label='sin(x)')
plt.title('Agent-Generated Sine Wave')
plt.xlabel('x')
plt.ylabel('sin(x)')
plt.legend()
plt.grid(True)
plt.show()

print("✅ Plot generated successfully!")
"Agent execution completed"  # This creates execute_result output
"""

    result = await agent.insert_code_and_execute(notebook_path, test_code)

    print("📊 Result:")
    print(f"   Cell ID: {result.get('cell_id', 'N/A')}")
    print(f"   Status: {result.get('status', 'N/A')}")
    print(f"   Outputs: {len(result.get('outputs', []))} items")
    print(f"   Execution Count: {result.get('execution_count', 'N/A')}")

    if result.get("status") == "error":
        print(f"   ❌ Error: {result.get('error', 'Unknown error')}")
    else:
        print("   ✅ Success!")

        # Show output types
        for i, output in enumerate(result.get("outputs", [])):
            output_type = output.get("output_type", "unknown")
            print(f"      Output {i + 1}: {output_type}")
            if output_type == "display_data" and "image/png" in output.get("data", {}):
                print("         📊 Contains PNG image data")

    # Test 2: Insert markdown cell
    print("\n📝 TEST 2: insert_markdown")
    print("-" * 40)

    markdown_content = """
# Agent Test Results

This markdown was inserted by the JupyterAgent!

## What was tested:
- ✅ Code execution with matplotlib
- ✅ Rich output capture (plots, text)
- ✅ Real-time notebook updates
- ✅ UUID-based cell targeting

The agent successfully demonstrated full parity with native JupyterLab execution.
"""

    markdown_cell_id = await agent.insert_markdown(notebook_path, markdown_content)
    print(f"📝 Markdown cell inserted: {markdown_cell_id}")

    # Test 3: Get notebook content
    print("\n📋 TEST 3: get_cell_content")
    print("-" * 40)

    notebook_data = await agent.get_cell_content(notebook_path)
    cells = notebook_data.get("cells", [])

    print(f"📋 Notebook '{notebook_path}' contains {len(cells)} cells:")
    for i, cell in enumerate(cells):
        cell_type = cell.get("cell_type", "unknown")
        cell_id = cell.get("id", "no-id")[:8]
        has_outputs = len(cell.get("outputs", [])) > 0
        exec_count = cell.get("execution_count", "None")

        print(
            f"   Cell {i + 1}: {cell_type} | ID: {cell_id}... | Outputs: {has_outputs} | Count: {exec_count}"
        )

    # Test 4: Same agent instance (should show execution_count=2)
    print("\n🔧 TEST 4: Second execution with same agent (should be count=2)")
    print("-" * 40)

    simple_code = """
print("🔧 Testing execution count sequence")
result = 42 + 8
print(f"Calculation result: {result}")
print(f"This should be execution count 2!")
result
"""

    second_result = await agent.insert_code_and_execute(notebook_path, simple_code)

    print("🔧 Second execution result:")
    print(f"   Status: {second_result.get('status', 'N/A')}")
    print(
        f"   Execution Count: {second_result.get('execution_count', 'N/A')} (should be 2)"
    )
    print(f"   Outputs: {len(second_result.get('outputs', []))} items")

    print("\n" + "=" * 50)
    print("✅ All tests completed!")
    print(f"📝 Check notebook '{notebook_path}' to see the results")
    print("=" * 50)


async def test_error_handling():
    """Test error handling"""
    print("\n🚨 Testing Error Handling")
    print("-" * 30)

    agent = JupyterAgent("http://127.0.0.1:8890", "invalid-token")

    result = await agent.insert_code_and_execute("test.ipynb", "print('test')")

    if result.get("status") == "error":
        print(f"✅ Error handling works: {result.get('error', 'Unknown')[:50]}...")
    else:
        print("❌ Error handling failed - should have failed with invalid token")


if __name__ == "__main__":
    print("🧪 JupyterAgent Tools Test Suite")
    print("Make sure JupyterLab is running on http://127.0.0.1:8890")
    print("Update the token in this script before running!")

    try:
        asyncio.run(test_agent_tools())
        asyncio.run(test_error_handling())
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
