// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

/**
 * State interface for the LangGraph data analysis workflow
 */
export interface AnalysisState {
  // Core context
  originalRequest: string;
  notebookPath: string;
  conversationHistory: Array<{ role: string; content: string }>;
  
  // Notebook state
  notebookCells: Array<{
    type: string;
    source: string;
    execution_count?: number;
    outputs?: Array<any>;
    cell_id?: string;
  }>;
  executionHistory: Array<{
    cell_id: string;
    code: string;
    outputs: Array<any>;
    execution_count: number;
    timestamp: string;
  }>;
  
  // Planning
  plan?: AnalysisPlan;
  completedSteps: string[];
  
  // LLM decisions
  nextAction: string;
  actionParams: Record<string, any>;
  reasoning: string;
  
  // External resources
  availableDataSources: Array<{
    name: string;
    type: string;
    description: string;
    connection_info?: Record<string, any>;
  }>;
  
  // Control
  isComplete: boolean;
  currentStep?: string;
  statusMessage?: string;
}

/**
 * Analysis plan structure
 */
export interface AnalysisPlan {
  title: string;
  description: string;
  steps: PlanStep[];
  estimatedTime?: string;
  dependencies?: string[];
}

/**
 * Individual plan step
 */
export interface PlanStep {
  stepId: string;
  title: string;
  description: string;
  type: 'data_loading' | 'analysis' | 'visualization' | 'documentation';
  dependencies?: string[];
  isComplete: boolean;
  estimatedTime?: string;
  code?: string;
  outputs?: Array<any>;
}

/**
 * LLM decision structure
 */
export interface Decision {
  action: string;
  params: Record<string, any>;
  reasoning: string;
  statusMessage: string;
  confidence: number;
}

/**
 * Available actions for the LangGraph agent
 */
export type AgentAction = 
  | 'create_plan'
  | 'execute_code' 
  | 'query_snowflake'
  | 'create_visualization'
  | 'handle_feedback'
  | 'complete_analysis'
  | 'analyze_data'
  | 'document_findings';

/**
 * Configuration for the LangGraph agent
 */
export interface AgentConfig {
  serverUrl: string;
  token: string;
  defaultNotebook?: string;
  llmProvider: 'openai' | 'anthropic' | 'local';
  llmModel: string;
  maxSteps: number;
  enableMCP: boolean;
  mcpServices: string[];
}

/**
 * Status update for real-time communication
 */
export interface StatusUpdate {
  type: 'progress' | 'error' | 'complete' | 'waiting_for_input';
  message: string;
  step?: string;
  progress?: number;
  data?: any;
} 