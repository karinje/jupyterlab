import { Agent, run } from '@openai/agents';

// Test the OpenAI Agents SDK integration
async function testAgentsSDK() {
  console.log('🧪 Testing OpenAI Agents SDK integration...');

  // Check if API key is available
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    console.log('❌ OPENAI_API_KEY environment variable not set');
    console.log('To test: export OPENAI_API_KEY=your-key-here');
    return;
  }

  try {
    // Create a simple agent
    const agent = new Agent({
      name: 'Test Agent',
      instructions: 'You are a helpful assistant. Respond briefly and clearly.',
      model: 'gpt-4o-mini'
    });

    console.log('✅ Agent created successfully');

    // Test a simple query
    const result = await run(agent, 'Say hello and confirm you can respond');

    console.log('✅ Agent responded successfully:');
    console.log(result.finalOutput);
  } catch (error) {
    console.error('❌ Error testing Agents SDK:', error.message);
  }
}

testAgentsSDK().catch(console.error);
