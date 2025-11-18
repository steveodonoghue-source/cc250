"""
Pytest Configuration and Fixtures for AutoGen v0.4 Ultimate Platform Testing

This module provides comprehensive mocking for external services:
- Gemini API (OpenAIChatCompletionClient)
- ChromaDB (vector database)
- Redis Queue (RQ for distributed execution)
- Streamlit session state
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from pathlib import Path

import pytest
from pydantic import BaseModel


# ============================================================================
# Mock Response Classes
# ============================================================================

class MockUsage:
    """Mock token usage from LLM responses."""
    def __init__(self, prompt_tokens: int = 100, completion_tokens: int = 50):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class MockChatResponse:
    """Mock LLM chat response."""
    def __init__(self, content: str, usage: Optional[MockUsage] = None):
        self.content = content
        self.usage = usage or MockUsage()
        self.finish_reason = "stop"
        self.choices = [type('obj', (object,), {'message': type('obj', (object,), {'content': content})()})]


class MockToolCall:
    """Mock tool call in LLM response."""
    def __init__(self, name: str, arguments: Dict[str, Any]):
        self.name = name
        self.arguments = json.dumps(arguments)
        self.id = f"call_{name}_{id(self)}"


# ============================================================================
# Gemini API Mocking
# ============================================================================

@pytest.fixture
def mock_gemini_client():
    """
    Mock OpenAIChatCompletionClient (used for Gemini).

    Returns deterministic responses for testing without API costs.
    """
    mock_client = AsyncMock()

    # Default response for simple queries
    async def create_response(messages, *args, **kwargs):
        # Extract last message content
        last_message = messages[-1] if messages else ""
        content = last_message.get("content", "") if isinstance(last_message, dict) else str(last_message)

        # Deterministic responses based on message content
        if "plan" in content.lower():
            response_content = json.dumps({
                "task_summary": "Test Task",
                "requirements": ["Requirement 1", "Requirement 2"],
                "steps": [
                    {"step_number": 1, "description": "Step 1", "estimated_complexity": "Low", "dependencies": []},
                    {"step_number": 2, "description": "Step 2", "estimated_complexity": "Medium", "dependencies": [1]}
                ],
                "estimated_time": "30 minutes",
                "technologies": ["Python"],
                "risks": ["None identified"]
            })
        elif "review" in content.lower():
            response_content = json.dumps({
                "overall_quality": "Good",
                "strengths": ["Clean code", "Well documented"],
                "issues": [],
                "security_concerns": [],
                "approved": True,
                "feedback_summary": "Code looks good"
            })
        elif "code" in content.lower():
            response_content = "def test_function():\n    return 'Hello, World!'"
        else:
            response_content = "Test response from mocked Gemini"

        return MockChatResponse(response_content, MockUsage())

    mock_client.create = AsyncMock(side_effect=create_response)
    return mock_client


@pytest.fixture
def mock_cost_tracking_client(mock_gemini_client):
    """Mock CostTrackingChatClient wrapper."""
    with patch('streamlit_app.CostTrackingChatClient') as mock_class:
        mock_instance = Mock()
        mock_instance.create = mock_gemini_client.create
        mock_instance.agent_name = "TestAgent"
        mock_instance.model = "gemini-2.5-pro"
        mock_class.return_value = mock_instance
        yield mock_class


# ============================================================================
# ChromaDB Mocking
# ============================================================================

@pytest.fixture
def mock_chroma_collection():
    """Mock ChromaDB collection for vector storage."""
    collection = Mock()
    collection.count = Mock(return_value=10)

    # Mock query results
    def query_mock(query_embeddings=None, n_results=5, **kwargs):
        return {
            'documents': [
                [
                    "This is a test document about authentication.",
                    "API uses OAuth 2.0 for secure authentication.",
                    "Tokens expire after 1 hour."
                ][:n_results]
            ],
            'distances': [[0.1, 0.2, 0.3][:n_results]],
            'metadatas': [[
                {"source": "test.md", "chunk_index": 0},
                {"source": "test.md", "chunk_index": 1},
                {"source": "test.md", "chunk_index": 2}
            ][:n_results]]
        }

    collection.query = Mock(side_effect=query_mock)

    # Mock add
    collection.add = Mock(return_value=None)

    return collection


@pytest.fixture
def mock_chroma_client(mock_chroma_collection):
    """Mock ChromaDB persistent client."""
    client = Mock()
    client.get_or_create_collection = Mock(return_value=mock_chroma_collection)

    with patch('streamlit_app.chromadb.PersistentClient', return_value=client):
        with patch('streamlit_app.get_chroma_client', return_value=client):
            yield client


@pytest.fixture
def mock_embedding_model():
    """Mock SentenceTransformer for embeddings."""
    model = Mock()

    # Return deterministic embeddings
    def encode_mock(texts):
        import numpy as np
        if isinstance(texts, str):
            texts = [texts]
        # Return dummy embeddings (384 dimensions for all-MiniLM-L6-v2)
        return np.random.rand(len(texts), 384)

    model.encode = Mock(side_effect=encode_mock)

    with patch('streamlit_app.SentenceTransformer', return_value=model):
        with patch('streamlit_app.get_embedding_model', return_value=model):
            yield model


# ============================================================================
# Redis Queue (RQ) Mocking
# ============================================================================

@pytest.fixture
def mock_rq_job():
    """Mock RQ job."""
    job = Mock()
    job.id = "test_job_123"
    job.is_finished = True
    job.is_failed = False
    job.result = {"status": "success", "output": "Hello from mock worker"}
    job.refresh = Mock()

    return job


@pytest.fixture
def mock_rq_queue(mock_rq_job):
    """Mock Redis Queue."""
    queue = Mock()
    queue.enqueue = Mock(return_value=mock_rq_job)

    with patch('streamlit_app.get_redis_queue', return_value=queue):
        yield queue


@pytest.fixture
def mock_redis_unavailable():
    """Mock Redis being unavailable (for graceful degradation testing)."""
    with patch('streamlit_app.get_redis_queue', return_value=None):
        yield


# ============================================================================
# Streamlit Session State Mocking
# ============================================================================

class MockSessionState(dict):
    """Mock Streamlit session state that supports both dict and attribute access."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")


@pytest.fixture
def mock_streamlit_session():
    """Mock Streamlit session state."""
    session_state = MockSessionState({
        'messages': [],
        'team': None,
        'google_api_key': 'test_api_key',
        'chat_active': True,
        'pending_approval': None,
        'approval_granted': False,
        'tool_calls': [],
        'cost_tracking': {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_cost': 0.0,
            'by_agent': {},
            'history': []
        },
        'filehandler_agent': None,
        'baselines': {},
        'regression_mode': False,
        'current_baseline': None,
        'uploaded_files': [],
        'chroma_client': None,
        'embedding_model': None,
        'testing_agent': None
    })

    with patch('streamlit.session_state', session_state):
        yield session_state


# ============================================================================
# Agent Mocking
# ============================================================================

@pytest.fixture
def mock_planner_agent(mock_gemini_client):
    """Mock Planner agent."""
    agent = Mock()
    agent.name = "Planner"
    agent.model_client = mock_gemini_client
    agent.tools = []
    agent.handoffs = ["Coder", "Reviewer"]
    return agent


@pytest.fixture
def mock_coder_agent(mock_gemini_client):
    """Mock Coder agent."""
    agent = Mock()
    agent.name = "Coder"
    agent.model_client = mock_gemini_client
    agent.tools = []
    agent.handoffs = ["Reviewer", "FileHandler"]
    return agent


@pytest.fixture
def mock_reviewer_agent(mock_gemini_client):
    """Mock Reviewer agent."""
    agent = Mock()
    agent.name = "Reviewer"
    agent.model_client = mock_gemini_client
    agent.tools = []
    agent.handoffs = ["Coder", "User"]
    return agent


@pytest.fixture
def mock_filehandler_agent(mock_gemini_client):
    """Mock FileHandler agent with dynamic skill registration."""
    agent = Mock()
    agent.name = "FileHandler"
    agent.model_client = mock_gemini_client
    agent.tools = []
    agent.dynamic_tools = []
    agent.handoffs = ["User"]

    # Mock skill registration
    def register_skill_mock(skill_def):
        agent.dynamic_tools.append({
            "name": skill_def.tool_name,
            "description": skill_def.description
        })
        return f"✅ Registered new skill: {skill_def.tool_name}"

    agent.register_new_skill = Mock(side_effect=register_skill_mock)

    return agent


@pytest.fixture
def mock_skillgenerator_agent(mock_gemini_client):
    """Mock SkillGenerator agent."""
    agent = Mock()
    agent.name = "SkillGenerator"
    agent.model_client = mock_gemini_client
    agent.tools = []
    agent.handoffs = ["Reviewer"]
    return agent


@pytest.fixture
def mock_testing_agent(mock_gemini_client):
    """Mock Testing agent."""
    agent = Mock()
    agent.name = "Testing"
    agent.model_client = mock_gemini_client
    agent.tools = []
    agent.handoffs = ["User"]
    return agent


# ============================================================================
# Team Mocking
# ============================================================================

@pytest.fixture
def mock_team(mock_planner_agent, mock_coder_agent, mock_reviewer_agent,
              mock_filehandler_agent, mock_skillgenerator_agent, mock_testing_agent):
    """Mock SelectorGroupChat team."""
    team = Mock()
    team.participants = [
        mock_planner_agent,
        mock_coder_agent,
        mock_reviewer_agent,
        mock_filehandler_agent,
        mock_skillgenerator_agent,
        mock_testing_agent
    ]

    # Mock run method
    async def run_mock(task):
        result = Mock()
        result.messages = [
            {"role": "user", "content": task.content if hasattr(task, 'content') else str(task)},
            {"role": "assistant", "content": "Test response", "agent": "Planner"}
        ]
        return result

    team.run = AsyncMock(side_effect=run_mock)

    return team


# ============================================================================
# File System Mocking
# ============================================================================

@pytest.fixture
def temp_test_dir(tmp_path):
    """Create temporary directory for test files."""
    test_dir = tmp_path / "test_workspace"
    test_dir.mkdir()

    # Create some test files
    (test_dir / "test.txt").write_text("This is a test file.")
    (test_dir / "test.md").write_text("# Test Markdown\nThis is markdown content.")
    (test_dir / "test.py").write_text("def hello():\n    return 'world'")

    return test_dir


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a sample PDF file for testing."""
    pdf_path = tmp_path / "sample.pdf"
    # Create a minimal PDF (would need PyPDF2 to create properly, for now just create empty)
    pdf_path.write_bytes(b'%PDF-1.4\n%%EOF')
    return pdf_path


# ============================================================================
# Pydantic Schema Fixtures
# ============================================================================

@pytest.fixture
def sample_task_plan():
    """Sample TaskPlan for testing."""
    return {
        "task_summary": "Create a test function",
        "requirements": ["Python 3.11+", "pytest"],
        "steps": [
            {
                "step_number": 1,
                "description": "Write test function",
                "estimated_complexity": "Low",
                "dependencies": []
            }
        ],
        "estimated_time": "15 minutes",
        "technologies": ["Python", "pytest"],
        "risks": []
    }


@pytest.fixture
def sample_code_review():
    """Sample CodeReview for testing."""
    return {
        "overall_quality": "Excellent",
        "strengths": ["Clean code", "Good documentation", "Proper error handling"],
        "issues": [],
        "security_concerns": [],
        "approved": True,
        "feedback_summary": "Code is production-ready"
    }


@pytest.fixture
def sample_skill_definition():
    """Sample SkillDefinition for testing."""
    return {
        "tool_name": "tool_test_skill",
        "description": "A test skill for unit testing",
        "parameters": {"input": "str"},
        "code": "def tool_test_skill(input: str) -> str:\n    return f'Processed: {input}'",
        "safety_notes": ["No security concerns"]
    }


@pytest.fixture
def sample_test_comparison():
    """Sample TestComparison for testing."""
    return {
        "coherence_score": 8,
        "differences_found": ["Added error handling"],
        "improvements": ["Better edge case coverage"],
        "regressions": [],
        "critique": "Minor improvements over baseline, no regressions detected",
        "recommendation": "Accept"
    }


# ============================================================================
# Environment Setup
# ============================================================================

@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_api_key_12345")
    monkeypatch.setenv("GOOGLE_API_KEY", "test_api_key_12345")


# ============================================================================
# Async Test Support
# ============================================================================

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Playwright Fixtures (for E2E tests)
# ============================================================================

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure Playwright browser context."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "ignore_https_errors": True
    }


@pytest.fixture
def streamlit_url():
    """URL for Streamlit app in E2E tests."""
    return "http://localhost:8501"
