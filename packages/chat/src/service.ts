import {
  ICellManager,
  IChatMessage,
  IChatService,
  ILLMProvider,
  IMCPServersConfig
} from './tokens';
import { ISignal, Signal } from '@lumino/signaling';
import { UUID } from '@lumino/coreutils';

/**
 * Chat service implementation
 */
export class ChatService implements IChatService {
  private _llmProvider: ILLMProvider;
  private _cellManager: ICellManager;
  private _messages: IChatMessage[] = [];
  private _messageAdded = new Signal<this, IChatMessage>(this);
  private _isDisposed = false;

  constructor(llmProvider: ILLMProvider, cellManager: ICellManager) {
    console.log('ChatService constructor called');
    console.log('LLM Provider:', llmProvider);
    console.log('Cell Manager:', cellManager);

    this._llmProvider = llmProvider;
    this._cellManager = cellManager;
  }

  /**
   * Signal emitted when a new message is added
   */
  get messageAdded(): ISignal<this, IChatMessage> {
    return this._messageAdded;
  }

  /**
   * Send a message and get a response
   */
  async sendMessage(message: string): Promise<void> {
    console.log('🚀 ChatService.sendMessage called with:', message);

    // Add user message
    const userMessage: IChatMessage = {
      id: UUID.uuid4(),
      role: 'user',
      content: message,
      timestamp: new Date()
    };

    this._messages.push(userMessage);
    this._messageAdded.emit(userMessage);

    try {
      console.log('🚀 About to build context...');
      // Get context from notebook cells
      const context = this._buildContext();
      console.log('Context built successfully:', context);

      console.log('About to enhance message with context...');
      // Enhance message with context if it references cells
      const enhancedMessage = this._enhanceMessageWithContext(message, context);
      console.log('Message enhanced successfully:', enhancedMessage);

      console.log('About to send to LLM...');
      // Send to LLM
      const response = await this._llmProvider.sendMessage(
        enhancedMessage,
        context
      );
      console.log('LLM response received:', response);

      // Process any cell operations in the response
      await this._processCellOperations(response);

      // Add assistant message
      const assistantMessage: IChatMessage = {
        id: UUID.uuid4(),
        role: 'assistant',
        content: response,
        timestamp: new Date()
      };

      this._messages.push(assistantMessage);
      this._messageAdded.emit(assistantMessage);
    } catch (error) {
      console.error('Error in ChatService.sendMessage:', error);
      // Add error message
      const errorMessage: IChatMessage = {
        id: UUID.uuid4(),
        role: 'assistant',
        content: `Error: ${error.message}`,
        timestamp: new Date(),
        metadata: { error: true }
      };

      this._messages.push(errorMessage);
      this._messageAdded.emit(errorMessage);
    }
  }

  /**
   * Get chat history
   */
  getHistory(): IChatMessage[] {
    return [...this._messages];
  }

  /**
   * Clear chat history
   */
  clearHistory(): void {
    this._messages = [];
  }

  /**
   * Build context from current notebook state
   */
  private _buildContext(): any {
    console.log('ChatService._buildContext called');
    try {
      console.log('About to call getAllCells...');
      const allCells = this._cellManager.getAllCells();
      console.log('getAllCells returned:', allCells);

      console.log('About to call getCurrentCell...');
      const currentCell = this._cellManager.getCurrentCell();
      console.log('getCurrentCell returned:', currentCell);

      // NEW: active notebook path for backend routing
      const notebookPath = this._cellManager.getActiveNotebookPath?.() || null;

      const context = {
        allCells,
        currentCell,
        totalCells: allCells.length,
        notebook_path: notebookPath
      };

      console.log('_buildContext returning:', context);
      return context;
    } catch (error) {
      console.error('Error in ChatService._buildContext:', error);
      console.warn('Failed to build notebook context:', error);
      // Return safe fallback context
      return {
        allCells: [],
        currentCell: null,
        totalCells: 0,
        notebook_path: null
      };
    }
  }

  /**
   * Enhance message with notebook context
   */
  private _enhanceMessageWithContext(message: string, context: any): string {
    try {
      let enhancedMessage = message;

      // Add context if user is asking about cells
      if (this._mentionsCells(message)) {
        enhancedMessage += '\n\nCurrent notebook state:\n';
        enhancedMessage += `Total cells: ${context.totalCells || 0}\n`;

        if (context.currentCell && context.currentCell.content !== undefined) {
          enhancedMessage += `Current cell (${context.currentCell.index}): ${context.currentCell.type}\n`;
          enhancedMessage += `Content: ${context.currentCell.content}\n`;
        }

        // Add cell contents if specifically requested
        if (
          message.toLowerCase().includes('all cells') ||
          message.toLowerCase().includes('show cells')
        ) {
          enhancedMessage += '\nAll cells:\n';
          if (Array.isArray(context.allCells)) {
            context.allCells.forEach((cell: any, index: number) => {
              if (cell && cell.content !== undefined) {
                enhancedMessage += `Cell ${index} (${
                  cell.type
                }): ${cell.content.substring(0, 200)}${
                  cell.content.length > 200 ? '...' : ''
                }\n`;
              }
            });
          }
        }

        // Pattern matching removed - backend now handles all notebook operations via function tools
      }

      return enhancedMessage;
    } catch (error) {
      console.warn('Failed to enhance message with context:', error);
      return message; // Return original message if context enhancement fails
    }
  }

  /**
   * Check if message mentions cells
   */
  private _mentionsCells(message: string): boolean {
    const cellMentions = [
      'cell',
      'code',
      'execute',
      'run',
      'insert',
      'delete',
      'modify'
    ];
    const lowerMessage = message.toLowerCase();
    return cellMentions.some(mention => lowerMessage.includes(mention));
  }

  // Cell modification detection removed - backend handles all operations via function tools

  /**
   * Process cell operations from LLM response
   * NOTE: Cell operations now handled by backend function tools - no frontend processing needed
   */
  private async _processCellOperations(response: string): Promise<void> {
    // Cell operations now handled by backend function tools - no processing needed
    return;
  }

  // Pattern matching methods removed - backend handles all operations via function tools

  // All pattern matching methods removed - backend handles operations via function tools

  /**
   * Set LLM provider
   */
  setLLMProvider(provider: ILLMProvider): void {
    this._llmProvider = provider;
  }

  /**
   * Get current LLM provider
   */
  getLLMProvider(): ILLMProvider {
    return this._llmProvider;
  }

  /**
   * Test if disposed
   */
  get isDisposed(): boolean {
    return this._isDisposed;
  }

  /**
   * Dispose of resources
   */
  dispose(): void {
    if (this._isDisposed) {
      return;
    }

    this._isDisposed = true;
    this._messages = [];
    Signal.clearData(this);
  }

  /**
   * Configure MCP servers for the LLM provider
   */
  async setMCPServers(mcpServers: IMCPServersConfig): Promise<void> {
    if (this._llmProvider.setMCPServers) {
      console.log('🔧 Configuring MCP servers:', Object.keys(mcpServers));
      await this._llmProvider.setMCPServers(mcpServers);
      console.log('✅ MCP servers configured successfully');
    } else {
      console.log('⚠️ LLM provider does not support MCP servers');
    }
  }

  /**
   * Get number of active MCP servers
   */
  getMCPServerCount(): number {
    return this._llmProvider.getMCPServerCount?.() || 0;
  }
}
