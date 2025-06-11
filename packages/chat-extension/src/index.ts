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

import { ICommandPalette, WidgetTracker } from '@jupyterlab/apputils';

import { INotebookTracker } from '@jupyterlab/notebook';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

import {
  ChatWidget,
  ChatService,
  CellManager,
  OpenAIProvider,
  ClaudeProvider,
  LocalProvider,
  ICellManager,
  ILLMProvider
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
    
    // Widget tracker
    const chatTracker = new WidgetTracker<ChatWidget>({
      namespace: 'chat'
    });

    // Settings handling
    let settings: ISettingRegistry.ISettings;
    
    const updateProvider = () => {
      if (!settings) return;
      
      const provider = settings.get('provider').composite as string;
      
      switch (provider) {
        case 'openai':
          const openaiKey = settings.get('openaiApiKey').composite as string;
          const openaiModel = settings.get('openaiModel').composite as string;
          llmProvider = new OpenAIProvider(openaiKey);
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
          llmProvider = new OpenAIProvider();
      }
      
      // Update existing chat services
      chatTracker.forEach(widget => {
        widget.chatService.setLLMProvider(llmProvider);
      });
    };

    // Load settings
    settingRegistry
      .load(plugin.id)
      .then(loadedSettings => {
        settings = loadedSettings;
        updateProvider();
        
        // Listen for settings changes
        settings.changed.connect(() => {
          updateProvider();
        });
      })
      .catch(reason => {
        console.error('Failed to load settings for chat extension:', reason);
        // Fallback to default OpenAI provider
        llmProvider = new OpenAIProvider();
      });

    // Create chat widget factory
    const createChatWidget = (): ChatWidget => {
      const chatService = new ChatService(llmProvider, cellManager);
      const widget = new ChatWidget(chatService);
      
      // Track the widget
      chatTracker.add(widget);
      
      return widget;
    };

    // Add commands
    app.commands.addCommand(commandIDs.open, {
      label: 'Open Chat',
      caption: 'Open the chat panel',
      execute: () => {
        // Check if chat widget already exists
        let widget = chatTracker.currentWidget;
        
        if (!widget || widget.isDisposed) {
          widget = createChatWidget();
          app.shell.add(widget, 'right', { rank: 200 });
        }
        
        if (!widget.isAttached) {
          app.shell.add(widget, 'right', { rank: 200 });
        }
        
        app.shell.activateById(widget.id);
      }
    });

    app.commands.addCommand(commandIDs.toggle, {
      label: 'Toggle Chat',
      caption: 'Toggle the chat panel',
      execute: () => {
        const widget = chatTracker.currentWidget;
        
        if (widget && !widget.isDisposed) {
          if (widget.isVisible) {
            widget.hide();
          } else {
            widget.show();
            app.shell.activateById(widget.id);
          }
        } else {
          app.commands.execute(commandIDs.open);
        }
      }
    });

    app.commands.addCommand(commandIDs.clear, {
      label: 'Clear Chat History',
      caption: 'Clear the chat conversation history',
      execute: () => {
        const widget = chatTracker.currentWidget;
        if (widget && !widget.isDisposed) {
          widget.chatService.clearHistory();
        }
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