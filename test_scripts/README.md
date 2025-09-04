# Test Scripts - JupyterLab Agent Extension

This folder contains all test scripts for validating the JupyterLab Agent Extension functionality.

## 🧪 **Main Test Suites**

### **`test_agent_tools.py`** ⭐ **MAIN TEST SUITE**
- **Purpose**: Comprehensive test of all JupyterAgent tools
- **Tests**: insert_code_and_execute, insert_markdown, get_cell_content, execution count sequencing
- **Status**: ✅ All tests passing
- **Usage**: `python test_scripts/test_agent_tools.py`

### **`test_complete_flow.py`** ⭐ **END-TO-END FLOW**
- **Purpose**: Complete workflow testing with cross-cell targeting
- **Tests**: Cell insertion, code execution, output routing, matplotlib plots
- **Status**: ✅ Working perfectly with real-time updates
- **Usage**: `python test_scripts/test_complete_flow.py`

## 🔧 **Component Tests**

### **`test_working_flow.py`**
- **Purpose**: Core functionality validation
- **Focus**: Basic insert/execute/update operations
- **Status**: ✅ Working

### **`test_realtime_check.py`**
- **Purpose**: Real-time Y-document update verification
- **Focus**: WebSocket synchronization testing
- **Status**: ✅ Working

### **`test_kernel_execution.py`**
- **Purpose**: Kernel WebSocket communication testing
- **Focus**: Code execution and output capture
- **Status**: ✅ Working

### **`test_endpoints.py`**
- **Purpose**: REST API endpoint testing
- **Focus**: Handler validation and response testing
- **Status**: ✅ Working

## 🧩 **Debugging & Development Tests**

### **`test_agent_flow.py`**
- **Purpose**: Agent workflow debugging
- **Status**: Development/debugging tool

### **`test_direct_ydoc.py`**
- **Purpose**: Direct Y-document manipulation testing
- **Status**: Low-level Y-document debugging

### **`test_simple_output_insert.py`**
- **Purpose**: Basic output insertion testing
- **Status**: Simple validation tool

## 🔮 **Future Integration Tests**

### **`test_mcp.py`**
- **Purpose**: MCP (Model Context Protocol) integration testing
- **Status**: 🔄 Placeholder - not implemented yet

### **`test_agents.py`**
- **Purpose**: LangGraph agent integration testing
- **Status**: 🔄 Placeholder - not implemented yet

---

## 🚀 **Quick Start**

1. **Start JupyterLab in dev mode**:
   ```bash
   jupyter lab --dev-mode --extensions-in-dev-mode --port=8890
   ```

2. **Run main test suite**:
   ```bash
   python test_scripts/test_agent_tools.py
   ```

3. **Watch your JupyterLab notebook** - cells should appear in real-time!

---

## 📝 **Test Requirements**

- JupyterLab running on port 8890
- Update token in test scripts (get from JupyterLab logs)
- Clear notebook (`Untitled.ipynb`) for clean testing

**All core functionality is tested and working! 🎉**
