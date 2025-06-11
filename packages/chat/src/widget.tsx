import React, { useState, useEffect, useRef } from 'react';
import { ReactWidget } from '@jupyterlab/apputils';
import { IChatService, IChatMessage } from './tokens';
import { Message } from '@lumino/messaging';

/**
 * Props for ChatComponent
 */
interface IChatComponentProps {
  chatService: IChatService;
}

/**
 * React component for the chat interface
 */
const ChatComponent: React.FC<IChatComponentProps> = ({ chatService }) => {
  const [messages, setMessages] = useState<IChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Load existing messages
    setMessages(chatService.getHistory());

    // Listen for new messages
    const handleNewMessage = (sender: IChatService, message: IChatMessage) => {
      setMessages(prev => [...prev, message]);
      if (message.role === 'assistant') {
        setIsLoading(false);
      }
    };

    chatService.messageAdded.connect(handleNewMessage);

    return () => {
      chatService.messageAdded.disconnect(handleNewMessage);
    };
  }, [chatService]);

  useEffect(() => {
    // Scroll to bottom when new messages arrive
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async () => {
    console.log('ChatComponent.handleSendMessage called');
    console.log('Input value:', inputValue);
    console.log('Is loading:', isLoading);
    
    if (!inputValue.trim() || isLoading) {
      console.log('Returning early: empty input or loading');
      return;
    }

    const message = inputValue.trim();
    setInputValue('');
    setIsLoading(true);

    console.log('About to call chatService.sendMessage with:', message);
    try {
      await chatService.sendMessage(message);
      console.log('chatService.sendMessage completed successfully');
    } catch (error) {
      console.error('Failed to send message in handleSendMessage:', error);
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const clearChat = () => {
    chatService.clearHistory();
    setMessages([]);
  };

  const formatTimestamp = (timestamp: Date) => {
    return timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const renderMessage = (message: IChatMessage) => {
    const isUser = message.role === 'user';
    const isError = message.metadata?.error;

    return (
      <div
        key={message.id}
        className={`jp-Chat-message ${isUser ? 'jp-Chat-message-user' : 'jp-Chat-message-assistant'} ${
          isError ? 'jp-Chat-message-error' : ''
        }`}
      >
        <div className="jp-Chat-message-header">
          <span className="jp-Chat-message-role">
            {isUser ? 'You' : 'Assistant'}
          </span>
          <span className="jp-Chat-message-timestamp">
            {formatTimestamp(message.timestamp)}
          </span>
        </div>
        <div className="jp-Chat-message-content">
          {message.content}
        </div>
      </div>
    );
  };

  return (
    <div className="jp-Chat">
      <div className="jp-Chat-header">
        <h3>JupyterLab Assistant</h3>
        <button
          className="jp-Chat-clear-button"
          onClick={clearChat}
          title="Clear chat history"
        >
          Clear
        </button>
      </div>
      
      <div className="jp-Chat-messages">
        {messages.length === 0 ? (
          <div className="jp-Chat-welcome">
            <p>👋 Hi! I'm your JupyterLab assistant.</p>
            <p>I can help you with:</p>
            <ul>
              <li>Writing and explaining code</li>
              <li>Analyzing your notebook cells</li>
              <li>Executing and modifying cells</li>
              <li>Data analysis and visualization</li>
            </ul>
            <p>Try asking: "What's in cell 0?" or "Add a cell with print('hello')"</p>
          </div>
        ) : (
          messages.map(renderMessage)
        )}
        
        {isLoading && (
          <div className="jp-Chat-message jp-Chat-message-assistant jp-Chat-loading">
            <div className="jp-Chat-message-header">
              <span className="jp-Chat-message-role">Assistant</span>
            </div>
            <div className="jp-Chat-message-content">
              <div className="jp-Chat-typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      <div className="jp-Chat-input-container">
        <textarea
          className="jp-Chat-input"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask me anything about your notebook..."
          rows={3}
          disabled={isLoading}
        />
        <button
          className="jp-Chat-send-button"
          onClick={handleSendMessage}
          disabled={!inputValue.trim() || isLoading}
        >
          Send
        </button>
      </div>
    </div>
  );
};

/**
 * Chat widget implementation
 */
export class ChatWidget extends ReactWidget {
  private _chatService: IChatService;

  constructor(chatService: IChatService) {
    super();
    this._chatService = chatService;
    this.id = 'jupyterlab-chat-widget';
    this.addClass('jp-ChatWidget');
    this.title.label = 'Chat';
    this.title.caption = 'JupyterLab Assistant';
    this.title.iconClass = 'jp-MaterialIcon jp-ChatIcon';
  }

  protected render(): JSX.Element {
    return <ChatComponent chatService={this._chatService} />;
  }

  protected onActivateRequest(msg: Message): void {
    super.onActivateRequest(msg);
    // Focus the input when widget is activated
    const input = this.node.querySelector('.jp-Chat-input') as HTMLTextAreaElement;
    if (input) {
      input.focus();
    }
  }

  /**
   * Handle update requests.
   */
  protected onUpdateRequest(msg: Message): void {
    super.onUpdateRequest(msg);
  }

  /**
   * Get the chat service
   */
  get chatService(): IChatService {
    return this._chatService;
  }
} 