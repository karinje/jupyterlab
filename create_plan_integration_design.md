# CreatePlan Integration Design Document

## 🎯 **Overview**

Design for seamless LLM-driven plan creation and editing workflow in JupyterLab Agent. The system allows the agent to create interactive plan cards, users to edit them visually, and the LLM to decide next steps based on user feedback and updated plans.

## 🏗️ **Architecture Principles**

### **1. LLM-Driven Decision Making**
- **No hardcoded buttons** like "Continue with Plan"
- **Agent asks user questions** like "Should I proceed with this plan?"
- **User responds naturally** in chat
- **LLM decides next action** based on user response and current plan state

### **2. Plan Context Integration**
- **Plan becomes part of conversation context** once created
- **LLM sees current plan state** in every decision cycle
- **Plan modifications tracked** and included in context
- **Plan implementation guided by LLM** using existing tools

### **3. Visual Plan Management**
- **Interactive editable cards** displayed in chat
- **Real-time editing** with contenteditable fields
- **Add/delete cards** with visual buttons
- **Plan state synced** with agent context automatically

---

## ✅ **Existing Frontend Infrastructure**

### **Card Rendering System (COMPLETE)**
```typescript
// packages/chat/src/widget.tsx - ALREADY EXISTS

private _renderCards(cards: any[]): string {
  // Renders array of card objects in flex column layout
}

private _renderCard(card: any, index: number): string {
  // Renders individual card with:
  // - contenteditable="true" title and description fields
  // - Green "+" button (addStepAfterCard)
  // - 🗑️ delete button (deleteCard)
  // - Professional styling with shadows and borders
}

private _extractCardsFromContent(content: string): any[] {
  // Extracts cards from text using pattern: [CARD:title|description]
}
```

### **Card Management Methods (COMPLETE)**
```typescript
// packages/chat/src/widget.tsx - ALREADY EXISTS

deleteCard(cardId: string): void {
  // Removes card with confirmation dialog
}

addStepAfterCard(cardId: string): void {
  // Inserts new editable card after current one
  // Auto-focuses on title field for immediate editing
  // Generates unique card IDs
}

editCard(cardId: string): void {
  // Highlights card fields for editing (visual feedback)
}
```

### **Plan Message Display (COMPLETE)**
```typescript
// packages/chat/src/widget.tsx - ALREADY EXISTS

// In _addMessageToDisplay():
const isPlanMessage = messageType === 'plan';
const hasCards = cards.length > 0;

if (hasCards || isPlanMessage) {
  // Automatically renders cards for plan messages
  messageDiv.innerHTML = `
    <div style="flex: 1;">
      ${this._renderCards(cards)}  // Uses existing card rendering
      <div style="timestamp styling">
    </div>
  `;
}
```

### **Plan Signal Infrastructure (COMPLETE)**
```typescript
// packages/chat/src/service.ts - ALREADY EXISTS

private _planReceived = new Signal<this, any>(this);

get planReceived(): ISignal<this, any> {
  return this._planReceived;
}

// packages/chat/src/widget.tsx - ALREADY EXISTS
// Subscribe to live plan events if available
if ((this._chatService as any).planReceived) {
  (this._chatService as any).planReceived.connect((_: any, payload: any) => {
    const steps = Array.isArray(payload?.steps) ? payload.steps : [];
    if (steps.length === 0) return;
    const content = `Plan:\n` +
      steps.map((s: any, i: number) => `${i + 1}. ${s.title || 'Step'} — ${s.description || ''}`).join('\n');
    this._addMessageToDisplay('assistant', content, new Date(), { messageType: 'plan' });
  });
}
```

---

## ❌ **Missing Components (TO IMPLEMENT)**

### **Backend Components**

#### **1. ChatPlanCardsHandler** (NEW)
```python
class ChatPlanCardsHandler(APIHandler):
    """Receive plan steps from agent and broadcast to frontend"""

    async def post(self):
        data = self.get_json_body()
        plan_steps = data.get("plan_steps", [])
        notebook_path = data.get("notebook_path")

        # Broadcast plan cards to frontend via existing chat_broadcaster
        chat_broadcaster.broadcast({
            "type": "plan_cards",
            "notebook_path": notebook_path,
            "payload": {
                "plan_steps": plan_steps,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
```

#### **2. Plan Context Integration** (MODIFY EXISTING)
```python
# In ChatAgentHandler - ADD to existing _build_context_for_agent()
def _extract_current_plan_from_dom(self, user_message_context):
    """Extract current plan cards from frontend DOM state"""
    # Look for updated_plan in context (sent by frontend)
    return user_message_context.get("updated_plan", [])

def _build_context_for_agent(self, conversation_context, notebook_path, user_context=None):
    context = {
        "conversation_history": conversation_context,
        "notebook_path": notebook_path,
        "current_plan": self._extract_current_plan_from_dom(user_context or {}),  # NEW
        # ... existing context
    }
```

### **Frontend Components**

#### **3. Plan Cards WebSocket Handler** (ADD TO EXISTING)
```typescript
// In packages/chat/src/service.ts - ADD to existing WebSocket handler
else if (type === 'plan_cards') {
  // Convert plan steps to card format for existing _renderCards()
  const cards = payload.plan_steps.map((step: any, index: number) => ({
    id: `plan-card-${index}-${Date.now()}`,
    title: step.title || `Step ${index + 1}`,
    description: step.description || ''
  }));

  // Use existing planReceived signal infrastructure
  this._planReceived.emit({
    steps: cards,  // Send as cards, not raw steps
    timestamp: payload.timestamp
  });
}
```

#### **4. Plan Collection on User Response** (NEW)
```typescript
// In packages/chat/src/service.ts - ADD to existing sendMessage()
async sendMessage(message: string): Promise<void> {
  // ... existing code ...

  // Collect current plan cards if they exist (NEW)
  const updatedPlan = this._collectCurrentPlanCards();

  const context = this._buildContext();
  if (updatedPlan && updatedPlan.length > 0) {
    context.updated_plan = updatedPlan;  // Include in context
  }

  // ... rest of existing sendMessage logic
}

private _collectCurrentPlanCards(): any[] | null {
  // Extract all card data from DOM using existing card structure
  const cardElements = document.querySelectorAll('.chat-card');
  if (cardElements.length === 0) return null;

  return Array.from(cardElements).map(card => ({
    id: card.id,
    title: card.querySelector('.card-title')?.textContent?.trim() || '',
    description: card.querySelector('.card-description')?.textContent?.trim() || ''
  }));
}
```

### **Agent Workflow Integration**

#### **5. Plan Context in Agent State** (ADD TO EXISTING)
```python
# In packages/jupyter-agent/jupyter_agent_lg/agent.py - MODIFY existing analyze_and_decide()
async def analyze_and_decide(self, state):
    # ... existing code ...

    # Include current plan in LLM context (NEW)
    current_plan = state.get("current_plan", [])
    updated_plan = state.get("updated_plan", [])  # From user edits

    # Use updated plan if available, otherwise current plan
    active_plan = updated_plan if updated_plan else current_plan

    if active_plan:
        plan_context = self._format_plan_for_llm(active_plan)
        # Add plan context to system message or conversation

    # ... rest of existing analyze_and_decide logic
```

#### **6. Plan Implementation Logic** (NEW)
```python
# In packages/jupyter-agent/jupyter_agent_lg/agent.py - ADD new method
def _format_plan_for_llm(self, plan_steps):
    """Format plan steps for LLM context"""
    if not plan_steps:
        return ""

    plan_text = "Current Plan:\n"
    for i, step in enumerate(plan_steps, 1):
        status = "✅" if step.get("completed") else "⏳"
        plan_text += f"{i}. {status} {step.get('title', '')} - {step.get('description', '')}\n"

    return plan_text
```

---

## 🔄 **Complete End-to-End Workflow**

### **Phase 1: Plan Creation**
```
User: "Create plots for x,y powers 1-10"
  ↓
Agent (analyze_and_decide): Decides to create plan
  ↓
Agent calls: CreatePlan([
  {title: "Import libraries", description: "Import matplotlib and numpy"},
  {title: "Create x values", description: "Generate x = np.linspace(0, 10, 100)"},
  {title: "Plot x^1", description: "Plot y = x"},
  {title: "Plot x^2", description: "Plot y = x^2"},
  // ... up to x^10
])
  ↓
CreatePlan tool → display_plan_cards() → POST /api/chat/plan_cards (NEW)
  ↓
ChatPlanCardsHandler → WebSocket broadcast (type: "plan_cards") (NEW)
  ↓
Frontend service → planReceived signal → _addMessageToDisplay() (EXISTS)
  ↓
ChatManager renders 10 editable cards using existing _renderCards() (EXISTS)
  ↓
Agent transitions to END (waits for user response)
```

### **Phase 2: User Interaction & Plan Editing**
```
User sees 10 plan cards displayed in chat
  ↓
User edits cards:
- Changes "Plot x^3" title to "Plot cubic function"
- Deletes "Plot x^9" card using 🗑️ button (deleteCard - EXISTS)
- Clicks + button to add "Save plots to file" after "Plot x^10" (addStepAfterCard - EXISTS)
  ↓
User types: "Yes, proceed but make the plots bigger"
  ↓
Frontend _collectCurrentPlanCards() extracts 10 cards (9 original + 1 new) (NEW)
  ↓
Frontend sends message with context: {
  message: "Yes, proceed but make the plots bigger",
  context: {
    notebook_path: "...",
    updated_plan: [
      {id: "...", title: "Import libraries", description: "..."},
      {id: "...", title: "Plot cubic function", description: "..."},  // edited
      // ... (x^9 missing - deleted)
      {id: "...", title: "Save plots to file", description: "..."}    // added
    ]
  }
} (NEW)
```

### **Phase 3: Plan-Aware Execution**
```
Backend extracts updated_plan from context (NEW)
  ↓
Agent receives updated_plan in process_request() (NEW)
  ↓
Agent adds updated_plan to initial_state (NEW)
  ↓
Agent (analyze_and_decide): _format_plan_for_llm() adds plan to LLM context: (NEW)

"Current Plan:
--------
1. ⏳ Import libraries - Import matplotlib and numpy
2. ⏳ Create x values - Generate x = np.linspace(0, 10, 100)
3. ⏳ Plot x^1 - Plot y = x
4. ⏳ Plot cubic function - Plot y = x^3
...
9. ⏳ Save plots to file - Save plots to file

Note: This plan was recently edited by the user. Use the updated version above."
  ↓
LLM sees:
- User message: "Yes, proceed but make the plots bigger"
- Current plan state with user modifications
- Notebook context
  ↓
LLM decides: "User wants to proceed with modified plan and make plots bigger"
  ↓
Agent calls: insert_and_execute_cell(
  code="import matplotlib.pyplot as plt\nimport numpy as np\nplt.rcParams['figure.figsize'] = (12, 8)",
  status_message="Setting up libraries with larger plot size"
)
  ↓
Agent continues implementing the modified plan step by step
```

### **Phase 4: Continuous Plan Awareness**
```
On each subsequent turn:
  ↓
Agent sees current plan state in LLM context (NEW)
  ↓
Agent can mark steps as completed: step["completed"] = True
  ↓
LLM sees: "1. ✅ Import libraries - Import matplotlib and numpy"
  ↓
Agent continues with remaining ⏳ steps
  ↓
User can interrupt: "Stop after step 5"
  ↓
Agent sees updated user request + current plan progress
  ↓
Agent decides to stop and mark remaining steps as skipped
```

---

## 📋 **User Experience Flow**

### **Example Interaction:**

**User:** "Create plots for x,y powers 1-10"

**Agent:** Creates plan → Displays 10 editable cards → "Should I proceed with this plan?"

**User:** *Edits cards (deletes step 3, changes step 5 title)* → "Yes, but make the plots bigger"

**Agent:** Sees updated plan + user response → Implements modified plan with larger plots

**User:** "Stop after step 7"

**Agent:** Sees current progress + user request → Stops implementation, marks remaining steps as skipped

---

## 🔧 **Implementation Priority**

### **Phase 1: Basic Plan Display** (1-2 days)
1. ✅ **Tool call logging fix** (already done)
2. **Add ChatPlanCardsHandler** backend endpoint (NEW)
3. **Add WebSocket plan_cards handling** in frontend service (NEW)
4. **Test plan cards display** with existing card rendering (EXISTS)

### **Phase 2: Plan Context Integration** (2-3 days)
1. **Add plan collection** on user response (NEW)
2. **Include current plan** in agent context (NEW)
3. **Test LLM plan awareness** and decision making

### **Phase 3: Plan Implementation** (3-4 days)
1. **Add plan step tracking** (completed/pending status)
2. **Add plan-guided execution** logic
3. **Test complete workflow** end-to-end

---

## 🎯 **Success Criteria**

✅ **CreatePlan tool displays editable cards** in chat (using existing _renderCards)
✅ **User can edit/delete/add cards** visually (using existing card management)
✅ **User responds naturally** without hardcoded buttons
✅ **Agent sees updated plan** in context automatically
✅ **LLM decides next steps** based on plan + user response
✅ **Agent implements plan** using existing tools
✅ **Plan progress tracked** and visible to LLM

---

## 📁 **Files to Modify**

### **Backend (NEW CODE):**
- `packages/chat/jupyterlab_chat/__init__.py` - Add ChatPlanCardsHandler, plan context extraction

### **Frontend (MINIMAL CHANGES - LEVERAGE EXISTING):**
- `packages/chat/src/service.ts` - Add plan_cards WebSocket handling, plan collection method
- `packages/chat/src/widget.tsx` - NO CHANGES NEEDED (existing card infrastructure sufficient)

### **Agent (NEW CODE):**
- `packages/jupyter-agent/jupyter_agent_lg/agent.py` - Add plan context formatting

---

## 🚀 **Key Insight**

**The frontend card infrastructure is complete!** We only need:
1. **Backend endpoint** to receive plans from CreatePlan tool
2. **WebSocket broadcasting** to trigger existing plan display
3. **Plan collection** to extract edited cards on user response
4. **Plan context integration** in agent decisions

**Total implementation: ~3-4 new methods leveraging existing robust card system.**

---

## ✅ **IMPLEMENTATION COMPLETE - REVISED ARCHITECTURE**

### **🔄 MAJOR ARCHITECTURE CHANGE:**
**From:** Plan in system prompt (broken sequence context)
**To:** Plan as conversation messages (natural sequence flow)

### **New Architecture Benefits:**
- ✅ **Natural Conversation Flow** - Plans stored as assistant messages preserve timeline
- ✅ **Sequence Awareness** - LLM understands request → plan → edits → new request naturally
- ✅ **Plan Persistence** - Plans survive conversation reloads
- ✅ **Edit Tracking** - User modifications update conversation history
- ✅ **Timeline Context** - LLM knows if user request came before/after plan

### **What Was Built:**

#### **Backend Components:**
1. **ChatPlanCardsHandler** - Receives plan steps and broadcasts via WebSocket
2. **Plan Message Storage** - Stores plans as assistant messages in conversation history
3. **Plan Message Updates** - Updates existing plan messages when user edits cards
4. **Plan Context Removal** - Removed plan from system prompt entirely

#### **Frontend Components:**
1. **WebSocket Plan Cards Handler** - Displays plan cards in chat
2. **Plan Collection Method** - Collects edited cards and updates conversation
3. **Plan Message Rendering** - Renders plan cards from conversation history on reload
4. **Card UI Improvements** - Single-line format, smaller subtle buttons

#### **Agent Integration:**
1. **Enhanced System Prompt** - Comprehensive plan management instructions
2. **Conversation-Based Planning** - LLM reads plans from conversation history
3. **Natural Decision Making** - Follows conversation sequence for plan decisions
4. **Plan Precedence Rules** - Clear rules for when to create vs implement plans

### **New Workflow:**
```
User: "Create plots for x,y powers 1-10"
Agent: Calls CreatePlan → Plan stored as assistant message with cards
User: [Edits cards, deletes 5 steps]
User: "proceed"
Backend: Updates the assistant plan message with edited 5 steps
Agent: Reads updated plan from conversation → Implements 5 steps
```

### **Key Benefits Achieved:**
- ✅ **Sequence Context Preserved** - LLM understands conversation timeline
- ✅ **Natural Plan Management** - No artificial system prompt rules
- ✅ **Persistent Plan State** - Plans survive page reloads
- ✅ **Clean Conversation Flow** - Single source of truth for active plan
- ✅ **User Edit Integration** - Modifications seamlessly update conversation

### **Files Modified:**
- `packages/chat/jupyterlab_chat/__init__.py` - Plan message storage and updates
- `packages/chat/src/service.ts` - Plan collection and conversation integration
- `packages/chat/src/widget.tsx` - Improved card UI and conversation rendering
- `packages/jupyter-agent/jupyter_agent_lg/agent.py` - Enhanced system prompt, removed plan context

**Architecture is now robust and natural! 🚀**
