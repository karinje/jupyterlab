// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { StatusUpdate } from '../types';

/**
 * Handler for communicating with the existing chat extension
 * Sends status updates, plan cards, and other UI interactions
 */
export class ChatHandler {
  private serverUrl: string;
  private webSocket?: WebSocket;
  private chatServiceUrl: string;

  constructor(serverUrl: string) {
    this.serverUrl = serverUrl;
    this.chatServiceUrl = `${serverUrl.replace('http', 'ws')}/api/chat/ws`;
  }

  /**
   * Initialize WebSocket connection to chat service
   */
  async initialize(): Promise<void> {
    try {
      await this._connectWebSocket();
    } catch (error) {
      console.warn('Failed to initialize chat WebSocket, using HTTP fallback:', error);
      // Continue without WebSocket - will use HTTP for status updates
    }
  }

  /**
   * Send status update to chat UI
   */
  async sendStatus(status: StatusUpdate): Promise<void> {
    try {
      if (this.webSocket && this.webSocket.readyState === WebSocket.OPEN) {
        // Send via WebSocket for real-time updates
        this.webSocket.send(JSON.stringify({
          type: 'agent_status',
          data: status
        }));
      } else {
        // Fallback to HTTP
        await this._sendStatusHTTP(status);
      }
    } catch (error) {
      console.warn('Failed to send status update:', error);
    }
  }

  /**
   * Display interactive plan cards in chat UI
   */
  async displayPlanCards(cards: Array<{
    id: string;
    title: string;
    description: string;
    editable: boolean;
    type?: string;
  }>): Promise<void> {
    try {
      const message = {
        type: 'agent_plan_cards',
        data: {
          cards,
          timestamp: new Date().toISOString()
        }
      };

      if (this.webSocket && this.webSocket.readyState === WebSocket.OPEN) {
        this.webSocket.send(JSON.stringify(message));
      } else {
        await this._sendMessageHTTP(message);
      }
    } catch (error) {
      console.warn('Failed to display plan cards:', error);
    }
  }

  /**
   * Send agent message to chat
   */
  async sendMessage(
    message: string,
    messageType: 'info' | 'success' | 'warning' | 'error' = 'info'
  ): Promise<void> {
    try {
      const chatMessage = {
        type: 'agent_message',
        data: {
          message,
          messageType,
          timestamp: new Date().toISOString(),
          sender: 'jupyter_agent_lg'
        }
      };

      if (this.webSocket && this.webSocket.readyState === WebSocket.OPEN) {
        this.webSocket.send(JSON.stringify(chatMessage));
      } else {
        await this._sendMessageHTTP(chatMessage);
      }
    } catch (error) {
      console.warn('Failed to send chat message:', error);
    }
  }

  /**
   * Send progress update with percentage
   */
  async sendProgress(
    message: string,
    percentage: number,
    step?: string
  ): Promise<void> {
    await this.sendStatus({
      type: 'progress',
      message,
      step,
      progress: percentage
    });
  }

  /**
   * Send completion message
   */
  async sendCompletion(message: string, data?: any): Promise<void> {
    await this.sendStatus({
      type: 'complete',
      message,
      data
    });
  }

  /**
   * Send error message
   */
  async sendError(message: string, error?: any): Promise<void> {
    await this.sendStatus({
      type: 'error',
      message,
      data: error ? { error: error.message || error } : undefined
    });
  }

  /**
   * Request user input (for interactive workflows)
   */
  async requestUserInput(
    prompt: string,
    inputType: 'text' | 'choice' | 'confirmation' = 'text',
    options?: string[]
  ): Promise<void> {
    try {
      const request = {
        type: 'agent_input_request',
        data: {
          prompt,
          inputType,
          options,
          timestamp: new Date().toISOString()
        }
      };

      if (this.webSocket && this.webSocket.readyState === WebSocket.OPEN) {
        this.webSocket.send(JSON.stringify(request));
      } else {
        await this._sendMessageHTTP(request);
      }
    } catch (error) {
      console.warn('Failed to request user input:', error);
    }
  }

  /**
   * Show analysis results summary
   */
  async showAnalysisSummary(summary: {
    title: string;
    keyFindings: string[];
    recommendations: string[];
    executionCount: number;
    duration?: string;
  }): Promise<void> {
    try {
      const message = {
        type: 'agent_analysis_summary',
        data: {
          ...summary,
          timestamp: new Date().toISOString()
        }
      };

      if (this.webSocket && this.webSocket.readyState === WebSocket.OPEN) {
        this.webSocket.send(JSON.stringify(message));
      } else {
        await this._sendMessageHTTP(message);
      }
    } catch (error) {
      console.warn('Failed to show analysis summary:', error);
    }
  }

  /**
   * Close connections
   */
  async dispose(): Promise<void> {
    if (this.webSocket) {
      this.webSocket.close();
      this.webSocket = undefined;
    }
  }

  /**
   * Private methods
   */
  private async _connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.webSocket = new WebSocket(this.chatServiceUrl);
        
        this.webSocket.onopen = () => {
          console.log('Chat WebSocket connected');
          resolve();
        };

        this.webSocket.onerror = (error) => {
          console.warn('Chat WebSocket error:', error);
          reject(error);
        };

        this.webSocket.onclose = () => {
          console.log('Chat WebSocket disconnected');
          // Attempt to reconnect after delay
          setTimeout(() => this._reconnectWebSocket(), 5000);
        };

        this.webSocket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this._handleIncomingMessage(message);
          } catch (error) {
            console.warn('Failed to parse WebSocket message:', error);
          }
        };

        // Timeout if connection takes too long
        setTimeout(() => {
          if (this.webSocket?.readyState !== WebSocket.OPEN) {
            reject(new Error('WebSocket connection timeout'));
          }
        }, 5000);
      } catch (error) {
        reject(error);
      }
    });
  }

  private async _reconnectWebSocket(): Promise<void> {
    try {
      await this._connectWebSocket();
    } catch (error) {
      console.warn('WebSocket reconnection failed, will retry:', error);
      setTimeout(() => this._reconnectWebSocket(), 10000);
    }
  }

  private _handleIncomingMessage(message: any): void {
    // Handle incoming messages from chat (user responses, etc.)
    switch (message.type) {
      case 'user_response':
        // Handle user responses to agent requests
        console.log('Received user response:', message.data);
        break;
      case 'plan_card_edited':
        // Handle plan card edits from user
        console.log('Plan card edited:', message.data);
        break;
      default:
        console.log('Received chat message:', message);
    }
  }

  private async _sendStatusHTTP(status: StatusUpdate): Promise<void> {
    try {
      const response = await fetch(`${this.serverUrl}/api/chat/status`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(status)
      });

      if (!response.ok) {
        throw new Error(`HTTP status update failed: ${response.status}`);
      }
    } catch (error) {
      console.warn('HTTP status update failed:', error);
    }
  }

  private async _sendMessageHTTP(message: any): Promise<void> {
    try {
      const response = await fetch(`${this.serverUrl}/api/chat/message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(message)
      });

      if (!response.ok) {
        throw new Error(`HTTP message send failed: ${response.status}`);
      }
    } catch (error) {
      console.warn('HTTP message send failed:', error);
    }
  }
} 