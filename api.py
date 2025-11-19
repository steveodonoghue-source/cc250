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
import json

# Import our modules
import database as db
import database_marketplace as db_market
import database_cost_optimization as db_cost
import database_orchestration as db_orch
import database_testing_quality as db_test
import database_integrations as db_int
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
# Marketplace API Endpoints
# ============================================================================

# --- Pydantic Models for Marketplace ---

class CategoryCreate(BaseModel):
    """Request model for creating a category."""
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = ""

class SkillRating(BaseModel):
    """Request model for rating a skill."""
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5")
    review_text: Optional[str] = ""

class SkillPricingUpdate(BaseModel):
    """Request model for updating skill pricing."""
    pricing_type: str = Field(..., description="One of: free, one_time, subscription, pay_per_use")
    price: Optional[float] = 0.0
    currency: Optional[str] = "USD"
    billing_period: Optional[str] = None

class SkillPackCreate(BaseModel):
    """Request model for creating a skill pack."""
    name: str
    description: str
    skill_ids: List[int]
    pricing_type: Optional[str] = "free"
    price: Optional[float] = 0.0
    icon: Optional[str] = ""

# Cost Optimization Models
class BudgetConfig(BaseModel):
    """Request model for setting budget."""
    budget_type: str = Field(..., description="One of: daily, weekly, monthly, per_session")
    budget_limit: float = Field(..., gt=0, description="Budget limit in USD")
    alert_threshold: Optional[float] = Field(0.8, ge=0, le=1, description="Alert threshold (0-1)")

class AgentModelConfig(BaseModel):
    """Request model for configuring agent model."""
    agent_name: str
    model_name: str = Field(..., description="e.g., gemini-2.0-flash-exp or gemini-2.5-pro")
    max_tokens: Optional[int] = 8192
    temperature: Optional[float] = Field(0.7, ge=0, le=1)

class CostTrackingRequest(BaseModel):
    """Request model for tracking cost."""
    session_id: str
    agent_name: str
    model_name: str
    input_tokens: int
    output_tokens: int

# Orchestration Models
class WorkflowCreate(BaseModel):
    """Request model for creating a workflow."""
    name: str
    description: str
    workflow_type: str = Field(..., description="One of: sequential, parallel, conditional, hybrid")
    config: Dict
    created_by: Optional[str] = "api_user"

class WorkflowStepCreate(BaseModel):
    """Request model for adding a workflow step."""
    step_number: int
    agent_name: str
    task_description: Optional[str] = None
    depends_on_step: Optional[int] = None
    parallel_group: Optional[int] = 0
    condition: Optional[str] = None
    config: Optional[Dict] = None

class WorkflowExecutionStart(BaseModel):
    """Request model for starting workflow execution."""
    workflow_id: int
    session_id: str
    input_data: Optional[Dict] = None

class RoutingRequest(BaseModel):
    """Request model for task routing."""
    task: str
    keywords: Optional[List[str]] = None

# Testing & Quality Models
class TestSuiteCreate(BaseModel):
    """Request model for creating a test suite."""
    skill_id: int
    name: str
    description: Optional[str] = ""

class TestCaseCreate(BaseModel):
    """Request model for creating a test case."""
    suite_id: int
    name: str
    test_code: str
    expected_output: Optional[Any] = None
    description: Optional[str] = ""

class SafetyCheckRequest(BaseModel):
    """Request model for safety check."""
    skill_id: int
    code: str

class QualityScoreRequest(BaseModel):
    """Request model for quality score calculation."""
    skill_id: int

# --- Category Endpoints ---

@app.get("/api/v1/marketplace/categories")
async def list_categories():
    """List all skill categories."""
    categories = db_market.list_categories()
    return categories

@app.post("/api/v1/marketplace/categories")
async def create_category(category: CategoryCreate):
    """Create a new skill category."""
    category_id = db_market.create_category(
        name=category.name,
        description=category.description,
        icon=category.icon
    )
    return {"id": category_id, "name": category.name}

@app.post("/api/v1/marketplace/skills/{skill_id}/tag/{category_id}")
async def tag_skill_with_category(skill_id: int, category_id: int):
    """Tag a skill with a category."""
    db_market.tag_skill(skill_id, category_id)
    return {"status": "tagged", "skill_id": skill_id, "category_id": category_id}

@app.get("/api/v1/marketplace/skills/{skill_id}/categories")
async def get_skill_categories(skill_id: int):
    """Get categories for a specific skill."""
    categories = db_market.get_skill_categories(skill_id)
    return categories

# --- Rating Endpoints ---

@app.post("/api/v1/marketplace/skills/{skill_id}/rate")
async def rate_skill(skill_id: int, rating: SkillRating, user_id: str = "default_user"):
    """Rate a skill (1-5 stars) with optional review."""
    rating_id = db_market.add_rating(
        skill_id=skill_id,
        user_id=user_id,
        rating=rating.rating,
        review_text=rating.review_text
    )
    return {"rating_id": rating_id, "status": "rated"}

@app.get("/api/v1/marketplace/skills/{skill_id}/rating")
async def get_skill_rating(skill_id: int):
    """Get rating summary for a skill."""
    summary = db_market.get_skill_rating_summary(skill_id)
    return summary

@app.get("/api/v1/marketplace/skills/{skill_id}/reviews")
async def get_skill_reviews(skill_id: int, limit: int = 10):
    """Get recent reviews for a skill."""
    reviews = db_market.get_skill_reviews(skill_id, limit)
    return reviews

# --- Pricing Endpoints ---

@app.post("/api/v1/marketplace/skills/{skill_id}/pricing")
async def set_skill_pricing(skill_id: int, pricing: SkillPricingUpdate):
    """Set or update pricing for a skill."""
    pricing_id = db_market.set_skill_pricing(
        skill_id=skill_id,
        pricing_type=pricing.pricing_type,
        price=pricing.price,
        currency=pricing.currency,
        billing_period=pricing.billing_period
    )
    return {"pricing_id": pricing_id, "status": "updated"}

@app.get("/api/v1/marketplace/skills/{skill_id}/pricing")
async def get_skill_pricing(skill_id: int):
    """Get current pricing for a skill."""
    pricing = db_market.get_skill_pricing(skill_id)
    if not pricing:
        return {"pricing_type": "free", "price": 0.0}
    return pricing

# --- Install Tracking Endpoints ---

@app.post("/api/v1/marketplace/skills/{skill_id}/install")
async def track_skill_install(skill_id: int, user_id: str = "default_user"):
    """Track a skill installation."""
    db_market.track_install(skill_id, user_id)
    return {"status": "installed", "skill_id": skill_id}

@app.get("/api/v1/marketplace/skills/{skill_id}/installs")
async def get_install_count(skill_id: int):
    """Get total install count for a skill."""
    count = db_market.get_install_count(skill_id)
    return {"skill_id": skill_id, "install_count": count}

# --- Skill Pack Endpoints ---

@app.post("/api/v1/marketplace/packs")
async def create_skill_pack(pack: SkillPackCreate):
    """Create a skill pack (bundle)."""
    pack_id = db_market.create_skill_pack(
        name=pack.name,
        description=pack.description,
        skill_ids=pack.skill_ids,
        pricing_type=pack.pricing_type,
        price=pack.price,
        icon=pack.icon
    )
    return {"pack_id": pack_id, "name": pack.name}

@app.get("/api/v1/marketplace/packs")
async def list_skill_packs():
    """List all skill packs."""
    packs = db_market.list_skill_packs()
    return packs

@app.get("/api/v1/marketplace/packs/{pack_id}/skills")
async def get_pack_skills(pack_id: int):
    """Get all skills in a pack."""
    skills = db_market.get_pack_skills(pack_id)
    return skills

# --- Enhanced Skill Listing ---

@app.get("/api/v1/marketplace/skills")
async def list_marketplace_skills(
    limit: int = 100,
    category_id: Optional[int] = None,
    min_rating: Optional[float] = None
):
    """List skills with marketplace metadata (ratings, installs, pricing)."""
    skills = db_market.list_skills_with_marketplace_data(
        limit=limit,
        category_id=category_id,
        min_rating=min_rating
    )
    return skills

# --- Dependency Endpoints ---

@app.post("/api/v1/marketplace/skills/{skill_id}/dependencies/{depends_on_skill_id}")
async def add_skill_dependency(
    skill_id: int,
    depends_on_skill_id: int,
    min_version: Optional[str] = None,
    max_version: Optional[str] = None,
    is_required: bool = True
):
    """Add a dependency between skills."""
    db_market.add_dependency(
        skill_id=skill_id,
        depends_on_skill_id=depends_on_skill_id,
        min_version=min_version,
        max_version=max_version,
        is_required=is_required
    )
    return {"status": "dependency_added"}

@app.get("/api/v1/marketplace/skills/{skill_id}/dependencies")
async def get_skill_dependencies(skill_id: int):
    """Get dependencies for a skill."""
    deps = db_market.get_skill_dependencies(skill_id)
    return deps

# --- Version Endpoints ---

@app.get("/api/v1/marketplace/skills/{skill_id}/versions")
async def get_skill_versions(skill_id: int):
    """Get all versions of a skill."""
    versions = db_market.get_skill_versions(skill_id)
    return versions


# ============================================================================
# Cost Optimization Endpoints
# ============================================================================

# --- Budget Management ---

@app.post("/api/v1/cost/budget")
async def set_budget(config: BudgetConfig):
    """Set a budget configuration."""
    budget_id = db_cost.set_budget(
        budget_type=config.budget_type,
        budget_limit=config.budget_limit,
        alert_threshold=config.alert_threshold
    )
    return {"budget_id": budget_id, "status": "budget_set"}

@app.get("/api/v1/cost/budget/{budget_type}")
async def get_budget(budget_type: str):
    """Get active budget configuration."""
    budget = db_cost.get_active_budget(budget_type)
    if budget:
        return budget
    return {"message": f"No active budget found for type: {budget_type}"}

# --- Agent Model Configuration ---

@app.post("/api/v1/cost/agents/config")
async def configure_agent_model(config: AgentModelConfig):
    """Configure which model an agent should use."""
    config_id = db_cost.set_agent_model(
        agent_name=config.agent_name,
        model_name=config.model_name,
        max_tokens=config.max_tokens,
        temperature=config.temperature
    )
    return {"config_id": config_id, "status": "agent_configured"}

@app.get("/api/v1/cost/agents/config/{agent_name}")
async def get_agent_config(agent_name: str):
    """Get model configuration for an agent."""
    config = db_cost.get_agent_model_config(agent_name)
    if config:
        return config
    return {"message": f"No configuration found for agent: {agent_name}"}

@app.get("/api/v1/cost/agents/configs")
async def list_agent_configs():
    """List all agent model configurations."""
    configs = db_cost.list_agent_configs()
    return configs

# --- Cost Tracking ---

@app.post("/api/v1/cost/track")
async def track_cost(request: CostTrackingRequest):
    """Track cost for an API call."""
    tracking_id, estimated_cost = db_cost.track_cost(
        session_id=request.session_id,
        agent_name=request.agent_name,
        model_name=request.model_name,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens
    )
    return {
        "tracking_id": tracking_id,
        "estimated_cost": estimated_cost,
        "status": "tracked"
    }

@app.get("/api/v1/cost/session/{session_id}/summary")
async def get_session_cost_summary(session_id: str):
    """Get cost summary for a session."""
    summary = db_cost.get_session_cost_summary(session_id)
    return summary

@app.get("/api/v1/cost/analytics")
async def get_cost_analytics(days: int = 7):
    """Get cost analytics for the last N days."""
    analytics = db_cost.get_cost_analytics(days=days)
    return analytics

# --- Alerts ---

@app.get("/api/v1/cost/alerts")
async def get_alerts(session_id: Optional[str] = None):
    """Get unacknowledged cost alerts."""
    alerts = db_cost.get_unacknowledged_alerts(session_id)
    return alerts

@app.post("/api/v1/cost/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """Acknowledge a cost alert."""
    db_cost.acknowledge_alert(alert_id)
    return {"status": "acknowledged"}

# --- Cache Stats ---

@app.get("/api/v1/cost/cache/stats")
async def get_cache_stats():
    """Get cache performance statistics."""
    stats = db_cost.get_cache_stats()
    return stats


# ============================================================================
# Orchestration Endpoints
# ============================================================================

# --- Workflow Management ---

@app.post("/api/v1/orchestration/workflows")
async def create_workflow(workflow: WorkflowCreate):
    """Create a new workflow definition."""
    workflow_id = db_orch.create_workflow(
        name=workflow.name,
        description=workflow.description,
        workflow_type=workflow.workflow_type,
        config=workflow.config,
        created_by=workflow.created_by
    )
    return {"workflow_id": workflow_id, "status": "created"}

@app.get("/api/v1/orchestration/workflows")
async def list_workflows(active_only: bool = True):
    """List all workflow definitions."""
    workflows = db_orch.list_workflows(active_only=active_only)
    return workflows

@app.get("/api/v1/orchestration/workflows/{workflow_id}")
async def get_workflow(workflow_id: int):
    """Get workflow definition with steps."""
    workflow = db_orch.get_workflow(workflow_id)
    if workflow:
        return workflow
    return {"error": f"Workflow {workflow_id} not found"}

@app.post("/api/v1/orchestration/workflows/{workflow_id}/steps")
async def add_workflow_step(workflow_id: int, step: WorkflowStepCreate):
    """Add a step to a workflow."""
    step_id = db_orch.add_workflow_step(
        workflow_id=workflow_id,
        step_number=step.step_number,
        agent_name=step.agent_name,
        task_description=step.task_description,
        depends_on_step=step.depends_on_step,
        parallel_group=step.parallel_group,
        condition=step.condition,
        config=step.config
    )
    return {"step_id": step_id, "status": "added"}

@app.post("/api/v1/orchestration/workflows/{workflow_id}/execute")
async def start_workflow_execution(workflow_id: int, execution: WorkflowExecutionStart):
    """Start a workflow execution."""
    execution_id = db_orch.start_workflow_execution(
        workflow_id=workflow_id,
        session_id=execution.session_id,
        input_data=execution.input_data
    )
    return {"execution_id": execution_id, "status": "started"}

@app.put("/api/v1/orchestration/executions/{execution_id}")
async def update_execution(execution_id: int, status: str, output_data: Optional[Dict] = None, error: Optional[str] = None):
    """Update workflow execution status."""
    db_orch.update_workflow_execution(
        execution_id=execution_id,
        status=status,
        output_data=output_data,
        error=error
    )
    return {"status": "updated"}

# --- Workflow Templates ---

@app.get("/api/v1/orchestration/templates")
async def list_templates(category: Optional[str] = None):
    """List workflow templates."""
    templates = db_orch.list_workflow_templates(category=category)
    return templates

@app.post("/api/v1/orchestration/templates/{template_id}/instantiate")
async def create_from_template(template_id: int, name: str, session_id: str):
    """Create and start a workflow from a template."""
    workflow_id = db_orch.create_workflow_from_template(
        template_id=template_id,
        name=name,
        session_id=session_id
    )
    return {"workflow_id": workflow_id, "status": "created_from_template"}

# --- Routing ---

@app.post("/api/v1/orchestration/route")
async def route_task(request: RoutingRequest):
    """Route a task to the best agent."""
    agent = db_orch.get_best_agent_for_task(
        task=request.task,
        keywords=request.keywords
    )
    return {"recommended_agent": agent}

@app.get("/api/v1/orchestration/agents/{agent_name}/specializations")
async def get_specializations(agent_name: str):
    """Get agent specializations."""
    specializations = db_orch.get_agent_specializations(agent_name)
    return specializations


# ============================================================================
# Testing & Quality Endpoints
# ============================================================================

# --- Test Management ---

@app.post("/api/v1/testing/suites")
async def create_test_suite(suite: TestSuiteCreate):
    """Create a test suite for a skill."""
    suite_id = db_test.create_test_suite(
        skill_id=suite.skill_id,
        name=suite.name,
        description=suite.description
    )
    return {"suite_id": suite_id, "status": "created"}

@app.post("/api/v1/testing/cases")
async def create_test_case(test_case: TestCaseCreate):
    """Add a test case to a suite."""
    case_id = db_test.add_test_case(
        suite_id=test_case.suite_id,
        name=test_case.name,
        test_code=test_case.test_code,
        expected_output=test_case.expected_output,
        description=test_case.description
    )
    return {"test_case_id": case_id, "status": "created"}

@app.post("/api/v1/testing/cases/{test_case_id}/run")
async def run_test(test_case_id: int, skill_id: int, skill_code: str):
    """Execute a test case."""
    result = db_test.run_test_case(
        test_case_id=test_case_id,
        skill_id=skill_id,
        skill_code=skill_code
    )
    return result

# --- Safety Checks ---

@app.post("/api/v1/testing/safety/check")
async def check_safety(request: SafetyCheckRequest):
    """Perform safety analysis on skill code."""
    risk_level, issues = db_test.check_code_safety(
        skill_id=request.skill_id,
        code=request.code
    )
    return {
        "risk_level": risk_level,
        "issues_found": len(issues),
        "issues": issues
    }

@app.get("/api/v1/testing/safety/patterns")
async def list_unsafe_patterns():
    """List all unsafe code patterns."""
    import sqlite3
    conn = sqlite3.connect(db_test.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM unsafe_patterns WHERE is_active = 1")
    patterns = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return patterns

# --- Quality Scoring ---

@app.post("/api/v1/testing/quality/calculate")
async def calculate_quality(request: QualityScoreRequest):
    """Calculate comprehensive quality score."""
    scores = db_test.calculate_quality_score(skill_id=request.skill_id)
    return scores

@app.get("/api/v1/testing/quality/report/{skill_id}")
async def get_quality_report(skill_id: int):
    """Get comprehensive quality report for a skill."""
    report = db_test.get_skill_quality_report(skill_id=skill_id)
    return report

@app.get("/api/v1/testing/quality/leaderboard")
async def get_quality_leaderboard(limit: int = 10):
    """Get top quality skills (leaderboard)."""
    import sqlite3
    conn = sqlite3.connect(db_test.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT qs.*, s.tool_name, s.description
        FROM quality_scores qs
        JOIN skills s ON qs.skill_id = s.id
        ORDER BY qs.overall_score DESC
        LIMIT ?
    """, (limit,))

    leaderboard = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return leaderboard

# --- Code Analysis ---

@app.post("/api/v1/testing/analyze/complexity")
async def analyze_complexity(code: str):
    """Analyze code complexity metrics."""
    metrics = db_test.analyze_code_complexity(code)
    return metrics

@app.post("/api/v1/testing/analyze/imports")
async def validate_imports(code: str):
    """Validate code imports for safety."""
    is_safe, issues = db_test.validate_imports(code)
    return {
        "is_safe": is_safe,
        "issues": issues
    }


# ============================================================================
# INTEGRATION HUB (Feature #16)
# ============================================================================

# --- Integration Models ---

class IntegrationCreate(BaseModel):
    """Request model for creating an integration."""
    integration_type: str = Field(..., description="Type: github, slack, webhook, api_client, export_import")
    name: str
    description: str = ""
    config: Dict
    credentials: Optional[Dict] = None

class GitHubRepoAdd(BaseModel):
    """Request model for adding a GitHub repository."""
    integration_id: int
    repo_full_name: str = Field(..., description="e.g., 'owner/repo'")
    repo_url: str
    auto_import: bool = True
    skill_path_pattern: str = "*.py"

class WebhookCreate(BaseModel):
    """Request model for creating a webhook."""
    integration_id: Optional[int] = None
    events: List[str] = Field(..., description="Events to trigger on")
    description: str = ""

class SlackChannelAdd(BaseModel):
    """Request model for adding a Slack channel."""
    integration_id: int
    channel_id: str
    channel_name: str
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    event_subscriptions: List[str]

class ExportJobCreate(BaseModel):
    """Request model for creating an export job."""
    job_type: str = Field(..., description="export or import")
    export_format: str = Field(..., description="json, yaml, zip, tar.gz")
    scope: str = Field(..., description="skills, workflows, integrations, all")
    metadata: Optional[Dict] = None

# --- Integration Management ---

@app.get("/api/v1/integrations/types")
async def list_integration_types():
    """List all available integration types."""
    import sqlite3
    conn = sqlite3.connect(db_int.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM integration_types WHERE is_active = 1")
    types = [dict(row) for row in cursor.fetchall()]

    for t in types:
        t['config_schema'] = json.loads(t['config_schema']) if t['config_schema'] else {}

    conn.close()
    return types

@app.post("/api/v1/integrations")
async def create_integration(integration: IntegrationCreate):
    """Create a new integration."""
    integration_id = db_int.create_integration(
        integration_type=integration.integration_type,
        name=integration.name,
        config=integration.config,
        credentials=integration.credentials,
        description=integration.description
    )
    return {"integration_id": integration_id, "status": "created"}

@app.get("/api/v1/integrations/{integration_id}")
async def get_integration(integration_id: int):
    """Get integration by ID."""
    integration = db_int.get_integration(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration

@app.get("/api/v1/integrations")
async def list_integrations(integration_type: Optional[str] = None, enabled_only: bool = False):
    """List all integrations."""
    integrations = db_int.list_integrations(
        integration_type=integration_type,
        enabled_only=enabled_only
    )
    return integrations

@app.put("/api/v1/integrations/{integration_id}/toggle")
async def toggle_integration(integration_id: int, enabled: bool):
    """Enable or disable an integration."""
    success = db_int.toggle_integration(integration_id, enabled)
    if not success:
        raise HTTPException(status_code=404, detail="Integration not found")
    return {"status": "enabled" if enabled else "disabled"}

@app.get("/api/v1/integrations/{integration_id}/logs")
async def get_integration_logs(integration_id: int, log_level: Optional[str] = None, limit: int = 100):
    """Get logs for an integration."""
    logs = db_int.get_integration_logs(integration_id, log_level, limit)
    return logs

# --- GitHub Integration ---

@app.post("/api/v1/integrations/github/repos")
async def add_github_repo(repo: GitHubRepoAdd):
    """Add a GitHub repository to an integration."""
    repo_id = db_int.add_github_repo(
        integration_id=repo.integration_id,
        repo_full_name=repo.repo_full_name,
        repo_url=repo.repo_url,
        auto_import=repo.auto_import,
        skill_path_pattern=repo.skill_path_pattern
    )
    return {"repo_id": repo_id, "status": "added"}

@app.get("/api/v1/integrations/github/{integration_id}/repos")
async def list_github_repos(integration_id: int, active_only: bool = False):
    """List GitHub repositories for an integration."""
    repos = db_int.list_github_repos(integration_id, active_only)
    return repos

@app.post("/api/v1/integrations/github/repos/{repo_id}/sync")
async def sync_github_repo(repo_id: int):
    """Sync a GitHub repository and import skills."""
    success, message = db_int.sync_github_repo(repo_id)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"status": "success", "message": message}

# --- Webhook System ---

@app.post("/api/v1/integrations/webhooks")
async def create_webhook(webhook: WebhookCreate):
    """Create a new webhook endpoint."""
    webhook_id, endpoint_url, secret_key = db_int.create_webhook(
        integration_id=webhook.integration_id,
        events=webhook.events,
        description=webhook.description
    )
    return {
        "webhook_id": webhook_id,
        "endpoint_url": endpoint_url,
        "secret_key": secret_key,
        "status": "created"
    }

@app.get("/api/v1/integrations/webhooks")
async def list_webhooks(integration_id: Optional[int] = None, active_only: bool = False):
    """List all webhooks."""
    webhooks = db_int.list_webhooks(integration_id, active_only)
    return webhooks

@app.post("/api/v1/integrations/webhooks/{webhook_id}/trigger")
async def trigger_webhook_manually(webhook_id: int, event_type: str, payload: Dict):
    """Manually trigger a webhook for testing."""
    delivery_id = db_int.trigger_webhook(webhook_id, event_type, payload)
    return {"delivery_id": delivery_id, "status": "triggered"}

# --- Slack Notifications ---

@app.post("/api/v1/integrations/slack/channels")
async def add_slack_channel(channel: SlackChannelAdd):
    """Add a Slack channel for notifications."""
    channel_id = db_int.add_slack_channel(
        integration_id=channel.integration_id,
        channel_id=channel.channel_id,
        channel_name=channel.channel_name,
        event_subscriptions=channel.event_subscriptions,
        workspace_id=channel.workspace_id,
        workspace_name=channel.workspace_name
    )
    return {"slack_channel_id": channel_id, "status": "added"}

@app.get("/api/v1/integrations/slack/{integration_id}/channels")
async def list_slack_channels(integration_id: int, active_only: bool = False):
    """List Slack channels for an integration."""
    channels = db_int.list_slack_channels(integration_id, active_only)
    return channels

@app.post("/api/v1/integrations/slack/channels/{channel_id}/notify")
async def send_slack_notification_api(channel_id: int, event_type: str, message: str, details: Optional[Dict] = None):
    """Send a test notification to a Slack channel."""
    success = db_int.send_slack_notification(channel_id, event_type, message, details)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send notification")
    return {"status": "sent"}

# --- Export/Import ---

@app.post("/api/v1/integrations/export")
async def create_export(job: ExportJobCreate):
    """Create an export job."""
    job_id = db_int.create_export_job(
        job_type=job.job_type,
        export_format=job.export_format,
        scope=job.scope,
        metadata=job.metadata
    )

    # Process export immediately for now
    if job.scope == "skills":
        export_data = db_int.export_skills_to_json()

        # Save to file
        import json
        output_path = f"/tmp/export_{job_id}.json"
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        file_size = os.path.getsize(output_path)
        db_int.update_export_job(
            job_id=job_id,
            status="completed",
            file_path=output_path,
            file_size=file_size,
            items_processed=export_data['count']
        )

    return {"job_id": job_id, "status": "created"}

@app.get("/api/v1/integrations/export/{job_id}")
async def get_export_job(job_id: int):
    """Get export job status and details."""
    job = db_int.get_export_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    return job

@app.get("/api/v1/integrations/export")
async def list_export_jobs(job_type: Optional[str] = None, limit: int = 50):
    """List export/import jobs."""
    jobs = db_int.list_export_jobs(job_type, limit)
    return jobs

@app.post("/api/v1/integrations/import/skills")
async def import_skills(import_data: Dict):
    """Import skills from JSON data."""
    imported_count, errors = db_int.import_skills_from_json(import_data)
    return {
        "imported_count": imported_count,
        "errors": errors,
        "status": "completed" if not errors else "completed_with_errors"
    }


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
