import { IChatService } from './tokens';

/**
 * Chat Manager - handles the floating dialog with pure DOM manipulation
 */
export class ChatManager {
  private _isVisible: boolean = false;
  private _chatService: IChatService;
  private _dialogElement: HTMLDivElement | null = null;

  constructor(chatService: IChatService) {
    this._chatService = chatService;
    // Expose chat manager globally for card interactions
    (window as any).chatManager = this;
    console.log('🔥 ChatManager created with service:', chatService);
  }

  private _createDialog(): void {
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
          <span style="font-size: 16px;">🤖</span>
          <span style="font-weight: 600; color: #333;">JupyterLab Assistant</span>
        </div>
        <button id="chat-close-btn" style="border: none; background: none; font-size: 18px; cursor: pointer; color: #666;">✕</button>
      </div>

             <div id="chat-messages" style="flex: 1; padding: 16px; overflow-y: auto; background: #fafafa;">
         <div id="welcome-section" style="text-align: center; color: #666; margin-bottom: 20px;">
           <div style="font-size: 24px; margin-bottom: 8px;">🚀</div>
           <h3 style="margin: 0 0 8px 0;">Welcome to JupyterLab Assistant</h3>
           <p style="margin: 0; font-size: 14px;">I can help you with code, notebook analysis, and more!</p>

           <div style="margin: 16px 0;">
             <div style="padding: 8px 12px; background: #f0f0f0; border-radius: 8px; margin-bottom: 8px; font-size: 14px; color: #666; cursor: pointer;" onclick="document.querySelector('#chat-input').value = 'What\\'s in cell 0?'">
               💡 "What's in cell 0?"
             </div>
             <div style="padding: 8px 12px; background: #f0f0f0; border-radius: 8px; margin-bottom: 8px; font-size: 14px; color: #666; cursor: pointer;" onclick="document.querySelector('#chat-input').value = 'Add a print statement'">
               💡 "Add a print statement"
             </div>
             <div style="padding: 8px 12px; background: #f0f0f0; border-radius: 8px; margin-bottom: 8px; font-size: 14px; color: #666; cursor: pointer;" onclick="document.querySelector('#chat-input').value = 'Explain this function'">
               💡 "Explain this function"
             </div>
           </div>
         </div>
       </div>

      <div style="padding: 16px; border-top: 1px solid #e0e0e0;">
        <div style="display: flex; gap: 8px; margin-bottom: 12px;">
          <textarea id="chat-input" placeholder="Ask me anything about your notebook..." style="flex: 1; padding: 8px; border: 1px solid #c0c0c0; border-radius: 6px; resize: none; font-family: inherit; font-size: 14px; min-height: 35px;"></textarea>
          <button id="chat-send-btn" style="padding: 8px 12px; background: #007acc; color: white; border: none; border-radius: 6px; cursor: pointer;">➤</button>
        </div>

        <div style="display: flex; gap: 8px;">
          <select id="chat-provider" style="padding: 4px 8px; border: 1px solid #c0c0c0; border-radius: 4px; font-size: 12px;">
            <option>OpenAI</option>
            <option>Claude</option>
            <option>Local</option>
          </select>
          <select id="chat-mode" style="padding: 4px 8px; border: 1px solid #c0c0c0; border-radius: 4px; font-size: 12px;">
            <option>Auto</option>
            <option>Agent</option>
            <option>Manual</option>
          </select>
          <button id="chat-clear-btn" style="padding: 4px 8px; border: 1px solid #c0c0c0; background: white; border-radius: 4px; cursor: pointer; font-size: 12px;">🗑️</button>
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

          this._addMessageToDisplay('user', message);
          console.log('🔥 User message added to display');

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

    clearBtn?.addEventListener('click', () => {
      console.log('🔥 Clear button clicked');
      this._chatService.clearHistory();
      this._clearMessagesDisplay();
    });

    // Make dialog draggable
    const header = this._dialogElement.querySelector(
      '#chat-header'
    ) as HTMLDivElement;
    this._makeDraggable(this._dialogElement, header);

    document.body.appendChild(this._dialogElement);
    console.log('🔥 Dialog appended to body');

    // Listen for chat service messages
    this._chatService.messageAdded.connect((sender: any, message: any) => {
      console.log('🔥 Message received from service:', message);
      if (message.role === 'assistant') {
        this._addMessageToDisplay('assistant', message.content);
      }
    });
  }

  private _addMessageToDisplay(
    role: 'user' | 'assistant',
    content: string
  ): void {
    console.log('🔥 Adding message to display:', role, content);
    const messagesContainer =
      this._dialogElement?.querySelector('#chat-messages');
    if (!messagesContainer) {
      console.error('🔥 Messages container not found!');
      return;
    }

    // Clear welcome message if this is the first real message
    const welcomeSection = messagesContainer.querySelector('#welcome-section');
    if (welcomeSection && (role === 'user' || role === 'assistant')) {
      console.log('🔥 Removing welcome section');
      welcomeSection.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.style.cssText = `
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
      align-items: flex-start;
    `;

    const isUser = role === 'user';

    // Check if content contains card data
    const cards = this._extractCardsFromContent(content);
    const hasCards = cards.length > 0;

    if (hasCards) {
      // Render cards instead of plain text
      messageDiv.innerHTML = `
        <div style="font-size: 16px; margin-top: 4px; min-width: 20px;">
          ${isUser ? '👤' : '🤖'}
        </div>
        <div style="flex: 1;">
          ${this._renderCards(cards)}
          <div style="font-size: 11px; color: #666; margin-top: 4px;">
            ${new Date().toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </div>
        </div>
      `;
    } else {
      // Render regular message
      messageDiv.innerHTML = `
        <div style="font-size: 16px; margin-top: 4px; min-width: 20px;">
          ${isUser ? '👤' : '🤖'}
        </div>
        <div style="flex: 1;">
          <div style="background: ${isUser ? '#007acc' : '#f5f5f5'}; color: ${
            isUser ? 'white' : '#333'
          }; padding: 8px 12px; border-radius: 8px; font-size: 14px; word-wrap: break-word; max-width: 280px;">
            ${content.replace(/\n/g, '<br>')}
          </div>
          <div style="font-size: 11px; color: #666; margin-top: 4px;">
            ${new Date().toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </div>
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

    messagesContainer.innerHTML = `
      <div style="text-align: center; color: #666; margin-bottom: 20px;">
        <div style="font-size: 24px; margin-bottom: 8px;">🚀</div>
        <h3 style="margin: 0 0 8px 0;">Welcome to JupyterLab Assistant</h3>
        <p style="margin: 0; font-size: 14px;">I can help you with code, notebook analysis, and more!</p>
      </div>
    `;
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

  get isVisible(): boolean {
    return this._isVisible;
  }

  show(): void {
    console.log('🔥 ChatManager.show() called');
    this._isVisible = true;
    this._createDialog();
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

  toggle(): void {
    console.log(
      '🔥 ChatManager.toggle() called, current state:',
      this._isVisible
    );
    if (this._isVisible) {
      this.hide();
    } else {
      this.show();
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
