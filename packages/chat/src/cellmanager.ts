import { ICellManager } from './tokens';
import { INotebookTracker } from '@jupyterlab/notebook';
import { CodeCell } from '@jupyterlab/cells';
import { Signal, ISignal } from '@lumino/signaling';

/**
 * Cell manager implementation for interacting with notebook cells
 */
export class CellManager implements ICellManager {
  private _notebookTracker: INotebookTracker;
  private _activeNotebookChanged = new Signal<this, void>(this);

  constructor(notebookTracker: INotebookTracker) {
    this._notebookTracker = notebookTracker;
    
    // Listen for notebook changes
    this._notebookTracker.currentChanged.connect(() => {
      this._activeNotebookChanged.emit();
    });
  }

  /**
   * Signal emitted when the active notebook changes
   */
  get activeNotebookChanged(): ISignal<this, void> {
    return this._activeNotebookChanged;
  }

  /**
   * Get the currently active notebook
   */
  getActiveNotebook(): any {
    const current = this._notebookTracker.currentWidget;
    return current?.content || null;
  }

  /**
   * Get the content of a specific cell
   */
  getCellContent(cellIndex: number): string | null {
    const notebook = this.getActiveNotebook();
    if (!notebook || !notebook.model || !notebook.model.cells) {
      return null;
    }

    const cells = notebook.model.cells;
    if (cellIndex < 0 || cellIndex >= cells.length) {
      return null;
    }

    const cell = cells.get(cellIndex);
    if (!cell || !cell.value) {
      return null;
    }

    return cell.value.text || '';
  }

  /**
   * Set the content of a specific cell
   */
  setCellContent(cellIndex: number, content: string): void {
    console.log(`🔧 CellManager.setCellContent called: index=${cellIndex}, content="${content}"`);
    
    const notebook = this.getActiveNotebook();
    if (!notebook || !notebook.model || !notebook.model.cells) {
      throw new Error('No active notebook or notebook model');
    }

    const cells = notebook.model.cells;
    if (cellIndex < 0 || cellIndex >= cells.length) {
      throw new Error(`Invalid cell index: ${cellIndex}`);
    }

    const cell = cells.get(cellIndex);
    if (!cell) {
      throw new Error(`Cell at index ${cellIndex} is invalid`);
    }

    console.log(`🔧 Cell ${cellIndex} has value:`, !!cell.value);
    console.log(`🔧 Cell ${cellIndex} has sharedModel:`, !!cell.sharedModel);

    // Try to set content using the appropriate API
    if (cell.value && cell.value.text !== undefined) {
      console.log(`🔧 Setting via cell.value.text`);
      cell.value.text = content;
    } else if (cell.sharedModel && cell.sharedModel.source !== undefined) {
      console.log(`🔧 Setting via cell.sharedModel.source`);
      cell.sharedModel.source = content;
    } else {
      console.error(`🔧 Cannot set content for cell ${cellIndex} - no accessible content API`);
      throw new Error(`Cannot set content for cell ${cellIndex} - no accessible content API`);
    }
    
    console.log(`🔧 Cell ${cellIndex} content set successfully`);
  }

  /**
   * Insert a new cell at the specified index
   */
  insertCell(cellIndex: number, content: string, cellType: 'code' | 'markdown'): void {
    console.log(`🔧 CellManager.insertCell called: index=${cellIndex}, content="${content}", type=${cellType}`);
    
    const notebook = this.getActiveNotebook();
    if (!notebook || !notebook.model) {
      throw new Error('No active notebook or notebook model');
    }

    console.log('📝 Notebook model:', notebook.model);
    console.log('📝 Notebook model contentFactory:', notebook.model.contentFactory);

    const cells = notebook.model.cells;
    if (!cells) {
      throw new Error('No cells model available');
    }

    if (!notebook.model.contentFactory) {
      throw new Error('No contentFactory available on notebook model');
    }

    console.log('📝 Available contentFactory methods:', Object.getOwnPropertyNames(notebook.model.contentFactory));

    // Create new cell model using the contentFactory
    const cellModel = notebook.model.contentFactory.createCell(cellType, {});
    if (!cellModel) {
      throw new Error('Failed to create cell model');
    }

    console.log('📝 Created cell model:', cellModel);
    console.log('📝 Cell model has sharedModel:', !!cellModel.sharedModel);

    // Set content using sharedModel.source since that's what we've been using
    if (cellModel.sharedModel) {
      cellModel.sharedModel.source = content;
      console.log('📝 Content set via sharedModel.source:', cellModel.sharedModel.source);
    } else if (cellModel.value) {
      cellModel.value.text = content;
      console.log('📝 Content set via value.text:', cellModel.value.text);  
    } else {
      console.error('📝 No way to set content on cell model');
    }

    // Insert at specified index
    const insertIndex = Math.max(0, Math.min(cellIndex, cells.length));
    console.log(`📝 Inserting at index ${insertIndex} (requested: ${cellIndex}, max: ${cells.length})`);
    
    cells.insert(insertIndex, cellModel);
    console.log('📝 Cell inserted successfully');

    // Select the new cell
    notebook.activeCellIndex = insertIndex;
    console.log(`📝 Active cell set to index ${insertIndex}`);
  }

  /**
   * Execute a specific cell
   */
  async executeCell(cellIndex: number): Promise<void> {
    const notebook = this.getActiveNotebook();
    if (!notebook || !notebook.model || !notebook.model.cells) {
      throw new Error('No active notebook or notebook model');
    }

    const cells = notebook.model.cells;
    if (cellIndex < 0 || cellIndex >= cells.length) {
      throw new Error(`Invalid cell index: ${cellIndex}`);
    }

    // Set active cell and execute
    notebook.activeCellIndex = cellIndex;
    const cell = notebook.activeCell;
    
    if (cell instanceof CodeCell) {
      await CodeCell.execute(cell, notebook.sessionContext);
    }
  }

  /**
   * Get all cells content
   */
  getAllCells(): Array<{ content: string; type: string; index: number }> {
    console.log('CellManager.getAllCells() called');
    
    const notebook = this.getActiveNotebook();
    if (!notebook) {
      console.log('No active notebook');
      return [];
    }
    
    console.log('Active notebook found:', notebook);
    
    if (!notebook.model) {
      console.log('No notebook model');
      return [];
    }
    
    console.log('Notebook model found:', notebook.model);
    
    if (!notebook.model.cells) {
      console.log('No notebook cells');
      return [];
    }
    
    console.log('Notebook cells found, length:', notebook.model.cells.length);

    const cells = notebook.model.cells;
    const result: Array<{ content: string; type: string; index: number }> = [];
    
    try {
      for (let i = 0; i < cells.length; i++) {
        console.log(`Processing cell ${i}`);
        const cell = cells.get(i);
        console.log(`Cell ${i}:`, cell);
        
        if (cell) {
          console.log(`Cell ${i} has value:`, !!cell.value);
          console.log(`Cell ${i} has sharedModel:`, !!cell.sharedModel);
          
          let content = '';
          
          // Try different ways to get cell content
          if (cell.value && cell.value.text !== undefined) {
            content = cell.value.text;
            console.log(`Cell ${i} text from value:`, content);
          } else if (cell.sharedModel && cell.sharedModel.source !== undefined) {
            content = cell.sharedModel.source;
            console.log(`Cell ${i} text from sharedModel:`, content);
          } else {
            console.log(`Cell ${i} has no accessible content`);
          }
          
          result.push({
            content: content,
            type: cell.type,
            index: i
          });
        } else {
          console.log(`Cell ${i} is undefined`);
        }
      }
    } catch (error) {
      console.error('Error in getAllCells loop:', error);
      return [];
    }

    console.log('getAllCells result:', result);
    return result;
  }

  /**
   * Get cell at current cursor position
   */
  getCurrentCell(): { content: string; type: string; index: number } | null {
    console.log('CellManager.getCurrentCell() called');
    
    const notebook = this.getActiveNotebook();
    if (!notebook) {
      console.log('No active notebook for getCurrentCell');
      return null;
    }

    console.log('Active notebook found for getCurrentCell');
    const activeIndex = notebook.activeCellIndex;
    const cell = notebook.activeCell;
    
    console.log('Active cell index:', activeIndex);
    console.log('Active cell:', cell);
    
    if (!cell) {
      console.log('No active cell');
      return null;
    }
    
    if (!cell.model) {
      console.log('No active cell model');
      return null;
    }
    
    console.log('Cell model has value:', !!cell.model.value);
    console.log('Cell model has sharedModel:', !!cell.model.sharedModel);

    let content = '';
    
    // Try different ways to get cell content
    if (cell.model.value && cell.model.value.text !== undefined) {
      content = cell.model.value.text;
      console.log('Active cell text from value:', content);
    } else if (cell.model.sharedModel && cell.model.sharedModel.source !== undefined) {
      content = cell.model.sharedModel.source;
      console.log('Active cell text from sharedModel:', content);
    } else {
      console.log('Active cell has no accessible content');
    }

    return {
      content: content,
      type: cell.model.type,
      index: activeIndex
    };
  }

  /**
   * Add a new cell at the end
   */
  addCell(content: string, cellType: 'code' | 'markdown' = 'code'): void {
    const notebook = this.getActiveNotebook();
    if (!notebook || !notebook.model) {
      throw new Error('No active notebook or notebook model');
    }

    const cells = notebook.model.cells;
    if (!cells) {
      throw new Error('No cells model available');
    }

    this.insertCell(cells.length, content, cellType);
  }

  /**
   * Delete a cell at the specified index
   */
  deleteCell(cellIndex: number): void {
    const notebook = this.getActiveNotebook();
    if (!notebook || !notebook.model || !notebook.model.cells) {
      throw new Error('No active notebook or notebook model');
    }

    const cells = notebook.model.cells;
    if (cellIndex < 0 || cellIndex >= cells.length) {
      throw new Error(`Invalid cell index: ${cellIndex}`);
    }

    cells.remove(cellIndex);
  }
} 