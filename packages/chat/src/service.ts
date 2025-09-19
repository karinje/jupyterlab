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
  private _currentRequest: Promise<any> | null = null;  // Track current request for cancellation

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
      const context = this._buildContext();

      console.log('About to send to LLM...');
      // Send to LLM (track for cancellation)
      this._currentRequest = this._llmProvider.sendMessage(message, context);
      const response = await this._currentRequest;
      this._currentRequest = null;
      console.log('LLM response received:', response);

      // Do not add assistant message from HTTP response; rely solely on WS stream
      console.log('[CHAT] HTTP return ignored; waiting for WS broadcast');
    } catch (error) {
      this._currentRequest = null;
      
      if (error.name === 'AbortError') {
        console.log('🛑 Message request was cancelled');
        return;
      }
      
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

  private async _cancelCurrentRequest(): Promise<void> {
    if (this._currentRequest) {
      console.log('🛑 Cancelling current request');
      // Note: This won't actually cancel HTTP requests, but will prevent processing
      this._currentRequest = null;
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
    async loadConversationHistory(notebookPath: string): Promise<void> {
    try {
      console.log('🔄 Loading conversation history for:', notebookPath);

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

      console.log(`📚 Frontend: Found ${threadCount} conversation threads for ${notebookPath}`);

      // Find the most recent thread based on last_updated timestamp
      let mostRecentThreadId = data.active_thread;
      let mostRecentTime = 0;

      if (threadCount > 0) {
        for (const [tid, threadData] of Object.entries(allThreads)) {
          const messageCount = (threadData as any).messages?.length || 0;
          const lastUpdated = (threadData as any).last_updated;
          const updateTime = lastUpdated ? new Date(lastUpdated).getTime() : 0;

          console.log(`  📝 Frontend: Thread ${tid.substring(0, 8)}... has ${messageCount} messages (updated: ${lastUpdated})`);

          if (updateTime > mostRecentTime) {
            mostRecentTime = updateTime;
            mostRecentThreadId = tid;
          }
        }
      }

      console.log(`🎯 Frontend: Most recent thread ID: ${mostRecentThreadId} (was active: ${data.active_thread})`);
      const activeThreadId = mostRecentThreadId;

      if (activeThreadId && data.threads && data.threads[activeThreadId]) {
        const threadMessages = data.threads[activeThreadId].messages || [];

        console.log(`✅ Frontend: Loading ${threadMessages.length} messages from active thread`);

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

        console.log(`✅ Frontend: Successfully loaded ${threadMessages.length} messages into chat UI`);

        // Log first and last messages for verification
        if (threadMessages.length > 0) {
          const firstMsg = threadMessages[0];
          const lastMsg = threadMessages[threadMessages.length - 1];
          console.log(`  📖 Frontend: First message: ${firstMsg.role} - ${firstMsg.content.substring(0, 100)}...`);
          if (threadMessages.length > 1) {
            console.log(`  📖 Frontend: Last message: ${lastMsg.role} - ${lastMsg.content.substring(0, 100)}...`);
          }
        }
      } else {
        console.log('📝 Frontend: No active thread found, starting fresh conversation');
      }
    } catch (error) {
      console.error('Error loading conversation history:', error);
    }
  }

  async loadThreads(): Promise<any> {
    try {
      const notebookPath = this._cellManager.getActiveNotebookPath?.() || 'Untitled.ipynb';
      console.log('🔄 Loading threads for:', notebookPath);

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
        console.warn('Failed to load threads:', response.status);
        return { threads: [], selected_thread_id: null };
      }

      const data = await response.json();
      console.log(`📚 Loaded ${data.threads?.length || 0} threads`);
      return data;
    } catch (error) {
      console.error('Error loading threads:', error);
      return { threads: [], selected_thread_id: null };
    }
  }

  async switchThread(threadId: string): Promise<void> {
    try {
      console.log('🔄 Switching to thread:', threadId);
      
      // Cancel any current request before switching
      await this._cancelCurrentRequest();
      
      const notebookPath = this._cellManager.getActiveNotebookPath?.() || 'Untitled.ipynb';
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

      console.log(`✅ Switching to thread: ${selectedThread.title} (${selectedThread.message_count} messages)`);

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

      console.log(`✅ Successfully switched to thread with ${selectedThread.message_count} messages`);
    } catch (error) {
      console.error('Error switching thread:', error);
    }
  }

  async clearAllConversations(): Promise<void> {
    try {
      const notebookPath = this._cellManager.getActiveNotebookPath?.() || 'Untitled.ipynb';
      console.log('🧹 Clearing all conversations for:', notebookPath);

      const settings = ServerConnection.makeSettings();
      const requestUrl = new URL('/api/chat/debug', settings.baseUrl).href;

      const response = await ServerConnection.makeRequest(
        requestUrl,
        {
          method: 'POST',
          body: JSON.stringify({
            action: 'clear_conversations',
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
      console.log('✅ Conversations cleared:', data.message);
    } catch (error) {
      console.error('Error clearing conversations:', error);
    }
  }

  /**
   * Clear chat history
   */
  clearHistory(): void {
    this._messages = [];
    this._selectedThreadId = null;  // Clear selected thread for new conversation
    console.log('🧹 Cleared chat history and selected thread ID');
  }

  /**
   * Build context from current notebook state
   */
  private _buildContext(): any {
    try {
      const notebookPath = this._cellManager.getActiveNotebookPath?.() || null;
      return { 
        notebook_path: notebookPath,
        selected_thread_id: this._selectedThreadId
      };
    } catch (error) {
      console.warn('Failed to build minimal context:', error);
      return { 
        notebook_path: null,
        selected_thread_id: this._selectedThreadId
      };
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
        console.log('[WS] already connected for path', path, 'connId=', this._wsConnId);
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
      console.log('[WS] open path=', path, 'connId=', this._wsConnId, 'url=', wsUrl);
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
        const type = data?.type;
        const payload = data?.payload || {};
        const toolCallId = (data && (data.tool_call_id || (data as any)["tool_call_id"])) || null;
        const threadId = (data && (data.thread_id || (data as any)["thread_id"])) || null;
        console.log('[WS msg]', 'connId=', this._wsConnId, 'type=', type, 'len=', (payload?.content?.length || 0));

        if (type === 'message') {
          const assistantMessage: IChatMessage = {
            id: UUID.uuid4(),
            role: (payload.role as any) || 'assistant',
            content: String(payload.content ?? ''),
            timestamp: new Date(),
            metadata: { wsConnId: this._wsConnId, toolCallId, threadId }
          };
          console.log('[WS add]', 'connId=', this._wsConnId, 'toolCallId=', toolCallId, 'threadId=', threadId);
          this._messages.push(assistantMessage);
          this._messageAdded.emit(assistantMessage);
        } else if (type === 'status') {
          const msg = String(payload.message ?? '');
          if (!msg) return;
          const statusMessage: IChatMessage = {
            id: UUID.uuid4(),
            role: 'assistant',
            content: `⏳ ${msg}`,
            timestamp: new Date(),
            metadata: { status: payload.status || 'working' }
          };
          this._messages.push(statusMessage);
          this._messageAdded.emit(statusMessage);
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
    const attempts = Math.min(this._reconnectAttempts + 1, 6);
    this._reconnectAttempts = attempts;
    const delay = 500 * attempts + Math.floor(Math.random() * 250);
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
    }
    const path = this._wsPath;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      if (!this._isDisposed && path) {
        this.connectStream(path);
      }
    }, delay);
  }
}
