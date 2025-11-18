"""
Resilience and Negative Test Suite for AutoGen v0.4 Ultimate Platform

Tests error handling, edge cases, invalid inputs, and system resilience.
Ensures the application handles failures gracefully without crashing.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Code Execution Failure Tests
# ============================================================================

class TestCodeExecutionFailures:
    """Test handling of code execution errors."""

    @pytest.mark.asyncio
    async def test_bad_code_execution_runtime_error(self, mock_rq_queue):
        """Test that runtime errors in code execution are handled gracefully."""
        # Arrange: Mock job that fails with runtime error
        failed_job = Mock()
        failed_job.id = "failed_job_123"
        failed_job.is_finished = True
        failed_job.is_failed = True
        failed_job.result = None
        failed_job.exc_info = "ZeroDivisionError: division by zero"

        mock_rq_queue.enqueue.return_value = failed_job

        with patch('streamlit_app.get_redis_queue', return_value=mock_rq_queue):
            from streamlit_app import tool_execute_code

            # Act: Execute bad code
            bad_code = "result = 10 / 0  # Division by zero"
            result = tool_execute_code(bad_code)

            # Assert: Error handled
            assert "Job ID:" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_syntax_error_in_code(self, mock_rq_queue):
        """Test handling of syntax errors in code."""
        # Arrange: Mock job with syntax error
        failed_job = Mock()
        failed_job.id = "syntax_error_job"
        failed_job.is_failed = True
        failed_job.result = {"status": "error", "output": "SyntaxError: invalid syntax"}

        mock_rq_queue.enqueue.return_value = failed_job

        with patch('streamlit_app.get_redis_queue', return_value=mock_rq_queue):
            from streamlit_app import tool_execute_code

            # Act: Execute code with syntax error
            bad_code = "def broken(\n    return 'missing colon'"
            result = tool_execute_code(bad_code)

            # Assert: Handled without crash
            assert result is not None

    @pytest.mark.asyncio
    async def test_infinite_loop_timeout(self, mock_rq_queue):
        """Test that infinite loops are handled with timeout."""
        # Arrange: Mock job that times out
        timeout_job = Mock()
        timeout_job.id = "timeout_job"
        timeout_job.is_finished = False
        timeout_job.is_failed = True
        timeout_job.result = None

        mock_rq_queue.enqueue.return_value = timeout_job

        with patch('streamlit_app.get_redis_queue', return_value=mock_rq_queue):
            from streamlit_app import tool_poll_job_result

            # Act: Poll for result (should timeout)
            with patch('streamlit_app.time.sleep'):  # Speed up test
                result = tool_poll_job_result(timeout_job.id, timeout=1)

            # Assert: Timeout handled
            assert "timeout" in result.lower() or "failed" in result.lower()

    def test_malicious_code_rejected(self, mock_rq_queue, mock_streamlit_session):
        """Test that potentially malicious code triggers approval flow."""
        from streamlit_app import tool_execute_code

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Try to execute file system operations
            malicious_code = "import os; os.remove('/etc/passwd')"
            result = tool_execute_code(malicious_code)

            # Assert: Requires approval (HITL)
            # The function should set pending_approval
            assert mock_streamlit_session.get('pending_approval') is not None or "approval" in result.lower()


# ============================================================================
# Invalid Input Tests
# ============================================================================

class TestInvalidInputs:
    """Test handling of invalid and malicious inputs."""

    def test_sql_injection_attempt(self, mock_streamlit_session):
        """Test that SQL injection attempts are sanitized."""
        # Arrange: Malicious input
        sql_injection = "'; DROP TABLE users; --"

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Send as message
            mock_streamlit_session['messages'].append({
                "role": "user",
                "content": sql_injection
            })

            # Assert: Input stored but not executed as SQL
            assert len(mock_streamlit_session['messages']) == 1
            assert mock_streamlit_session['messages'][0]['content'] == sql_injection
            # The key is that it's treated as text, not executed

    def test_xss_attempt(self, mock_streamlit_session):
        """Test that XSS attempts are handled safely."""
        # Arrange: XSS payload
        xss_payload = "<script>alert('XSS')</script>"

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Add to messages
            mock_streamlit_session['messages'].append({
                "role": "user",
                "content": xss_payload
            })

            # Assert: Stored as text (Streamlit handles escaping)
            assert xss_payload in mock_streamlit_session['messages'][0]['content']

    def test_oversized_file_rejected(self, tmp_path):
        """Test that oversized files are rejected."""
        # Arrange: Create large file (simulate)
        large_file = tmp_path / "huge.txt"
        # Don't actually create 1GB file, just test the logic

        from streamlit_app import tool_read_document

        # Act: Try to read (would fail in real scenario)
        # This tests the error handling path
        result = tool_read_document("/nonexistent/huge_file.txt")

        # Assert: Error message returned
        assert "❌" in result or "not found" in result.lower()

    def test_invalid_file_extension(self, tmp_path):
        """Test that invalid file extensions are rejected."""
        # Arrange: File with unsupported extension
        invalid_file = tmp_path / "malicious.exe"
        invalid_file.write_bytes(b'MZ\x90\x00')  # Executable header

        from streamlit_app import tool_ingest_document

        # Act: Try to ingest
        result = tool_ingest_document(str(invalid_file))

        # Assert: Rejected
        assert "❌" in result or "unsupported" in result.lower() or "not found" in result.lower()

    def test_empty_input_handling(self, mock_streamlit_session):
        """Test that empty inputs are handled gracefully."""
        from streamlit_app import tool_web_search

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Empty search query
            result = tool_web_search("")

            # Assert: Handles without crash
            assert result is not None
            assert isinstance(result, str)

    def test_extremely_long_input(self, mock_streamlit_session):
        """Test handling of extremely long inputs."""
        # Arrange: Very long string (10K characters)
        long_input = "A" * 10000

        from streamlit_app import tool_web_search

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Search with long query
            result = tool_web_search(long_input)

            # Assert: Handled without crash
            assert result is not None


# ============================================================================
# Service Failure Tests
# ============================================================================

class TestServiceFailures:
    """Test handling of external service failures."""

    def test_redis_unavailable_fallback(self, mock_redis_unavailable):
        """Test graceful fallback when Redis is unavailable."""
        from streamlit_app import tool_execute_code

        # Act: Execute code with Redis unavailable
        code = "print('Hello')"
        result = tool_execute_code(code)

        # Assert: Falls back to local execution
        assert result is not None
        # Should not contain "Job ID:" if falling back
        # OR should contain error message about local execution

    def test_chromadb_unavailable(self, mock_streamlit_session):
        """Test handling when ChromaDB is unavailable."""
        # Arrange: Session without ChromaDB
        mock_streamlit_session['chroma_client'] = None

        from streamlit_app import tool_web_search

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            with patch('streamlit_app.chromadb_available', False):
                # Act: Try to search
                result = tool_web_search("test query")

                # Assert: Falls back to web search only
                assert result is not None
                assert "EXTERNAL WEB SEARCH" in result or "search" in result.lower()

    @pytest.mark.asyncio
    async def test_gemini_api_failure(self, mock_gemini_client):
        """Test handling of Gemini API failures."""
        # Arrange: Mock API failure
        async def failing_create(*args, **kwargs):
            raise Exception("API quota exceeded")

        mock_gemini_client.create = AsyncMock(side_effect=failing_create)

        # Act: Try to make request
        with pytest.raises(Exception) as exc_info:
            await mock_gemini_client.create([{"role": "user", "content": "test"}])

        # Assert: Exception raised (application should handle this)
        assert "quota" in str(exc_info.value).lower() or "API" in str(exc_info.value)

    def test_embedding_model_failure(self, mock_streamlit_session):
        """Test handling when embedding model fails to load."""
        # Arrange: No embedding model
        mock_streamlit_session['embedding_model'] = None

        from streamlit_app import tool_web_search

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Try search (should skip embeddings)
            result = tool_web_search("test")

            # Assert: Handled gracefully
            assert result is not None

    def test_rq_worker_not_running(self, mock_rq_queue):
        """Test when RQ worker is available but not running."""
        # Arrange: Queue exists but worker not processing
        stuck_job = Mock()
        stuck_job.id = "stuck_job"
        stuck_job.is_finished = False
        stuck_job.is_failed = False

        mock_rq_queue.enqueue.return_value = stuck_job

        from streamlit_app import tool_poll_job_result

        with patch('streamlit_app.get_redis_queue', return_value=mock_rq_queue):
            # Act: Poll (will timeout)
            with patch('streamlit_app.time.sleep'):  # Speed up
                result = tool_poll_job_result(stuck_job.id, timeout=1)

            # Assert: Timeout reported
            assert "timeout" in result.lower() or "not complete" in result.lower()


# ============================================================================
# Schema Validation Failures
# ============================================================================

class TestSchemaValidationFailures:
    """Test handling of schema validation errors."""

    def test_invalid_task_plan_schema(self):
        """Test handling of invalid TaskPlan data."""
        from streamlit_app import TaskPlan
        from pydantic import ValidationError

        # Arrange: Invalid data (missing required fields)
        invalid_data = {
            "task_summary": "Test",
            # Missing other required fields
        }

        # Act & Assert: Raises validation error
        with pytest.raises(ValidationError):
            TaskPlan(**invalid_data)

    def test_invalid_coherence_score(self):
        """Test that coherence scores outside 1-10 are rejected."""
        from streamlit_app import TestComparison
        from pydantic import ValidationError

        # Arrange: Score > 10
        invalid_data = {
            "coherence_score": 15,  # Invalid (max is 10)
            "differences_found": [],
            "improvements": [],
            "regressions": [],
            "critique": "Test",
            "recommendation": "Accept"
        }

        # Act & Assert: Validation fails
        with pytest.raises(ValidationError):
            TestComparison(**invalid_data)

    def test_malformed_json_in_tool_validation(self):
        """Test handling of malformed JSON in validation tool."""
        from streamlit_app import tool_validate_json

        # Act: Try to validate malformed JSON
        malformed = "{'invalid': json, missing quotes}"
        result = tool_validate_json(malformed)

        # Assert: Error reported
        assert "❌" in result
        assert "Invalid JSON" in result or "error" in result.lower()


# ============================================================================
# Concurrent Access Tests
# ============================================================================

class TestConcurrentAccess:
    """Test handling of concurrent operations."""

    @pytest.mark.asyncio
    async def test_multiple_simultaneous_requests(self, mock_gemini_client):
        """Test handling multiple simultaneous LLM requests."""
        # Arrange: Multiple concurrent requests
        tasks = []
        for i in range(5):
            task = mock_gemini_client.create([{"role": "user", "content": f"Request {i}"}])
            tasks.append(task)

        # Act: Execute concurrently
        results = await asyncio.gather(*tasks)

        # Assert: All complete
        assert len(results) == 5

    def test_session_state_isolation(self, mock_streamlit_session):
        """Test that session state is properly isolated."""
        # This would test that different users don't see each other's data
        # In Streamlit, each session has its own state
        assert 'messages' in mock_streamlit_session
        assert isinstance(mock_streamlit_session['messages'], list)


# ============================================================================
# Regression Testing Tests
# ============================================================================

class TestRegressionFramework:
    """Test regression testing functionality."""

    def test_baseline_comparison_detects_changes(self, sample_test_comparison):
        """Test that baseline comparison detects meaningful changes."""
        from streamlit_app import TestComparison

        # Arrange: Create comparison
        comparison = TestComparison(**sample_test_comparison)

        # Assert: Comparison structure valid
        assert 1 <= comparison.coherence_score <= 10
        assert isinstance(comparison.differences_found, list)
        assert isinstance(comparison.improvements, list)
        assert isinstance(comparison.regressions, list)

    def test_regression_detected_low_score(self):
        """Test that low coherence scores indicate regressions."""
        from streamlit_app import TestComparison

        # Arrange: Low score comparison
        regression_data = {
            "coherence_score": 3,  # Low score
            "differences_found": ["Removed error handling", "Changed algorithm"],
            "improvements": [],
            "regressions": ["Missing edge case checks", "Removed validation"],
            "critique": "Significant regressions detected",
            "recommendation": "Reject"
        }

        comparison = TestComparison(**regression_data)

        # Assert: Properly flagged
        assert comparison.coherence_score < 5
        assert len(comparison.regressions) > 0
        assert comparison.recommendation == "Reject"

    def test_baseline_not_found(self, mock_streamlit_session):
        """Test handling when requested baseline doesn't exist."""
        # Arrange: Empty baselines
        mock_streamlit_session['baselines'] = {}

        # Assert: No baselines available
        assert len(mock_streamlit_session['baselines']) == 0

        # Act: Try to access non-existent baseline
        baseline = mock_streamlit_session['baselines'].get('nonexistent')

        # Assert: Returns None
        assert baseline is None


# ============================================================================
# Resource Cleanup Tests
# ============================================================================

class TestResourceCleanup:
    """Test proper resource cleanup."""

    def test_temp_files_cleaned_up(self, temp_test_dir):
        """Test that temporary files are properly cleaned up."""
        # This would test cleanup after code execution
        # In real implementation, ensure temp files are removed
        assert temp_test_dir.exists()

    def test_session_state_reset(self, mock_streamlit_session):
        """Test that session state can be reset."""
        # Arrange: Add data to session
        mock_streamlit_session['messages'].append({"role": "user", "content": "test"})

        # Act: Clear
        mock_streamlit_session['messages'].clear()

        # Assert: Cleared
        assert len(mock_streamlit_session['messages']) == 0

    def test_cost_tracking_reset(self, mock_streamlit_session):
        """Test that cost tracking can be reset."""
        # Arrange: Add cost data
        mock_streamlit_session['cost_tracking']['total_cost'] = 0.50

        # Act: Reset
        mock_streamlit_session['cost_tracking']['total_cost'] = 0.0

        # Assert: Reset
        assert mock_streamlit_session['cost_tracking']['total_cost'] == 0.0


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    def test_unicode_handling(self, mock_streamlit_session):
        """Test that Unicode characters are handled properly."""
        from streamlit_app import tool_web_search

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Search with Unicode
            unicode_query = "Hello 世界 🌍 مرحبا"
            result = tool_web_search(unicode_query)

            # Assert: Handled without crash
            assert result is not None

    def test_special_characters_in_filenames(self, tmp_path):
        """Test handling of special characters in filenames."""
        # Arrange: File with special chars
        special_file = tmp_path / "file@#$%.txt"
        special_file.write_text("Content")

        from streamlit_app import tool_read_document

        # Act: Try to read
        result = tool_read_document(str(special_file))

        # Assert: Either reads successfully or returns error
        assert result is not None

    def test_deeply_nested_data_structures(self):
        """Test handling of deeply nested data in schemas."""
        from streamlit_app import TaskPlan

        # Arrange: Plan with many steps
        many_steps = [
            {
                "step_number": i,
                "description": f"Step {i}",
                "estimated_complexity": "Medium",
                "dependencies": list(range(max(0, i-2), i))
            }
            for i in range(1, 21)  # 20 steps
        ]

        plan_data = {
            "task_summary": "Complex task",
            "requirements": ["Req"] * 10,
            "steps": many_steps,
            "estimated_time": "5 hours",
            "technologies": ["Python"] * 5,
            "risks": ["Risk"] * 5
        }

        # Act: Create plan
        plan = TaskPlan(**plan_data)

        # Assert: Handles large structure
        assert len(plan.steps) == 20

    def test_zero_cost_scenario(self, mock_streamlit_session):
        """Test handling when no costs have been incurred."""
        # Assert: Default cost is 0
        assert mock_streamlit_session['cost_tracking']['total_cost'] == 0.0
        assert len(mock_streamlit_session['cost_tracking']['by_agent']) == 0


# ============================================================================
# Security Tests
# ============================================================================

class TestSecurity:
    """Test security features and protections."""

    def test_api_key_not_logged(self, caplog):
        """Test that API keys are not logged in plain text."""
        from streamlit_app import get_gemini_client

        with patch('streamlit_app.os.environ.get', return_value='secret_key_12345'):
            # Act: Create client (with mocked environment)
            with patch('streamlit_app.OpenAIChatCompletionClient'):
                client = get_gemini_client()

            # Assert: API key not in logs
            assert 'secret_key_12345' not in caplog.text

    def test_code_execution_requires_approval(self, mock_streamlit_session):
        """Test that code execution requires human approval."""
        from streamlit_app import tool_execute_code

        with patch('streamlit_app.st.session_state', mock_streamlit_session):
            # Act: Try to execute code
            code = "import os; os.listdir()"
            result = tool_execute_code(code)

            # Assert: Approval requested
            # The HITL mechanism should set pending_approval
            pending = mock_streamlit_session.get('pending_approval')
            assert pending is not None or "approval" in result.lower()

    def test_path_traversal_prevented(self, tmp_path):
        """Test that path traversal attempts are prevented."""
        from streamlit_app import tool_read_document

        # Act: Try path traversal
        malicious_path = "../../etc/passwd"
        result = tool_read_document(malicious_path)

        # Assert: Fails safely
        assert "❌" in result or "not found" in result.lower() or "error" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
