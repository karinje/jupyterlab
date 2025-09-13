"""
Test script for LangGraph Data Analysis Agent

Run this to verify the agent implementation works correctly.
"""

import os
import logging
from .agent import DataAnalysisAgent

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_agent():
    """Test the LangGraph agent with a simple request"""

    # Configuration
    server_url = "http://127.0.0.1:8890"  # Default JupyterLab port
    token = "your-jupyter-token-here"  # Replace with actual token
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_api_key:
        print("❌ OPENAI_API_KEY environment variable not set")
        return

    try:
        # Create agent
        agent = DataAnalysisAgent(
            server_url=server_url, token=token, openai_api_key=openai_api_key
        )

        # Test request
        request = "Create a simple data analysis with a plot"
        notebook_path = "test_notebook.ipynb"
        conversation_history = []

        print(f"🚀 Testing LangGraph agent with request: {request}")

        # Process request
        result = await agent.process_request(
            request=request,
            notebook_path=notebook_path,
            conversation_history=conversation_history,
            model="gpt-4o-mini",
            provider="openai",
        )

        print("✅ Agent completed successfully!")
        print(f"📊 Result: {result}")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


def test_state_management():
    """Test state management components"""
    from .state import StateManager, PlanStep

    print("🧪 Testing state management...")

    # Test state manager
    state_manager = StateManager()

    # Create initial state
    state = state_manager.create_initial_state(
        request="Test request",
        notebook_path="test.ipynb",
        conversation_history=[],
        model="gpt-4o",
        provider="openai",
    )

    print(f"✅ Initial state created: {state['original_request']}")

    # Test plan step
    step = PlanStep(
        step_id="", title="Test Step", description="A test step for validation"
    )

    print(f"✅ Plan step created: {step.title}")

    # Test serialization
    serialized = state_manager.serialize_plan([step])
    deserialized = state_manager.deserialize_plan(serialized)

    print(f"✅ Plan serialization works: {deserialized[0].title}")


def test_llm_router():
    """Test LLM router components"""
    from .llm import LLMRouter, OpenAILLM

    print("🧪 Testing LLM router...")

    router = LLMRouter()

    # Test provider registration
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        openai_llm = OpenAILLM(openai_api_key, "gpt-4o-mini")
        router.register_provider("openai", openai_llm)

        providers = router.get_available_providers()
        print(f"✅ Providers registered: {providers}")
    else:
        print("⚠️ Skipping LLM tests (no API key)")


if __name__ == "__main__":
    print("🤖 LangGraph Agent Test Suite")
    print("=" * 50)

    # Run synchronous tests
    test_state_management()
    test_llm_router()

    # Run async test
    print("\n🚀 Running agent integration test...")
    print("⚠️ Make sure JupyterLab is running on port 8890")
    print("⚠️ Update the token variable in this script")

    # Uncomment to run full agent test
    # asyncio.run(test_agent())

    print("\n✅ Test suite completed!")
    print("\nTo run the full agent test:")
    print("1. Start JupyterLab: jupyter lab --port=8890")
    print("2. Set OPENAI_API_KEY environment variable")
    print("3. Update the token in this script")
    print("4. Uncomment the asyncio.run(test_agent()) line")
