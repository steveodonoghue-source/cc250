"""
FastAPI Wrapper for AutoGen Multi-Agent System

Provides RESTful API access to the agent system for programmatic use,
CI/CD integration, and external tool integration.

Endpoints:
- POST /api/v1/chat - Start a new agent task
- GET /api/v1/tasks/{task_id} - Get task status and results
- GET /api/v1/conversations - List saved conversations
- GET /api/v1/conversations/{session_id} - Get conversation details
- GET /api/v1/skills - List available skills
- POST /api/v1/skills - Register a new skill
- GET /api/v1/health - Health check

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import uuid
import logging
import os

# Import our modules
import database as db
from streamlit_app import create_team, TextMessage
import streamlit as st

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="AutoGen Multi-Agent API",
    description="RESTful API for AutoGen v0.4 Multi-Agent Coding System",
    version="1.0.0"
)

# CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., description="User message to send to agents")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    api_key: str = Field(..., description="Google Gemini API key")
    max_turns: Optional[int] = Field(40, description="Maximum agent turns")

class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    task_id: str = Field(..., description="Unique task ID for polling")
    session_id: str = Field(..., description="Session ID for this conversation")
    status: str = Field(..., description="Task status: pending, running, completed, failed")
    message: str = Field(..., description="Status message")

class TaskStatus(BaseModel):
    """Response model for task status."""
    task_id: str
    session_id: str
    status: str  # pending, running, completed, failed
    progress: Optional[str] = None
    messages: Optional[List[Dict]] = None
    cost: Optional[float] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None

class ConversationListItem(BaseModel):
    """Conversation list item."""
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    total_cost: float

class SkillRequest(BaseModel):
    """Request model for registering a skill."""
    tool_name: str
    description: str
    code: str
    parameters: Dict[str, Any]
    safety_notes: List[str]

class SkillResponse(BaseModel):
    """Response model for skill."""
    id: int
    tool_name: str
    description: str
    code: str
    parameters: Dict[str, Any]
    safety_notes: List[str]
    created_at: str
    usage_count: int

# ============================================================================
# In-Memory Task Store (In production, use Redis or database)
# ============================================================================

tasks = {}  # task_id -> TaskStatus

def create_task(session_id: str) -> str:
    """Create a new task and return task ID."""
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        'task_id': task_id,
        'session_id': session_id,
        'status': 'pending',
        'progress': None,
        'messages': [],
        'cost': None,
        'error': None,
        'created_at': datetime.now().isoformat(),
        'completed_at': None
    }
    return task_id

def update_task(task_id: str, **kwargs):
    """Update task status."""
    if task_id in tasks:
        tasks[task_id].update(kwargs)

# ============================================================================
# Authentication (Simple API Key Check)
# ============================================================================

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key from header (optional for now)."""
    # In production, implement proper API key validation
    # For now, we'll use the Gemini API key passed in requests
    return True

# ============================================================================
# Agent Task Execution
# ============================================================================

async def run_agent_task(task_id: str, message: str, api_key: str, session_id: str, max_turns: int):
    """Run agent task in background."""
    try:
        update_task(task_id, status='running', progress='Initializing agents...')
        logger.info(f"Starting task {task_id} for session {session_id}")

        # Set API key
        os.environ["GEMINI_API_KEY"] = api_key

        # Initialize session state (mimic Streamlit's session state)
        class MockSessionState:
            def __init__(self):
                self.messages = []
                self.cost_tracking = {
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_cost": 0.0,
                    "by_agent": {},
                    "history": []
                }
                self.tool_calls = []
                self.uploaded_files = []
                self.filehandler_agent = None
                self.pending_approval = None
                self.approval_granted = False

        # Create mock session state
        mock_state = MockSessionState()

        # Load existing conversation if session_id provided
        if session_id:
            existing = db.load_conversation(session_id)
            if existing:
                mock_state.messages = existing.get('messages', [])
                logger.info(f"Loaded {len(mock_state.messages)} existing messages")

        # Create team
        update_task(task_id, progress='Creating agent team...')

        # Temporarily set st.session_state
        original_session_state = getattr(st, 'session_state', None)
        st.session_state = mock_state

        try:
            team = create_team()
            logger.info("Team created successfully")

            # Add user message
            mock_state.messages.append({
                "role": "user",
                "content": message,
                "agent": "User",
                "timestamp": datetime.now().isoformat()
            })

            # Run team
            update_task(task_id, progress='Agents collaborating...')
            initial_message = TextMessage(content=message, source="User")

            result = await team.run(task=initial_message, max_turns=max_turns)
            logger.info(f"Team run completed. Messages: {len(result.messages)}")

            # Save conversation
            cost = mock_state.cost_tracking.get("total_cost", 0.0)
            title = message[:50] + "..." if len(message) > 50 else message

            db.save_conversation(
                session_id=session_id,
                title=title,
                messages=mock_state.messages,
                cost_tracking=mock_state.cost_tracking
            )
            logger.info(f"Conversation saved: {session_id}")

            # Update task as completed
            update_task(
                task_id,
                status='completed',
                progress='Task completed successfully',
                messages=mock_state.messages,
                cost=cost,
                completed_at=datetime.now().isoformat()
            )
            logger.info(f"Task {task_id} completed successfully")

        finally:
            # Restore original session state
            if original_session_state is not None:
                st.session_state = original_session_state
            else:
                delattr(st, 'session_state')

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)
        update_task(
            task_id,
            status='failed',
            error=str(e),
            completed_at=datetime.now().isoformat()
        )

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "AutoGen Multi-Agent API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "chat": "POST /api/v1/chat",
            "task_status": "GET /api/v1/tasks/{task_id}",
            "conversations": "GET /api/v1/conversations",
            "conversation_detail": "GET /api/v1/conversations/{session_id}",
            "skills": "GET /api/v1/skills",
            "register_skill": "POST /api/v1/skills",
            "health": "GET /api/v1/health"
        }
    }

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_tasks": len([t for t in tasks.values() if t['status'] in ['pending', 'running']]),
        "total_tasks": len(tasks)
    }

@app.post("/api/v1/chat", response_model=ChatResponse)
async def create_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    authorized: bool = Depends(verify_api_key)
):
    """
    Start a new agent task.

    The task runs in the background. Use the returned task_id to poll for results.
    """
    # Generate session ID if not provided
    session_id = request.session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    # Create task
    task_id = create_task(session_id)

    # Run in background
    background_tasks.add_task(
        run_agent_task,
        task_id=task_id,
        message=request.message,
        api_key=request.api_key,
        session_id=session_id,
        max_turns=request.max_turns
    )

    return ChatResponse(
        task_id=task_id,
        session_id=session_id,
        status="pending",
        message="Task created successfully. Use task_id to poll for results."
    )

@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Get status of a task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatus(**tasks[task_id])

@app.get("/api/v1/conversations", response_model=List[ConversationListItem])
async def list_conversations(limit: int = 50, archived: bool = False):
    """List saved conversations."""
    conversations = db.list_conversations(limit=limit, archived=archived)
    return [ConversationListItem(**conv) for conv in conversations]

@app.get("/api/v1/conversations/{session_id}")
async def get_conversation(session_id: str):
    """Get conversation details including full message history."""
    conversation = db.load_conversation(session_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation

@app.delete("/api/v1/conversations/{session_id}")
async def delete_conversation(session_id: str):
    """Delete a conversation."""
    db.delete_conversation(session_id)
    return {"status": "deleted", "session_id": session_id}

@app.get("/api/v1/conversations/{session_id}/export")
async def export_conversation(session_id: str):
    """Export conversation as Markdown."""
    md_content = db.export_conversation_markdown(session_id)
    if not md_content:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return JSONResponse(
        content={"markdown": md_content},
        media_type="application/json"
    )

@app.get("/api/v1/skills", response_model=List[SkillResponse])
async def list_skills(active_only: bool = True, limit: int = 100):
    """List available skills."""
    skills = db.list_skills(active_only=active_only, limit=limit)
    return [SkillResponse(**skill) for skill in skills]

@app.post("/api/v1/skills", response_model=SkillResponse)
async def register_skill(skill: SkillRequest):
    """Register a new skill."""
    skill_id = db.save_skill(
        tool_name=skill.tool_name,
        description=skill.description,
        code=skill.code,
        parameters=skill.parameters,
        safety_notes=skill.safety_notes
    )

    saved_skill = db.get_skill(skill.tool_name)
    if not saved_skill:
        raise HTTPException(status_code=500, detail="Failed to save skill")

    return SkillResponse(**saved_skill)

@app.delete("/api/v1/skills/{tool_name}")
async def delete_skill(tool_name: str):
    """Delete a skill."""
    db.delete_skill(tool_name)
    return {"status": "deleted", "tool_name": tool_name}

@app.get("/api/v1/cost/summary")
async def get_cost_summary(days: int = 7):
    """Get cost summary for the last N days."""
    summary = db.get_cost_summary(days=days)
    return summary

# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("🚀 AutoGen Multi-Agent API Server")
    print("=" * 60)
    print()
    print("📚 API Documentation: http://localhost:8000/docs")
    print("🔍 Health Check: http://localhost:8000/api/v1/health")
    print()
    print("Starting server...")
    print("=" * 60)

    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
