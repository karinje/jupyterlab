import { Token } from '@lumino/coreutils';
import { IDisposable } from '@lumino/disposable';

/**
 * The chat service token.
 */
export const IChatService = new Token<IChatService>('@jupyterlab/chat:IChatService');

/**
 * The LLM provider service token.
 */
export const ILLMProvider = new Token<ILLMProvider>('@jupyterlab/chat:ILLMProvider');

/**
 * The cell manager service token.
 */
export const ICellManager = new Token<ICellManager>('@jupyterlab/chat:ICellManager');

/**
 * Interface for LLM providers
 */
export interface ILLMProvider {
  /**
   * Send a message to the LLM and get a response
   */
  sendMessage(message: string, context?: any): Promise<string>;

  /**
   * Get available models
   */
  getModels(): Promise<string[]>;

  /**
   * Set the current model
   */
  setModel(model: string): void;

  /**
   * Get the current model
   */
  getCurrentModel(): string;
}

/**
 * Interface for managing notebook cells
 */
export interface ICellManager {
  /**
   * Get the content of a specific cell
   */
  getCellContent(cellIndex: number): string | null;

  /**
   * Set the content of a specific cell
   */
  setCellContent(cellIndex: number, content: string): void;

  /**
   * Insert a new cell at the specified index
   */
  insertCell(cellIndex: number, content: string, cellType: 'code' | 'markdown'): void;

  /**
   * Execute a specific cell
   */
  executeCell(cellIndex: number): Promise<void>;

  /**
   * Get all cells content
   */
  getAllCells(): Array<{ content: string; type: string; index: number }>;

  /**
   * Get the currently active notebook
   */
  getActiveNotebook(): any;

  /**
   * Get cell at current cursor position
   */
  getCurrentCell(): { content: string; type: string; index: number } | null;

  /**
   * Add a new cell at the end
   */
  addCell(content: string, cellType?: 'code' | 'markdown'): void;

  /**
   * Delete a cell at the specified index
   */
  deleteCell(cellIndex: number): void;
}

/**
 * Interface for chat messages
 */
export interface IChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  metadata?: any;
}

/**
 * Interface for chat service
 */
export interface IChatService extends IDisposable {
  /**
   * Send a message and get a response
   */
  sendMessage(message: string): Promise<void>;

  /**
   * Get chat history
   */
  getHistory(): IChatMessage[];

  /**
   * Clear chat history
   */
  clearHistory(): void;

  /**
   * Signal emitted when a new message is added
   */
  messageAdded: any;

  /**
   * Set LLM provider
   */
  setLLMProvider(provider: ILLMProvider): void;

  /**
   * Get current LLM provider
   */
  getLLMProvider(): ILLMProvider;
} 