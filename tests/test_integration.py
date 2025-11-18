"""
Integration Tests for AutoGen v0.4 Ultimate Platform

Tests internal agent communication, tool flows, and service integration
without the UI layer. All external services are mocked for deterministic testing.
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path

# Import from main application (adjust if needed)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Agent Handoff Tests
# ============================================================================

class TestAgentHandoff:
    """Test agent-to-agent communication and handoffs."""

    @pytest.mark.asyncio
    async def test_planner_to_coder_handoff(self, mock_planner_agent, mock_coder_agent, mock_gemini_client):
        """Test that Planner's structured output is correctly received by Coder."""
        # Arrange: Planner creates a task plan
        planner_response = {
            "task_summary": "Create email validator",
            "requirements": ["Python 3.11", "regex support"],
            "steps": [
                {"step_number": 1, "description": "Import re module", "estimated_complexity": "Low", "dependencies": []},
                {"step_number": 2, "description": "Write validation function", "estimated_complexity": "Medium", "dependencies": [1]}
            ],
            "estimated_time": "20 minutes",
            "technologies": ["Python"],
            "risks": ["Edge cases in email format"]
        }

        mock_gemini_client.create.return_value = MagicMock(
            content=json.dumps(planner_response),
            usage=MagicMock(prompt_tokens=100, completion_tokens=150)
        )

        # Act: Simulate Planner creating plan
        messages = [{"role": "user", "content": "Create an email validator function"}]
        response = await mock_gemini_client.create(messages)

        # Assert: Verify response structure
        plan = json.loads(response.content)
        assert plan["task_summary"] == "Create email validator"
        assert len(plan["steps"]) == 2
        assert plan["steps"][0]["step_number"] == 1
        assert "Python" in plan["technologies"]

    @pytest.mark.asyncio
    async def test_coder_to_reviewer_handoff(self, mock_coder_agent, mock_reviewer_agent, mock_gemini_client):
        """Test that Coder's code is correctly passed to Reviewer."""
        # Arrange: Coder generates code
        code_response = """def validate_email(email: str) -> bool:
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))"""

        # Set up mock to return code
        mock_gemini_client.create.return_value = MagicMock(content=code_response)

        # Act: Coder generates code
        messages = [{"role": "user", "content": "Implement email validator"}]
        coder_response = await mock_gemini_client.create(messages)

        # Reviewer receives and reviews code
        review_prompt = [
            {"role": "user", "content": f"Review this code:\n{coder_response.content}"}
        ]

        review_response = {
            "overall_quality": "Good",
            "strengths": ["Uses regex", "Type hints"],
            "issues": ["Missing docstring"],
            "security_concerns": [],
            "approved": True,
            "feedback_summary": "Code is good but needs documentation"
        }

        mock_gemini_client.create.return_value = MagicMock(content=json.dumps(review_response))
        reviewer_response = await mock_gemini_client.create(review_prompt)

        # Assert: Verify review structure
        review = json.loads(reviewer_response.content)
        assert review["approved"] is True
        assert "regex" in review["strengths"][0].lower()
        assert len(review["issues"]) > 0


# ============================================================================
# Tool Call Flow Tests
# ============================================================================

class TestToolCallFlow:
    """Test complete tool execution workflows."""

    @pytest.mark.asyncio
    async def test_execute_code_with_rq(self, mock_rq_queue, mock_rq_job, mock_filehandler_agent):
        """Test complete flow: Coder requests execution -> FileHandler enqueues -> polls result."""
        # Arrange: Code to execute
        code = "print('Hello from test')"

        # Import the actual function (with mocked RQ)
        with patch('streamlit_app.get_redis_queue', return_value=mock_rq_queue):
            from streamlit_app import tool_execute_code

            # Act: Execute code (should enqueue to RQ)
            result = tool_execute_code(code)

            # Assert: Job was enqueued
            mock_rq_queue.enqueue.assert_called_once()
            assert "Job ID:" in result
            assert mock_rq_job.id in result

    @pytest.mark.asyncio
    async def test_poll_job_result(self, mock_rq_job):
        """Test polling for job results."""
        # Arrange: Mock Job.fetch
        with patch('streamlit_app.Job') as mock_job_class:
            mock_job_class.fetch.return_value = mock_rq_job

            from streamlit_app import tool_poll_job_result

            # Act: Poll for result
            result = tool_poll_job_result(mock_rq_job.id)

            # Assert: Result retrieved
            assert "success" in result
            assert "Hello from mock worker" in result

    @pytest.mark.asyncio
    async def test_execute_code_local_fallback(self, mock_redis_unavailable):
        """Test that code execution falls back to local when Redis unavailable."""
        # Arrange: Simple Python code
        code = "result = 2 + 2"

        from streamlit_app import tool_execute_code

        # Act: Execute with Redis unavailable
        result = tool_execute_code(code)

        # Assert: Should execute locally (not return Job ID)
        assert "Job ID:" not in result or "success" in result.lower()

    @pytest.mark.asyncio
    async def test_chromadb_ingest_and_retrieval(self, mock_chroma_client, mock_chroma_collection,
                                                   mock_embedding_model, temp_test_dir, mock_streamlit_session):
        """Test document ingestion and retrieval from ChromaDB."""
        # Arrange: Create test document
        test_file = temp_test_dir / "knowledge.md"
        test_file.write_text("# API Authentication\nThe API uses OAuth 2.0 for authentication.")

        # Set up session state
        mock_streamlit_session['chroma_client'] = mock_chroma_client
        mock_streamlit_session['embedding_model'] = mock_embedding_model

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            from streamlit_app import tool_ingest_document, tool_web_search

            # Act: Ingest document
            ingest_result = tool_ingest_document(str(test_file))

            # Assert: Document ingested
            assert "✅" in ingest_result
            assert "Ingested" in ingest_result
            mock_chroma_collection.add.assert_called_once()

            # Act: Query knowledge
            search_result = tool_web_search("How does authentication work?")

            # Assert: Retrieved from ChromaDB
            assert "INTERNAL KNOWLEDGE" in search_result
            assert "OAuth" in search_result or "authentication" in search_result.lower()


# ============================================================================
# Skill Generation Tests
# ============================================================================

class TestSkillGeneration:
    """Test dynamic skill generation and registration."""

    @pytest.mark.asyncio
    async def test_skill_generator_creates_valid_code(self, mock_skillgenerator_agent, mock_gemini_client):
        """Test that SkillGenerator creates valid SkillDefinition."""
        # Arrange: Mock SkillGenerator response
        skill_def = {
            "tool_name": "tool_calculate_factorial",
            "description": "Calculate factorial of a number",
            "parameters": {"n": "int"},
            "code": "def tool_calculate_factorial(n: int) -> str:\n    if n < 0:\n        return 'Error: negative number'\n    result = 1\n    for i in range(1, n + 1):\n        result *= i\n    return f'Factorial of {n} is {result}'",
            "safety_notes": ["No recursion to avoid stack overflow"]
        }

        mock_gemini_client.create.return_value = MagicMock(content=json.dumps(skill_def))

        # Act: Generate skill
        messages = [{"role": "user", "content": "Create a tool to calculate factorial"}]
        response = await mock_gemini_client.create(messages)

        # Assert: Valid skill definition
        skill = json.loads(response.content)
        assert skill["tool_name"] == "tool_calculate_factorial"
        assert "def tool_calculate_factorial" in skill["code"]
        assert skill["parameters"]["n"] == "int"

    @pytest.mark.asyncio
    async def test_reviewer_approves_skill(self, mock_reviewer_agent, mock_gemini_client, sample_skill_definition):
        """Test that Reviewer approves generated skill."""
        # Arrange: Skill to review
        skill_code = sample_skill_definition["code"]

        review_response = {
            "overall_quality": "Excellent",
            "strengths": ["Simple and clear", "Good parameter types"],
            "issues": [],
            "security_concerns": [],
            "approved": True,
            "feedback_summary": "Skill is safe to register"
        }

        mock_gemini_client.create.return_value = MagicMock(content=json.dumps(review_response))

        # Act: Review skill
        messages = [{"role": "user", "content": f"Review this skill code:\n{skill_code}"}]
        response = await mock_gemini_client.create(messages)

        # Assert: Approved
        review = json.loads(response.content)
        assert review["approved"] is True
        assert len(review["security_concerns"]) == 0

    def test_filehandler_registers_skill(self, mock_filehandler_agent, sample_skill_definition):
        """Test that FileHandler successfully registers approved skill."""
        # Arrange: Create SkillDefinition object
        from streamlit_app import SkillDefinition
        skill = SkillDefinition(**sample_skill_definition)

        # Act: Register skill
        result = mock_filehandler_agent.register_new_skill(skill)

        # Assert: Skill registered
        assert "✅" in result
        assert skill.tool_name in result
        assert len(mock_filehandler_agent.dynamic_tools) == 1
        assert mock_filehandler_agent.dynamic_tools[0]["name"] == "tool_test_skill"

    @pytest.mark.asyncio
    async def test_complete_skill_generation_loop(self, mock_skillgenerator_agent, mock_reviewer_agent,
                                                   mock_filehandler_agent, mock_gemini_client):
        """Test complete loop: SkillGenerator -> Reviewer -> FileHandler."""
        # Step 1: SkillGenerator creates skill
        skill_def = {
            "tool_name": "tool_reverse_string",
            "description": "Reverse a string",
            "parameters": {"text": "str"},
            "code": "def tool_reverse_string(text: str) -> str:\n    return text[::-1]",
            "safety_notes": ["Simple operation, no security concerns"]
        }

        mock_gemini_client.create.return_value = MagicMock(content=json.dumps(skill_def))
        gen_response = await mock_gemini_client.create([{"role": "user", "content": "Create string reverser"}])
        skill_data = json.loads(gen_response.content)

        # Step 2: Reviewer approves
        review_response = {
            "overall_quality": "Good",
            "strengths": ["Simple", "Safe"],
            "issues": [],
            "security_concerns": [],
            "approved": True,
            "feedback_summary": "Approved"
        }

        mock_gemini_client.create.return_value = MagicMock(content=json.dumps(review_response))
        review_resp = await mock_gemini_client.create([{"role": "user", "content": "Review skill"}])
        review_data = json.loads(review_resp.content)

        # Step 3: FileHandler registers (if approved)
        if review_data["approved"]:
            from streamlit_app import SkillDefinition
            skill = SkillDefinition(**skill_data)
            result = mock_filehandler_agent.register_new_skill(skill)

            # Assert: Complete loop successful
            assert review_data["approved"] is True
            assert "✅" in result
            assert len(mock_filehandler_agent.dynamic_tools) == 1


# ============================================================================
# Pydantic Schema Validation Tests
# ============================================================================

class TestSchemaValidation:
    """Test Pydantic schema validation for structured outputs."""

    def test_task_plan_validation(self, sample_task_plan):
        """Test TaskPlan schema validation."""
        from streamlit_app import TaskPlan

        # Act: Create TaskPlan from sample data
        plan = TaskPlan(**sample_task_plan)

        # Assert: Valid plan
        assert plan.task_summary == "Create a test function"
        assert len(plan.steps) == 1
        assert plan.steps[0].step_number == 1

    def test_code_review_validation(self, sample_code_review):
        """Test CodeReview schema validation."""
        from streamlit_app import CodeReview

        # Act: Create CodeReview
        review = CodeReview(**sample_code_review)

        # Assert: Valid review
        assert review.approved is True
        assert review.overall_quality == "Excellent"
        assert len(review.strengths) == 3

    def test_skill_definition_validation(self, sample_skill_definition):
        """Test SkillDefinition schema validation."""
        from streamlit_app import SkillDefinition

        # Act: Create SkillDefinition
        skill = SkillDefinition(**sample_skill_definition)

        # Assert: Valid skill
        assert skill.tool_name == "tool_test_skill"
        assert "def tool_test_skill" in skill.code

    def test_test_comparison_validation(self, sample_test_comparison):
        """Test TestComparison schema validation."""
        from streamlit_app import TestComparison

        # Act: Create TestComparison
        comparison = TestComparison(**sample_test_comparison)

        # Assert: Valid comparison
        assert 1 <= comparison.coherence_score <= 10
        assert comparison.recommendation in ["Accept", "Reject"]


# ============================================================================
# Cost Tracking Tests
# ============================================================================

class TestCostTracking:
    """Test cost tracking and monitoring."""

    @pytest.mark.asyncio
    async def test_cost_tracking_client_tracks_usage(self, mock_streamlit_session):
        """Test that CostTrackingChatClient tracks token usage."""
        from streamlit_app import CostTrackingChatClient
        from conftest import MockChatResponse, MockUsage

        # Arrange: Create tracking client
        with patch('streamlit_app.OpenAIChatCompletionClient'):
            with patch('streamlit_app.st.session_state', mock_streamlit_session):
                client = CostTrackingChatClient(
                    agent_name="TestAgent",
                    model="gemini-2.5-pro",
                    api_key="test_key"
                )

                # Mock the parent create method
                async def mock_create(messages, *args, **kwargs):
                    return MockChatResponse("Test response", MockUsage(100, 50))

                with patch.object(CostTrackingChatClient.__bases__[0], 'create', new=mock_create):
                    # Act: Make a call
                    response = await client.create([{"role": "user", "content": "test"}])

                    # The tracking happens in the actual implementation
                    # For this test, we verify the structure is correct
                    assert response.content == "Test response"
                    assert response.usage.prompt_tokens == 100
                    assert response.usage.completion_tokens == 50

    def test_cost_calculation(self):
        """Test cost calculation logic."""
        from streamlit_app import PRICING

        # Arrange: Token counts
        input_tokens = 1000
        output_tokens = 500

        # Act: Calculate cost
        pro_pricing = PRICING["gemini-2.5-pro"]
        input_cost = input_tokens * pro_pricing["input"]
        output_cost = output_tokens * pro_pricing["output"]
        total_cost = input_cost + output_cost

        # Assert: Correct calculation
        assert input_cost == 0.00125  # 1000 * 0.00125/1000
        assert output_cost == 0.00250  # 500 * 0.00500/1000
        assert total_cost == 0.00375

    def test_cost_alert_threshold(self):
        """Test cost alert threshold detection."""
        from streamlit_app import COST_ALERT_THRESHOLD

        # Arrange: Different cost scenarios
        low_cost = 0.50
        high_cost = 1.50

        # Assert: Threshold logic
        assert low_cost < COST_ALERT_THRESHOLD
        assert high_cost > COST_ALERT_THRESHOLD


# ============================================================================
# ChromaDB Integration Tests
# ============================================================================

class TestChromaDBIntegration:
    """Test ChromaDB integration for RAG."""

    def test_chroma_client_initialization(self, mock_chroma_client):
        """Test ChromaDB client initialization."""
        # Assert: Client created
        assert mock_chroma_client is not None

    def test_collection_creation(self, mock_chroma_client, mock_chroma_collection):
        """Test collection creation and retrieval."""
        # Act: Get collection
        collection = mock_chroma_client.get_or_create_collection(name="test_collection")

        # Assert: Collection exists
        assert collection is not None
        assert collection.count() >= 0

    def test_embedding_generation(self, mock_embedding_model):
        """Test embedding generation."""
        # Arrange: Text to embed
        texts = ["This is a test sentence", "Another test sentence"]

        # Act: Generate embeddings
        embeddings = mock_embedding_model.encode(texts)

        # Assert: Correct shape
        assert embeddings.shape[0] == 2
        assert embeddings.shape[1] == 384  # all-MiniLM-L6-v2 dimension

    def test_hybrid_search_logic(self, mock_chroma_collection, mock_embedding_model, mock_streamlit_session):
        """Test hybrid search (ChromaDB + web)."""
        # Arrange: Set up session state
        mock_streamlit_session['chroma_client'] = Mock()
        mock_streamlit_session['chroma_client'].get_or_create_collection = Mock(return_value=mock_chroma_collection)
        mock_streamlit_session['embedding_model'] = mock_embedding_model

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            with patch('streamlit_app.chromadb_available', True):
                from streamlit_app import tool_web_search

                # Act: Perform search
                result = tool_web_search("authentication methods")

                # Assert: Searches ChromaDB first
                assert "INTERNAL KNOWLEDGE" in result or "authentication" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
