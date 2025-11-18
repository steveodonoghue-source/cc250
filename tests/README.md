# AutoGen v0.4 Ultimate Platform - Test Suite

Comprehensive testing framework covering integration tests, E2E tests, and negative/resilience tests.

## Test Structure

```
tests/
├── conftest.py              # Pytest fixtures and mocks
├── test_integration.py      # Integration tests (agent communication, tools)
├── test_e2e.py             # End-to-end tests (Playwright UI testing)
├── test_negative.py        # Negative tests (error handling, edge cases)
└── README.md               # This file
```

## Installation

Install test dependencies:

```bash
pip install --user pytest pytest-asyncio pytest-mock playwright pytest-playwright
```

Install Playwright browsers (required for E2E tests):

```bash
playwright install
```

## Running Tests

### All Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=streamlit_app --cov-report=html
```

### Integration Tests Only

```bash
pytest tests/test_integration.py -v
```

**What it tests:**
- Agent-to-agent handoffs (Planner → Coder → Reviewer)
- Tool execution flows (RQ distributed execution)
- Skill generation loop (SkillGenerator → Reviewer → FileHandler)
- ChromaDB integration (document ingestion and retrieval)
- Cost tracking functionality
- Pydantic schema validation

**All external services mocked:**
- Gemini API (OpenAIChatCompletionClient)
- ChromaDB (vector database)
- Redis Queue (distributed execution)

### End-to-End Tests Only

```bash
pytest tests/test_e2e.py -v -m e2e
```

**What it tests:**
- Complete user journeys through Streamlit UI
- Chat interface interaction
- File upload (multimodal)
- Cost monitoring display
- Regression testing UI
- State persistence

**Requirements:**
- Streamlit server auto-starts during tests
- Playwright browser automation
- Tests run in headless browser by default

**Run with visible browser:**

```bash
pytest tests/test_e2e.py -v -m e2e --headed
```

### Negative/Resilience Tests Only

```bash
pytest tests/test_negative.py -v
```

**What it tests:**
- Code execution failures (runtime errors, syntax errors)
- Invalid inputs (SQL injection, XSS, oversized files)
- Service failures (Redis down, ChromaDB unavailable)
- Schema validation failures
- Concurrent access
- Security (path traversal, code injection)
- Edge cases (Unicode, special characters)

## Test Markers

Tests are organized with pytest markers:

```bash
# Run only fast tests (skip slow E2E)
pytest tests/ -v -m "not slow"

# Run only E2E tests
pytest tests/ -v -m "e2e"

# Run specific test class
pytest tests/test_integration.py::TestAgentHandoff -v

# Run specific test
pytest tests/test_integration.py::TestAgentHandoff::test_planner_to_coder_handoff -v
```

## Mocking Strategy

### External Services Mocked

1. **Gemini API (LLM)**
   - Mock: `mock_gemini_client` fixture
   - Returns deterministic responses
   - No API costs during testing

2. **ChromaDB (Vector Database)**
   - Mock: `mock_chroma_client`, `mock_chroma_collection`
   - Simulates document storage and retrieval
   - No actual vector database needed

3. **Redis Queue (RQ)**
   - Mock: `mock_rq_queue`, `mock_rq_job`
   - Simulates job enqueueing and results
   - No Redis server needed for unit/integration tests

4. **Streamlit Session State**
   - Mock: `mock_streamlit_session`
   - Simulates session state dictionary
   - Tests state management logic

### Fixtures Available

See `conftest.py` for complete list:

- `mock_gemini_client` - Mocked LLM client
- `mock_chroma_client` - Mocked ChromaDB
- `mock_rq_queue` - Mocked Redis Queue
- `mock_streamlit_session` - Mocked session state
- `mock_planner_agent`, `mock_coder_agent`, etc. - Mocked agents
- `mock_team` - Mocked SelectorGroupChat
- `temp_test_dir` - Temporary directory for file operations
- `sample_task_plan`, `sample_code_review`, etc. - Sample data

## Configuration

### pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    e2e: End-to-end tests with Playwright
    slow: Slow-running tests
    integration: Integration tests
asyncio_mode = auto
```

### Environment Variables

Set test environment variables in `.env` or export:

```bash
export GEMINI_API_KEY=test_api_key_12345
export GOOGLE_API_KEY=test_api_key_12345
```

(Tests use mocked clients, so actual API keys not needed)

## Writing New Tests

### Integration Test Template

```python
@pytest.mark.asyncio
async def test_my_feature(mock_gemini_client, mock_streamlit_session):
    """Test description."""
    # Arrange
    # Set up mocks and data

    # Act
    # Execute the feature

    # Assert
    # Verify expected behavior
```

### E2E Test Template

```python
@pytest.mark.e2e
def test_my_ui_feature(page: Page, streamlit_server):
    """Test description."""
    # Arrange
    app = StreamlitAppPage(page)
    app.navigate(streamlit_server)

    # Act
    # Interact with UI

    # Assert
    # Verify UI state
```

### Negative Test Template

```python
def test_my_error_handling():
    """Test description."""
    # Arrange
    # Set up error condition

    # Act
    # Trigger error

    # Assert
    # Verify graceful handling
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install
      - name: Run tests
        run: |
          pytest tests/ -v --cov=streamlit_app
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Troubleshooting

### Import Errors

If you get import errors:

```bash
# Add project root to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/ -v
```

### Playwright Issues

```bash
# Reinstall browsers
playwright install --force

# Check installation
playwright --version
```

### Async Test Issues

If async tests fail:

```bash
# Install pytest-asyncio
pip install pytest-asyncio

# Check pytest.ini has asyncio_mode = auto
```

### Streamlit Server Issues (E2E)

```bash
# Kill any running Streamlit processes
pkill -f streamlit

# Run E2E tests with more wait time
pytest tests/test_e2e.py -v --timeout=60
```

## Coverage Report

Generate HTML coverage report:

```bash
pytest tests/ --cov=streamlit_app --cov-report=html

# Open in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Test Metrics

Current test coverage (update after running tests):

- **Integration Tests:** 45 test cases
- **E2E Tests:** 15 test cases (some skipped pending UI implementation)
- **Negative Tests:** 35 test cases
- **Total:** ~95 test cases
- **Coverage:** Target 80%+

## Best Practices

1. **Keep tests isolated** - Each test should be independent
2. **Use fixtures** - Reuse setup code via conftest.py
3. **Mock external services** - Don't hit real APIs in tests
4. **Test both happy and sad paths** - Cover success and failure
5. **Use descriptive names** - Test name should describe what it tests
6. **Keep tests fast** - Use marks for slow tests
7. **Assert specific values** - Avoid generic assertions

## Known Limitations

1. Some E2E tests are skipped (marked with `@pytest.mark.skip`) because:
   - File upload UI not yet implemented
   - Baseline management UI not yet implemented

2. Actual Gemini API not called in tests (all mocked)

3. Redis server not required for integration tests (mocked)

4. Full Streamlit session persistence not tested (requires real Streamlit server)

## Future Enhancements

- [ ] Add performance benchmarking tests
- [ ] Add load testing for concurrent users
- [ ] Add visual regression testing (screenshot comparison)
- [ ] Add accessibility testing (WCAG compliance)
- [ ] Add mutation testing (verify test quality)
- [ ] Add property-based testing (Hypothesis)

## Support

For issues or questions:
- Check test output for error messages
- Review conftest.py for available fixtures
- Consult pytest documentation: https://docs.pytest.org/
- Consult Playwright documentation: https://playwright.dev/python/
