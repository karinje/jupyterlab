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
      // Send to LLM
      const response = await this._llmProvider.sendMessage(message, context);
      console.log('LLM response received:', response);

      // Do not add assistant message from HTTP response; rely solely on WS stream
      console.log('[CHAT] HTTP return ignored; waiting for WS broadcast');
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
    try {
      const notebookPath = this._cellManager.getActiveNotebookPath?.() || null;
      return { notebook_path: notebookPath };
    } catch (error) {
      console.warn('Failed to build minimal context:', error);
      return { notebook_path: null };
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
