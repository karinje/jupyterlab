import { ILLMProvider, IMCPServersConfig } from './tokens';
import { ServerConnection } from '@jupyterlab/services';
import { getProviderForModel } from './models';

/**
 * Base LLM Provider implementation
 */
export abstract class BaseLLMProvider implements ILLMProvider {
  protected _currentModel: string = '';

  abstract sendMessage(message: string, context?: any, signal?: AbortSignal): Promise<string>;
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

  async sendMessage(message: string, context?: any, signal?: AbortSignal): Promise<string> {
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
            mcpServers: this.mcpServers, // MCP servers from settings
            context: context,
            chat_mode: 'langgraph' // Add chat mode selection
          }),
          signal: signal  // Add abort signal support
        },
        settings
      );

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Server error: ${response.status} ${errorText}`);
      }

      const data = await response.json();
      return data; // Return full object with thread_id, not just data.response
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
   * Get selected provider (auto-inferred from model selection)
   */
  private _getSelectedProvider(): string {
    const modelSelect = document.querySelector(
      '#chat-model'
    ) as HTMLSelectElement;
    
    // Get provider from dataset (set by model selection event handler)
    const provider = modelSelect?.dataset?.provider;
    if (provider) {
      return provider;
    }
    
    // Fallback: infer from current model using configuration
    const selectedModel = this._getSelectedModel();
    return getProviderForModel(selectedModel);
  }
}

/**
 * Claude (Anthropic) provider implementation
 */
export class ClaudeProvider extends BaseLLMProvider {
  constructor(apiKey?: string) {
    super();
    // API key not stored - read from server-side settings
    this._currentModel = 'claude-3-sonnet-20240229';
  }

  setApiKey(apiKey: string): void {
    // API key not stored - read from server-side settings
  }

  async sendMessage(message: string, context?: any, signal?: AbortSignal): Promise<string> {
    // All providers now go through the backend agent (no direct API calls)
    const settings = ServerConnection.makeSettings();
    const requestUrl = new URL('/api/chat/openai', settings.baseUrl).href;

    const response = await ServerConnection.makeRequest(
      requestUrl,
      {
        method: 'POST',
        body: JSON.stringify({
          message: message,
          model: this._currentModel,
          provider: 'claude',
          context: context,
          chat_mode: 'langgraph'
        }),
        signal: signal
      },
      settings
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Server error: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    return data; // Return full object with thread_id, not just data.response
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
  constructor(baseUrl?: string) {
    super();
    // Base URL not stored - read from server-side settings
    this._currentModel = 'llama2';
  }

  setBaseUrl(baseUrl: string): void {
    // Base URL not stored - read from server-side settings
  }

  async sendMessage(message: string, context?: any, signal?: AbortSignal): Promise<string> {
    // All providers now go through the backend agent (no direct API calls)
    const settings = ServerConnection.makeSettings();
    const requestUrl = new URL('/api/chat/openai', settings.baseUrl).href;

    const response = await ServerConnection.makeRequest(
      requestUrl,
      {
        method: 'POST',
        body: JSON.stringify({
          message: message,
          model: this._currentModel,
          provider: 'ollama',
          context: context,
          chat_mode: 'langgraph'
        }),
        signal: signal
      },
      settings
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Server error: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    return data; // Return full object with thread_id, not just data.response
  }

  async getModels(): Promise<string[]> {
    return ['llama2'];
  }
}
