# Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Streamlit Web Interface                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │   Sidebar    │  │  Chat Area   │  │  Approval Panel    │   │
│  │              │  │              │  │                    │   │
│  │ - API Config │  │ - Messages   │  │ - Code Review      │   │
│  │ - Initialize │  │ - Real-time  │  │ - Approve/Reject   │   │
│  │ - Clear/Reset│  │ - Streaming  │  │ - HITL Controls    │   │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘   │
└─────────┼──────────────────┼───────────────────┼───────────────┘
          │                  │                   │
          └──────────────────┼───────────────────┘
                            │
                 ┌──────────▼──────────┐
                 │  st.session_state   │
                 │                     │
                 │ - messages[]        │
                 │ - team              │
                 │ - pending_approval  │
                 │ - google_api_key    │
                 └──────────┬──────────┘
                            │
              ┌─────────────▼─────────────┐
              │   SelectorGroupChat       │
              │   (AutoGen v0.4 Team)     │
              │                           │
              │  ┌─────────────────────┐ │
              │  │  Model Client       │ │
              │  │  (Google Gemini)    │ │
              │  └─────────────────────┘ │
              │                           │
              │  ┌─────────────────────┐ │
              │  │ Termination Logic   │ │
              │  │ Max Turns: 20       │ │
              │  └─────────────────────┘ │
              └─────────────┬─────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────────┐  ┌──────▼──────┐  ┌────────▼────────┐
│ Planner Agent  │  │ Coder Agent │  │ Reviewer Agent  │
│                │  │             │  │                 │
│ Role:          │  │ Role:       │  │ Role:           │
│ - Analyze task │  │ - Implement │  │ - Review code   │
│ - Break down   │  │ - Document  │  │ - Find bugs     │
│ - Create plan  │  │ - Best      │  │ - Suggest fixes │
│                │  │   practices │  │                 │
│ Handoffs:      │  │ Handoffs:   │  │ Handoffs:       │
│ → Coder        │  │ → Reviewer  │  │ → Coder         │
│                │  │ → Planner   │  │ → User          │
└────────────────┘  └─────────────┘  └─────────────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                ┌───────────▼───────────┐
                │  Message Pipeline     │
                │                       │
                │  TextMessage          │
                │  ToolCallMessage      │
                │  ToolCallResultMessage│
                └───────────┬───────────┘
                            │
              ┌─────────────▼─────────────┐
              │   Custom Integration      │
              │                           │
              │  StreamlitAssistantAgent  │
              │  ├─ on_messages()         │
              │  └─ _add_to_streamlit()   │
              │                           │
              │  StreamlitUserProxyAgent  │
              │  ├─ handle_user_input()   │
              │  └─ request_approval()    │
              └───────────────────────────┘
```

## Data Flow

### 1. User Input Flow
```
User Types Message
    ↓
Streamlit Chat Input
    ↓
Add to session_state.messages[]
    ↓
Create TextMessage
    ↓
team.run(task=message)
    ↓
Async Processing
    ↓
Results to session_state
    ↓
st.rerun() → UI Update
```

### 2. Agent Collaboration Flow
```
Initial Message (User)
    ↓
SelectorGroupChat (selects agent)
    ↓
Planner Agent
    ├─ Analyzes task
    ├─ Creates plan
    └─ Handoff → Coder
    ↓
Coder Agent
    ├─ Implements code
    ├─ Adds documentation
    └─ Handoff → Reviewer
    ↓
Reviewer Agent
    ├─ Reviews code
    ├─ Checks quality
    └─ Decision:
        ├─ Approve → Handoff to User
        └─ Reject → Handoff to Coder (iterate)
    ↓
Final Result → User
```

### 3. Message Logging Flow
```
Agent generates message
    ↓
on_messages() intercepts
    ↓
_add_to_streamlit_chat()
    ↓
Append to st.session_state.messages[]
    ↓
Include metadata:
    - role (user/assistant)
    - content (message text)
    - agent (agent name)
    - timestamp (ISO format)
    ↓
UI automatically renders
```

### 4. Approval Flow (HITL)
```
Agent requests code execution
    ↓
Store in pending_approval
    ↓
Render approval UI
    ├─ Display code
    ├─ Show "Approve" button
    └─ Show "Reject" button
    ↓
User clicks button
    ↓
Update approval_granted
    ↓
Clear pending_approval
    ↓
st.rerun()
    ↓
Continue or abort execution
```

## Component Interactions

### Streamlit Session State
```python
{
    "messages": [
        {
            "role": "user",
            "content": "Create a function...",
            "agent": "User",
            "timestamp": "2025-11-18T18:42:00"
        },
        {
            "role": "assistant",
            "content": "**[Planner]** I'll break this down...",
            "agent": "Planner",
            "timestamp": "2025-11-18T18:42:05"
        }
    ],
    "team": <SelectorGroupChat instance>,
    "pending_approval": {
        "action": "execute_code",
        "code": "def my_function():\n    ...",
        "timestamp": "2025-11-18T18:42:10"
    },
    "google_api_key": "***",
    "chat_active": True,
    "approval_granted": False
}
```

### Agent Configuration
```python
{
    "Planner": {
        "model_client": <Gemini Client>,
        "system_message": "You are a Planner...",
        "handoffs": ["Coder"]
    },
    "Coder": {
        "model_client": <Gemini Client>,
        "system_message": "You are a Coder...",
        "handoffs": ["Reviewer", "Planner"]
    },
    "Reviewer": {
        "model_client": <Gemini Client>,
        "system_message": "You are a Reviewer...",
        "handoffs": ["Coder", "User"]
    }
}
```

## Technology Stack

```
┌─────────────────────────────────────┐
│         User Interface              │
│         (Streamlit 1.51+)           │
├─────────────────────────────────────┤
│      Agent Orchestration            │
│      (AutoGen v0.4)                 │
│  ┌─────────────────────────────┐   │
│  │  - AgentChat API            │   │
│  │  - SelectorGroupChat        │   │
│  │  - Message Pipeline         │   │
│  └─────────────────────────────┘   │
├─────────────────────────────────────┤
│         LLM Backend                 │
│    (Google Gemini 2.0 Flash)        │
│  ┌─────────────────────────────┐   │
│  │  - OpenAI-compatible API    │   │
│  │  - Streaming support        │   │
│  │  - Context management       │   │
│  └─────────────────────────────┘   │
├─────────────────────────────────────┤
│       Python Runtime                │
│       (Python 3.11.14)              │
└─────────────────────────────────────┘
```

## Async Execution Model

```
Streamlit Main Thread
    │
    ├─ Render UI (synchronous)
    │
    ├─ User Input Event
    │  └─ asyncio.run(run_team())
    │      │
    │      ├─ await team.run()
    │      │   │
    │      │   ├─ Agent 1: await on_messages()
    │      │   ├─ Agent 2: await on_messages()
    │      │   └─ Agent 3: await on_messages()
    │      │
    │      └─ Update session_state
    │
    └─ st.rerun() → Re-render UI
```

## Security Architecture

```
┌──────────────────────────────────────┐
│         Security Layers              │
├──────────────────────────────────────┤
│  1. API Key Protection               │
│     - Never in version control       │
│     - .gitignore enforcement         │
│     - Three secure input methods     │
├──────────────────────────────────────┤
│  2. Input Validation                 │
│     - API key required check         │
│     - Team initialization guard      │
│     - Error message sanitization     │
├──────────────────────────────────────┤
│  3. Code Execution Safety            │
│     - Human approval required        │
│     - Code display before run        │
│     - Explicit approve/reject        │
├──────────────────────────────────────┤
│  4. Session Isolation                │
│     - Per-session state              │
│     - No shared state between users  │
│     - Automatic cleanup              │
└──────────────────────────────────────┘
```

## Extensibility Points

### 1. Custom Tools
```python
from autogen_agentchat.tools import Tool

def my_tool(param: str) -> str:
    """Custom functionality"""
    return result

coder = StreamlitAssistantAgent(
    name="Coder",
    tools=[Tool(my_tool)]
)
```

### 2. Custom Agents
```python
class CustomAgent(StreamlitAssistantAgent):
    async def on_messages(self, messages):
        # Custom logic
        return await super().on_messages(messages)
```

### 3. Custom UI Components
```python
def render_custom_component():
    with st.expander("Custom View"):
        st.dataframe(agent_metrics)
```

### 4. Persistence Layer
```python
def save_to_db():
    db.save(st.session_state.messages)

def load_from_db():
    st.session_state.messages = db.load()
```

---

**Architecture designed for**: Scalability, Maintainability, Extensibility, Security
