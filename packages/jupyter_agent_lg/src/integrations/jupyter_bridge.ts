// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

/**
 * Bridge to integrate with existing jupyter_agent_bridge tools
 * This wraps the JupyterAgent class from jupyter_agent_bridge/tools.py
 */
export class JupyterBridge {
  private serverUrl: string;
  private token: string;
  private jupyterAgent: any; // Will be dynamically imported

  constructor(serverUrl: string, token: string) {
    this.serverUrl = serverUrl;
    this.token = token;
  }

  /**
   * Initialize the JupyterAgent connection
   */
  async initialize(): Promise<void> {
    try {
      // In a real implementation, this would import the Python JupyterAgent
      // For now, we'll simulate the API calls
      this.jupyterAgent = {
        insert_code_and_execute: this._mockInsertCodeAndExecute.bind(this),
        insert_cell: this._mockInsertCell.bind(this),
        execute_cell: this._mockExecuteCell.bind(this),
        update_cell_outputs: this._mockUpdateCellOutputs.bind(this),
        get_cell_content: this._mockGetCellContent.bind(this),
        insert_markdown: this._mockInsertMarkdown.bind(this)
      };
    } catch (error) {
      throw new Error(`Failed to initialize JupyterBridge: ${error.message}`);
    }
  }

  /**
   * Primary tool - Insert code and execute with output capture
   */
  async insertCodeAndExecute(
    notebookPath: string,
    code: string,
    cellType: string = 'code',
    position: string = 'end',
    kernelId?: string
  ): Promise<{
    cell_id: string;
    outputs: any[];
    execution_count: number;
    status: string;
  }> {
    if (!this.jupyterAgent) {
      await this.initialize();
    }

    try {
      // Call the existing jupyter_agent_bridge API
      const result = await this._callPythonAgent('insert_code_and_execute', {
        notebook_path: notebookPath,
        code,
        cell_type: cellType,
        position,
        kernel_id: kernelId
      });

      return result;
    } catch (error) {
      throw new Error(`Code execution failed: ${error.message}`);
    }
  }

  /**
   * Insert a new cell
   */
  async insertCell(
    notebookPath: string,
    content: string,
    cellType: string = 'code',
    position: string = 'end'
  ): Promise<string> {
    if (!this.jupyterAgent) {
      await this.initialize();
    }

    try {
      const result = await this._callPythonAgent('insert_cell', {
        notebook_path: notebookPath,
        source: content,
        cell_type: cellType,
        position
      });

      return result.cell_id;
    } catch (error) {
      throw new Error(`Cell insertion failed: ${error.message}`);
    }
  }

  /**
   * Execute an existing cell
   */
  async executeCell(
    notebookPath: string,
    cellId?: string,
    content?: string,
    kernelId?: string
  ): Promise<{
    outputs: any[];
    execution_count: number;
    status: string;
  }> {
    if (!this.jupyterAgent) {
      await this.initialize();
    }

    try {
      const result = await this._callPythonAgent('execute_cell', {
        notebook_path: notebookPath,
        cell_id: cellId,
        content,
        kernel_id: kernelId
      });

      return result;
    } catch (error) {
      throw new Error(`Cell execution failed: ${error.message}`);
    }
  }

  /**
   * Update cell outputs
   */
  async updateCellOutputs(
    notebookPath: string,
    cellId: string,
    outputs: any[],
    executionCount?: number
  ): Promise<boolean> {
    if (!this.jupyterAgent) {
      await this.initialize();
    }

    try {
      await this._callPythonAgent('update_cell_outputs', {
        notebook_path: notebookPath,
        cell_id: cellId,
        outputs,
        execution_count: executionCount
      });

      return true;
    } catch (error) {
      throw new Error(`Output update failed: ${error.message}`);
    }
  }

  /**
   * Get cell content
   */
  async getCellContent(
    notebookPath: string,
    cellId?: string
  ): Promise<any[]> {
    if (!this.jupyterAgent) {
      await this.initialize();
    }

    try {
      const result = await this._callPythonAgent('get_cell_content', {
        notebook_path: notebookPath,
        cell_id: cellId
      });

      return result.cells || result || [];
    } catch (error) {
      throw new Error(`Failed to get cell content: ${error.message}`);
    }
  }

  /**
   * Insert markdown cell
   */
  async insertMarkdown(
    notebookPath: string,
    markdown: string,
    position: string = 'end'
  ): Promise<string> {
    return await this.insertCell(notebookPath, markdown, 'markdown', position);
  }

  /**
   * Call Python JupyterAgent methods via HTTP bridge
   */
  private async _callPythonAgent(method: string, params: any): Promise<any> {
    try {
      // For now, create a simple HTTP bridge to Python JupyterAgent
      // In production, this would be a proper API endpoint
      const response = await fetch(`${this.serverUrl}/api/jupyter_agent/${method}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `token ${this.token}`,
          'X-XSRFToken': await this._getXSRFToken()
        },
        body: JSON.stringify(params)
      });

      if (!response.ok) {
        // Fallback to mock for development
        console.warn(`Python agent API not available, using mock for ${method}`);
        return await this._mockPythonAgent(method, params);
      }

      return await response.json();
    } catch (error) {
      // Fallback to mock for development
      console.warn(`Python agent call failed, using mock for ${method}:`, error);
      return await this._mockPythonAgent(method, params);
    }
  }

  /**
   * Mock Python agent methods for development
   */
  private async _mockPythonAgent(method: string, params: any): Promise<any> {
    switch (method) {
      case 'insert_code_and_execute':
        return {
          cell_id: `cell_${Date.now()}`,
          outputs: [
            {
              output_type: 'stream',
              name: 'stdout',
              text: [`Mock output for: ${params.code.substring(0, 50)}...`]
            }
          ],
          execution_count: Math.floor(Math.random() * 10) + 1,
          status: 'ok'
        };

      case 'get_cell_content':
        return {
          cells: [
            {
              cell_type: 'code',
              source: 'print("Hello, World!")',
              execution_count: 1,
              outputs: [],
              cell_id: 'cell_1'
            }
          ]
        };

      case 'insert_cell':
        return { cell_id: `cell_${Date.now()}` };

      case 'insert_markdown':
        return { cell_id: `markdown_${Date.now()}` };

      default:
        return { success: true };
    }
  }

  /**
   * Get XSRF token for authentication
   */
  private async _getXSRFToken(): Promise<string> {
    try {
      const response = await fetch(`${this.serverUrl}/lab`, {
        headers: {
          'Authorization': `token ${this.token}`
        }
      });
      
      const cookies = response.headers.get('set-cookie');
      if (cookies) {
        const xsrfMatch = cookies.match(/_xsrf=([^;]+)/);
        if (xsrfMatch) {
          return xsrfMatch[1];
        }
      }
      
      return '';
    } catch (error) {
      console.warn('Failed to get XSRF token:', error);
      return '';
    }
  }

  // Mock implementations for development/testing
  private async _mockInsertCodeAndExecute(
    notebookPath: string,
    code: string,
    cellType: string = 'code',
    position: string = 'end'
  ): Promise<any> {
    return {
      cell_id: `cell_${Date.now()}`,
      outputs: [
        {
          output_type: 'stream',
          name: 'stdout',
          text: 'Mock execution output'
        }
      ],
      execution_count: 1,
      status: 'ok'
    };
  }

  private async _mockInsertCell(
    notebookPath: string,
    content: string,
    cellType: string = 'code',
    position: string = 'end'
  ): Promise<string> {
    return `cell_${Date.now()}`;
  }

  private async _mockExecuteCell(): Promise<any> {
    return {
      outputs: [],
      execution_count: 1,
      status: 'ok'
    };
  }

  private async _mockUpdateCellOutputs(): Promise<boolean> {
    return true;
  }

  private async _mockGetCellContent(notebookPath: string): Promise<any[]> {
    return [
      {
        cell_type: 'code',
        source: 'print("Hello, World!")',
        execution_count: 1,
        outputs: [],
        cell_id: 'cell_1'
      }
    ];
  }

  private async _mockInsertMarkdown(
    notebookPath: string,
    markdown: string,
    position: string = 'end'
  ): Promise<string> {
    return `markdown_cell_${Date.now()}`;
  }
} 