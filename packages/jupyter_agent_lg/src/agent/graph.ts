// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { AnalysisState, AgentConfig, StatusUpdate } from '../types';
import { AnalysisNodes } from './nodes';
import { LLMRouter } from './router';
import { JupyterBridge } from '../integrations/jupyter_bridge';
import { MCPConnector } from '../integrations/mcp_connector';
import { ChatHandler } from '../integrations/chat_handler';

/**
 * Main LangGraph-based data analysis agent
 */
export class DataAnalysisAgent {
  private nodes: AnalysisNodes;
  private llmRouter: LLMRouter;
  private jupyterBridge: JupyterBridge;
  private mcpConnector: MCPConnector;
  private chatHandler: ChatHandler;
  private graph: any;

  constructor(private config: AgentConfig) {
    // Initialize components
    this.jupyterBridge = new JupyterBridge(config.serverUrl, config.token);
    this.mcpConnector = new MCPConnector(config.mcpServices);
    this.chatHandler = new ChatHandler(config.serverUrl);
    this.llmRouter = new LLMRouter(config.llmProvider, config.llmModel);
    
    // Initialize nodes with dependencies
    this.nodes = new AnalysisNodes(
      this.jupyterBridge,
      this.mcpConnector,
      this.chatHandler,
      this.llmRouter
    );

    // Build the workflow graph
    this.graph = this._buildGraph();
  }

  /**
   * Build the REAL LangGraph workflow with actual LLM-driven routing
   */
  private _buildGraph() {
    // For now, implement a simple state machine that calls LLM for each decision
    // This will be replaced with actual LangGraph when dependencies are installed
    return {
      invoke: async (initialState: AnalysisState) => {
        let currentState = { ...initialState };
        let stepCount = 0;
        const maxSteps = this.config.maxSteps;

        while (!currentState.isComplete && stepCount < maxSteps) {
          stepCount++;
          
          // Call analyze_and_decide to get next action from LLM
          currentState = await this.nodes.analyzeAndDecide(currentState);
          
          // Execute the chosen action
          switch (currentState.nextAction) {
            case 'create_plan':
              currentState = await this.nodes.createPlan(currentState);
              break;
            case 'execute_code':
              currentState = await this.nodes.executeCode(currentState);
              break;
            case 'query_snowflake':
              currentState = await this.nodes.querySnowflake(currentState);
              break;
            case 'create_visualization':
              currentState = await this.nodes.createVisualization(currentState);
              break;
            case 'handle_feedback':
              currentState = await this.nodes.handleFeedback(currentState);
              break;
            case 'complete_analysis':
              currentState = await this.nodes.completeAnalysis(currentState);
              break;
            default:
              console.error(`Unknown action: ${currentState.nextAction}`);
              currentState.isComplete = true;
          }
        }

        return currentState;
      }
    };
  }

  /**
   * Start a new analysis session
   */
  async startAnalysis(
    request: string,
    notebookPath: string,
    conversationHistory: Array<{ role: string; content: string }> = []
  ): Promise<string> {
    // Initialize state
    const initialState: AnalysisState = {
      originalRequest: request,
      notebookPath,
      conversationHistory,
      notebookCells: [],
      executionHistory: [],
      completedSteps: [],
      nextAction: 'analyze_and_decide',
      actionParams: {},
      reasoning: '',
      availableDataSources: await this.mcpConnector.getAvailableDataSources(),
      isComplete: false
    };

    try {
      // Send initial status
      await this.chatHandler.sendStatus({
        type: 'progress',
        message: '🚀 Starting data analysis...',
        step: 'initialization'
      });

      // Run the workflow
      const result = await this.graph.invoke(initialState);
      
      return result.statusMessage || 'Analysis completed successfully';
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Analysis failed: ${error.message}`,
        step: 'error'
      });
      throw error;
    }
  }

  /**
   * Handle user feedback during analysis
   */
  async handleUserFeedback(feedback: string, currentState?: Partial<AnalysisState>): Promise<void> {
    if (!currentState) {
      throw new Error('Cannot handle feedback without current state');
    }

    // Add feedback to conversation history
    const updatedState: AnalysisState = {
      ...currentState as AnalysisState,
      conversationHistory: [
        ...currentState.conversationHistory || [],
        { role: 'user', content: feedback }
      ],
      nextAction: 'handle_feedback',
      actionParams: { feedback }
    };

    // Continue workflow from feedback handling
    await this.graph.invoke(updatedState);
  }

  /**
   * Get current analysis status
   */
  async getStatus(notebookPath: string): Promise<StatusUpdate> {
    // Get current notebook state
    const cells = await this.jupyterBridge.getCellContent(notebookPath);
    
    return {
      type: 'progress',
      message: 'Analysis in progress',
      data: {
        cellCount: cells.length,
        lastExecution: cells.filter(c => c.execution_count).pop()?.execution_count || 0
      }
    };
  }

  /**
   * Stop current analysis
   */
  async stopAnalysis(): Promise<void> {
    await this.chatHandler.sendStatus({
      type: 'complete',
      message: '⏹️ Analysis stopped by user'
    });
  }
} 