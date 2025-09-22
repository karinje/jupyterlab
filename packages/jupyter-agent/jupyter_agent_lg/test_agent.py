"""
Test script for LangGraph Data Analysis Agent

Run this to verify the agent implementation works correctly.
"""

import os
import logging
from .agent import JupyterAgent

# Set up proper logging using simplified config
try:
    from jupyter_tools_bridge.logging_config import get_logger
    logger = get_logger()
except ImportError:
    # Fallback if centralized logging not available
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(filename)s:%(lineno)d] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger("jupyterlab")


async def test_agent():
    """Test the LangGraph agent with a simple request"""

    # Configuration
    server_url = "http://127.0.0.1:8890"  # Default JupyterLab port
    token = "your-jupyter-token-here"  # Replace with actual token
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_api_key:
        logger.error("❌ OPENAI_API_KEY environment variable not set")
        return

    try:
        # Create agent
        agent = JupyterAgent(
            server_url=server_url, token=token, openai_api_key=openai_api_key
        )

        # Test request
        request = "Create a simple data analysis with a plot"
        notebook_path = "test_notebook.ipynb"
        conversation_history = []

        logger.info(f"🚀 Testing LangGraph agent with request: {request}")

        # Process request
        result = await agent.process_request(
            request=request,
            notebook_path=notebook_path,
            conversation_history=conversation_history,
            model="gpt-4o-mini",
            provider="openai",
        )

        logger.info("✅ Agent completed successfully!")
        logger.info(f"📊 Result: {result}")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


def test_state_management():
    """Test state management components"""
    logger.info("🧪 Testing state management...")

    # Test 1: Initial state creation
    from .state import create_initial_state

    try:
        state = create_initial_state(
            original_request="test request",
            notebook_path="test.ipynb",
            conversation_history=[],
            model="gpt-4o-mini",
            provider="openai",
        )
        logger.info(f"✅ Initial state created: {state['original_request']}")
    except Exception as e:
        logger.error(f"❌ State creation failed: {e}")

    # Test 2: Plan step creation
    from .state import PlanStep

    try:
        step = PlanStep(title="Test Step", description="Test description", completed=False)
        logger.info(f"✅ Plan step created: {step.title}")
    except Exception as e:
        logger.error(f"❌ Plan step creation failed: {e}")

    # Test 3: Plan serialization
    from .state import serialize_plan_steps, deserialize_plan_steps

    try:
        steps = [PlanStep(title="Step 1", description="First step", completed=False)]
        serialized = serialize_plan_steps(steps)
        deserialized = deserialize_plan_steps(serialized)
        logger.info(f"✅ Plan serialization works: {deserialized[0].title}")
    except Exception as e:
        logger.error(f"❌ Plan serialization failed: {e}")





if __name__ == "__main__":
    logger.info("🤖 LangGraph Agent Test Suite")
    logger.info("=" * 50)

    # Run synchronous tests
    test_state_management()

    logger.info("\n🚀 Running agent integration test...")
    logger.info("⚠️ Make sure JupyterLab is running on port 8890")
    logger.info("⚠️ Update the token variable in this script")

    # Uncomment to run full agent test
    # asyncio.run(test_agent())

    logger.info("\n✅ Test suite completed!")
    logger.info("\nTo run the full agent test:")
    logger.info("1. Start JupyterLab: jupyter lab --port=8890")
    logger.info("2. Set OPENAI_API_KEY environment variable")
    logger.info("3. Update the token in this script")
    logger.info("4. Uncomment the asyncio.run(test_agent()) line")
