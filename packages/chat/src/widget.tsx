import { IChatService } from './tokens';
import { getProviderForModel } from './models';

/**
 * Chat Manager - handles the floating dialog with pure DOM manipulation
 */
export class ChatManager {
  private _isVisible: boolean = false;
  private _chatService: IChatService;
  private _dialogElement: HTMLDivElement | null = null;
  private _currentThreadId: string | null = null;
  private _availableThreads: any[] = [];


  constructor(chatService: IChatService) {
    this._chatService = chatService;
    // Expose chat manager globally for card interactions
    (window as any).chatManager = this;
    console.log('🔥 ChatManager created with service:', chatService);

    // Subscribe to live plan events if available
    try {
      if ((this._chatService as any).planReceived) {
        (this._chatService as any).planReceived.connect((_: any, payload: any) => {
          const steps = Array.isArray(payload?.steps) ? payload.steps : [];
          if (steps.length === 0) return;
          const content = `Plan:\n` +
            steps
              .map((s: any, i: number) => `${i + 1}. ${s.title || 'Step'} — ${s.description || ''}`)
              .join('\n');
          this._addMessageToDisplay('assistant', content);
        });
      }
    } catch (e) {
      console.warn('Failed to bind planReceived:', e);
    }
  }

  private async _createDialog(): Promise<void> {
    if (this._dialogElement) {
      console.log('🔥 Dialog already exists, returning');
      return;
    }

    console.log('🔥 Creating new chat dialog');

    // Create dialog HTML structure directly
    this._dialogElement = document.createElement('div');
    this._dialogElement.style.cssText = `
      position: fixed;
      top: 50px;
      right: 50px;
      width: 350px;
      height: 500px;
      background: white;
      border: 1px solid #c0c0c0;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
      z-index: 2000;
      display: none;
      flex-direction: column;
      font-family: system-ui;
    `;

    this._dialogElement.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 16px; border-bottom: 1px solid #e0e0e0; cursor: move;" id="chat-header">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="font-weight: 600; color: #333;">JupyterLab Assistant</span>
        </div>
        <button id="chat-close-btn" style="border: none; background: none; font-size: 18px; cursor: pointer; color: #666;">✕</button>
      </div>
      
      <!-- Resize handles - invisible, cover entire borders like normal apps -->
      <div class="resize-handle resize-handle-n"></div>
      <div class="resize-handle resize-handle-s"></div>
      <div class="resize-handle resize-handle-e"></div>
      <div class="resize-handle resize-handle-w"></div>
      <div class="resize-handle resize-handle-ne"></div>
      <div class="resize-handle resize-handle-nw"></div>
      <div class="resize-handle resize-handle-se"></div>
      <div class="resize-handle resize-handle-sw"></div>

      
      <div id="thread-history-panel" style="
        display: none;
        background: #ffffff;
        border-bottom: 1px solid #e0e0e0;
        max-height: 200px;
        overflow-y: auto;
      ">
        <div id="thread-list" style="padding: 8px;">
          <div style="text-align: center; color: #666; padding: 16px;">Loading threads...</div>
        </div>
      </div>

             <div id="chat-messages" class="jp-ChatDialog-messages">
       </div>

      <div style="padding: 16px; border-top: 1px solid #e0e0e0;">
        <div style="display: flex; gap: 8px; margin-bottom: 12px;">
          <textarea id="chat-input" placeholder="Ask me anything about your notebook..." style="flex: 1; padding: 8px; border: 1px solid #c0c0c0; border-radius: 6px; resize: none; font-family: inherit; font-size: 14px; min-height: 35px;"></textarea>
          <button id="chat-send-btn" style="padding: 8px 12px; background: #007acc; color: white; border: none; border-radius: 6px; cursor: pointer;">➤</button>
        </div>

        <div style="display: flex; gap: 8px; align-items: center; justify-content: space-between;">
          <!-- Model Selection -->
          <select id="chat-model" style="padding: 6px 10px; border: 1px solid #c0c0c0; border-radius: 4px; font-size: 12px; min-width: 140px;">
            <option value="gpt-4o" selected>GPT-4o</option>
            <option value="gpt-4o-mini">GPT-4o Mini</option>
            <option value="o1-preview">o1-preview</option>
            <option value="o1-mini">o1-mini</option>
            <option value="gpt-4-turbo">GPT-4 Turbo</option>
            <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
            <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
            <option value="claude-3-5-haiku-20241022">Claude 3.5 Haiku</option>
            <option value="claude-3-opus-20240229">Claude 3 Opus</option>
            <option value="gemini-pro" disabled>Gemini Pro (Soon)</option>
          </select>
          
          <!-- Thread Management Buttons -->
          <div style="display: flex; gap: 4px;">
            <button id="thread-history-btn" style="
              background: none;
              border: 1px solid #c0c0c0;
              font-size: 14px;
              cursor: pointer;
              color: #666;
              padding: 6px 8px;
              border-radius: 4px;
              display: flex;
              align-items: center;
              justify-content: center;
            " title="Chat History">🕐</button>
            <button id="new-thread-btn" style="
              background: #007acc;
              color: white;
              border: none;
              padding: 6px 10px;
              border-radius: 4px;
              font-size: 16px;
              cursor: pointer;
              font-weight: bold;
              line-height: 1;
            " title="New conversation">+</button>
            <button id="clear-debug-btn" style="
              background: #dc3545;
              color: white;
              border: none;
              padding: 6px 8px;
              border-radius: 4px;
              font-size: 12px;
              cursor: pointer;
            " title="Clear all conversations (debug)">🧹</button>
            <button id="chat-clear-btn" style="
              background: white;
              border: 1px solid #c0c0c0;
              padding: 6px 8px;
              border-radius: 4px;
              cursor: pointer;
              font-size: 12px;
              color: #666;
            " title="Clear current chat">🗑️</button>
          </div>
        </div>
      </div>
    `;

    // Add event listeners
    const closeBtn = this._dialogElement.querySelector(
      '#chat-close-btn'
    ) as HTMLButtonElement;
    closeBtn?.addEventListener('click', () => {
      console.log('🔥 Close button clicked');
      this.hide();
    });

    // Model selection is now handled below with auto-provider inference

    const sendBtn = this._dialogElement.querySelector(
      '#chat-send-btn'
    ) as HTMLButtonElement;
    const input = this._dialogElement.querySelector(
      '#chat-input'
    ) as HTMLTextAreaElement;
    const clearBtn = this._dialogElement.querySelector(
      '#chat-clear-btn'
    ) as HTMLButtonElement;

    const sendMessage = async () => {
      console.log('🔥 sendMessage function called');
      const message = input?.value.trim();
      console.log('🔥 Input value:', input?.value, 'Trimmed:', message);

      if (message) {
        console.log('🔥 Sending message:', message);
        input.value = '';

        try {
          // Add user message to display immediately
          console.log('🔥 About to add user message to display');
          console.log('🔥 Dialog element exists:', !!this._dialogElement);
          console.log(
            '🔥 Messages container exists:',
            !!this._dialogElement?.querySelector('#chat-messages')
          );

          // Don't add user message immediately - it will come through the service
          // Send to service
          console.log('🔥 Calling chat service sendMessage');
          await this._chatService.sendMessage(message);
          console.log('🔥 Chat service sendMessage completed');
        } catch (error) {
          console.error('🔥 Error sending message:', error);
          this._addMessageToDisplay(
            'assistant',
            'Sorry, I encountered an error. Please try again.'
          );
        }
      } else {
        console.log('🔥 Empty message, not sending');
      }
    };

    sendBtn?.addEventListener('click', sendMessage);
    input?.addEventListener('keypress', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    clearBtn?.addEventListener('click', async () => {
      console.log('🔥 Clear button clicked - clearing current thread messages');
      await (this._chatService as any).clearCurrentThread();
      this._clearMessagesDisplay();
    });

    // Thread selector event handlers
    const threadHistoryBtn = this._dialogElement.querySelector('#thread-history-btn') as HTMLButtonElement;
    const newThreadBtn = this._dialogElement.querySelector('#new-thread-btn') as HTMLButtonElement;
    const clearDebugBtn = this._dialogElement.querySelector('#clear-debug-btn') as HTMLButtonElement;

    threadHistoryBtn?.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      console.log('🔥 Thread history button clicked');
      await this._toggleThreadHistory();
    });

    newThreadBtn?.addEventListener('click', async () => {
      console.log('🔥 New thread button clicked');
      await this._createNewThread();
    });

    clearDebugBtn?.addEventListener('click', async () => {
      console.log('🔥 Clear debug button clicked');
      if (confirm('Clear all conversation history for this notebook? This cannot be undone.')) {
        await this._clearAllConversations();
      }
    });

    // Handle model selection and auto-infer provider
    const modelSelect = this._dialogElement.querySelector('#chat-model') as HTMLSelectElement;
    modelSelect?.addEventListener('change', () => {
      const selectedModel = modelSelect.value;
      const provider = getProviderForModel(selectedModel);
      console.log(`🤖 Model changed to: ${selectedModel} (provider: ${provider})`);
      
      // Store the provider for use in requests (you can access it via modelSelect.dataset.provider)
      modelSelect.dataset.provider = provider;
    });

    // Set initial provider for default model
    if (modelSelect) {
      const initialModel = modelSelect.value;
      const initialProvider = getProviderForModel(initialModel);
      modelSelect.dataset.provider = initialProvider;
      console.log(`🤖 Initial model: ${initialModel} (provider: ${initialProvider})`);
    }

    // Make dialog draggable
    const header = this._dialogElement.querySelector(
      '#chat-header'
    ) as HTMLDivElement;
    this._makeDraggable(this._dialogElement, header);

    // Make dialog resizable
    this._makeResizable(this._dialogElement);

    document.body.appendChild(this._dialogElement);
    console.log('🔥 Dialog appended to body');

    // Add click-outside detection to close thread history dropdown
    document.addEventListener('click', (event) => {
      const panel = this._dialogElement?.querySelector('#thread-history-panel') as HTMLElement;
      const button = this._dialogElement?.querySelector('#thread-history-btn') as HTMLElement;
      
      if (panel && panel.style.display !== 'none') {
        const target = event.target as HTMLElement;
        
        // Check if click is outside both the panel and the button
        if (!panel.contains(target) && !button.contains(target)) {
          this._hideThreadHistory();
        }
      }
    });

    // Listen for chat service messages - NO DUPLICATE FILTERING
    this._chatService.messageAdded.connect((sender: any, message: any) => {
      console.log('🔥 Message received from service:', message);
      
      // Handle special clear signal
      if (message.metadata?.action === 'clear') {
        console.log('🔥 Clearing chat UI for thread switch');
        this._clearMessagesDisplay();
        return;
      }
      
      // Handle notebook switch message
      if (message.metadata?.action === 'notebook_switch') {
        console.log('🔥 Handling notebook switch message:', message.content);
        this._addMessageToDisplay(message.role as 'user' | 'assistant', message.content, message.timestamp);
        
        // After a short delay, update connection info and remove the temporary message
        setTimeout(async () => {
          try {
            // Remove the temporary switching message
            const messagesContainer = this._dialogElement?.querySelector('#chat-messages');
            if (messagesContainer) {
              const lastMessage = messagesContainer.lastElementChild;
              if (lastMessage && lastMessage.textContent?.includes('🔄 Switching to notebook:')) {
                lastMessage.remove();
              }
            }
            
            // Show updated connection info for new notebook
            await this._showConnectionInfo();
          } catch (error) {
            console.warn('Error updating connection info after notebook switch:', error);
          }
        }, 1500); // 1.5 second delay to show switching message
        
        return;
      }
      
      // Show all real-time messages (including status), but filter status from history
      if (message.metadata?.fromHistory) {
        // Historical messages: filter out status messages
        if (message.content && !message.content.startsWith('[status]') && !message.content.startsWith('⏳')) {
          this._addMessageToDisplay(message.role as 'user' | 'assistant', message.content, message.timestamp);
        } else {
          console.log('🔥 Filtering out historical status message:', message.content.substring(0, 50));
        }
      } else {
        // Real-time messages: show everything (including status for live feedback)
        if (message.content) {
          this._addMessageToDisplay(message.role as 'user' | 'assistant', message.content, message.timestamp);
        }
      }
    });

    // CRITICAL FIX: Display any messages that were loaded from history before the listener was connected
    const existingMessages = this._chatService.getHistory();
    console.log(`🔄 Displaying ${existingMessages.length} existing messages from history`);
    for (const msg of existingMessages) {
      // Filter out status messages from history too
      if (msg.content && !msg.content.startsWith('[status]') && !msg.content.startsWith('⏳')) {
        console.log(`🔄 Displaying history message: ${msg.role} - ${msg.content.substring(0, 100)}...`);
        this._addMessageToDisplay(msg.role as 'user' | 'assistant', msg.content, msg.timestamp);
      } else {
        console.log(`🔄 Filtering out status message from history: ${msg.content.substring(0, 50)}...`);
      }
    }

    // Load threads for the thread selector
    await this._loadThreads();

    // Show connection info (always, not saved to history)
    await this._showConnectionInfo();
  }

  private _addMessageToDisplay(
    role: 'user' | 'assistant',
    content: string,
    timestamp?: Date
  ): void {
    console.log('🔥 Adding message to display:', role, content);
    const messagesContainer =
      this._dialogElement?.querySelector('#chat-messages');
    if (!messagesContainer) {
      console.error('🔥 Messages container not found!');
      return;
    }

    // No welcome section to remove anymore

    const messageDiv = document.createElement('div');

    const isUser = role === 'user';

    // Check if content contains card data
    const cards = this._extractCardsFromContent(content);
    const hasCards = cards.length > 0;

    if (hasCards) {
      // Render cards instead of plain text
      messageDiv.innerHTML = `
        <div style="flex: 1;">
          ${this._renderCards(cards)}
          <div style="font-size: 11px; color: #666; margin-top: 4px;">
            ${(timestamp || new Date()).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </div>
        </div>
      `;
    } else {
      // Render regular message - keep original simple layout but without width constraints
      messageDiv.style.marginBottom = '12px';
      messageDiv.innerHTML = `
        <div style="background: ${isUser ? '#007acc' : '#f5f5f5'}; color: ${
          isUser ? 'white' : '#333'
        }; padding: 8px 12px; border-radius: 8px; font-size: 14px; word-wrap: break-word; display: inline-block; max-width: 85%;">
          ${content.replace(/\n/g, '<br>')}
        </div>
        <div style="font-size: 11px; color: #666; margin-top: 4px;">
          ${(timestamp || new Date()).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
          })}
        </div>
      `;
    }

    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    console.log(
      '🔥 Message added to DOM, total messages:',
      messagesContainer.children.length
    );
  }

  private _extractCardsFromContent(content: string): any[] {
    const cards: any[] = [];

    // Look for card patterns in the content
    // Pattern: [CARD:title|description]
    const cardPattern = /\[CARD:([^|]+)\|([^\]]+)\]/g;
    let match;

    while ((match = cardPattern.exec(content)) !== null) {
      cards.push({
        id: `card-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        title: match[1].trim(),
        description: match[2].trim()
      });
    }

    return cards;
  }

  private _renderCards(cards: any[]): string {
    return `
      <div style="display: flex; flex-direction: column; gap: 8px;">
        ${cards.map((card, index) => this._renderCard(card, index)).join('')}
      </div>
    `;
  }

  private _renderCard(card: any, index: number): string {
    return `
      <div id="${card.id}" class="chat-card" style="
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        position: relative;
        max-width: 280px;
        margin-bottom: 8px;
      ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div style="flex: 1; min-width: 0;">
            <div class="card-title" contenteditable="true" style="
              font-size: 14px;
              font-weight: 600;
              color: #333;
              margin-bottom: 4px;
              outline: none;
              border: 1px solid transparent;
              padding: 2px 4px;
              border-radius: 4px;
            ">${card.title}</div>
            <div class="card-description" contenteditable="true" style="
              font-size: 13px;
              color: #666;
              line-height: 1.4;
              outline: none;
              border: 1px solid transparent;
              padding: 2px 4px;
              border-radius: 4px;
            ">${card.description}</div>
          </div>
          <div style="display: flex; gap: 4px; margin-left: 8px;">
            <button class="add-step-btn" onclick="window.chatManager.addStepAfterCard('${card.id}')" style="
              background: #4caf50;
              color: white;
              border: none;
              border-radius: 50%;
              width: 24px;
              height: 24px;
              font-size: 16px;
              cursor: pointer;
              display: flex;
              align-items: center;
              justify-content: center;
              font-weight: bold;
            ">+</button>
            <button class="delete-card-btn" onclick="window.chatManager.deleteCard('${card.id}')" style="
              background: none;
              border: none;
              cursor: pointer;
              font-size: 12px;
              color: #666;
              padding: 2px;
              opacity: 0.7;
            ">🗑️</button>
          </div>
        </div>
      </div>
    `;
  }

  // Card management methods
  editCard(cardId: string): void {
    const cardElement = document.getElementById(cardId);
    if (!cardElement) return;

    const titleElement = cardElement.querySelector(
      '.card-title'
    ) as HTMLElement;
    const descriptionElement = cardElement.querySelector(
      '.card-description'
    ) as HTMLElement;

    if (titleElement && descriptionElement) {
      // Focus on title and make it editable
      titleElement.focus();
      titleElement.style.border = '1px solid #007acc';
      titleElement.style.backgroundColor = '#f8f9fa';

      // Add event listeners for saving on blur
      const saveChanges = () => {
        titleElement.style.border = '1px solid transparent';
        titleElement.style.backgroundColor = 'transparent';
        descriptionElement.style.border = '1px solid transparent';
        descriptionElement.style.backgroundColor = 'transparent';
      };

      titleElement.addEventListener('blur', saveChanges, { once: true });
      descriptionElement.addEventListener('blur', saveChanges, { once: true });
    }
  }

  deleteCard(cardId: string): void {
    const cardElement = document.getElementById(cardId);
    if (cardElement && confirm('Are you sure you want to delete this card?')) {
      cardElement.remove();
    }
  }

  addStepAfterCard(cardId: string): void {
    const cardElement = document.getElementById(cardId);
    if (!cardElement) return;

    const newCard = {
      id: `card-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      title: 'New Step',
      description: 'Click to edit this step'
    };

    // Insert the new card after the current one
    const newCardElement = document.createElement('div');
    newCardElement.innerHTML = this._renderCard(newCard, 0);
    const newCardDiv = newCardElement.firstElementChild as HTMLElement;

    cardElement.parentNode?.insertBefore(newCardDiv, cardElement.nextSibling);

    // Focus on the new card's title for immediate editing
    setTimeout(() => {
      const newTitleElement = newCardDiv.querySelector(
        '.card-title'
      ) as HTMLElement;
      if (newTitleElement) {
        newTitleElement.focus();
        newTitleElement.style.border = '1px solid #007acc';
        newTitleElement.style.backgroundColor = '#f8f9fa';

        // Select all text for easy replacement
        const range = document.createRange();
        range.selectNodeContents(newTitleElement);
        const selection = window.getSelection();
        if (selection) {
          selection.removeAllRanges();
          selection.addRange(range);
        }
      }
    }, 100);
  }

  private _clearMessagesDisplay(): void {
    const messagesContainer =
      this._dialogElement?.querySelector('#chat-messages');
    if (!messagesContainer) return;

    messagesContainer.innerHTML = '';
  }

  private async _showConnectionInfo(): Promise<void> {
    try {
      // Get notebook name from chat service
      const notebookPath = (this._chatService as any)._cellManager?.getActiveNotebookPath?.() || 'Untitled.ipynb';
      const notebookName = notebookPath.split('/').pop() || notebookPath;

      // Get available tools
      const toolsInfo = await (this._chatService as any).getAvailableTools();
      const toolCategories = toolsInfo.categories || [];

      // Create connection message
      let connectionText = `Connected to notebook ${notebookName}`;
      
      if (toolCategories.length > 0) {
        connectionText += ` with ${toolCategories.join(', ')}`;
      }

      // Display as assistant message but don't save to history
      this._addConnectionMessage(connectionText);
    } catch (error) {
      console.error('Error showing connection info:', error);
      // Fallback connection message
      const notebookPath = (this._chatService as any)._cellManager?.getActiveNotebookPath?.() || 'Untitled.ipynb';
      const notebookName = notebookPath.split('/').pop() || notebookPath;
      this._addConnectionMessage(`Connected to notebook ${notebookName}`);
    }
  }

  private _addConnectionMessage(content: string): void {
    const messagesContainer = this._dialogElement?.querySelector('#chat-messages');
    if (!messagesContainer) return;

    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
      margin-bottom: 12px;
      opacity: 0.7;
    `;

    // Display like assistant message but with subtle styling
    messageDiv.innerHTML = `
      <div style="flex: 1;">
        <div style="background: #f0f8ff; color: #666; padding: 8px 12px; border-radius: 8px; font-size: 13px; word-wrap: break-word; max-width: 280px; border-left: 3px solid #007acc;">
          ${content.replace(/\n/g, '<br>')}
        </div>
      </div>
    `;

    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  private async _loadThreads(): Promise<void> {
    try {
      console.log('🔄 Loading threads for thread selector');
      if ((this._chatService as any).loadThreads) {
        const threadsData = await (this._chatService as any).loadThreads();
        this._availableThreads = threadsData.threads || [];
        // Only set _currentThreadId from backend if we don't already have one set
        if (!this._currentThreadId) {
          this._currentThreadId = threadsData.selected_thread_id;
        }
        this._updateThreadList();
        console.log(`✅ Loaded ${this._availableThreads.length} threads, selected: ${this._currentThreadId}`);
      }
    } catch (error) {
      console.error('Error loading threads:', error);
    }
  }

  private _updateThreadList(): void {
    const threadList = this._dialogElement?.querySelector('#thread-list');
    if (!threadList) return;

    if (this._availableThreads.length === 0) {
      threadList.innerHTML = '<div style="text-align: center; color: #666; padding: 16px;">No conversation history</div>';
      return;
    }

    threadList.innerHTML = '';
    
    this._availableThreads.forEach(thread => {
      const threadItem = document.createElement('div');
      threadItem.style.cssText = `
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 4px;
        cursor: pointer;
        border: 1px solid transparent;
        ${thread.id === this._currentThreadId ? 'background: #e3f2fd; border-color: #2196f3;' : 'background: #f5f5f5;'}
      `;
      
      threadItem.innerHTML = `
        <div style="font-weight: 500; font-size: 13px; color: #333; margin-bottom: 2px;">
          ${thread.title || 'Untitled'}
        </div>
        <div style="font-size: 11px; color: #666;">
          ${thread.message_count} messages • ${this._formatDate(thread.last_updated)}
        </div>
      `;
      
      threadItem.addEventListener('click', async (event) => {
        event.preventDefault();
        event.stopPropagation();
        console.log('🔄 Switching to thread:', thread.id);
        
        // Immediately hide dropdown and update UI selection
        this._hideThreadHistory();
        this._currentThreadId = thread.id;
        this._updateThreadList(); // Update selection highlight immediately
        
        // Then perform the async switch
        await this._switchToThread(thread.id);
      });
      
      threadItem.addEventListener('mouseenter', () => {
        if (thread.id !== this._currentThreadId) {
          threadItem.style.background = '#e8e8e8';
        }
      });
      
      threadItem.addEventListener('mouseleave', () => {
        if (thread.id !== this._currentThreadId) {
          threadItem.style.background = '#f5f5f5';
        }
      });
      
      threadList.appendChild(threadItem);
    });
  }

  private async _toggleThreadHistory(): Promise<void> {
    const panel = this._dialogElement?.querySelector('#thread-history-panel') as HTMLElement;
    if (!panel) return;

    if (panel.style.display === 'none') {
      await this._showThreadHistory();
    } else {
      this._hideThreadHistory();
    }
  }

  private async _showThreadHistory(): Promise<void> {
    const panel = this._dialogElement?.querySelector('#thread-history-panel') as HTMLElement;
    if (panel) {
      panel.style.display = 'block';
      
      // CRITICAL FIX: Load fresh thread data for current notebook before showing list
      console.log('🔄 Loading fresh thread data for current notebook...');
      await this._loadThreads();
    }
  }

  private _hideThreadHistory(): void {
    const panel = this._dialogElement?.querySelector('#thread-history-panel') as HTMLElement;
    if (panel) {
      panel.style.display = 'none';
    }
  }

  private _formatDate(dateStr: string): string {
    if (!dateStr) return 'Unknown';
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / (1000 * 60));
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch {
      return 'Unknown';
    }
  }

  private async _switchToThread(threadId: string): Promise<void> {
    try {
      console.log(`🔄 Switching to thread: ${threadId}`);
      
      if ((this._chatService as any).switchThread) {
        await (this._chatService as any).switchThread(threadId);
        console.log('✅ Thread switched successfully');
        
        // Show connection info after switching
        await this._showConnectionInfo();
        
        // Refresh thread list to show all available threads
        await this._loadThreads();
      }
    } catch (error) {
      console.error('Error switching thread:', error);
    }
  }

  private async _createNewThread(): Promise<void> {
    console.log('🔥 Creating new thread');
    this._currentThreadId = null;
    (this._chatService as any).createNewThread();
    this._clearMessagesDisplay();
    this._hideThreadHistory();
    
    // Show connection info for new thread
    await this._showConnectionInfo();
    
    // Reload thread list from server but don't auto-select any thread
    const threadsData = await (this._chatService as any).loadThreads();
    this._availableThreads = threadsData.threads || [];
    // Don't set _currentThreadId from threadsData.selected_thread_id - keep it null for new thread
    this._updateThreadList();
    console.log('🆕 New thread created, ready for fresh conversation');
  }

  private async _clearAllConversations(): Promise<void> {
    try {
      console.log('🧹 Clearing all conversations');
      if ((this._chatService as any).clearAllConversations) {
        await (this._chatService as any).clearAllConversations();
        this._availableThreads = [];
        this._currentThreadId = null;
        this._clearMessagesDisplay();
        this._hideThreadHistory();
        this._updateThreadList();
        console.log('✅ All conversations cleared');
      }
    } catch (error) {
      console.error('Error clearing conversations:', error);
    }
  }

  private _makeDraggable(dialog: HTMLDivElement, handle: HTMLDivElement): void {
    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let startLeft = 0;
    let startTop = 0;

    handle.addEventListener('mousedown', e => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;

      const rect = dialog.getBoundingClientRect();
      startLeft = rect.left;
      startTop = rect.top;

      e.preventDefault();
      console.log('🔥 Drag started');
    });

    document.addEventListener('mousemove', e => {
      if (!isDragging) return;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      const newLeft = Math.max(10, startLeft + deltaX);
      const newTop = Math.max(10, startTop + deltaY);

      dialog.style.left = newLeft + 'px';
      dialog.style.top = newTop + 'px';
      dialog.style.right = 'auto'; // Remove right positioning when dragging
    });

    document.addEventListener('mouseup', () => {
      if (isDragging) {
        console.log('🔥 Drag ended');
      }
      isDragging = false;
    });
  }

  private _makeResizable(dialog: HTMLDivElement): void {
    let isResizing = false;
    let resizeDirection = '';
    let startX = 0;
    let startY = 0;
    let startWidth = 0;
    let startHeight = 0;
    let startLeft = 0;
    let startTop = 0;

    const minWidth = 300;
    const minHeight = 400;

    // Add event listeners to all resize handles
    const resizeHandles = dialog.querySelectorAll('.resize-handle');
    
    resizeHandles.forEach(handle => {
      handle.addEventListener('mousedown', (e: Event) => {
        const mouseEvent = e as MouseEvent;
        isResizing = true;
        resizeDirection = (handle as HTMLElement).className.split(' ')[1]; // Get direction class
        
        startX = mouseEvent.clientX;
        startY = mouseEvent.clientY;
        
        const rect = dialog.getBoundingClientRect();
        startWidth = rect.width;
        startHeight = rect.height;
        startLeft = rect.left;
        startTop = rect.top;
        
        mouseEvent.preventDefault();
        mouseEvent.stopPropagation();
        console.log('🔥 Resize started:', resizeDirection);
        
        // Add resizing class for visual feedback
        dialog.classList.add('jp-ChatDialog-resizing');
      });
    });

    document.addEventListener('mousemove', (e: MouseEvent) => {
      if (!isResizing) return;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      let newWidth = startWidth;
      let newHeight = startHeight;
      let newLeft = startLeft;
      let newTop = startTop;

      // Handle different resize directions
      switch (resizeDirection) {
        case 'resize-handle-e': // East (right)
          newWidth = Math.max(minWidth, startWidth + deltaX);
          break;
        case 'resize-handle-w': // West (left)
          newWidth = Math.max(minWidth, startWidth - deltaX);
          newLeft = startLeft + (startWidth - newWidth);
          break;
        case 'resize-handle-s': // South (bottom)
          newHeight = Math.max(minHeight, startHeight + deltaY);
          break;
        case 'resize-handle-n': // North (top)
          newHeight = Math.max(minHeight, startHeight - deltaY);
          newTop = startTop + (startHeight - newHeight);
          break;
        case 'resize-handle-se': // Southeast (bottom-right)
          newWidth = Math.max(minWidth, startWidth + deltaX);
          newHeight = Math.max(minHeight, startHeight + deltaY);
          break;
        case 'resize-handle-sw': // Southwest (bottom-left)
          newWidth = Math.max(minWidth, startWidth - deltaX);
          newHeight = Math.max(minHeight, startHeight + deltaY);
          newLeft = startLeft + (startWidth - newWidth);
          break;
        case 'resize-handle-ne': // Northeast (top-right)
          newWidth = Math.max(minWidth, startWidth + deltaX);
          newHeight = Math.max(minHeight, startHeight - deltaY);
          newTop = startTop + (startHeight - newHeight);
          break;
        case 'resize-handle-nw': // Northwest (top-left)
          newWidth = Math.max(minWidth, startWidth - deltaX);
          newHeight = Math.max(minHeight, startHeight - deltaY);
          newLeft = startLeft + (startWidth - newWidth);
          newTop = startTop + (startHeight - newHeight);
          break;
      }

      // Apply the new dimensions and position
      dialog.style.width = newWidth + 'px';
      dialog.style.height = newHeight + 'px';
      dialog.style.left = newLeft + 'px';
      dialog.style.top = newTop + 'px';
      dialog.style.right = 'auto';
      dialog.style.bottom = 'auto';
    });

    document.addEventListener('mouseup', () => {
      if (isResizing) {
        console.log('🔥 Resize ended');
        dialog.classList.remove('jp-ChatDialog-resizing');
      }
      isResizing = false;
      resizeDirection = '';
    });
  }

  get isVisible(): boolean {
    return this._isVisible;
  }

  async show(): Promise<void> {
    console.log('🔥 ChatManager.show() called');
    this._isVisible = true;
    await this._createDialog();
    if (this._dialogElement) {
      this._dialogElement.style.display = 'flex';
      console.log('🔥 Dialog should now be visible');
    } else {
      console.error('🔥 Dialog element is null!');
    }
  }

  hide(): void {
    console.log('🔥 ChatManager.hide() called');
    this._isVisible = false;
    if (this._dialogElement) {
      this._dialogElement.style.display = 'none';
    }
  }

  async toggle(): Promise<void> {
    console.log(
      '🔥 ChatManager.toggle() called, current state:',
      this._isVisible
    );
    if (this._isVisible) {
      this.hide();
    } else {
      await this.show();
    }
  }

  get chatService(): IChatService {
    return this._chatService;
  }

  dispose(): void {
    console.log('🔥 ChatManager.dispose() called');
    if (this._dialogElement && this._dialogElement.parentNode) {
      this._dialogElement.parentNode.removeChild(this._dialogElement);
    }
    this._dialogElement = null;
  }


}
