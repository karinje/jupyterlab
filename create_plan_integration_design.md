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

## 🔄 **Complete Workflow**

### **Phase 1: Plan Creation**
```
User: "Create plots for x,y powers 1-10"
  ↓
Agent (analyze_and_decide): Decides to create plan
  ↓
Agent (tools): Executes CreatePlan tool
  ↓
Backend: POST /api/chat/plan_cards → WebSocket broadcast (NEW)
  ↓
Frontend: planReceived signal → _addMessageToDisplay() with messageType: 'plan' (EXISTS)
  ↓
Frontend: _renderCards() displays editable cards (EXISTS)
  ↓
Agent: Transitions to END node (waits for user response)
```

### **Phase 2: User Interaction**
```
User: Edits cards using existing contenteditable fields (EXISTS)
User: Clicks + button to add steps (addStepAfterCard - EXISTS)
User: Clicks 🗑️ to delete steps (deleteCard - EXISTS)
  ↓
User: Types response "Yes, proceed but skip step 3"
  ↓
Frontend: _collectCurrentPlanCards() extracts edited cards (NEW)
  ↓
Frontend: Sends user message + updated_plan in context (NEW)
```

### **Phase 3: Plan Implementation**
```
Backend: Includes updated_plan in agent context (NEW)
  ↓
Agent: _format_plan_for_llm() adds plan to LLM context (NEW)
  ↓
Agent (analyze_and_decide): Sees user response + current plan state
  ↓
Agent: Decides to implement plan using existing insert_and_execute_cell
  ↓
Agent: Continues until plan complete or user interrupts
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
