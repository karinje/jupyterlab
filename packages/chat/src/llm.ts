import { ILLMProvider } from './tokens';

/**
 * Base LLM Provider implementation
 */
export abstract class BaseLLMProvider implements ILLMProvider {
  protected _currentModel: string = '';

  abstract sendMessage(message: string, context?: any): Promise<string>;
  abstract getModels(): Promise<string[]>;

  setModel(model: string): void {
    this._currentModel = model;
  }

  getCurrentModel(): string {
    return this._currentModel;
  }
}

/**
 * OpenAI provider implementation
 */
export class OpenAIProvider extends BaseLLMProvider {
  private _apiKey: string = '';
  private _baseUrl: string = 'https://api.openai.com/v1';

  constructor(apiKey?: string) {
    super();
    if (apiKey) {
      this._apiKey = apiKey;
    }
    this._currentModel = 'gpt-3.5-turbo';
  }

  setApiKey(apiKey: string): void {
    this._apiKey = apiKey;
  }

  async sendMessage(message: string, context?: any): Promise<string> {
    console.log('🔥 OpenAI sendMessage called with message:', message);
    console.log('🔥 OpenAI API key exists:', !!this._apiKey);

    if (!this._apiKey) {
      console.log('🔥 No API key, returning fallback message');
      return (
        "I'm a JupyterLab assistant, but I need an OpenAI API key to be configured to provide intelligent responses. You can set this in the settings. For now, I can confirm that I received your message: " +
        message
      );
    }

    try {
      const response = await fetch(`${this._baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this._apiKey}`
        },
        body: JSON.stringify({
          model: this._currentModel,
          messages: [
            {
              role: 'system',
              content: `You are a helpful assistant integrated into JupyterLab. You can help with code, analysis, and notebook manipulation. When you need to interact with cells, you can reference them by index (e.g., "cell 0", "cell 1").

IMPORTANT: When a user asks for a plan, task breakdown, or steps to accomplish something, format your response using cards. Each card should follow this exact format:
[CARD:Title|Description]

For example:
[CARD:Research the topic|Gather information about the subject from reliable sources]
[CARD:Create outline|Structure the main points and subtopics]
[CARD:Write first draft|Begin writing the content based on the outline]

For regular questions that don't require planning, respond normally.`
            },
            {
              role: 'user',
              content: message
            }
          ],
          max_tokens: 2000
        })
      });

      if (!response.ok) {
        throw new Error(
          `OpenAI API error: ${response.status} ${response.statusText}`
        );
      }

      const data = await response.json();

      // Much more defensive handling
      if (!data) {
        throw new Error('OpenAI API returned null/undefined response');
      }

      if (!data.choices) {
        throw new Error('OpenAI API response missing choices array');
      }

      if (!Array.isArray(data.choices)) {
        throw new Error('OpenAI API choices is not an array');
      }

      if (data.choices.length === 0) {
        throw new Error('OpenAI API returned empty choices array');
      }

      const choice = data.choices[0];
      if (!choice) {
        throw new Error('OpenAI API first choice is null/undefined');
      }

      if (!choice.message) {
        throw new Error('OpenAI API choice missing message');
      }

      if (
        choice.message.content === undefined ||
        choice.message.content === null
      ) {
        throw new Error('OpenAI API message content is null/undefined');
      }

      return String(choice.message.content || '');
    } catch (error) {
      if (error.message && error.message.includes('OpenAI API')) {
        throw error; // Re-throw our custom errors
      }
      throw new Error(`OpenAI API request failed: ${error.message}`);
    }
  }

  async getModels(): Promise<string[]> {
    return ['gpt-3.5-turbo', 'gpt-4', 'gpt-4-turbo-preview'];
  }
}

/**
 * Claude (Anthropic) provider implementation
 */
export class ClaudeProvider extends BaseLLMProvider {
  private _apiKey: string = '';
  private _baseUrl: string = 'https://api.anthropic.com/v1';

  constructor(apiKey?: string) {
    super();
    if (apiKey) {
      this._apiKey = apiKey;
    }
    this._currentModel = 'claude-3-sonnet-20240229';
  }

  setApiKey(apiKey: string): void {
    this._apiKey = apiKey;
  }

  async sendMessage(message: string, context?: any): Promise<string> {
    if (!this._apiKey) {
      throw new Error('Claude API key not set');
    }

    const response = await fetch(`${this._baseUrl}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this._apiKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: this._currentModel,
        max_tokens: 2000,
        system: `You are a helpful assistant integrated into JupyterLab. You can help with code, analysis, and notebook manipulation. When you need to interact with cells, you can reference them by index (e.g., "cell 0", "cell 1").

IMPORTANT: When a user asks for a plan, task breakdown, or steps to accomplish something, format your response using cards. Each card should follow this exact format:
[CARD:Title|Description]

For example:
[CARD:Research the topic|Gather information about the subject from reliable sources]
[CARD:Create outline|Structure the main points and subtopics]
[CARD:Write first draft|Begin writing the content based on the outline]

For regular questions that don't require planning, respond normally.`,
        messages: [
          {
            role: 'user',
            content: message
          }
        ]
      })
    });

    if (!response.ok) {
      throw new Error(`Claude API error: ${response.statusText}`);
    }

    const data = await response.json();

    // Add proper null checks for Claude response
    if (
      !data ||
      !data.content ||
      !Array.isArray(data.content) ||
      data.content.length === 0
    ) {
      throw new Error('Invalid response from Claude API: no content returned');
    }

    const content = data.content[0];
    if (!content || typeof content.text !== 'string') {
      throw new Error(
        'Invalid response from Claude API: invalid content format'
      );
    }

    return content.text;
  }

  async getModels(): Promise<string[]> {
    return [
      'claude-3-sonnet-20240229',
      'claude-3-opus-20240229',
      'claude-3-haiku-20240307'
    ];
  }
}

/**
 * Local model provider (for Ollama, etc.)
 */
export class LocalProvider extends BaseLLMProvider {
  private _baseUrl: string = 'http://localhost:11434';

  constructor(baseUrl?: string) {
    super();
    if (baseUrl) {
      this._baseUrl = baseUrl;
    }
    this._currentModel = 'llama2';
  }

  setBaseUrl(baseUrl: string): void {
    this._baseUrl = baseUrl;
  }

  async sendMessage(message: string, context?: any): Promise<string> {
    const response = await fetch(`${this._baseUrl}/api/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: this._currentModel,
        prompt: `You are a helpful assistant integrated into JupyterLab. You can help with code, analysis, and notebook manipulation.

IMPORTANT: When a user asks for a plan, task breakdown, or steps to accomplish something, format your response using cards. Each card should follow this exact format:
[CARD:Title|Description]

For example:
[CARD:Research the topic|Gather information about the subject from reliable sources]
[CARD:Create outline|Structure the main points and subtopics]
[CARD:Write first draft|Begin writing the content based on the outline]

For regular questions that don't require planning, respond normally.

User: ${message}

Assistant: `
      })
    });

    if (!response.ok) {
      throw new Error(`Local model error: ${response.statusText}`);
    }

    const data = await response.json();
    return data.result;
  }

  async getModels(): Promise<string[]> {
    return ['llama2'];
  }
}
