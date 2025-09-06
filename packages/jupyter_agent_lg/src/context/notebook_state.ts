// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

/**
 * Efficient notebook state management for LLM context
 * Provides smart summarization to avoid token explosion
 */
export class NotebookStateManager {
  private serverUrl: string;
  private token: string;
  private stateCache: Map<string, any> = new Map();
  private cacheTimeout: number = 30000; // 30 seconds

  constructor(serverUrl: string, token: string) {
    this.serverUrl = serverUrl;
    this.token = token;
  }

  /**
   * Get complete notebook state with smart summarization
   */
  async getCompleteNotebookState(notebookPath: string): Promise<Array<{
    type: string;
    source: string;
    execution_count?: number;
    outputs?: Array<any>;
    cell_id?: string;
  }>> {
    try {
      // Check cache first
      const cacheKey = `notebook_${notebookPath}`;
      const cached = this.stateCache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
        return cached.data;
      }

      // Fetch notebook from Jupyter API
      const notebook = await this._fetchNotebook(notebookPath);
      
      // Process and summarize cells
      const processedCells = notebook.cells.map(cell => ({
        type: cell.cell_type,
        source: this._truncateSource(cell.source),
        execution_count: cell.execution_count,
        outputs: this._summarizeOutputs(cell.outputs || []),
        cell_id: cell.metadata?.cell_id || `cell_${Date.now()}_${Math.random()}`
      }));

      // Cache the result
      this.stateCache.set(cacheKey, {
        data: processedCells,
        timestamp: Date.now()
      });

      return processedCells;
    } catch (error) {
      throw new Error(`Failed to get notebook state: ${error.message}`);
    }
  }

  /**
   * Get notebook metadata and summary statistics
   */
  async getNotebookSummary(notebookPath: string): Promise<{
    cellCount: number;
    codeCount: number;
    markdownCount: number;
    executedCount: number;
    lastExecution?: number;
    hasOutputs: boolean;
    dataVariables: string[];
  }> {
    try {
      const cells = await this.getCompleteNotebookState(notebookPath);
      
      const codeCells = cells.filter(c => c.type === 'code');
      const markdownCells = cells.filter(c => c.type === 'markdown');
      const executedCells = codeCells.filter(c => c.execution_count);
      const cellsWithOutputs = codeCells.filter(c => c.outputs && c.outputs.length > 0);
      
      // Extract data variable names from code
      const dataVariables = this._extractDataVariables(codeCells);
      
      return {
        cellCount: cells.length,
        codeCount: codeCells.length,
        markdownCount: markdownCells.length,
        executedCount: executedCells.length,
        lastExecution: Math.max(...executedCells.map(c => c.execution_count || 0), 0),
        hasOutputs: cellsWithOutputs.length > 0,
        dataVariables
      };
    } catch (error) {
      throw new Error(`Failed to get notebook summary: ${error.message}`);
    }
  }

  /**
   * Get cells containing specific patterns (e.g., data loading, plots)
   */
  async getCellsByPattern(
    notebookPath: string,
    patterns: string[]
  ): Promise<Array<{
    cell_id: string;
    type: string;
    source: string;
    execution_count?: number;
    matchedPattern: string;
  }>> {
    try {
      const cells = await this.getCompleteNotebookState(notebookPath);
      const matches: Array<any> = [];
      
      for (const cell of cells) {
        for (const pattern of patterns) {
          if (cell.source.toLowerCase().includes(pattern.toLowerCase())) {
            matches.push({
              cell_id: cell.cell_id,
              type: cell.type,
              source: cell.source,
              execution_count: cell.execution_count,
              matchedPattern: pattern
            });
            break; // Only match first pattern per cell
          }
        }
      }
      
      return matches;
    } catch (error) {
      throw new Error(`Failed to search cells by pattern: ${error.message}`);
    }
  }

  /**
   * Get execution timeline
   */
  async getExecutionTimeline(notebookPath: string): Promise<Array<{
    execution_count: number;
    cell_id: string;
    source_preview: string;
    output_summary: string;
    estimated_timestamp?: string;
  }>> {
    try {
      const cells = await this.getCompleteNotebookState(notebookPath);
      const executedCells = cells
        .filter(c => c.type === 'code' && c.execution_count)
        .sort((a, b) => (a.execution_count || 0) - (b.execution_count || 0));
      
      return executedCells.map(cell => ({
        execution_count: cell.execution_count!,
        cell_id: cell.cell_id!,
        source_preview: cell.source.substring(0, 100) + (cell.source.length > 100 ? '...' : ''),
        output_summary: this._summarizeOutputsForTimeline(cell.outputs || [])
      }));
    } catch (error) {
      throw new Error(`Failed to get execution timeline: ${error.message}`);
    }
  }

  /**
   * Clear cache for specific notebook or all
   */
  clearCache(notebookPath?: string): void {
    if (notebookPath) {
      this.stateCache.delete(`notebook_${notebookPath}`);
    } else {
      this.stateCache.clear();
    }
  }

  /**
   * Private helper methods
   */
  private async _fetchNotebook(notebookPath: string): Promise<any> {
    const url = `${this.serverUrl}/api/contents/${encodeURIComponent(notebookPath)}`;
    
    try {
      const response = await fetch(url, {
        headers: {
          'Authorization': `token ${this.token}`
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch notebook: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      return data.content;
    } catch (error) {
      throw new Error(`Notebook fetch failed: ${error.message}`);
    }
  }

  private _truncateSource(source: string | string[]): string {
    const sourceStr = Array.isArray(source) ? source.join('') : source;
    const maxLength = 1000; // Limit source length for LLM context
    
    if (sourceStr.length <= maxLength) {
      return sourceStr;
    }
    
    return sourceStr.substring(0, maxLength) + '\n# ... (truncated)';
  }

  private _summarizeOutputs(outputs: Array<any>): Array<any> {
    return outputs.map(output => {
      const summarized: any = {
        output_type: output.output_type
      };
      
      if (output.data) {
        summarized.data = {};
        
        // Summarize different output types
        if (output.data['text/plain']) {
          const text = output.data['text/plain'];
          summarized.data['text/plain'] = this._truncateText(text, 200);
        }
        
        if (output.data['text/html']) {
          summarized.data['text/html'] = '<HTML content present>';
        }
        
        if (output.data['image/png']) {
          summarized.data['image/png'] = '<PNG image present>';
        }
        
        if (output.data['application/json']) {
          summarized.data['application/json'] = '<JSON data present>';
        }
      }
      
      if (output.text) {
        summarized.text = this._truncateText(output.text, 200);
      }
      
      if (output.traceback) {
        summarized.traceback = ['<Error traceback present>'];
      }
      
      return summarized;
    });
  }

  private _summarizeOutputsForTimeline(outputs: Array<any>): string {
    if (outputs.length === 0) {
      return 'No outputs';
    }
    
    const types = outputs.map(o => o.output_type).join(', ');
    const hasImage = outputs.some(o => o.data?.['image/png']);
    const hasHTML = outputs.some(o => o.data?.['text/html']);
    const hasError = outputs.some(o => o.output_type === 'error');
    
    let summary = `${outputs.length} output(s): ${types}`;
    if (hasImage) summary += ' [Image]';
    if (hasHTML) summary += ' [HTML]';
    if (hasError) summary += ' [Error]';
    
    return summary;
  }

  private _truncateText(text: string | string[], maxLength: number): string {
    const textStr = Array.isArray(text) ? text.join('') : text;
    if (textStr.length <= maxLength) {
      return textStr;
    }
    return textStr.substring(0, maxLength) + '...';
  }

  private _extractDataVariables(codeCells: Array<any>): string[] {
    const variables = new Set<string>();
    
    // Common patterns for data variables
    const patterns = [
      /(\w+)\s*=\s*pd\.read_/g,           // df = pd.read_csv(...)
      /(\w+)\s*=\s*pd\.DataFrame/g,       // df = pd.DataFrame(...)
      /(\w+)\s*=\s*np\.array/g,           // arr = np.array(...)
      /(\w+)\s*=\s*\w+\.query/g,          // result = conn.query(...)
    ];
    
    for (const cell of codeCells) {
      for (const pattern of patterns) {
        let match;
        while ((match = pattern.exec(cell.source)) !== null) {
          variables.add(match[1]);
        }
      }
    }
    
    return Array.from(variables);
  }
} 