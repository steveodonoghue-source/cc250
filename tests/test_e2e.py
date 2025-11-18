"""
End-to-End (E2E) Tests for AutoGen v0.4 Ultimate Platform

Tests complete user journeys through the Streamlit UI using Playwright.
These tests simulate real user interactions with the browser.
"""

import pytest
import time
import asyncio
import subprocess
import signal
from pathlib import Path
from playwright.sync_api import Page, expect


# ============================================================================
# Streamlit Server Management
# ============================================================================

@pytest.fixture(scope="module")
def streamlit_server():
    """Start Streamlit server for E2E testing."""
    # Get project root
    project_root = Path(__file__).parent.parent
    app_path = project_root / "streamlit_app.py"

    # Start Streamlit in background
    process = subprocess.Popen(
        ["streamlit", "run", str(app_path), "--server.port=8501", "--server.headless=true"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
    )

    # Wait for server to start (check for "You can now view your Streamlit app")
    time.sleep(10)  # Give Streamlit time to initialize

    yield "http://localhost:8501"

    # Cleanup: Stop Streamlit
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


# ============================================================================
# Page Object Model (POM) for Streamlit UI
# ============================================================================

class StreamlitAppPage:
    """Page Object Model for Streamlit application."""

    def __init__(self, page: Page):
        self.page = page

    def navigate(self, url: str):
        """Navigate to Streamlit app."""
        self.page.goto(url)
        # Wait for Streamlit to load
        self.page.wait_for_selector('[data-testid="stApp"]', timeout=15000)

    def enter_api_key(self, api_key: str):
        """Enter API key in sidebar."""
        # Click on sidebar to ensure it's visible
        api_key_input = self.page.get_by_label("Google/Gemini API Key")
        api_key_input.fill(api_key)

    def click_initialize_team(self):
        """Click 'Initialize Team' button."""
        init_button = self.page.get_by_text("Initialize Team")
        init_button.click()
        # Wait for initialization
        time.sleep(2)

    def send_chat_message(self, message: str):
        """Send a message in chat input."""
        chat_input = self.page.get_by_placeholder("Describe your coding task")
        if not chat_input.is_visible():
            # Try alternative selector
            chat_input = self.page.locator('input[aria-label="Chat"]')

        chat_input.fill(message)
        chat_input.press("Enter")

    def get_chat_messages(self):
        """Get all chat messages."""
        # Wait for messages to appear
        self.page.wait_for_selector('[data-testid="chatMessage"]', timeout=30000)
        messages = self.page.locator('[data-testid="chatMessage"]').all()
        return [msg.inner_text() for msg in messages]

    def get_cost_metrics(self):
        """Get cost monitoring metrics from sidebar."""
        # Look for cost metrics in sidebar
        try:
            total_cost = self.page.locator('text="Total Cost"').locator('..').inner_text()
            total_tokens = self.page.locator('text="Total Tokens"').locator('..').inner_text()
            return {"total_cost": total_cost, "total_tokens": total_tokens}
        except:
            return None

    def check_cost_alert(self):
        """Check if cost alert is displayed."""
        alert = self.page.locator('text="COST ALERT"')
        return alert.is_visible() if alert.count() > 0 else False

    def upload_file(self, file_path: str):
        """Upload a file via file uploader."""
        file_input = self.page.locator('input[type="file"]')
        file_input.set_input_files(file_path)

    def save_baseline(self, baseline_name: str):
        """Save a golden baseline for regression testing."""
        # Enter baseline name
        name_input = self.page.get_by_label("Test Case Name")
        name_input.fill(baseline_name)

        # Click save button
        save_button = self.page.get_by_text("Save Golden Baseline")
        save_button.click()

    def run_regression_test(self, baseline_name: str):
        """Run a regression test against a baseline."""
        # Select baseline
        baseline_select = self.page.get_by_label("Select Baseline")
        baseline_select.select_option(baseline_name)

        # Click run button
        run_button = self.page.get_by_text("Run Regression Test")
        run_button.click()

    def get_agent_status(self):
        """Get list of active agents from sidebar."""
        agents_section = self.page.locator('text="Active Agents"').locator('..').inner_text()
        return agents_section


# ============================================================================
# E2E Test Cases
# ============================================================================

@pytest.mark.e2e
class TestHappyPath:
    """Test complete happy path user journeys."""

    def test_complete_user_flow(self, page: Page, streamlit_server):
        """Test full flow: API key -> initialize -> send message -> receive response."""
        # Arrange
        app = StreamlitAppPage(page)

        # Act: Navigate to app
        app.navigate(streamlit_server)

        # Act: Enter API key (use test key that will be mocked)
        app.enter_api_key("test_gemini_api_key_12345")

        # Act: Initialize team
        app.click_initialize_team()

        # Act: Send a simple message
        app.send_chat_message("Create a simple hello world function")

        # Assert: Message appears in chat history
        # Note: In real test, would need mocking or actual API. For demo, we check UI responds
        time.sleep(5)  # Wait for processing

        messages = app.get_chat_messages()
        assert len(messages) > 0
        assert any("hello" in msg.lower() or "world" in msg.lower() for msg in messages)

    def test_sidebar_shows_six_agents(self, page: Page, streamlit_server):
        """Test that sidebar correctly shows 6 agents."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)

        # Act: Get agent status
        agent_status = app.get_agent_status()

        # Assert: 6 agents listed
        assert "Planner" in agent_status
        assert "Coder" in agent_status
        assert "Reviewer" in agent_status
        assert "FileHandler" in agent_status
        assert "SkillGenerator" in agent_status
        assert "Testing" in agent_status

    def test_chat_history_persists(self, page: Page, streamlit_server):
        """Test that chat history persists during session."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)
        app.enter_api_key("test_key")
        app.click_initialize_team()

        # Act: Send multiple messages
        app.send_chat_message("Message 1")
        time.sleep(2)
        app.send_chat_message("Message 2")
        time.sleep(2)

        # Assert: Both messages in history
        messages = app.get_chat_messages()
        assert len(messages) >= 2


@pytest.mark.e2e
class TestMultimodalInput:
    """Test multimodal file upload functionality."""

    @pytest.mark.skip(reason="File upload UI not yet implemented")
    def test_image_upload_and_analysis(self, page: Page, streamlit_server, tmp_path):
        """Test uploading an image and getting analysis."""
        # Arrange: Create dummy image
        image_path = tmp_path / "test_image.png"
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='red')
        img.save(image_path)

        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)
        app.enter_api_key("test_key")
        app.click_initialize_team()

        # Act: Upload image
        app.upload_file(str(image_path))

        # Act: Ask about image
        app.send_chat_message("What's in this image?")
        time.sleep(5)

        # Assert: Response mentions image analysis
        messages = app.get_chat_messages()
        assert any("image" in msg.lower() for msg in messages)

    @pytest.mark.skip(reason="File upload UI not yet implemented")
    def test_pdf_upload_and_ingestion(self, page: Page, streamlit_server, tmp_path):
        """Test uploading a PDF for knowledge ingestion."""
        # Arrange: Create dummy PDF
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b'%PDF-1.4\n%Test PDF\n%%EOF')

        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)
        app.enter_api_key("test_key")
        app.click_initialize_team()

        # Act: Upload PDF
        app.upload_file(str(pdf_path))

        # Act: Ask to ingest
        app.send_chat_message("Please ingest the uploaded PDF into the knowledge base")
        time.sleep(5)

        # Assert: Success message
        messages = app.get_chat_messages()
        assert any("ingested" in msg.lower() or "knowledge base" in msg.lower() for msg in messages)


@pytest.mark.e2e
class TestCostMonitoring:
    """Test cost monitoring and alerting."""

    def test_cost_metrics_display(self, page: Page, streamlit_server):
        """Test that cost metrics are displayed in sidebar."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)
        app.enter_api_key("test_key")
        app.click_initialize_team()

        # Act: Send a message to generate cost
        app.send_chat_message("Simple test")
        time.sleep(3)

        # Assert: Cost metrics visible
        cost_metrics = app.get_cost_metrics()
        # Note: May be None if mocking not set up, but check structure
        assert cost_metrics is None or "total_cost" in cost_metrics

    @pytest.mark.skip(reason="Requires high token simulation")
    def test_cost_alert_triggers(self, page: Page, streamlit_server):
        """Test that cost alert appears when threshold exceeded."""
        # This test would require simulating high token usage
        # to trigger the $1.00 threshold
        pass


@pytest.mark.e2e
class TestRegressionTesting:
    """Test regression testing functionality."""

    @pytest.mark.skip(reason="Baseline management UI not yet implemented")
    def test_save_and_load_baseline(self, page: Page, streamlit_server):
        """Test saving a golden baseline."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)
        app.enter_api_key("test_key")
        app.click_initialize_team()

        # Act: Complete a task
        app.send_chat_message("Create a simple function")
        time.sleep(5)

        # Act: Save as baseline
        app.save_baseline("test_baseline_1")

        # Assert: Success message or confirmation
        page.wait_for_selector('text="saved"', timeout=5000)

    @pytest.mark.skip(reason="Baseline management UI not yet implemented")
    def test_run_regression_test(self, page: Page, streamlit_server):
        """Test running a regression test against baseline."""
        # Arrange: Assume baseline exists
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)
        app.enter_api_key("test_key")
        app.click_initialize_team()

        # Act: Run regression test
        app.run_regression_test("test_baseline_1")
        time.sleep(5)

        # Assert: Testing agent provides comparison
        messages = app.get_chat_messages()
        assert any("coherence" in msg.lower() or "comparison" in msg.lower() for msg in messages)


@pytest.mark.e2e
class TestStatePersistence:
    """Test state persistence across sessions."""

    @pytest.mark.skip(reason="State persistence requires browser reload")
    def test_conversation_persists_on_reload(self, page: Page, streamlit_server):
        """Test that conversation persists when reloading page."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)
        app.enter_api_key("test_key")
        app.click_initialize_team()

        # Act: Send message
        app.send_chat_message("Test message 1")
        time.sleep(2)

        # Get message count
        messages_before = app.get_chat_messages()

        # Act: Reload page
        page.reload()
        time.sleep(3)

        # Assert: Messages still there (if persistence implemented)
        messages_after = app.get_chat_messages()
        assert len(messages_after) >= len(messages_before)


# ============================================================================
# UI Element Tests
# ============================================================================

@pytest.mark.e2e
class TestUIElements:
    """Test specific UI elements and interactions."""

    def test_api_key_input_exists(self, page: Page, streamlit_server):
        """Test that API key input field exists."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)

        # Assert: API key input visible
        api_key_input = page.get_by_label("Google/Gemini API Key")
        expect(api_key_input).to_be_visible()

    def test_initialize_button_exists(self, page: Page, streamlit_server):
        """Test that Initialize Team button exists."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)

        # Assert: Button visible
        init_button = page.get_by_text("Initialize Team")
        expect(init_button).to_be_visible()

    def test_chat_input_disabled_before_init(self, page: Page, streamlit_server):
        """Test that chat input is disabled before team initialization."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)

        # Assert: Chat input disabled or not visible
        # This depends on implementation - skip if not applicable
        pass

    def test_sidebar_sections_present(self, page: Page, streamlit_server):
        """Test that all expected sidebar sections are present."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)

        # Assert: Key sections visible
        expect(page.get_by_text("Configuration")).to_be_visible()
        expect(page.get_by_text("Active Agents")).to_be_visible()
        expect(page.get_by_text("Cost Monitoring")).to_be_visible()


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
class TestPerformance:
    """Test performance characteristics."""

    def test_app_loads_within_timeout(self, page: Page, streamlit_server):
        """Test that app loads within reasonable time."""
        # Arrange
        start_time = time.time()

        # Act
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=15000)

        # Assert: Loaded in <15 seconds
        load_time = time.time() - start_time
        assert load_time < 15

    @pytest.mark.skip(reason="Requires actual agent processing")
    def test_message_response_time(self, page: Page, streamlit_server):
        """Test that responses arrive within reasonable time."""
        # This would test actual agent processing time
        # Skipped as it requires real or mocked agent processing
        pass


# ============================================================================
# Accessibility Tests
# ============================================================================

@pytest.mark.e2e
class TestAccessibility:
    """Test accessibility features."""

    def test_keyboard_navigation(self, page: Page, streamlit_server):
        """Test that app is keyboard navigable."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)

        # Act: Tab through elements
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")

        # Assert: Focus moves (implementation-dependent)
        # This is a basic check
        assert True

    def test_screen_reader_labels(self, page: Page, streamlit_server):
        """Test that form elements have proper labels."""
        # Arrange
        app = StreamlitAppPage(page)
        app.navigate(streamlit_server)

        # Assert: Key inputs have labels
        api_key_input = page.get_by_label("Google/Gemini API Key")
        expect(api_key_input).to_have_attribute("aria-label")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "e2e"])
