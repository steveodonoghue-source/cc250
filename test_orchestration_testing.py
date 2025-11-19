"""
Comprehensive Test Suite for Orchestration & Testing Features
===============================================================
Tests Features #10 (Advanced Orchestration) and #11 (Testing & Quality Framework).
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import database as db
import database_orchestration as db_orch
import database_testing_quality as db_test


class TestResults:
    """Track test results."""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def add_pass(self, test_name):
        self.passed += 1
        print(f"  ✅ {test_name}")

    def add_fail(self, test_name, error):
        self.failed += 1
        self.errors.append((test_name, error))
        print(f"  ❌ {test_name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed} ✅")
        print(f"Failed: {self.failed} ❌")
        print(f"Success Rate: {(self.passed/total*100):.1f}%")

        if self.errors:
            print(f"\n{'='*60}")
            print(f"FAILURES")
            print(f"{'='*60}")
            for test_name, error in self.errors:
                print(f"\n{test_name}:")
                print(f"  {error}")


def cleanup_test_data():
    """Clean up any previous test data."""
    import sqlite3

    # Clean orchestration test data
    conn = sqlite3.connect(db_orch.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM workflow_definitions WHERE name LIKE 'Test%'")
        cursor.execute("DELETE FROM workflow_definitions WHERE created_by = 'test_user'")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    # Clean testing test data
    conn = sqlite3.connect(db_test.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM test_suites WHERE name LIKE 'Test%'")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def test_orchestration_database(results):
    """Test orchestration database and functions."""
    print("\n[1] Testing Advanced Orchestration")
    print("-" * 60)

    # Test 1: Workflow creation
    try:
        workflow_id = db_orch.create_workflow(
            name="Test Workflow",
            description="Test workflow for validation",
            workflow_type="sequential",
            config={"type": "sequential", "steps": []},
            created_by="test_user"
        )
        assert workflow_id > 0, "Workflow ID should be positive"
        results.add_pass("Workflow creation")
    except Exception as e:
        results.add_fail("Workflow creation", str(e))

    # Test 2: Add workflow steps
    try:
        step_id = db_orch.add_workflow_step(
            workflow_id=workflow_id,
            step_number=1,
            agent_name="Planner",
            task_description="Plan the implementation",
            parallel_group=0
        )
        assert step_id > 0, "Step ID should be positive"
        results.add_pass("Workflow step creation")
    except Exception as e:
        results.add_fail("Workflow step creation", str(e))

    # Test 3: Get workflow with steps
    try:
        workflow = db_orch.get_workflow(workflow_id)
        assert workflow is not None, "Workflow should exist"
        assert len(workflow['steps']) == 1, "Should have 1 step"
        assert workflow['steps'][0]['agent_name'] == "Planner", "Step agent should be Planner"
        results.add_pass("Get workflow with steps")
    except Exception as e:
        results.add_fail("Get workflow with steps", str(e))

    # Test 4: List workflows
    try:
        workflows = db_orch.list_workflows(active_only=True)
        assert len(workflows) > 0, "Should have at least 1 workflow"
        results.add_pass("List workflows")
    except Exception as e:
        results.add_fail("List workflows", str(e))

    # Test 5: Workflow execution
    try:
        execution_id = db_orch.start_workflow_execution(
            workflow_id=workflow_id,
            session_id="test_session_123",
            input_data={"test": "data"}
        )
        assert execution_id > 0, "Execution ID should be positive"
        results.add_pass("Start workflow execution")
    except Exception as e:
        results.add_fail("Start workflow execution", str(e))

    # Test 6: Update execution status
    try:
        db_orch.update_workflow_execution(
            execution_id=execution_id,
            status="completed",
            output_data={"result": "success"}
        )
        results.add_pass("Update workflow execution")
    except Exception as e:
        results.add_fail("Update workflow execution", str(e))

    # Test 7: Workflow templates
    try:
        templates = db_orch.list_workflow_templates()
        assert len(templates) >= 4, f"Should have 4+ templates, got {len(templates)}"

        # Verify template structure
        template = templates[0]
        assert 'name' in template, "Template should have name"
        assert 'complexity_level' in template, "Template should have complexity"

        results.add_pass("Workflow templates")
    except Exception as e:
        results.add_fail("Workflow templates", str(e))

    # Test 8: Create from template
    try:
        template_id = templates[0]['id']
        new_wf_id = db_orch.create_workflow_from_template(
            template_id=template_id,
            name="Test From Template",
            session_id="test_session_456"
        )
        assert new_wf_id > 0, "Should create workflow from template"
        results.add_pass("Create from template")
    except Exception as e:
        results.add_fail("Create from template", str(e))

    # Test 9: Agent specializations
    try:
        specs = db_orch.get_agent_specializations("Planner")
        assert len(specs) >= 3, f"Planner should have 3+ specializations, got {len(specs)}"

        # Check specialization structure
        spec = specs[0]
        assert 'specialization_area' in spec, "Should have specialization area"
        assert 'proficiency_level' in spec, "Should have proficiency level"
        assert spec['proficiency_level'] >= 1 and spec['proficiency_level'] <= 10, "Proficiency should be 1-10"

        results.add_pass("Agent specializations")
    except Exception as e:
        results.add_fail("Agent specializations", str(e))

    # Test 10: Task routing
    try:
        best_agent = db_orch.get_best_agent_for_task(
            task="Read a JSON file and parse it",
            keywords=["file", "read", "json"]
        )
        assert best_agent in ["Planner", "Coder", "FileHandler", "Reviewer", "SkillGenerator", "Executor"], \
            f"Should route to a valid agent, got {best_agent}"
        results.add_pass("Task routing")
    except Exception as e:
        results.add_fail("Task routing", str(e))

    # Test 11: Agent performance update
    try:
        db_orch.update_agent_performance(
            agent_name="Planner",
            specialization_area="Architecture Design",
            success=True,
            duration=1.5
        )
        results.add_pass("Agent performance tracking")
    except Exception as e:
        results.add_fail("Agent performance tracking", str(e))


def test_safety_validation(results):
    """Test safety validation features."""
    print("\n[2] Testing Safety Validation")
    print("-" * 60)

    # Test 1: Safe code check
    try:
        safe_code = """
def safe_function(x, y):
    return x + y
"""
        risk_level, issues = db_test.check_code_safety(skill_id=1, code=safe_code)
        assert risk_level in ["none", "low"], f"Safe code should have low/no risk, got {risk_level}"
        results.add_pass("Safe code detection")
    except Exception as e:
        results.add_fail("Safe code detection", str(e))

    # Test 2: Unsafe code detection (eval)
    try:
        unsafe_code = """
def unsafe_function(code):
    return eval(code)
"""
        risk_level, issues = db_test.check_code_safety(skill_id=1, code=unsafe_code)
        assert risk_level == "critical", f"eval() should be critical risk, got {risk_level}"
        assert len(issues) > 0, "Should detect eval() issue"
        results.add_pass("Unsafe code detection (eval)")
    except Exception as e:
        results.add_fail("Unsafe code detection (eval)", str(e))

    # Test 3: SQL injection detection
    try:
        sql_injection_code = """
def query_user(username):
    query = f"SELECT * FROM users WHERE name = '{username}'"
    cursor.execute(query)
"""
        risk_level, issues = db_test.check_code_safety(skill_id=1, code=sql_injection_code)
        assert risk_level in ["high", "critical"], f"SQL injection should be high risk, got {risk_level}"
        results.add_pass("SQL injection detection")
    except Exception as e:
        results.add_fail("SQL injection detection", str(e))

    # Test 4: Import validation
    try:
        dangerous_imports = """
import os
import subprocess
"""
        is_safe, issues = db_test.validate_imports(dangerous_imports)
        assert not is_safe, "Should detect dangerous imports"
        assert len(issues) > 0, "Should list dangerous imports"
        results.add_pass("Import validation")
    except Exception as e:
        results.add_fail("Import validation", str(e))

    # Test 5: Code complexity analysis
    try:
        complex_code = """
def complex_function(x):
    if x > 10:
        for i in range(x):
            if i % 2 == 0:
                while i > 0:
                    i -= 1
    return x
"""
        metrics = db_test.analyze_code_complexity(complex_code)
        assert 'functions' in metrics, "Should have function count"
        assert 'cyclomatic_complexity' in metrics, "Should have complexity metric"
        assert metrics['cyclomatic_complexity'] > 1, "Complex code should have complexity > 1"
        results.add_pass("Code complexity analysis")
    except Exception as e:
        results.add_fail("Code complexity analysis", str(e))


def test_quality_scoring(results):
    """Test quality scoring system."""
    print("\n[3] Testing Quality Scoring")
    print("-" * 60)

    # Get or create a skill for testing
    try:
        skills = db.list_skills(active_only=True, limit=1)
        if not skills:
            # Create a test skill
            skill_id = db.create_skill(
                tool_name="test_quality_skill",
                description="Test skill for quality scoring",
                category="Testing",
                code="def test(): return True",
                created_by="test_user"
            )
        else:
            skill = skills[0]
            skill_id = skill['id']

        # Test 1: Create test suite
        try:
            suite_id = db_test.create_test_suite(
                skill_id=skill_id,
                name="Test Suite for Quality",
                description="Testing quality scoring"
            )
            assert suite_id > 0, "Suite ID should be positive"
            results.add_pass("Create test suite")
        except Exception as e:
            results.add_fail("Create test suite", str(e))

        # Test 2: Add test case
        try:
            test_case_id = db_test.add_test_case(
                suite_id=suite_id,
                name="Basic Test",
                test_code="result = 2 + 2",
                expected_output=4,
                description="Test basic addition"
            )
            assert test_case_id > 0, "Test case ID should be positive"
            results.add_pass("Add test case")
        except Exception as e:
            results.add_fail("Add test case", str(e))

        # Test 3: Run test case
        try:
            test_result = db_test.run_test_case(
                test_case_id=test_case_id,
                skill_id=skill_id,
                skill_code="# Empty skill code for testing"
            )
            assert 'status' in test_result, "Should have status"
            assert 'execution_time_ms' in test_result, "Should have execution time"
            results.add_pass("Run test case")
        except Exception as e:
            results.add_fail("Run test case", str(e))

        # Test 4: Calculate quality score
        try:
            scores = db_test.calculate_quality_score(skill_id=skill_id)

            assert 'test_score' in scores, "Should have test score"
            assert 'safety_score' in scores, "Should have safety score"
            assert 'overall_score' in scores, "Should have overall score"
            assert 'certification_level' in scores, "Should have certification level"

            assert 0 <= scores['overall_score'] <= 100, "Overall score should be 0-100"
            assert scores['certification_level'] in ['uncertified', 'bronze', 'silver', 'gold', 'platinum'], \
                f"Invalid certification level: {scores['certification_level']}"

            results.add_pass("Calculate quality score")
        except Exception as e:
            results.add_fail("Calculate quality score", str(e))

        # Test 5: Get quality report
        try:
            report = db_test.get_skill_quality_report(skill_id=skill_id)

            assert 'quality_scores' in report, "Should have quality scores"
            assert 'test_results' in report, "Should have test results"
            assert 'safety_issues' in report, "Should have safety issues"
            assert 'recommendations' in report, "Should have recommendations"

            results.add_pass("Get quality report")
        except Exception as e:
            results.add_fail("Get quality report", str(e))

    except Exception as e:
        results.add_fail("Quality scoring setup", str(e))


def test_api_integration(results):
    """Test API endpoint availability (syntax only)."""
    print("\n[4] Testing API Integration")
    print("-" * 60)

    try:
        import api

        # Test 1: API module loads
        try:
            assert hasattr(api, 'app'), "API should have FastAPI app"
            results.add_pass("API module loads")
        except Exception as e:
            results.add_fail("API module loads", str(e))

        # Test 2: Orchestration models
        try:
            from api import WorkflowCreate, WorkflowStepCreate, RoutingRequest

            # Test model creation
            workflow = WorkflowCreate(
                name="Test",
                description="Test",
                workflow_type="sequential",
                config={}
            )
            assert workflow.name == "Test", "Model should work"
            results.add_pass("Orchestration Pydantic models")
        except Exception as e:
            results.add_fail("Orchestration Pydantic models", str(e))

        # Test 3: Testing models
        try:
            from api import TestSuiteCreate, TestCaseCreate, SafetyCheckRequest

            suite = TestSuiteCreate(skill_id=1, name="Test")
            assert suite.skill_id == 1, "Model should work"
            results.add_pass("Testing Pydantic models")
        except Exception as e:
            results.add_fail("Testing Pydantic models", str(e))

        # Test 4: Endpoint registration
        try:
            routes = [route.path for route in api.app.routes]

            # Check orchestration endpoints
            orch_endpoints = [
                '/api/v1/orchestration/workflows',
                '/api/v1/orchestration/templates',
                '/api/v1/orchestration/route'
            ]

            for endpoint in orch_endpoints:
                assert endpoint in routes, f"Missing endpoint: {endpoint}"

            # Check testing endpoints
            test_endpoints = [
                '/api/v1/testing/suites',
                '/api/v1/testing/safety/check',
                '/api/v1/testing/quality/calculate'
            ]

            for endpoint in test_endpoints:
                assert endpoint in routes, f"Missing endpoint: {endpoint}"

            results.add_pass("API endpoints registered")
        except Exception as e:
            results.add_fail("API endpoints registered", str(e))

    except Exception as e:
        results.add_fail("API integration", str(e))


def test_ui_integration(results):
    """Test UI component integration."""
    print("\n[5] Testing UI Integration")
    print("-" * 60)

    try:
        import streamlit_app

        # Test 1: UI module loads
        try:
            assert hasattr(streamlit_app, 'render_sidebar'), "Should have render_sidebar"
            results.add_pass("UI module loads")
        except Exception as e:
            results.add_fail("UI module loads", str(e))

        # Test 2: Database imports
        try:
            from streamlit_app import db, db_market, db_cost, db_orch, db_test

            assert db is not None, "Core database import failed"
            assert db_orch is not None, "Orchestration database import failed"
            assert db_test is not None, "Testing database import failed"

            results.add_pass("UI database imports")
        except Exception as e:
            results.add_fail("UI database imports", str(e))

    except Exception as e:
        results.add_fail("UI integration", str(e))


def run_all_tests():
    """Run all tests."""
    results = TestResults()

    print("=" * 60)
    print("ORCHESTRATION & TESTING FEATURE TEST SUITE")
    print("=" * 60)
    print(f"Testing: Advanced Orchestration, Testing & Quality Framework")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Clean up any previous test data
    print("\nCleaning up previous test data...")
    cleanup_test_data()

    try:
        test_orchestration_database(results)
        test_safety_validation(results)
        test_quality_scoring(results)
        test_api_integration(results)
        test_ui_integration(results)
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

    results.summary()

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    return results.failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
