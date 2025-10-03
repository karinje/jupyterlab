import {
  ICellManager,
  IChatMessage,
  IChatService,
  ILLMProvider,
  IMCPServersConfig
} from './tokens';
import { ISignal, Signal } from '@lumino/signaling';
import { UUID } from '@lumino/coreutils';
import { ServerConnection } from '@jupyterlab/services';
import { URLExt } from '@jupyterlab/coreutils';

/**
 * Chat service implementation
 */
export class ChatService implements IChatService {
  private _llmProvider: ILLMProvider;
  private _cellManager: ICellManager;
  private _messages: IChatMessage[] = [];
  private _messageAdded = new Signal<this, IChatMessage>(this);
  private _planReceived = new Signal<this, any>(this);
  private _isDisposed = false;
  private _ws: WebSocket | null = null;
  private _wsPath: string | null = null;
  private _wsConnId: string | null = null;
  private _reconnectTimer: any = null;
  private _reconnectAttempts = 0;
  private _selectedThreadId: string | null = null;
  private _currentRequest: Promise<any> | null = null; // Track current request for cancellation
  private _currentAbortController: AbortController | null = null; // For actual request cancellation

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

  get planReceived(): ISignal<this, any> {
    return this._planReceived;
  }

  /**
   * Send a message and get a response
   */
  async sendMessage(message: string): Promise<void> {
    console.log('🚀 ChatService.sendMessage called with:', message);

    // Cancel any current request before sending new message (ChatGPT-like behavior)
    // Use 'interrupt' intent to preserve thread continuity
    await this._cancelCurrentRequest('interrupt');

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
      // Build minimal context (only notebook_path for backend routing)
      const context = await this._buildContext();

      console.log('About to send to LLM...');
      // Create abort controller for this request
      this._currentAbortController = new AbortController();

      // Send to LLM (track for cancellation)
      this._currentRequest = this._llmProvider.sendMessage(
        message,
        context,
        this._currentAbortController.signal
      );
      const response = await this._currentRequest;
      this._currentRequest = null;
      this._currentAbortController = null;
      console.log('LLM response received:', response);

      // Frontend manages all thread IDs - no need to extract from response
      console.log(
        '✅ Message sent successfully with thread ID:',
        this._selectedThreadId
      );

      // Do not add assistant message from HTTP response; rely solely on WS stream
      console.log('[CHAT] HTTP return ignored; waiting for WS broadcast');
    } catch (error) {
      this._currentRequest = null;
      this._currentAbortController = null;

      // Check if this was an interruption/cancellation
      if (
        error &&
        (error.name === 'AbortError' || error.message?.includes('aborted'))
      ) {
        // Add interruption message
        const interruptMessage: IChatMessage = {
          id: UUID.uuid4(),
          role: 'assistant',
          content: 'Interrupting agent execution...',
          timestamp: new Date(),
          metadata: {
            messageType: 'interruption', // Add messageType metadata
            interruption: true
          }
        };
        this._messages.push(interruptMessage);
        this._messageAdded.emit(interruptMessage);
      } else {
        console.error('Error sending message:', error);
        // Add error message for other types of errors
        const errorMessage: IChatMessage = {
          id: UUID.uuid4(),
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date(),
          metadata: {
            messageType: 'error', // Add messageType metadata
            error: true
          }
        };
        this._messages.push(errorMessage);
        this._messageAdded.emit(errorMessage);
      }
    }
  }

  private async _cancelCurrentRequest(
    intent: 'interrupt' | 'switch' | 'notebook_switch' = 'interrupt',
    newThreadId?: string
  ): Promise<void> {
    console.log(
      `🛑 Cancelling current request with intent: ${intent}${
        newThreadId ? `, newThreadId: ${newThreadId}` : ''
      }`
    );

    if (this._currentRequest && this._currentAbortController) {
      console.log('🛑 Aborting HTTP request');
      // Actually abort the HTTP request
      this._currentAbortController.abort();
      this._currentRequest = null;
      this._currentAbortController = null;
    }

    // Send cancellation signal to backend to stop agent execution
    try {
      console.log('🛑 Sending cancellation signal to backend');
      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/cancel', settings.baseUrl).href;

      await ServerConnection.makeRequest(
        requestUrl,
        {
          method: 'POST',
          body: JSON.stringify({})
        },
        settings
      );
      console.log('✅ Cancellation signal sent successfully');
    } catch (error) {
      console.warn('⚠️ Failed to send cancellation signal:', error);
      // Don't throw - cancellation should be best-effort
    }

    // Handle thread ID based on intent
    switch (intent) {
      case 'interrupt':
        // Keep existing _selectedThreadId to preserve conversation continuity
        console.log(
          `📝 Preserving thread ID for interruption: ${this._selectedThreadId}`
        );
        break;
      case 'switch':
        // Change to new thread ID for thread switching
        if (newThreadId) {
          console.log(
            `🔄 Switching thread ID from ${this._selectedThreadId} to ${newThreadId}`
          );
          this._selectedThreadId = newThreadId;
        }
        break;
      case 'notebook_switch':
        // Thread ID will be handled separately in clearUIForNotebookSwitch
        console.log(
          `📚 Notebook switch - thread ID will be loaded from new notebook metadata`
        );
        break;
    }
  }

  /**
   * Get chat history
   */
  getHistory(): IChatMessage[] {
    return [...this._messages];
  }

  /**
   * Load conversation history from server for current notebook
   */
  async loadConversationHistory(
    notebookPath: string,
    clearUI: boolean = false
  ): Promise<void> {
    try {
      console.log(
        '🔄 Loading conversation history for:',
        notebookPath,
        clearUI ? '(with UI clear)' : ''
      );

      // If this is a notebook switch, clear the UI first
      if (clearUI) {
        await this.clearUIForNotebookSwitch(notebookPath);
      }

      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/threads', settings.baseUrl).href;

      const response = await ServerConnection.makeRequest(
        `${requestUrl}?notebook_path=${encodeURIComponent(notebookPath)}`,
        {
          method: 'GET'
        },
        settings
      );

      if (!response.ok) {
        console.warn('Failed to load conversation history:', response.status);
        return;
      }

      const data = await response.json();
      const allThreads = data.threads || {};
      const threadCount = Object.keys(allThreads).length;

      console.log(
        `📚 Frontend: Found ${threadCount} conversation threads for ${notebookPath}`
      );

      // Find the most recent thread based on last_updated timestamp
      let mostRecentThreadId = data.active_thread;
      let mostRecentTime = 0;

      if (threadCount > 0) {
        for (const [tid, threadData] of Object.entries(allThreads)) {
          const messageCount = (threadData as any).messages?.length || 0;
          const lastUpdated = (threadData as any).last_updated;
          const updateTime = lastUpdated ? new Date(lastUpdated).getTime() : 0;

          console.log(
            `  📝 Frontend: Thread ${tid.substring(
              0,
              8
            )}... has ${messageCount} messages (updated: ${lastUpdated})`
          );

          if (updateTime > mostRecentTime) {
            mostRecentTime = updateTime;
            mostRecentThreadId = tid;
          }
        }
      }

      console.log(
        `🎯 Frontend: Most recent thread ID: ${mostRecentThreadId} (was active: ${data.active_thread})`
      );
      const activeThreadId = mostRecentThreadId;

      if (activeThreadId && data.threads && data.threads[activeThreadId]) {
        const threadMessages = data.threads[activeThreadId].messages || [];

        console.log(
          `✅ Frontend: Loading ${threadMessages.length} messages from active thread`
        );

        // Clear current messages and load from history
        this._messages = [];

        // Convert server messages to chat messages
        for (const msg of threadMessages) {
          const chatMessage: IChatMessage = {
            id: UUID.uuid4(),
            role: msg.role as 'user' | 'assistant',
            content: msg.content,
            timestamp: new Date(msg.timestamp || Date.now()),
            metadata: { fromHistory: true }
          };
          this._messages.push(chatMessage);
          this._messageAdded.emit(chatMessage);
        }

        console.log(
          `✅ Frontend: Successfully loaded ${threadMessages.length} messages into chat UI`
        );

        // Set the thread ID for future messages
        this._selectedThreadId = activeThreadId;
        console.log(
          `🎯 Frontend: Set selected thread ID to: ${this._selectedThreadId}`
        );

        // Log first and last messages for verification
        if (threadMessages.length > 0) {
          const firstMsg = threadMessages[0];
          const lastMsg = threadMessages[threadMessages.length - 1];
          console.log(
            `  📖 Frontend: First message: ${
              firstMsg.role
            } - ${firstMsg.content.substring(0, 100)}...`
          );
          if (threadMessages.length > 1) {
            console.log(
              `  📖 Frontend: Last message: ${
                lastMsg.role
              } - ${lastMsg.content.substring(0, 100)}...`
            );
          }
        }
      } else {
        console.log(
          '📝 Frontend: No active thread found, will create new thread on first message'
        );
        // Don't set _selectedThreadId here - let _buildContext() generate it when needed
      }
    } catch (error) {
      console.error('Error loading conversation history:', error);
    }
  }

  /**
   * Clear UI and show switching message for notebook transitions
   */
  async clearUIForNotebookSwitch(notebookPath: string): Promise<void> {
    console.log('🔄 Clearing UI for notebook switch to:', notebookPath);

    // Cancel any current request before switching - use 'notebook_switch' intent
    await this._cancelCurrentRequest('notebook_switch');

    // Clear current messages completely
    this._messages = [];

    // Emit a special signal to clear the UI first
    this._messageAdded.emit({
      id: 'CLEAR_MESSAGES',
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      metadata: { action: 'clear' }
    });

    // Show switching message
    const notebookName = notebookPath.split('/').pop() || notebookPath;
    this._messageAdded.emit({
      id: 'NOTEBOOK_SWITCH',
      role: 'assistant',
      content: `🔄 Switching to notebook: ${notebookName}...`,
      timestamp: new Date(),
      metadata: {
        action: 'notebook_switch',
        notebookPath: notebookPath,
        temporary: true
      }
    });

    // Load the active thread for the NEW notebook or create new thread ID
    try {
      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/threads', settings.baseUrl).href;

      const response = await ServerConnection.makeRequest(
        `${requestUrl}?notebook_path=${encodeURIComponent(notebookPath)}`,
        { method: 'GET' },
        settings
      );

      if (response.ok) {
        const data = await response.json();
        const activeThreadId = data.active_thread;

        if (activeThreadId) {
          // Use existing active thread from new notebook
          this._selectedThreadId = activeThreadId;
          console.log(
            `📚 Switched to notebook ${notebookName}, using active thread: ${this._selectedThreadId}`
          );
        } else {
          // No threads in new notebook, create new thread ID
          this._selectedThreadId = this._generateThreadId();
          console.log(
            `📚 Switched to notebook ${notebookName}, created new thread: ${this._selectedThreadId}`
          );
        }
      } else {
        console.warn(
          'Failed to load threads for new notebook, creating new thread ID'
        );
        this._selectedThreadId = this._generateThreadId();
      }
    } catch (error) {
      console.error('Error loading active thread for new notebook:', error);
      this._selectedThreadId = this._generateThreadId();
    }
  }

  async loadThreads(): Promise<any> {
    try {
      const notebookPath =
        this._cellManager.getActiveNotebookPath?.() || 'Untitled.ipynb';
      console.log('🔍 [loadThreads] Loading threads for:', notebookPath);
      console.log(
        '🔍 [loadThreads] CellManager method exists:',
        !!this._cellManager.getActiveNotebookPath
      );

      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/threads', settings.baseUrl).href;

      console.log(
        '🔍 [loadThreads] Making request to:',
        `${requestUrl}?notebook_path=${encodeURIComponent(notebookPath)}`
      );

      const response = await ServerConnection.makeRequest(
        `${requestUrl}?notebook_path=${encodeURIComponent(notebookPath)}`,
        {
          method: 'GET'
        },
        settings
      );

      if (!response.ok) {
        console.warn('Failed to load threads:', response.status);
        return { threads: [], selected_thread_id: null };
      }

      const data = await response.json();
      console.log(
        `🔍 [loadThreads] Loaded ${
          data.threads?.length || 0
        } threads for ${notebookPath}`
      );
      console.log('🔍 [loadThreads] Thread data:', data);
      return data;
    } catch (error) {
      console.error('Error loading threads:', error);
      return { threads: [], selected_thread_id: null };
    }
  }

  async switchThread(threadId: string): Promise<void> {
    try {
      console.log('🔄 Switching to thread:', threadId);

      // Cancel any current request before switching - use 'switch' intent to change thread
      await this._cancelCurrentRequest('switch', threadId);

      const notebookPath =
        this._cellManager.getActiveNotebookPath?.() || 'Untitled.ipynb';
      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/threads', settings.baseUrl).href;

      const response = await ServerConnection.makeRequest(
        `${requestUrl}?notebook_path=${encodeURIComponent(notebookPath)}`,
        {
          method: 'GET'
        },
        settings
      );

      if (!response.ok) {
        console.warn('Failed to load threads for switching:', response.status);
        return;
      }

      const data = await response.json();
      const selectedThread = data.threads?.find((t: any) => t.id === threadId);

      if (!selectedThread) {
        console.warn('Thread not found:', threadId);
        return;
      }

      console.log(
        `✅ Switching to thread: ${selectedThread.title} (${selectedThread.message_count} messages)`
      );

      // Set the selected thread ID
      this._selectedThreadId = threadId;

      // Clear current messages completely
      this._messages = [];

      // Emit a special signal to clear the UI first
      this._messageAdded.emit({
        id: 'CLEAR_MESSAGES',
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        metadata: { action: 'clear' }
      });

      // Convert server messages to chat messages
      for (const msg of selectedThread.messages || []) {
        const chatMessage: IChatMessage = {
          id: UUID.uuid4(),
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          timestamp: new Date(msg.timestamp || Date.now()),
          metadata: { fromHistory: true, threadId: threadId }
        };
        this._messages.push(chatMessage);
        this._messageAdded.emit(chatMessage);
      }

      console.log(
        `✅ Successfully switched to thread with ${selectedThread.message_count} messages`
      );
    } catch (error) {
      console.error('Error switching thread:', error);
    }
  }

  async getAvailableTools(): Promise<any> {
    try {
      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/tools', settings.baseUrl).href;

      const response = await ServerConnection.makeRequest(
        requestUrl,
        {
          method: 'GET'
        },
        settings
      );

      if (!response.ok) {
        console.warn('Failed to get available tools:', response.status);
        return { categories: [], tools: {} };
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error getting available tools:', error);
      return { categories: [], tools: {} };
    }
  }

  /**
   * Generate a new thread ID
   */
  private _generateThreadId(): string {
    return UUID.uuid4();
  }

  /**
   * Clear display only - keep same thread and metadata
   */
  clearDisplayOnly(): void {
    this._messages = [];
    console.log(
      '🧹 Cleared display only, keeping thread ID:',
      this._selectedThreadId
    );
  }

  /**
   * Create new thread - clear display and generate new thread ID
   */
  createNewThread(): void {
    this._messages = [];
    this._selectedThreadId = this._generateThreadId();
    console.log('🆕 Created new thread ID:', this._selectedThreadId);
  }

  /**
   * Clear current thread messages - keep same thread ID but clear all messages
   */
  async clearCurrentThread(): Promise<void> {
    try {
      const notebookPath =
        this._cellManager.getActiveNotebookPath?.() || 'Untitled.ipynb';
      const currentThreadId = this._selectedThreadId;

      if (!currentThreadId) {
        console.log(
          '🧹 No current thread to clear, will create new thread on next message'
        );
        this._messages = [];
        return;
      }

      console.log('🧹 Clearing messages from current thread:', currentThreadId);

      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/conversations', settings.baseUrl)
        .href;

      const response = await ServerConnection.makeRequest(
        requestUrl,
        {
          method: 'PUT',
          body: JSON.stringify({
            action: 'clear_messages',
            notebook_path: notebookPath,
            thread_id: currentThreadId
          }),
          headers: {
            'Content-Type': 'application/json'
          }
        },
        settings
      );

      if (!response.ok) {
        console.warn('Failed to clear thread messages:', response.status);
        return;
      }

      const data = await response.json();
      console.log('✅ Thread messages cleared:', data.message);

      // Clear UI but keep same thread ID
      this._messages = [];
      console.log(
        '🧹 Cleared UI messages, keeping thread ID:',
        this._selectedThreadId
      );
    } catch (error) {
      console.error('Error clearing thread messages:', error);
    }
  }

  /**
   * Clear all conversations - delete all threads from metadata
   */
  async clearAllConversations(): Promise<void> {
    try {
      const notebookPath =
        this._cellManager.getActiveNotebookPath?.() || 'Untitled.ipynb';
      console.log('🧹 Clearing all conversations for:', notebookPath);

      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/conversations', settings.baseUrl)
        .href;

      const response = await ServerConnection.makeRequest(
        requestUrl,
        {
          method: 'POST',
          body: JSON.stringify({
            action: 'clear_all',
            notebook_path: notebookPath
          }),
          headers: {
            'Content-Type': 'application/json'
          }
        },
        settings
      );

      if (!response.ok) {
        console.warn('Failed to clear conversations:', response.status);
        return;
      }

      const data = await response.json();
      console.log('✅ All conversations cleared:', data.message);

      // Clear UI and create new thread
      this._messages = [];
      this._selectedThreadId = this._generateThreadId();
      console.log(
        '🆕 Created new thread after clearing all:',
        this._selectedThreadId
      );
    } catch (error) {
      console.error('Error clearing conversations:', error);
    }
  }

  /**
   * Build context from current notebook state
   */
  private async _buildContext(): Promise<any> {
    try {
      const notebookPath = this._cellManager.getActiveNotebookPath?.() || null;

      // Ensure we always have a valid thread ID
      if (!this._selectedThreadId) {
        this._selectedThreadId = this._generateThreadId();
        console.log(
          '🆕 No thread ID found, generated new one:',
          this._selectedThreadId
        );
      }

      // Collect current plan cards and include them in the context for synchronous processing
      const currentPlan = this._collectCurrentPlanCards();

      const context: any = {
        notebook_path: notebookPath,
        thread_id: this._selectedThreadId // Always send valid thread ID (renamed from selected_thread_id)
      };

      // Include plan cards in context for synchronous backend processing
      if (currentPlan && currentPlan.length > 0) {
        context.plan_cards = currentPlan;
        console.log(
          '🔄 Including plan cards in request context for synchronous update:',
          currentPlan.length
        );
      }

      return context;
    } catch (error) {
      console.warn('Failed to build minimal context:', error);
      // Even in error case, ensure valid thread ID
      if (!this._selectedThreadId) {
        this._selectedThreadId = this._generateThreadId();
      }
      return {
        notebook_path: null,
        thread_id: this._selectedThreadId
      };
    }
  }

  private _collectCurrentPlanCards(): any[] | null {
    try {
      // Find all messages in the chat
      const messagesContainer = document.querySelector('#chat-messages');
      if (!messagesContainer) return null;

      const messageElements = messagesContainer.children;

      // Find the LAST message that contains cards (most recent plan)
      let lastPlanMessage = null;
      for (let i = messageElements.length - 1; i >= 0; i--) {
        const message = messageElements[i] as HTMLElement;
        const cards = message.querySelectorAll('.chat-card');
        if (cards.length > 0) {
          lastPlanMessage = message;
          break;
        }
      }

      if (!lastPlanMessage) return null;

      // Extract cards only from the most recent plan message
      const cardElements = lastPlanMessage.querySelectorAll('.chat-card');
      if (cardElements.length === 0) return null;

      const collectedCards = Array.from(cardElements).map(card => {
        // Handle new single-line format with .card-content containing title and description
        const titleElement = card.querySelector('.card-title');
        const descriptionElement = card.querySelector('.card-description');

        return {
          id: card.id,
          title: titleElement?.textContent?.trim() || '',
          description: descriptionElement?.textContent?.trim() || ''
        };
      });

      console.log('🔍 [service] Collected plan cards:', collectedCards);
      return collectedCards;
    } catch (error) {
      console.warn('Failed to collect plan cards:', error);
      return null;
    }
  }

  // Frontend no longer enhances or inspects messages; backend owns execution and WS streaming

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
    this.disconnectStream?.();
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

  connectStream(notebookPath: string | null): void {
    try {
      const path = notebookPath || '*';
      if (this._ws && this._wsPath === path) {
        console.log(
          '[WS] already connected for path',
          path,
          'connId=',
          this._wsConnId
        );
        return;
      }
      this.disconnectStream();

      const settings = ServerConnection.makeSettings();
      let wsUrl = URLExt.join(settings.wsUrl, 'api', 'chat', 'stream');
      const params: string[] = [`notebook_path=${encodeURIComponent(path)}`];
      if (settings.appendToken && settings.token) {
        params.push(`token=${encodeURIComponent(settings.token)}`);
      }
      wsUrl = wsUrl + `?${params.join('&')}`;

      const ws = new settings.WebSocket(wsUrl);
      this._ws = ws;
      this._wsPath = path;
      this._wsConnId = UUID.uuid4();
      console.log(
        '[WS] open path=',
        path,
        'connId=',
        this._wsConnId,
        'url=',
        wsUrl
      );
      this._bindWS(ws);
    } catch (error) {
      console.error('WS connect error:', error);
      this._scheduleReconnect();
    }
  }

  disconnectStream(): void {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this._ws) {
      try {
        this._ws.onclose = null;
        this._ws.onerror = null;
        this._ws.onmessage = null;
        this._ws.close();
      } catch (e) {
        /* ignore */
      }
      this._ws = null;
    }
    this._wsPath = null;
    this._reconnectAttempts = 0;
  }

  private _bindWS(ws: WebSocket): void {
    ws.onmessage = evt => {
      try {
        const data = JSON.parse(evt.data);
        console.log('🔍 [WS] Raw data received:', data);
        const type = data?.type;
        const payload = data?.payload || {};
        const toolCallId =
          (data && (data.tool_call_id || (data as any)['tool_call_id'])) ||
          null;
        const threadId =
          (data && (data.thread_id || (data as any)['thread_id'])) || null;
        console.log(
          '[WS msg]',
          'connId=',
          this._wsConnId,
          'type=',
          type,
          'len=',
          payload?.content?.length || 0
        );
        console.log(
          '🔍 [WS] Type check:',
          type,
          'equals plan_cards?',
          type === 'plan_cards'
        );

        if (type === 'message') {
          const assistantMessage: IChatMessage = {
            id: UUID.uuid4(),
            role: (payload.role as any) || 'assistant',
            content: String(payload.content ?? ''),
            timestamp: new Date(),
            metadata: { wsConnId: this._wsConnId, toolCallId, threadId }
          };
          console.log(
            '[WS add]',
            'connId=',
            this._wsConnId,
            'toolCallId=',
            toolCallId,
            'threadId=',
            threadId
          );
          this._messages.push(assistantMessage);
          this._messageAdded.emit(assistantMessage);
        } else if (type === 'status') {
          const msg = String(payload.message ?? '');
          if (!msg) return;
          const statusMessage: IChatMessage = {
            id: UUID.uuid4(),
            role: 'assistant',
            content: msg, // Remove the ⏳ prefix - use metadata instead
            timestamp: new Date(),
            metadata: {
              messageType: 'status', // Add messageType metadata
              status: payload.status || 'working',
              wsConnId: this._wsConnId,
              toolCallId,
              threadId
            }
          };
          this._messages.push(statusMessage);
          this._messageAdded.emit(statusMessage);
        } else if (type === 'scroll_to_cell') {
          // Handle notebook scrolling commands
          const cellIndex = payload.cell_index;
          if (typeof cellIndex === 'number') {
            this._scrollToNotebookCell(cellIndex);
          }
        } else if (type === 'plan_cards') {
          // Debug logging
          console.log('🔍 [plan_cards] Received payload:', payload);
          console.log('🔍 [plan_cards] plan_steps:', payload.plan_steps);

          // Convert plan steps to card format for existing _renderCards()
          const planSteps = payload.plan_steps || [];
          console.log('🔍 [plan_cards] planSteps length:', planSteps.length);

          const cards = planSteps.map((step: any, index: number) => ({
            id: `plan-card-${index}-${Date.now()}`,
            title: step.title || `Step ${index + 1}`,
            description: step.description || ''
          }));

          console.log('🔍 [plan_cards] Generated cards:', cards);

          // Use existing planReceived signal infrastructure
          console.log('🔍 [plan_cards] Emitting planReceived signal');
          this._planReceived.emit({
            steps: cards, // Send as cards, not raw steps
            timestamp: payload.timestamp
          });
        } else if (type === 'plan') {
          this._planReceived.emit(payload);
        }
      } catch (e) {
        console.warn('Bad WS message:', e);
      }
    };

    const onCloseOrError = () => {
      this._ws = null;
      console.log('[WS] closed connId=', this._wsConnId);
      this._wsConnId = null;
      this._scheduleReconnect();
    };

    ws.onclose = onCloseOrError;
    ws.onerror = onCloseOrError;
  }

  private _scheduleReconnect(): void {
    if (this._isDisposed) return;

    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
    }

    const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts), 30000);
    this._reconnectAttempts++;

    this._reconnectTimer = setTimeout(() => {
      this.connectStream(this._wsPath);
    }, delay);
  }

  private _scrollToNotebookCell(cellIndex: number): void {
    try {
      console.log(`📍 Attempting to scroll to cell ${cellIndex}`);

      // Use the cell manager to access the notebook
      if (
        this._cellManager &&
        typeof (this._cellManager as any).scrollToCell === 'function'
      ) {
        (this._cellManager as any).scrollToCell(cellIndex);
        console.log(`📍 Scrolled to cell ${cellIndex} via cell manager`);
        return;
      }

      // Fallback: Try to access notebook through JupyterLab shell
      const app = (window as any).jupyterApp;
      if (app && app.shell && app.shell.currentWidget) {
        const currentWidget = app.shell.currentWidget;

        if (currentWidget.content && currentWidget.content.scrollToItem) {
          console.log(`📍 Scrolling to cell ${cellIndex} via notebook widget`);
          currentWidget.content
            .scrollToItem(cellIndex, 'center')
            .catch((e: any) => {
              console.warn('Failed to scroll to cell:', e);
            });
          return;
        }
      }

      // Last resort: Try to find notebook in DOM and scroll
      const notebookElement = document.querySelector('.jp-Notebook');
      if (notebookElement) {
        const cellElement = notebookElement.querySelector(
          `[data-windowed-list-index="${cellIndex}"]`
        );
        if (cellElement) {
          console.log(`📍 Scrolling to cell ${cellIndex} via DOM`);
          cellElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
          return;
        }
      }

      console.warn(
        `Could not scroll to cell ${cellIndex} - no method available`
      );
    } catch (error) {
      console.warn('Error scrolling to cell:', error);
    }
  }
}
