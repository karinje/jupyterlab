import { ILLMProvider, IMCPServersConfig } from './tokens';
import { ServerConnection } from '@jupyterlab/services';

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

  async setMCPServers?(mcpServers: IMCPServersConfig): Promise<void> {
    // Default implementation does nothing
  }

  getMCPServerCount?(): number {
    return 0;
  }
}

/**
 * OpenAI provider implementation - ALL requests go through server-side API
 */
export class OpenAIProvider extends BaseLLMProvider {
  private mcpServers: IMCPServersConfig = {};

  constructor(apiKey: string) {
    super();
    // API key not stored - read from server-side settings
  }

  async setMCPServers(mcpServers: IMCPServersConfig): Promise<void> {
    console.log('🔧 Setting MCP servers:', Object.keys(mcpServers));
    this.mcpServers = mcpServers;
  }

  getMCPServerCount(): number {
    return Object.keys(this.mcpServers).length;
  }

  async sendMessage(message: string, context?: any): Promise<string> {
    try {
      console.log(
        '🚀 Sending to server extension with MCP servers:',
        Object.keys(this.mcpServers)
      );

      // Use JupyterLab's ServerConnection which handles CSRF automatically
      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/openai', settings.baseUrl).href;

      const response = await ServerConnection.makeRequest(
        requestUrl,
        {
          method: 'POST',
          body: JSON.stringify({
            message: message,
            model: this._getSelectedModel(), // Use selected model from dropdown
            provider: this._getSelectedProvider(), // Add provider selection
            mcpServers: {}, // Temporarily disable MCP to isolate LangGraph
            context: context,
            chat_mode: 'langgraph' // Add chat mode selection
          })
        },
        settings
      );

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Server error: ${response.status} ${errorText}`);
      }

      const data = await response.json();
      return data.response || 'No response received';
    } catch (error) {
      console.error('Error in OpenAI provider:', error);
      throw error;
    }
  }

  async getModels(): Promise<string[]> {
    return [
      'gpt-4o',
      'gpt-4o-mini',
      'o1-preview',
      'o1-mini',
      'gpt-4-turbo',
      'gpt-3.5-turbo'
    ];
  }

  /**
   * Get selected model from UI dropdown
   */
  private _getSelectedModel(): string {
    const modelSelect = document.querySelector(
      '#chat-model'
    ) as HTMLSelectElement;
    return modelSelect?.value || this._currentModel || 'gpt-4o-mini';
  }

  /**
   * Get selected provider from UI dropdown
   */
  private _getSelectedProvider(): string {
    const providerSelect = document.querySelector(
      '#chat-provider'
    ) as HTMLSelectElement;
    return providerSelect?.value || 'openai';
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
      'claude-3-5-sonnet-20241022',
      'claude-3-opus-20240229',
      'claude-3-sonnet-20240229',
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
