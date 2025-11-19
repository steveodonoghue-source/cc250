"""
Comprehensive Test Suite for New Features
==========================================
Tests marketplace, cost optimization, and pre-built packs with minimal token usage.
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

# Import modules
import database as db
import database_marketplace as db_market
import database_cost_optimization as db_cost


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


def test_marketplace_database(results):
    """Test marketplace database functionality."""
    print("\n[1] Testing Marketplace Database")
    print("-" * 60)

    # Test 1: Categories exist
    try:
        categories = db_market.list_categories()
        assert len(categories) >= 10, f"Expected 10+ categories, got {len(categories)}"
        results.add_pass("Categories initialized")
    except Exception as e:
        results.add_fail("Categories initialized", str(e))

    # Test 2: Create and tag skill
    try:
        # Create a test skill
        skill_id = db.save_skill(
            tool_name="test_skill_temp",
            description="Test skill for validation",
            code="def test(): pass",
            parameters={},
            safety_notes=[]
        )

        # Tag it with a category
        category = categories[0]
        db_market.tag_skill(skill_id, category['id'])

        results.add_pass("Skill tagging works")

        # Cleanup
        db.delete_skill("test_skill_temp")
    except Exception as e:
        results.add_fail("Skill tagging works", str(e))

    # Test 3: Rating system
    try:
        # Get a real skill
        skills = db.list_skills(active_only=True, limit=1)
        if skills:
            skill = skills[0]

            # Add rating
            rating_id = db_market.add_rating(
                skill_id=skill['id'],
                user_id='test_user',
                rating=5,
                review_text='Test review'
            )

            # Get rating summary
            summary = db_market.get_skill_rating_summary(skill['id'])
            assert summary['review_count'] > 0, "Rating not counted"

            results.add_pass("Rating system works")
        else:
            results.add_fail("Rating system works", "No skills to test")
    except Exception as e:
        results.add_fail("Rating system works", str(e))

    # Test 4: Pricing system
    try:
        skills = db.list_skills(active_only=True, limit=1)
        if skills:
            skill = skills[0]

            # Set pricing
            pricing_id = db_market.set_skill_pricing(
                skill_id=skill['id'],
                pricing_type='free',
                price=0.0
            )

            # Get pricing
            pricing = db_market.get_skill_pricing(skill['id'])
            assert pricing is not None, "Pricing not retrieved"

            results.add_pass("Pricing system works")
        else:
            results.add_fail("Pricing system works", "No skills to test")
    except Exception as e:
        results.add_fail("Pricing system works", str(e))

    # Test 5: Skill packs
    try:
        packs = db_market.list_skill_packs()
        assert len(packs) >= 8, f"Expected 8+ packs, got {len(packs)}"

        # Get skills in first pack
        if packs:
            pack_skills = db_market.get_skill_pack_skills(packs[0]['id'])
            assert len(pack_skills) > 0, "Pack has no skills"

        results.add_pass("Skill packs work")
    except Exception as e:
        results.add_fail("Skill packs work", str(e))

    # Test 6: Enhanced skill listing
    try:
        skills = db_market.list_skills_with_marketplace_data(limit=10)
        assert len(skills) > 0, "No skills returned"

        # Check marketplace metadata exists
        skill = skills[0]
        assert 'average_rating' in skill, "Missing average_rating"
        assert 'install_count' in skill, "Missing install_count"

        results.add_pass("Enhanced skill listing works")
    except Exception as e:
        results.add_fail("Enhanced skill listing works", str(e))


def test_cost_optimization(results):
    """Test cost optimization functionality."""
    print("\n[2] Testing Cost Optimization")
    print("-" * 60)

    # Test 1: Agent configurations
    try:
        configs = db_cost.list_agent_configs()
        assert len(configs) >= 6, f"Expected 6+ agent configs, got {len(configs)}"

        # Check specific agents
        planner = db_cost.get_agent_model_config('Planner')
        assert planner is not None, "Planner config missing"
        assert 'gemini-2.5-pro' in planner['model_name'].lower() or 'pro' in planner['model_name'].lower(), "Planner should use Pro model"

        coder = db_cost.get_agent_model_config('Coder')
        assert coder is not None, "Coder config missing"
        assert 'flash' in coder['model_name'].lower(), "Coder should use Flash model"

        results.add_pass("Agent model configurations correct")
    except Exception as e:
        results.add_fail("Agent model configurations correct", str(e))

    # Test 2: Budget setting
    try:
        budget_id = db_cost.set_budget(
            budget_type='per_session',
            budget_limit=10.0,
            alert_threshold=0.8
        )

        # Get budget
        budget = db_cost.get_active_budget('per_session')
        assert budget is not None, "Budget not retrieved"
        assert budget['budget_limit'] == 10.0, "Budget limit incorrect"

        results.add_pass("Budget management works")
    except Exception as e:
        results.add_fail("Budget management works", str(e))

    # Test 3: Cost tracking
    try:
        session_id = 'test_session_' + datetime.now().isoformat()

        # Track some costs
        tracking_id1, cost1 = db_cost.track_cost(
            session_id=session_id,
            agent_name='Planner',
            model_name='gemini-2.5-pro',
            input_tokens=1000,
            output_tokens=500
        )

        tracking_id2, cost2 = db_cost.track_cost(
            session_id=session_id,
            agent_name='Coder',
            model_name='gemini-2.0-flash-exp',
            input_tokens=2000,
            output_tokens=1000
        )

        # Get session summary
        summary = db_cost.get_session_cost_summary(session_id)
        assert summary['call_count'] == 2, f"Expected 2 calls, got {summary['call_count']}"
        assert summary['total_tokens'] == 4500, f"Expected 4500 tokens, got {summary['total_tokens']}"

        results.add_pass("Cost tracking works")
    except Exception as e:
        results.add_fail("Cost tracking works", str(e))

    # Test 4: Cost analytics
    try:
        analytics = db_cost.get_cost_analytics(days=7)
        assert 'total_calls' in analytics, "Missing total_calls"
        assert 'by_agent' in analytics, "Missing by_agent breakdown"
        assert 'by_model' in analytics, "Missing by_model breakdown"

        results.add_pass("Cost analytics works")
    except Exception as e:
        results.add_fail("Cost analytics works", str(e))

    # Test 5: Cache functionality
    try:
        cache_id = db_cost.cache_response(
            cache_key='test_key_123',
            agent_name='Planner',
            model_name='gemini-2.5-pro',
            prompt_hash='hash123',
            response_text='Test response',
            ttl_hours=24
        )

        # Get cached response
        cached = db_cost.get_cached_response('test_key_123')
        assert cached is not None, "Cache not retrieved"
        assert cached['response_text'] == 'Test response', "Cached response incorrect"

        results.add_pass("Response caching works")
    except Exception as e:
        results.add_fail("Response caching works", str(e))

    # Test 6: Alerts
    try:
        alerts = db_cost.get_unacknowledged_alerts()
        # Should work even if empty
        assert isinstance(alerts, list), "Alerts not returned as list"

        results.add_pass("Cost alerts work")
    except Exception as e:
        results.add_fail("Cost alerts work", str(e))


def test_prebuilt_packs(results):
    """Test pre-built skill packs."""
    print("\n[3] Testing Pre-built Skill Packs")
    print("-" * 60)

    # Test 1: Skills created
    try:
        expected_skills = [
            'fetch_webpage', 'extract_links', 'analyze_csv',
            'create_visualization', 'read_json_file', 'write_json_file',
            'call_rest_api', 'extract_keywords', 'run_unit_tests', 'query_sqlite'
        ]

        all_skills = db.list_skills(active_only=True, limit=100)
        skill_names = [s['tool_name'] for s in all_skills]

        found_count = sum(1 for skill in expected_skills if skill in skill_names)
        assert found_count == len(expected_skills), f"Expected {len(expected_skills)} skills, found {found_count}"

        results.add_pass(f"All {len(expected_skills)} example skills created")
    except Exception as e:
        results.add_fail("Example skills created", str(e))

    # Test 2: Skills have proper structure
    try:
        skills = db.list_skills(active_only=True, limit=1)
        if skills:
            skill = skills[0]
            assert 'tool_name' in skill, "Missing tool_name"
            assert 'description' in skill, "Missing description"
            assert 'code' in skill, "Missing code"
            assert 'parameters' in skill, "Missing parameters"

            results.add_pass("Skills have proper structure")
        else:
            results.add_fail("Skills have proper structure", "No skills found")
    except Exception as e:
        results.add_fail("Skills have proper structure", str(e))

    # Test 3: Packs created
    try:
        expected_packs = [
            'Web Scraping Essentials', 'Data Analysis Pro',
            'File Operations Bundle', 'API Integration Kit',
            'Text Processing Suite', 'Testing & QA Pack',
            'Database Essentials', 'Full Stack Developer Pack'
        ]

        all_packs = db_market.list_skill_packs()
        pack_names = [p['name'] for p in all_packs]

        found_count = sum(1 for pack in expected_packs if pack in pack_names)
        assert found_count == len(expected_packs), f"Expected {len(expected_packs)} packs, found {found_count}"

        results.add_pass(f"All {len(expected_packs)} skill packs created")
    except Exception as e:
        results.add_fail("Skill packs created", str(e))

    # Test 4: Pack contents
    try:
        packs = db_market.list_skill_packs()
        full_stack_pack = next((p for p in packs if 'Full Stack' in p['name']), None)

        if full_stack_pack:
            pack_skills = db_market.get_skill_pack_skills(full_stack_pack['id'])
            assert len(pack_skills) == 5, f"Full Stack pack should have 5 skills, got {len(pack_skills)}"

            results.add_pass("Pack contents correct")
        else:
            results.add_fail("Pack contents correct", "Full Stack pack not found")
    except Exception as e:
        results.add_fail("Pack contents correct", str(e))

    # Test 5: Sample ratings
    try:
        skills = db.list_skills(active_only=True, limit=100)

        rated_count = 0
        for skill in skills:
            summary = db_market.get_skill_rating_summary(skill['id'])
            if summary['review_count'] > 0:
                rated_count += 1

        assert rated_count > 0, "No skills have ratings"

        results.add_pass(f"{rated_count} skills have ratings")
    except Exception as e:
        results.add_fail("Sample ratings added", str(e))

    # Test 6: Skill categorization
    try:
        skills = db_market.list_skills_with_marketplace_data(limit=100)

        # Check that skills can be filtered by category
        web_category = next((c for c in db_market.list_categories() if 'Web' in c['name']), None)
        if web_category:
            web_skills = db_market.list_skills_with_marketplace_data(
                limit=100,
                category_id=web_category['id']
            )
            assert len(web_skills) >= 2, "Expected at least 2 web scraping skills"

        results.add_pass("Skill categorization works")
    except Exception as e:
        results.add_fail("Skill categorization works", str(e))


def test_api_validation(results):
    """Test API endpoint validation (syntax only, no server required)."""
    print("\n[4] Testing API Endpoints (Syntax Validation)")
    print("-" * 60)

    try:
        import api

        # Check that API module loads
        assert hasattr(api, 'app'), "FastAPI app not found"

        results.add_pass("API module loads correctly")
    except Exception as e:
        results.add_fail("API module loads correctly", str(e))

    # Test 2: Pydantic models
    try:
        from api import (
            CategoryCreate, SkillRating, SkillPricingUpdate,
            SkillPackCreate, BudgetConfig, AgentModelConfig, CostTrackingRequest
        )

        # Test model instantiation
        category = CategoryCreate(name="Test", description="Test category")
        assert category.name == "Test", "CategoryCreate model broken"

        budget = BudgetConfig(budget_type="per_session", budget_limit=10.0)
        assert budget.budget_limit == 10.0, "BudgetConfig model broken"

        results.add_pass("Pydantic models work correctly")
    except Exception as e:
        results.add_fail("Pydantic models work correctly", str(e))

    # Test 3: Endpoint routes exist
    try:
        from api import app

        routes = [route.path for route in app.routes]

        # Check key marketplace endpoints
        marketplace_endpoints = [
            '/api/v1/marketplace/categories',
            '/api/v1/marketplace/skills',
            '/api/v1/marketplace/packs'
        ]

        for endpoint in marketplace_endpoints:
            assert endpoint in routes, f"Missing endpoint: {endpoint}"

        # Check key cost endpoints
        cost_endpoints = [
            '/api/v1/cost/budget',
            '/api/v1/cost/agents/configs',
            '/api/v1/cost/analytics'
        ]

        for endpoint in cost_endpoints:
            assert endpoint in routes, f"Missing endpoint: {endpoint}"

        results.add_pass("All API endpoints registered")
    except Exception as e:
        results.add_fail("All API endpoints registered", str(e))


def test_ui_validation(results):
    """Test UI component validation (syntax only)."""
    print("\n[5] Testing UI Components (Syntax Validation)")
    print("-" * 60)

    try:
        import streamlit_app

        # Check that module loads
        assert hasattr(streamlit_app, 'render_sidebar'), "render_sidebar function not found"

        results.add_pass("Streamlit app module loads")
    except Exception as e:
        results.add_fail("Streamlit app module loads", str(e))

    # Test 2: Database imports
    try:
        from streamlit_app import db, db_market, db_cost

        assert db is not None, "Core database import failed"
        assert db_market is not None, "Marketplace database import failed"
        assert db_cost is not None, "Cost database import failed"

        results.add_pass("Database modules imported correctly")
    except Exception as e:
        results.add_fail("Database modules imported correctly", str(e))


def test_integration(results):
    """Test integration between components."""
    print("\n[6] Testing Integration")
    print("-" * 60)

    # Test 1: End-to-end skill creation and marketplace listing
    try:
        # Create a skill
        skill_id = db.save_skill(
            tool_name="integration_test_skill",
            description="Integration test skill",
            code="def integration_test(): return 'success'",
            parameters={'test': 'str'},
            safety_notes=['Test only']
        )

        # Set pricing
        db_market.set_skill_pricing(skill_id, 'free', 0.0)

        # Add rating
        db_market.add_rating(skill_id, 'integration_user', 5, 'Great!')

        # Get with marketplace data
        skills = db_market.list_skills_with_marketplace_data(limit=100)
        integration_skill = next((s for s in skills if s['tool_name'] == 'integration_test_skill'), None)

        assert integration_skill is not None, "Skill not found in marketplace listing"
        assert integration_skill['average_rating'] == 5.0, "Rating not reflected"
        assert integration_skill['pricing_type'] == 'free', "Pricing not set"

        # Cleanup
        db.delete_skill("integration_test_skill")

        results.add_pass("End-to-end skill workflow")
    except Exception as e:
        results.add_fail("End-to-end skill workflow", str(e))

    # Test 2: Cost tracking integration
    try:
        session_id = 'integration_test_' + datetime.now().isoformat()

        # Track costs for multiple agents
        db_cost.track_cost(session_id, 'Planner', 'gemini-2.5-pro', 1000, 500)
        db_cost.track_cost(session_id, 'Coder', 'gemini-2.0-flash-exp', 2000, 1000)
        db_cost.track_cost(session_id, 'Reviewer', 'gemini-2.5-pro', 1500, 750)

        # Get summary
        summary = db_cost.get_session_cost_summary(session_id)

        # Verify agent breakdown
        agent_breakdown = summary['agent_breakdown']
        assert len(agent_breakdown) == 3, f"Expected 3 agents, got {len(agent_breakdown)}"

        planner_cost = next((a for a in agent_breakdown if a['agent_name'] == 'Planner'), None)
        assert planner_cost is not None, "Planner cost not found"

        results.add_pass("Multi-agent cost tracking")
    except Exception as e:
        results.add_fail("Multi-agent cost tracking", str(e))


def run_all_tests():
    """Run all tests and generate report."""
    results = TestResults()

    print("=" * 60)
    print("COMPREHENSIVE FEATURE TEST SUITE")
    print("=" * 60)
    print(f"Testing: Marketplace, Cost Optimization, Pre-built Packs")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        test_marketplace_database(results)
        test_cost_optimization(results)
        test_prebuilt_packs(results)
        test_api_validation(results)
        test_ui_validation(results)
        test_integration(results)
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        traceback.print_exc()

    results.summary()

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    return results.failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
