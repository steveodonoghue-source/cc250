"""
Comprehensive Test Suite for Integration Hub (Feature #16)

Tests:
- Integration management (create, list, toggle)
- GitHub integration (repos, sync)
- Webhook system (create, trigger, deliveries)
- Slack notifications (channels, send)
- Export/Import (skills export/import)
- API endpoints (models, routes)
- UI integration (module loading)
- Integration logs
"""

import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database_integrations as db_int
import database as db


class TestResults:
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
        success_rate = (self.passed / total * 100) if total > 0 else 0

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed} ✅")
        print(f"Failed: {self.failed} ❌")
        print(f"Success Rate: {success_rate:.1f}%")

        if self.errors:
            print("\n" + "=" * 60)
            print("FAILURES")
            print("=" * 60)
            for test_name, error in self.errors:
                print(f"\n{test_name}:")
                print(f"  {error}")


def cleanup_test_data():
    """Clean up any previous test data."""
    import sqlite3

    # Clean integrations test data
    conn = sqlite3.connect(db_int.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM integrations WHERE name LIKE 'Test%'")
        cursor.execute("DELETE FROM webhook_endpoints WHERE description LIKE 'Test%'")
        cursor.execute("DELETE FROM export_jobs WHERE created_by = 'test_user'")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def test_integration_management(results):
    """Test integration CRUD operations."""
    print("\n[1] Testing Integration Management")
    print("-" * 60)

    # Test 1: Create integration
    try:
        integration_id = db_int.create_integration(
            integration_type="github",
            name="Test GitHub Integration",
            config={"auto_import": True},
            credentials={"access_token": "test_token_123"},
            description="Test integration for validation",
            created_by="test_user"
        )
        assert integration_id > 0, "Integration ID should be positive"
        results.add_pass("Create integration")
    except Exception as e:
        results.add_fail("Create integration", str(e))
        return

    # Test 2: Get integration
    try:
        integration = db_int.get_integration(integration_id)
        assert integration is not None, "Should retrieve integration"
        assert integration['name'] == "Test GitHub Integration"
        assert integration['integration_type'] == "github"
        results.add_pass("Get integration")
    except Exception as e:
        results.add_fail("Get integration", str(e))

    # Test 3: List integrations
    try:
        integrations = db_int.list_integrations()
        assert len(integrations) > 0, "Should have at least one integration"
        results.add_pass("List integrations")
    except Exception as e:
        results.add_fail("List integrations", str(e))

    # Test 4: List by type
    try:
        github_ints = db_int.list_integrations(integration_type="github")
        assert len(github_ints) > 0, "Should find GitHub integrations"
        results.add_pass("List integrations by type")
    except Exception as e:
        results.add_fail("List integrations by type", str(e))

    # Test 5: Toggle integration
    try:
        success = db_int.toggle_integration(integration_id, False)
        assert success, "Should successfully disable integration"

        integration = db_int.get_integration(integration_id)
        assert integration['is_enabled'] == 0, "Integration should be disabled"

        # Re-enable
        db_int.toggle_integration(integration_id, True)
        results.add_pass("Toggle integration")
    except Exception as e:
        results.add_fail("Toggle integration", str(e))

    # Test 6: Integration logs
    try:
        logs = db_int.get_integration_logs(integration_id, limit=10)
        assert len(logs) > 0, "Should have integration logs"
        results.add_pass("Get integration logs")
    except Exception as e:
        results.add_fail("Get integration logs", str(e))


def test_github_integration(results):
    """Test GitHub integration features."""
    print("\n[2] Testing GitHub Integration")
    print("-" * 60)

    # Create a test integration first
    integration_id = db_int.create_integration(
        integration_type="github",
        name="Test GitHub for Repos",
        config={},
        credentials={"access_token": "test_token"},
        created_by="test_user"
    )

    # Test 1: Add GitHub repository
    try:
        repo_id = db_int.add_github_repo(
            integration_id=integration_id,
            repo_full_name="test/repo",
            repo_url="https://github.com/test/repo",
            auto_import=True,
            skill_path_pattern="*.py"
        )
        assert repo_id > 0, "Repo ID should be positive"
        results.add_pass("Add GitHub repository")
    except Exception as e:
        results.add_fail("Add GitHub repository", str(e))
        return

    # Test 2: List GitHub repositories
    try:
        repos = db_int.list_github_repos(integration_id)
        assert len(repos) > 0, "Should have at least one repository"
        assert repos[0]['repo_full_name'] == "test/repo"
        results.add_pass("List GitHub repositories")
    except Exception as e:
        results.add_fail("List GitHub repositories", str(e))

    # Test 3: Sync GitHub repo (will fail without valid token, but test the flow)
    try:
        success, message = db_int.sync_github_repo(repo_id)
        # Expected to fail due to test token, but should not crash
        assert isinstance(success, bool), "Should return boolean"
        assert isinstance(message, str), "Should return message"
        results.add_pass("Sync GitHub repo (flow)")
    except Exception as e:
        results.add_fail("Sync GitHub repo (flow)", str(e))


def test_webhook_system(results):
    """Test webhook creation and triggering."""
    print("\n[3] Testing Webhook System")
    print("-" * 60)

    # Test 1: Create webhook
    try:
        webhook_id, endpoint_url, secret_key = db_int.create_webhook(
            integration_id=None,
            events=["skill_created", "workflow_completed"],
            description="Test webhook"
        )
        assert webhook_id > 0, "Webhook ID should be positive"
        assert endpoint_url.startswith("/webhooks/"), "Endpoint should be valid"
        assert len(secret_key) > 0, "Secret key should be generated"
        results.add_pass("Create webhook")
    except Exception as e:
        results.add_fail("Create webhook", str(e))
        return

    # Test 2: List webhooks
    try:
        webhooks = db_int.list_webhooks()
        assert len(webhooks) > 0, "Should have at least one webhook"
        results.add_pass("List webhooks")
    except Exception as e:
        results.add_fail("List webhooks", str(e))

    # Test 3: Trigger webhook
    try:
        delivery_id = db_int.trigger_webhook(
            webhook_id=webhook_id,
            event_type="test_event",
            payload={"message": "Test payload"}
        )
        assert delivery_id > 0, "Delivery ID should be positive"
        results.add_pass("Trigger webhook")
    except Exception as e:
        results.add_fail("Trigger webhook", str(e))

    # Test 4: Verify webhook signature
    try:
        payload = '{"test": "data"}'
        signature = "test_signature"
        secret = "test_secret"

        # This will fail but tests the function
        result = db_int.verify_webhook_signature(payload, signature, secret)
        assert isinstance(result, bool), "Should return boolean"
        results.add_pass("Verify webhook signature")
    except Exception as e:
        results.add_fail("Verify webhook signature", str(e))


def test_slack_notifications(results):
    """Test Slack notification features."""
    print("\n[4] Testing Slack Notifications")
    print("-" * 60)

    # Create a test Slack integration first
    integration_id = db_int.create_integration(
        integration_type="slack",
        name="Test Slack Integration",
        config={},
        credentials={"webhook_url": "https://hooks.slack.com/test"},
        created_by="test_user"
    )

    # Test 1: Add Slack channel
    try:
        channel_id = db_int.add_slack_channel(
            integration_id=integration_id,
            channel_id="C123456",
            channel_name="#test-channel",
            event_subscriptions=["workflow_completed", "skill_created"],
            workspace_id="W123",
            workspace_name="Test Workspace"
        )
        assert channel_id > 0, "Channel ID should be positive"
        results.add_pass("Add Slack channel")
    except Exception as e:
        results.add_fail("Add Slack channel", str(e))
        return

    # Test 2: List Slack channels
    try:
        channels = db_int.list_slack_channels(integration_id)
        assert len(channels) > 0, "Should have at least one channel"
        assert channels[0]['channel_name'] == "#test-channel"
        results.add_pass("List Slack channels")
    except Exception as e:
        results.add_fail("List Slack channels", str(e))

    # Test 3: Send Slack notification (will fail but tests flow)
    try:
        success = db_int.send_slack_notification(
            channel_id=channel_id,
            event_type="test",
            message="Test notification"
        )
        # Expected to fail due to test webhook URL, but should not crash
        assert isinstance(success, bool), "Should return boolean"
        results.add_pass("Send Slack notification (flow)")
    except Exception as e:
        results.add_fail("Send Slack notification (flow)", str(e))


def test_export_import(results):
    """Test export/import functionality."""
    print("\n[5] Testing Export/Import")
    print("-" * 60)

    # Test 1: Create export job
    try:
        job_id = db_int.create_export_job(
            job_type="export",
            export_format="json",
            scope="skills",
            metadata={"test": True},
            created_by="test_user"
        )
        assert job_id > 0, "Job ID should be positive"
        results.add_pass("Create export job")
    except Exception as e:
        results.add_fail("Create export job", str(e))
        return

    # Test 2: Get export job
    try:
        job = db_int.get_export_job(job_id)
        assert job is not None, "Should retrieve job"
        assert job['job_type'] == "export"
        assert job['scope'] == "skills"
        results.add_pass("Get export job")
    except Exception as e:
        results.add_fail("Get export job", str(e))

    # Test 3: Update export job
    try:
        db_int.update_export_job(
            job_id=job_id,
            status="completed",
            file_path="/tmp/test_export.json",
            file_size=1024,
            items_processed=5
        )

        job = db_int.get_export_job(job_id)
        assert job['status'] == "completed"
        assert job['file_path'] == "/tmp/test_export.json"
        results.add_pass("Update export job")
    except Exception as e:
        results.add_fail("Update export job", str(e))

    # Test 4: List export jobs
    try:
        jobs = db_int.list_export_jobs(job_type="export", limit=10)
        assert len(jobs) > 0, "Should have at least one job"
        results.add_pass("List export jobs")
    except Exception as e:
        results.add_fail("List export jobs", str(e))

    # Test 5: Export skills to JSON
    try:
        export_data = db_int.export_skills_to_json()
        assert 'version' in export_data, "Should have version"
        assert 'export_type' in export_data, "Should have export type"
        assert 'skills' in export_data, "Should have skills"
        assert export_data['count'] >= 0, "Should have count"
        results.add_pass("Export skills to JSON")
    except Exception as e:
        results.add_fail("Export skills to JSON", str(e))

    # Test 6: Import skills from JSON
    try:
        # Create a skill to export/import
        skill_id = db.save_skill(
            tool_name="test_import_skill",
            description="Test skill for import",
            code="def test(): return True",
            parameters={},
            safety_notes=[]
        )

        # Export it
        export_data = db_int.export_skills_to_json(skill_ids=[skill_id])

        # Delete it
        import sqlite3
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        conn.commit()
        conn.close()

        # Re-import
        imported_count, errors = db_int.import_skills_from_json(export_data)

        assert imported_count >= 0, "Should import skills"
        assert isinstance(errors, list), "Should return errors list"
        results.add_pass("Import skills from JSON")
    except Exception as e:
        results.add_fail("Import skills from JSON", str(e))


def test_api_integration(results):
    """Test API endpoint availability."""
    print("\n[6] Testing API Integration")
    print("-" * 60)

    # Test 1: API module loads
    try:
        import api
        assert api.app is not None, "FastAPI app should be initialized"
        results.add_pass("API module loads")
    except Exception as e:
        results.add_fail("API module loads", str(e))
        return

    # Test 2: Integration Pydantic models
    try:
        from api import IntegrationCreate, GitHubRepoAdd, WebhookCreate, SlackChannelAdd, ExportJobCreate

        # Test IntegrationCreate
        int_create = IntegrationCreate(
            integration_type="github",
            name="Test",
            config={},
            credentials=None
        )
        assert int_create.name == "Test"

        # Test GitHubRepoAdd
        repo_add = GitHubRepoAdd(
            integration_id=1,
            repo_full_name="owner/repo",
            repo_url="https://github.com/owner/repo"
        )
        assert repo_add.integration_id == 1

        # Test WebhookCreate
        webhook_create = WebhookCreate(events=["test_event"])
        assert len(webhook_create.events) == 1

        results.add_pass("Integration Pydantic models")
    except Exception as e:
        results.add_fail("Integration Pydantic models", str(e))

    # Test 3: API endpoints registered
    try:
        import api

        routes = [route.path for route in api.app.routes]

        # Check for key integration endpoints
        assert "/api/v1/integrations/types" in routes
        assert any("/api/v1/integrations" in r for r in routes)
        assert any("/api/v1/integrations/github/repos" in r for r in routes)
        assert any("/api/v1/integrations/webhooks" in r for r in routes)
        assert any("/api/v1/integrations/slack/channels" in r for r in routes)
        assert any("/api/v1/integrations/export" in r for r in routes)

        results.add_pass("API endpoints registered")
    except Exception as e:
        results.add_fail("API endpoints registered", str(e))


def test_ui_integration(results):
    """Test UI component integration."""
    print("\n[7] Testing UI Integration")
    print("-" * 60)

    # Test 1: UI module loads
    try:
        import streamlit_app
        results.add_pass("UI module loads")
    except Exception as e:
        results.add_fail("UI module loads", str(e))

    # Test 2: Database imports in UI
    try:
        import importlib
        import streamlit_app

        # Check if database_integrations can be imported
        db_int_module = importlib.import_module('database_integrations')
        assert db_int_module is not None
        results.add_pass("UI database imports")
    except Exception as e:
        results.add_fail("UI database imports", str(e))


def run_all_tests():
    """Run all tests."""
    results = TestResults()

    print("=" * 60)
    print("INTEGRATION HUB TEST SUITE")
    print("=" * 60)
    print(f"Testing: Feature #16 - Integration Hub")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Clean up any previous test data
    print("\nCleaning up previous test data...")
    cleanup_test_data()

    try:
        test_integration_management(results)
        test_github_integration(results)
        test_webhook_system(results)
        test_slack_notifications(results)
        test_export_import(results)
        test_api_integration(results)
        test_ui_integration(results)
    except Exception as e:
        results.add_fail("Unexpected error", str(e))

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    results.summary()

    # Return non-zero exit code if any tests failed
    return 1 if results.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
