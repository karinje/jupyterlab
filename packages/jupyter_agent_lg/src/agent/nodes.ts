// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { AnalysisState, Decision, AnalysisPlan, PlanStep } from '../types';
import { JupyterBridge } from '../integrations/jupyter_bridge';
import { MCPConnector } from '../integrations/mcp_connector';
import { ChatHandler } from '../integrations/chat_handler';
import { LLMRouter } from './router';

/**
 * Individual node implementations for the LangGraph workflow
 */
export class AnalysisNodes {
  constructor(
    private jupyterBridge: JupyterBridge,
    private mcpConnector: MCPConnector,
    private chatHandler: ChatHandler,
    private llmRouter: LLMRouter
  ) {}

  /**
   * Core decision-making node - LLM analyzes context and decides next action
   */
  async analyzeAndDecide(state: AnalysisState): Promise<AnalysisState> {
    await this.chatHandler.sendStatus({
      type: 'progress',
      message: '🔍 Analyzing context and deciding next action...',
      step: 'analyze_and_decide'
    });

    try {
      // Get fresh notebook state
      const notebookCells = await this.jupyterBridge.getCellContent(state.notebookPath);
      
      // Build complete context for LLM
      const context = {
        user_request: state.originalRequest,
        conversation_history: state.conversationHistory,
        notebook_state: notebookCells,
        current_plan: state.plan,
        execution_history: state.executionHistory,
        completed_steps: state.completedSteps,
        available_data_sources: state.availableDataSources,
        available_actions: [
          'create_plan',      // Create analysis plan
          'execute_code',     // Write and run code
          'query_snowflake',  // Query external data
          'create_visualization',  // Make charts
          'handle_feedback',  // Process user input
          'complete_analysis'  // Finish analysis
        ]
      };

      // LLM makes decision with structured output
      const decision = await this.llmRouter.makeDecision(context);

      // Update state with decision
      const updatedState: AnalysisState = {
        ...state,
        notebookCells,
        nextAction: decision.action,
        actionParams: decision.params,
        reasoning: decision.reasoning,
        statusMessage: decision.statusMessage
      };

      // Send status update
      await this.chatHandler.sendStatus({
        type: 'progress',
        message: decision.statusMessage,
        step: decision.action
      });

      return updatedState;
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Decision making failed: ${error.message}`,
        step: 'analyze_and_decide'
      });
      throw error;
    }
  }

  /**
   * Create analysis plan node
   */
  async createPlan(state: AnalysisState): Promise<AnalysisState> {
    await this.chatHandler.sendStatus({
      type: 'progress',
      message: '📋 Creating analysis plan...',
      step: 'create_plan'
    });

    try {
      // LLM creates detailed plan based on request and context
      const plan = await this.llmRouter.createPlan(
        state.originalRequest,
        state.notebookCells,
        state.availableDataSources
      );

      // Display plan as interactive cards in chat UI
      await this.chatHandler.displayPlanCards(plan.steps.map(step => ({
        id: step.stepId,
        title: step.title,
        description: step.description,
        editable: true,
        type: step.type
      })));

      const updatedState: AnalysisState = {
        ...state,
        plan,
        statusMessage: `📋 Created ${plan.steps.length}-step analysis plan: "${plan.title}"`
      };

      return updatedState;
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Plan creation failed: ${error.message}`,
        step: 'create_plan'
      });
      throw error;
    }
  }

  /**
   * Execute code node
   */
  async executeCode(state: AnalysisState): Promise<AnalysisState> {
    const code = state.actionParams.code;
    const context = state.actionParams.context || '';
    
    await this.chatHandler.sendStatus({
      type: 'progress',
      message: `💻 Executing code: ${code.substring(0, 50)}...`,
      step: 'execute_code'
    });

    try {
      // Execute code using JupyterBridge
      const result = await this.jupyterBridge.insertCodeAndExecute(
        state.notebookPath,
        code,
        'code',
        'end'
      );

      // Update execution history
      const executionRecord = {
        cell_id: result.cell_id,
        code,
        outputs: result.outputs,
        execution_count: result.execution_count,
        timestamp: new Date().toISOString()
      };

      const updatedState: AnalysisState = {
        ...state,
        executionHistory: [...state.executionHistory, executionRecord],
        statusMessage: `✅ Code executed successfully (execution ${result.execution_count})`
      };

      // Send success status with output summary
      const outputSummary = result.outputs.length > 0 
        ? `Generated ${result.outputs.length} output(s)`
        : 'No outputs';
      
      await this.chatHandler.sendStatus({
        type: 'progress',
        message: `✅ Code executed: ${outputSummary}`,
        step: 'execute_code',
        data: { execution_count: result.execution_count, outputs: result.outputs.length }
      });

      return updatedState;
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Code execution failed: ${error.message}`,
        step: 'execute_code'
      });
      throw error;
    }
  }

  /**
   * Query Snowflake node
   */
  async querySnowflake(state: AnalysisState): Promise<AnalysisState> {
    const query = state.actionParams.query;
    const variableName = state.actionParams.variable_name || 'df';
    
    await this.chatHandler.sendStatus({
      type: 'progress',
      message: '🗄️ Querying Snowflake database...',
      step: 'query_snowflake'
    });

    try {
      // Execute query via MCP Snowflake
      const queryResult = await this.mcpConnector.executeQuery(query);
      
      // Generate code to load data into notebook
      const loadCode = `
# Data loaded from Snowflake
import pandas as pd
${variableName} = pd.DataFrame(${JSON.stringify(queryResult.data)})
print(f"Loaded {len(${variableName})} rows into variable '${variableName}'")
${variableName}.head()
      `.trim();

      // Execute the data loading code
      const result = await this.jupyterBridge.insertCodeAndExecute(
        state.notebookPath,
        loadCode,
        'code',
        'end'
      );

      // Update execution history
      const executionRecord = {
        cell_id: result.cell_id,
        code: loadCode,
        outputs: result.outputs,
        execution_count: result.execution_count,
        timestamp: new Date().toISOString()
      };

      const updatedState: AnalysisState = {
        ...state,
        executionHistory: [...state.executionHistory, executionRecord],
        statusMessage: `🗄️ Loaded ${queryResult.data.length} rows from Snowflake into '${variableName}'`
      };

      await this.chatHandler.sendStatus({
        type: 'progress',
        message: `✅ Data loaded: ${queryResult.data.length} rows`,
        step: 'query_snowflake',
        data: { rows: queryResult.data.length, variable: variableName }
      });

      return updatedState;
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Snowflake query failed: ${error.message}`,
        step: 'query_snowflake'
      });
      throw error;
    }
  }

  /**
   * Create visualization node
   */
  async createVisualization(state: AnalysisState): Promise<AnalysisState> {
    const vizType = state.actionParams.viz_type || 'auto';
    const dataVariable = state.actionParams.data_variable || 'df';
    const title = state.actionParams.title || 'Data Visualization';
    
    await this.chatHandler.sendStatus({
      type: 'progress',
      message: `📊 Creating ${vizType} visualization...`,
      step: 'create_visualization'
    });

    try {
      // Generate visualization code based on type and data
      const vizCode = await this.llmRouter.generateVisualizationCode(
        vizType,
        dataVariable,
        title,
        state.notebookCells
      );

      // Execute visualization code
      const result = await this.jupyterBridge.insertCodeAndExecute(
        state.notebookPath,
        vizCode,
        'code',
        'end'
      );

      // Update execution history
      const executionRecord = {
        cell_id: result.cell_id,
        code: vizCode,
        outputs: result.outputs,
        execution_count: result.execution_count,
        timestamp: new Date().toISOString()
      };

      const updatedState: AnalysisState = {
        ...state,
        executionHistory: [...state.executionHistory, executionRecord],
        statusMessage: `📊 Created ${vizType} visualization: "${title}"`
      };

      await this.chatHandler.sendStatus({
        type: 'progress',
        message: `✅ Visualization created: ${title}`,
        step: 'create_visualization',
        data: { type: vizType, outputs: result.outputs.length }
      });

      return updatedState;
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Visualization failed: ${error.message}`,
        step: 'create_visualization'
      });
      throw error;
    }
  }

  /**
   * Handle user feedback node
   */
  async handleFeedback(state: AnalysisState): Promise<AnalysisState> {
    const feedback = state.actionParams.feedback;
    
    await this.chatHandler.sendStatus({
      type: 'progress',
      message: '💬 Processing user feedback...',
      step: 'handle_feedback'
    });

    try {
      // Add feedback to conversation history
      const updatedConversation = [
        ...state.conversationHistory,
        { role: 'user', content: feedback }
      ];

      // LLM processes feedback and decides how to adapt
      const adaptation = await this.llmRouter.processFeedback(
        feedback,
        state.plan,
        state.executionHistory
      );

      const updatedState: AnalysisState = {
        ...state,
        conversationHistory: updatedConversation,
        plan: adaptation.updatedPlan || state.plan,
        statusMessage: `💬 Feedback processed: ${adaptation.summary}`
      };

      await this.chatHandler.sendStatus({
        type: 'progress',
        message: `✅ Feedback processed: ${adaptation.summary}`,
        step: 'handle_feedback'
      });

      return updatedState;
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Feedback processing failed: ${error.message}`,
        step: 'handle_feedback'
      });
      throw error;
    }
  }

  /**
   * Complete analysis node
   */
  async completeAnalysis(state: AnalysisState): Promise<AnalysisState> {
    await this.chatHandler.sendStatus({
      type: 'progress',
      message: '📝 Completing analysis and generating summary...',
      step: 'complete_analysis'
    });

    try {
      // Generate analysis summary
      const summary = await this.llmRouter.generateSummary(
        state.originalRequest,
        state.executionHistory,
        state.plan
      );

      // Create summary markdown cell
      const summaryMarkdown = `
## Analysis Summary

**Original Request:** ${state.originalRequest}

**Key Findings:**
${summary.keyFindings.map(finding => `- ${finding}`).join('\n')}

**Executed Steps:**
${state.executionHistory.map((exec, i) => `${i + 1}. Execution ${exec.execution_count}: ${exec.code.split('\n')[0]}...`).join('\n')}

**Recommendations:**
${summary.recommendations.map(rec => `- ${rec}`).join('\n')}

---
*Analysis completed on ${new Date().toLocaleString()}*
      `.trim();

      await this.jupyterBridge.insertMarkdown(state.notebookPath, summaryMarkdown, 'end');

      const updatedState: AnalysisState = {
        ...state,
        isComplete: true,
        statusMessage: `🎉 Analysis completed successfully! Generated summary with ${summary.keyFindings.length} key findings.`
      };

      await this.chatHandler.sendStatus({
        type: 'complete',
        message: '🎉 Analysis completed successfully!',
        step: 'complete_analysis',
        data: { 
          executions: state.executionHistory.length,
          findings: summary.keyFindings.length 
        }
      });

      return updatedState;
    } catch (error) {
      await this.chatHandler.sendStatus({
        type: 'error',
        message: `❌ Analysis completion failed: ${error.message}`,
        step: 'complete_analysis'
      });
      throw error;
    }
  }
} 