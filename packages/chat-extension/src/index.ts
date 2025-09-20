// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.
/**
 * @packageDocumentation
 * @module chat-extension
 */

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette } from '@jupyterlab/apputils';

import { INotebookTracker } from '@jupyterlab/notebook';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import {
  CellManager,
  ChatManager,
  ChatService,
  ClaudeProvider,
  ICellManager,
  ILLMProvider,
  LocalProvider,
  OpenAIProvider
} from '@jupyterlab/chat';

import { commandIDs } from './commands';

/**
 * Initialization data for the chat extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/chat-extension:plugin',
  description: 'Chat extension for JupyterLab',
  autoStart: true,
  requires: [INotebookTracker, ISettingRegistry],
  optional: [ICommandPalette],
  activate: (
    app: JupyterFrontEnd,
    notebookTracker: INotebookTracker,
    settingRegistry: ISettingRegistry,
    palette: ICommandPalette | null
  ) => {
    console.log('🌟🌟🌟 CHAT EXTENSION ACTIVATING - NEW VERSION! 🌟🌟🌟');
    console.log('🔥🔥🔥 TOTALLY NEW MESSAGE - CHANGED VERSION! 🔥🔥🔥');

    // Create services
    let llmProvider: ILLMProvider;
    const cellManager: ICellManager = new CellManager(notebookTracker);

    // Settings handling
    let settings: ISettingRegistry.ISettings;

    const updateProvider = async () => {
      if (!settings) return;

      const provider = settings.get('provider').composite as string;

      switch (provider) {
        case 'openai':
          const openaiKey = settings.get('openaiApiKey').composite as string;
          const openaiModel = settings.get('openaiModel').composite as string;
          llmProvider = new OpenAIProvider(openaiKey || '');
          llmProvider.setModel(openaiModel);
          break;

        case 'claude':
          const claudeKey = settings.get('claudeApiKey').composite as string;
          const claudeModel = settings.get('claudeModel').composite as string;
          llmProvider = new ClaudeProvider(claudeKey);
          llmProvider.setModel(claudeModel);
          break;

        case 'local':
          const localUrl = settings.get('localUrl').composite as string;
          const localModel = settings.get('localModel').composite as string;
          llmProvider = new LocalProvider(localUrl);
          llmProvider.setModel(localModel);
          break;

        default:
          llmProvider = new OpenAIProvider('');
      }

      // Configure MCP servers if available
      const mcpServers = settings.get('mcpServers').composite as any;
      if (mcpServers && Object.keys(mcpServers).length > 0) {
        console.log(
          '🔧 Configuring MCP servers from settings:',
          Object.keys(mcpServers)
        );

        // If we have a chat service, configure MCP servers
        if (globalChatService) {
          try {
            await globalChatService.setMCPServers(mcpServers);
            console.log('✅ MCP servers configured for existing chat service');
          } catch (error) {
            console.error('❌ Failed to configure MCP servers:', error);
          }
        }
      }

      // Update existing chat services
      if (globalChatService) {
        globalChatService.setLLMProvider(llmProvider);
      }
    };

    // Load settings
    settingRegistry
      .load(plugin.id)
      .then(loadedSettings => {
        settings = loadedSettings;
        updateProvider();

        // Listen for settings changes
        settings.changed.connect(() => {
          updateProvider().catch(error => {
            console.error(
              'Failed to update provider after settings change:',
              error
            );
          });
        });
      })
      .catch(reason => {
        console.error('Failed to load settings for chat extension:', reason);
        // Fallback to default OpenAI provider
        llmProvider = new OpenAIProvider('');
      });

    // Global chat service (pure service, no widget)
    let globalChatService: ChatService | null = null;
    let globalChatManager: ChatManager | null = null;

    // Hard singleton guard across potential multiple activations
    const __w = (window as any);
    if (__w.__JLAB_CHAT_SERVICE && __w.__JLAB_CHAT_MANAGER) {
      globalChatService = __w.__JLAB_CHAT_SERVICE as ChatService;
      globalChatManager = __w.__JLAB_CHAT_MANAGER as ChatManager;
    }

    const ensureChatService = async (): Promise<{
      chatService: ChatService;
      chatManager: ChatManager;
    }> => {
      if (!globalChatService || !globalChatManager) {
        globalChatService = new ChatService(llmProvider, cellManager);
        globalChatManager = new ChatManager(globalChatService);
        __w.__JLAB_CHAT_SERVICE = globalChatService;
        __w.__JLAB_CHAT_MANAGER = globalChatManager;

        // Configure MCP servers for new chat service
        if (settings) {
          const mcpServers = settings.get('mcpServers').composite as any;
          if (mcpServers && Object.keys(mcpServers).length > 0) {
            try {
              await globalChatService.setMCPServers(mcpServers);
              console.log('✅ MCP servers configured for new chat service');
            } catch (error) {
              console.error(
                '❌ Failed to configure MCP servers for new chat service:',
                error
              );
            }
          }
        }

        // Open WS stream for the active notebook and load conversation history
        try {
          const path = cellManager.getActiveNotebookPath?.() || null;
          globalChatService.connectStream?.(path);
          
          // Load conversation history for the active notebook
          if (path) {
            await globalChatService.loadConversationHistory(path);
          }
        } catch (e) {
          console.warn('WS connect on startup failed:', e);
        }

        // Reconnect WS on notebook change and load conversation history (set once)
        if (!__w.__JLAB_CHAT_WATCH_BOUND) {
          notebookTracker.currentChanged.connect(async () => {
            try {
              const newPath = cellManager.getActiveNotebookPath?.() || null;
              console.log('🔥 [Extension] Notebook changed to:', newPath);
              
              if (newPath) {
                // Enhanced notebook switching with UI clearing
                console.log('🔥 [Extension] Starting enhanced notebook switch process...');
                
                // First, reconnect WebSocket to new notebook
                globalChatService?.connectStream?.(newPath);
                
                // Then load conversation history with UI clearing
                if (globalChatService?.loadConversationHistory) {
                  console.log('🔥 [Extension] Calling loadConversationHistory with clearUI=true');
                  await globalChatService.loadConversationHistory(newPath, true); // clearUI = true
                }
                
                console.log('🔥 [Extension] Enhanced notebook switch completed for:', newPath);
              } else {
                console.log('🔥 [Extension] No active notebook path detected');
                // Still try to reconnect WebSocket
                globalChatService?.connectStream?.(null);
              }
            } catch (e) {
              console.warn('🔥 [Extension] Enhanced notebook switch failed:', e);
              // Fallback to basic reconnection
              try {
                const fallbackPath = cellManager.getActiveNotebookPath?.() || null;
                globalChatService?.connectStream?.(fallbackPath);
              } catch (fallbackError) {
                console.warn('🔥 [Extension] Fallback WS reconnect also failed:', fallbackError);
              }
            }
          });
          __w.__JLAB_CHAT_WATCH_BOUND = true;
        }
      }
      return { chatService: globalChatService, chatManager: globalChatManager };
    };

    // Add commands
    app.commands.addCommand(commandIDs.open, {
      label: 'Open Chat',
      caption: 'Open the floating chat dialog',
      execute: async () => {
        console.log('🔥 Open chat command executed');
        const { chatManager } = await ensureChatService();
        chatManager.show();
      }
    });

    app.commands.addCommand(commandIDs.toggle, {
      label: 'Toggle Chat',
      caption: 'Toggle the floating chat dialog',
      execute: async () => {
        console.log('🔥 Toggle chat command executed');
        const { chatManager } = await ensureChatService();
        await chatManager.toggle();
      }
    });

    // Add keyboard shortcut for quick access
    app.commands.addKeyBinding({
      command: commandIDs.toggle,
      keys: ['Ctrl Shift Space'],
      selector: 'body'
    });

    app.commands.addCommand(commandIDs.clear, {
      label: 'Clear Chat History',
      caption: 'Clear the chat conversation history',
      execute: async () => {
        const { chatService } = await ensureChatService();
        chatService.clearHistory();
      }
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: commandIDs.open,
        category: 'Chat'
      });

      palette.addItem({
        command: commandIDs.clear,
        category: 'Chat'
      });
    }

    // Add to main menu (if available) - commenting out as this property doesn't exist in all JupyterLab versions
    // const mainMenu = app.menu;
    // if (mainMenu) {
    //   // Add to View menu
    //   mainMenu.viewMenu.addGroup([
    //     { command: commandIDs.toggle }
    //   ], 100);
    // }

    // Auto-open chat panel on startup (optional)
    app.restored.then(() => {
      // Uncomment to auto-open chat on startup
      // app.commands.execute(commandIDs.open);
    });
  }
};

export default plugin;
