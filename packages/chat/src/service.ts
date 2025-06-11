import { IChatService, IChatMessage, ILLMProvider, ICellManager } from './tokens';
import { Signal, ISignal } from '@lumino/signaling';
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
      const response = await this._llmProvider.sendMessage(enhancedMessage, context);
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
      
      const context = {
        allCells,
        currentCell,
        totalCells: allCells.length
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
        totalCells: 0
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
        if (message.toLowerCase().includes('all cells') || message.toLowerCase().includes('show cells')) {
          enhancedMessage += '\nAll cells:\n';
          if (Array.isArray(context.allCells)) {
            context.allCells.forEach((cell: any, index: number) => {
              if (cell && cell.content !== undefined) {
                enhancedMessage += `Cell ${index} (${cell.type}): ${cell.content.substring(0, 200)}${cell.content.length > 200 ? '...' : ''}\n`;
              }
            });
          }
        }

        // Add instructions for cell operations
        if (this._requestsCellModification(message)) {
          enhancedMessage += '\n\n=== CELL OPERATION INSTRUCTIONS ===\n';
          enhancedMessage += 'When you want to modify notebook cells, use these EXACT commands at the end of your response:\n';
          enhancedMessage += '- To set cell content: SET_CELL <index> <content>\n';
          enhancedMessage += '- To add new cell: ADD_CELL <type> <content>\n';
          enhancedMessage += '- To execute cell: EXECUTE_CELL <index>\n';
          enhancedMessage += '- To delete cell: DELETE_CELL <index>\n';
          enhancedMessage += 'Example: SET_CELL 1 def is_palindrome(s): return s == s[::-1]\n';
        }
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
    const cellMentions = ['cell', 'code', 'execute', 'run', 'insert', 'delete', 'modify'];
    const lowerMessage = message.toLowerCase();
    return cellMentions.some(mention => lowerMessage.includes(mention));
  }

  /**
   * Check if message requests cell modification
   */
  private _requestsCellModification(message: string): boolean {
    const modificationKeywords = ['add', 'create', 'insert', 'modify', 'change', 'set', 'update', 'delete', 'remove', 'write', 'put'];
    const cellKeywords = ['cell', 'code'];
    const lowerMessage = message.toLowerCase();
    
    return modificationKeywords.some(mod => 
      cellKeywords.some(cell => 
        lowerMessage.includes(mod) && lowerMessage.includes(cell)
      )
    );
  }

  /**
   * Process cell operations from LLM response
   */
  private async _processCellOperations(response: string): Promise<void> {
    // Look for cell operation commands in the response
    const operations = this._extractCellOperations(response);
    
    for (const operation of operations) {
      try {
        await this._executeCellOperation(operation);
      } catch (error) {
        console.warn('Failed to execute cell operation:', operation, error);
      }
    }
  }

  /**
   * Extract cell operations from LLM response
   */
  private _extractCellOperations(response: string): any[] {
    const operations: any[] = [];
    console.log('🔍 Extracting cell operations from response:', response);
    
    // Look for our specific command patterns:
    // - SET_CELL <index> <content>
    // - ADD_CELL <type> <content>
    // - EXECUTE_CELL <index>
    // - DELETE_CELL <index>
    
    const patterns = [
      /SET_CELL\s+(\d+)\s+(.+)/gi,
      /ADD_CELL\s+(code|markdown)\s+(.+)/gi,
      /EXECUTE_CELL\s+(\d+)/gi,
      /DELETE_CELL\s+(\d+)/gi
    ];

    patterns.forEach(pattern => {
      let match;
      while ((match = pattern.exec(response)) !== null) {
        const operation = this._parseOperation(match);
        if (operation) {
          console.log('📝 Found operation:', operation);
          operations.push(operation);
        }
      }
    });

    console.log('🎯 Total operations found:', operations.length);
    return operations;
  }

  /**
   * Parse operation from regex match
   */
  private _parseOperation(match: RegExpExecArray): any {
    const fullMatch = match[0].toUpperCase();
    
    if (fullMatch.startsWith('SET_CELL')) {
      return {
        type: 'modify',
        cellIndex: parseInt(match[1]),
        content: match[2].trim()
      };
    } else if (fullMatch.startsWith('ADD_CELL')) {
      return {
        type: 'insert',
        cellType: match[1] as 'code' | 'markdown',
        content: match[2].trim()
      };
    } else if (fullMatch.startsWith('EXECUTE_CELL')) {
      return {
        type: 'execute',
        cellIndex: parseInt(match[1])
      };
    } else if (fullMatch.startsWith('DELETE_CELL')) {
      return {
        type: 'delete',
        cellIndex: parseInt(match[1])
      };
    }
    
    return null;
  }

  /**
   * Execute a cell operation
   */
  private async _executeCellOperation(operation: any): Promise<void> {
    if (!operation) return;

    switch (operation.type) {
      case 'execute':
        await this._cellManager.executeCell(operation.cellIndex);
        break;
      case 'insert':
        this._cellManager.addCell(operation.content, operation.cellType);
        break;
      case 'modify':
        this._cellManager.setCellContent(operation.cellIndex, operation.content);
        break;
      case 'delete':
        this._cellManager.deleteCell(operation.cellIndex);
        break;
    }
  }

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
} 