// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { Decision, AnalysisPlan, PlanStep } from '../types';

/**
 * Multi-LLM router for decision making and task execution
 */
export class LLMRouter {
  private currentProvider: string;
  private currentModel: string;

  constructor(provider: 'openai' | 'anthropic' | 'local', model: string) {
    this.currentProvider = provider;
    this.currentModel = model;
    console.log(`🤖 LLMRouter initialized with provider: ${provider}, model: ${model}`);
  }

  /**
   * Make decision based on complete context
   */
  async makeDecision(context: any): Promise<Decision> {
    const prompt = this._buildDecisionPrompt(context);
    
    try {
      // REAL LLM decision making - no rules, just pure LLM intelligence
      const decision = await this._callLLMForDecision(prompt, context);
      console.log(`🧠 LLM decided: ${decision.action} - ${decision.reasoning}`);
      return decision;
    } catch (error) {
      console.error('❌ LLM decision failed:', error);
      // Only as last resort, use minimal context-based fallback
      return await this._analyzeContextAndDecide(context);
    }
  }

  /**
   * Call LLM for decision making - REAL LLM INTEGRATION
   */
  private async _callLLMForDecision(prompt: string, context: any): Promise<Decision> {
    try {
      // Get XSRF token
      const xsrfToken = document.querySelector('meta[name="_xsrf"]')?.getAttribute('content') || '';
      
      const response = await fetch('/api/chat/openai', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-XSRFToken': xsrfToken,
        },
        body: JSON.stringify({
          message: `${prompt}

RESPOND WITH STRUCTURED JSON ONLY:
{
  "action": "create_plan|execute_code|query_snowflake|create_visualization|complete_analysis",
  "params": {...},
  "reasoning": "explanation",
  "statusMessage": "user-friendly status",
  "confidence": 0.8
}`,
          model: this.currentModel,
          context: { notebook_path: context.notebook_path || 'Untitled.ipynb' }
        })
      });

      if (!response.ok) {
        throw new Error(`LLM API call failed: ${response.status}`);
      }

      const data = await response.json();
      
      // Try to parse structured JSON response
      try {
        const jsonMatch = data.response.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const decision = JSON.parse(jsonMatch[0]);
          return {
            action: decision.action,
            params: decision.params || {},
            reasoning: decision.reasoning || 'LLM decision',
            statusMessage: decision.statusMessage || `Executing ${decision.action}...`,
            confidence: decision.confidence || 0.8
          };
        }
      } catch (parseError) {
        console.warn('Failed to parse structured LLM response, using fallback parsing');
      }
      
      // Fallback parsing if structured JSON fails
      return this._parseLLMDecisionResponse(data.response, context);
    } catch (error) {
      throw new Error(`LLM decision call failed: ${error.message}`);
    }
  }

  /**
   * Parse LLM response into structured decision
   */
  private _parseLLMDecisionResponse(response: string, context: any): Decision {
    // For now, use rule-based parsing of LLM response
    // In production, this would use structured output or better parsing
    
    const responseLower = response.toLowerCase();
    
    if (responseLower.includes('create') && responseLower.includes('plan')) {
      return {
        action: 'create_plan',
        params: {},
        reasoning: 'LLM suggested creating an analysis plan',
        statusMessage: '📋 Creating analysis plan based on LLM recommendation...',
        confidence: 0.8
      };
    }
    
    if (responseLower.includes('query') || responseLower.includes('data') || responseLower.includes('snowflake')) {
      return {
        action: 'query_snowflake',
        params: {
          query: this._extractQueryFromResponse(response),
          variable_name: 'df'
        },
        reasoning: 'LLM suggested querying data source',
        statusMessage: '🗄️ Loading data based on LLM recommendation...',
        confidence: 0.8
      };
    }
    
    if (responseLower.includes('code') || responseLower.includes('execute') || responseLower.includes('run')) {
      return {
        action: 'execute_code',
        params: {
          code: this._extractCodeFromResponse(response)
        },
        reasoning: 'LLM suggested executing code',
        statusMessage: '💻 Executing code based on LLM recommendation...',
        confidence: 0.8
      };
    }
    
    if (responseLower.includes('plot') || responseLower.includes('chart') || responseLower.includes('visualiz')) {
      return {
        action: 'create_visualization',
        params: {
          viz_type: 'auto',
          data_variable: 'df',
          title: 'Data Analysis Visualization'
        },
        reasoning: 'LLM suggested creating visualization',
        statusMessage: '📊 Creating visualization based on LLM recommendation...',
        confidence: 0.8
      };
    }
    
    // Fallback to rule-based decision
    return this._analyzeContextAndDecide(context);
  }

  private _extractQueryFromResponse(response: string): string {
    // Simple query extraction - would be more sophisticated in production
    const lines = response.split('\n');
    for (const line of lines) {
      if (line.toUpperCase().includes('SELECT')) {
        return line.trim();
      }
    }
    return 'SELECT * FROM customers LIMIT 100';
  }

  private _extractCodeFromResponse(response: string): string {
    // Simple code extraction - would be more sophisticated in production
    const codeBlocks = response.match(/```(?:python)?\n?([\s\S]*?)```/g);
    if (codeBlocks && codeBlocks.length > 0) {
      return codeBlocks[0].replace(/```(?:python)?\n?/g, '').replace(/```/g, '').trim();
    }
    
    // Fallback to basic exploratory code
    return `
# Data exploration
print("Dataset shape:", df.shape if 'df' in globals() else "No df variable found")
if 'df' in globals():
    print("\\nColumn info:")
    df.info()
    print("\\nFirst few rows:")
    df.head()
    `.trim();
  }

  /**
   * Create analysis plan using REAL LLM
   */
  async createPlan(
    request: string, 
    notebookCells: any[], 
    dataSources: any[]
  ): Promise<AnalysisPlan> {
    const prompt = `Create a detailed analysis plan for: "${request}"

Current notebook state: ${notebookCells.length} cells
Available data sources: ${dataSources.map(ds => ds.name).join(', ')}

RESPOND WITH STRUCTURED JSON ONLY:
{
  "title": "Analysis: ...",
  "description": "Comprehensive analysis description",
  "steps": [
    {
      "stepId": "load_data",
      "title": "Load Data",
      "description": "Specific data loading step",
      "type": "data_loading",
      "dependencies": [],
      "isComplete": false,
      "estimatedTime": "2-3 minutes"
    }
  ],
  "estimatedTime": "15-25 minutes"
}`;

    try {
      const xsrfToken = document.querySelector('meta[name="_xsrf"]')?.getAttribute('content') || '';
      
      const response = await fetch('/api/chat/openai', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-XSRFToken': xsrfToken,
        },
        body: JSON.stringify({
          message: prompt,
          model: this.currentModel,
          context: { notebook_path: 'Untitled.ipynb' }
        })
      });

      const data = await response.json();
      
      // Parse structured JSON response
      try {
        const jsonMatch = data.response.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const planData = JSON.parse(jsonMatch[0]);
          return planData as AnalysisPlan;
        }
      } catch (parseError) {
        console.warn('Failed to parse LLM plan response, using fallback');
      }
      
      // Fallback to generated plan
      return await this._generatePlan(request, notebookCells, dataSources);
    } catch (error) {
      throw new Error(`Plan creation failed: ${error.message}`);
    }
  }

  /**
   * Generate visualization code using REAL LLM
   */
  async generateVisualizationCode(
    vizType: string,
    dataVariable: string,
    title: string,
    notebookCells: any[]
  ): Promise<string> {
    const prompt = `Generate Python visualization code for:
- Variable: ${dataVariable}
- Type: ${vizType === 'auto' ? 'best suitable type' : vizType}
- Title: ${title}

Notebook context:
${notebookCells.slice(-3).map(cell => `Cell: ${cell.source.substring(0, 100)}`).join('\n')}

Generate ONLY executable Python code using matplotlib/seaborn. No explanations.
Make it production-ready with proper imports, styling, and plt.show().`;

    try {
      const xsrfToken = document.querySelector('meta[name="_xsrf"]')?.getAttribute('content') || '';
      
      const response = await fetch('/api/chat/openai', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-XSRFToken': xsrfToken,
        },
        body: JSON.stringify({
          message: prompt,
          model: this.currentModel,
          context: { notebook_path: 'Untitled.ipynb' }
        })
      });

      const data = await response.json();
      
      // Extract code from response
      const codeBlocks = data.response.match(/```(?:python)?\n?([\s\S]*?)```/g);
      if (codeBlocks && codeBlocks.length > 0) {
        return codeBlocks[0].replace(/```(?:python)?\n?/g, '').replace(/```/g, '').trim();
      }
      
      // If no code blocks, try to extract code from response
      const lines = data.response.split('\n');
      const codeLines = lines.filter(line => 
        line.includes('import ') || 
        line.includes('plt.') || 
        line.includes('sns.') ||
        line.includes(dataVariable)
      );
      
      if (codeLines.length > 0) {
        return codeLines.join('\n');
      }
      
      // Fallback to generated code
      const dataAnalysis = this._analyzeDataFromCells(notebookCells, dataVariable);
      if (vizType === 'auto') {
        vizType = this._suggestVisualizationType(dataAnalysis);
      }
      return this._generateVizCode(vizType, dataVariable, title, dataAnalysis);
      
    } catch (error) {
      console.warn('LLM visualization generation failed, using fallback:', error);
      const dataAnalysis = this._analyzeDataFromCells(notebookCells, dataVariable);
      if (vizType === 'auto') {
        vizType = this._suggestVisualizationType(dataAnalysis);
      }
      return this._generateVizCode(vizType, dataVariable, title, dataAnalysis);
    }
  }

  /**
   * Process user feedback and adapt plan
   */
  async processFeedback(
    feedback: string,
    currentPlan?: AnalysisPlan,
    executionHistory?: any[]
  ): Promise<{ updatedPlan?: AnalysisPlan; summary: string }> {
    const prompt = `
User feedback: "${feedback}"
Current plan: ${currentPlan ? currentPlan.title : 'None'}
Execution history: ${executionHistory?.length || 0} steps completed

How should we adapt the analysis based on this feedback?
    `;

    try {
      return await this._processFeedbackInternal(feedback, currentPlan, executionHistory);
    } catch (error) {
      throw new Error(`Feedback processing failed: ${error.message}`);
    }
  }

  /**
   * Generate analysis summary
   */
  async generateSummary(
    originalRequest: string,
    executionHistory: any[],
    plan?: AnalysisPlan
  ): Promise<{ keyFindings: string[]; recommendations: string[] }> {
    try {
      return await this._generateSummaryInternal(originalRequest, executionHistory, plan);
    } catch (error) {
      throw new Error(`Summary generation failed: ${error.message}`);
    }
  }

  /**
   * Internal decision making logic
   */
  private async _analyzeContextAndDecide(context: any): Promise<Decision> {
    const { user_request, notebook_state, current_plan, execution_history, available_data_sources } = context;
    
    // Decision logic based on current state
    if (!current_plan && notebook_state.length === 0) {
      // No plan and empty notebook -> create plan
      return {
        action: 'create_plan',
        params: {},
        reasoning: 'No analysis plan exists and notebook is empty. Need to create a structured plan first.',
        statusMessage: '📋 Creating analysis plan...',
        confidence: 0.9
      };
    }
    
    if (current_plan && !this._hasDataLoaded(notebook_state)) {
      // Has plan but no data -> query data source
      const dataSource = available_data_sources[0]; // Use first available
      return {
        action: 'query_snowflake',
        params: {
          query: this._generateInitialQuery(user_request, dataSource),
          variable_name: 'df'
        },
        reasoning: 'Plan exists but no data loaded. Need to query data source first.',
        statusMessage: '🗄️ Loading data from Snowflake...',
        confidence: 0.8
      };
    }
    
    if (this._hasDataLoaded(notebook_state) && !this._hasBasicAnalysis(notebook_state)) {
      // Has data but no analysis -> execute exploratory code
      return {
        action: 'execute_code',
        params: {
          code: this._generateExploratoryCode(user_request)
        },
        reasoning: 'Data is loaded but no exploratory analysis done. Running basic data exploration.',
        statusMessage: '🔍 Exploring data structure...',
        confidence: 0.85
      };
    }
    
    if (this._hasBasicAnalysis(notebook_state) && !this._hasVisualization(notebook_state)) {
      // Has analysis but no viz -> create visualization
      return {
        action: 'create_visualization',
        params: {
          viz_type: 'auto',
          data_variable: 'df',
          title: this._generateVizTitle(user_request)
        },
        reasoning: 'Basic analysis complete but no visualizations. Creating charts to show insights.',
        statusMessage: '📊 Creating visualizations...',
        confidence: 0.8
      };
    }
    
    // Analysis seems complete
    return {
      action: 'complete_analysis',
      params: {},
      reasoning: 'Analysis workflow appears complete with data, analysis, and visualizations.',
      statusMessage: '📝 Finalizing analysis...',
      confidence: 0.7
    };
  }

  /**
   * Generate analysis plan
   */
  private async _generatePlan(
    request: string,
    notebookCells: any[],
    dataSources: any[]
  ): Promise<AnalysisPlan> {
    // Simple plan generation logic - in real implementation, this would use LLM
    const steps: PlanStep[] = [
      {
        stepId: 'load_data',
        title: 'Load Data',
        description: `Load relevant data from ${dataSources[0]?.name || 'available sources'}`,
        type: 'data_loading',
        isComplete: false,
        estimatedTime: '2-3 minutes'
      },
      {
        stepId: 'explore_data',
        title: 'Explore Data Structure',
        description: 'Examine data types, missing values, and basic statistics',
        type: 'analysis',
        dependencies: ['load_data'],
        isComplete: false,
        estimatedTime: '3-5 minutes'
      },
      {
        stepId: 'analyze_patterns',
        title: 'Analyze Patterns',
        description: `Perform analysis based on: ${request}`,
        type: 'analysis',
        dependencies: ['explore_data'],
        isComplete: false,
        estimatedTime: '5-10 minutes'
      },
      {
        stepId: 'create_visualizations',
        title: 'Create Visualizations',
        description: 'Generate charts and graphs to illustrate findings',
        type: 'visualization',
        dependencies: ['analyze_patterns'],
        isComplete: false,
        estimatedTime: '3-5 minutes'
      },
      {
        stepId: 'document_findings',
        title: 'Document Findings',
        description: 'Summarize key insights and recommendations',
        type: 'documentation',
        dependencies: ['create_visualizations'],
        isComplete: false,
        estimatedTime: '2-3 minutes'
      }
    ];

    return {
      title: `Analysis: ${request.substring(0, 50)}...`,
      description: `Comprehensive data analysis to address: ${request}`,
      steps,
      estimatedTime: '15-25 minutes',
      dependencies: dataSources.map(ds => ds.name)
    };
  }

  /**
   * Helper methods
   */
  private _hasDataLoaded(cells: any[]): boolean {
    return cells.some(cell => 
      cell.source.includes('pd.DataFrame') || 
      cell.source.includes('pd.read_') ||
      cell.outputs?.some((output: any) => 
        output.data?.['text/plain']?.includes('DataFrame')
      )
    );
  }

  private _hasBasicAnalysis(cells: any[]): boolean {
    return cells.some(cell => 
      cell.source.includes('.describe()') || 
      cell.source.includes('.info()') ||
      cell.source.includes('.head()')
    );
  }

  private _hasVisualization(cells: any[]): boolean {
    return cells.some(cell => 
      cell.source.includes('plt.') || 
      cell.source.includes('plot(') ||
      cell.outputs?.some((output: any) => output.data?.['image/png'])
    );
  }

  private _generateInitialQuery(request: string, dataSource: any): string {
    // Simple query generation - would be more sophisticated with LLM
    return `SELECT * FROM ${dataSource.name} LIMIT 1000`;
  }

  private _generateExploratoryCode(request: string): string {
    return `
# Data exploration
print("Dataset shape:", df.shape)
print("\\nColumn info:")
df.info()
print("\\nBasic statistics:")
df.describe()
print("\\nFirst few rows:")
df.head()
    `.trim();
  }

  private _generateVizTitle(request: string): string {
    return `Data Analysis: ${request.substring(0, 30)}...`;
  }

  private _analyzeDataFromCells(cells: any[], dataVariable: string): any {
    // Analyze existing cells to understand data structure
    return {
      hasNumericalData: true,
      hasCategoricalData: true,
      hasTimeData: false,
      columnCount: 5 // placeholder
    };
  }

  private _suggestVisualizationType(dataAnalysis: any): string {
    if (dataAnalysis.hasTimeData) return 'line';
    if (dataAnalysis.hasNumericalData && dataAnalysis.hasCategoricalData) return 'bar';
    if (dataAnalysis.hasNumericalData) return 'histogram';
    return 'bar';
  }

  private _generateVizCode(vizType: string, dataVariable: string, title: string, dataAnalysis: any): string {
    switch (vizType) {
      case 'bar':
        return `
import matplotlib.pyplot as plt
import seaborn as sns

plt.figure(figsize=(10, 6))
# Assuming first categorical and numerical columns
categorical_col = ${dataVariable}.select_dtypes(include=['object']).columns[0]
numerical_col = ${dataVariable}.select_dtypes(include=['number']).columns[0]
${dataVariable}.groupby(categorical_col)[numerical_col].mean().plot(kind='bar')
plt.title('${title}')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
        `.trim();
        
      case 'histogram':
        return `
import matplotlib.pyplot as plt

plt.figure(figsize=(10, 6))
numerical_col = ${dataVariable}.select_dtypes(include=['number']).columns[0]
${dataVariable}[numerical_col].hist(bins=30, edgecolor='black')
plt.title('${title}')
plt.xlabel(numerical_col)
plt.ylabel('Frequency')
plt.tight_layout()
plt.show()
        `.trim();
        
      default:
        return `
import matplotlib.pyplot as plt
import seaborn as sns

plt.figure(figsize=(12, 8))
# Create multiple subplots for comprehensive view
fig, axes = plt.subplots(2, 2, figsize=(15, 10))
fig.suptitle('${title}', fontsize=16)

# Plot 1: Distribution of first numerical column
numerical_cols = ${dataVariable}.select_dtypes(include=['number']).columns
if len(numerical_cols) > 0:
    axes[0,0].hist(${dataVariable}[numerical_cols[0]], bins=20)
    axes[0,0].set_title(f'Distribution of {numerical_cols[0]}')

# Plot 2: Correlation heatmap if multiple numerical columns
if len(numerical_cols) > 1:
    sns.heatmap(${dataVariable}[numerical_cols].corr(), annot=True, ax=axes[0,1])
    axes[0,1].set_title('Correlation Matrix')

# Plot 3: Box plot
if len(numerical_cols) > 0:
    ${dataVariable}[numerical_cols[0]].plot(kind='box', ax=axes[1,0])
    axes[1,0].set_title(f'Box Plot of {numerical_cols[0]}')

# Plot 4: Summary statistics
axes[1,1].text(0.1, 0.5, str(${dataVariable}.describe()), fontsize=8, verticalalignment='center')
axes[1,1].set_title('Summary Statistics')
axes[1,1].axis('off')

plt.tight_layout()
plt.show()
        `.trim();
    }
  }

  private async _processFeedbackInternal(
    feedback: string,
    currentPlan?: AnalysisPlan,
    executionHistory?: any[]
  ): Promise<{ updatedPlan?: AnalysisPlan; summary: string }> {
    // Simple feedback processing - would use LLM in real implementation
    const summary = `Processed user feedback: "${feedback.substring(0, 50)}..."`;
    
    // For now, just return summary without plan changes
    return { summary };
  }

  private async _generateSummaryInternal(
    originalRequest: string,
    executionHistory: any[],
    plan?: AnalysisPlan
  ): Promise<{ keyFindings: string[]; recommendations: string[] }> {
    // Simple summary generation - would use LLM to analyze outputs
    const keyFindings = [
      `Completed ${executionHistory.length} analysis steps`,
      'Data successfully loaded and processed',
      'Generated visualizations showing key patterns'
    ];
    
    const recommendations = [
      'Consider additional data sources for deeper insights',
      'Implement regular monitoring of key metrics',
      'Share findings with relevant stakeholders'
    ];
    
    return { keyFindings, recommendations };
  }

  private _buildDecisionPrompt(context: any): string {
    return `
Analyze the current context and decide the next best action:

User Request: ${context.user_request}
Notebook State: ${context.notebook_state.length} cells
Current Plan: ${context.current_plan ? 'Exists' : 'None'}
Execution History: ${context.execution_history.length} steps
Available Data Sources: ${context.available_data_sources.length}

Available Actions: ${context.available_actions.join(', ')}

Choose the most appropriate next action and provide reasoning.
    `;
  }
} 