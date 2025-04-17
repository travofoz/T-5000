import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock # Use AsyncMock for async functions

# Import the Flask app instance from the web package
try:
     from web import app as flask_app # If running tests with `python -m pytest` from root
except ImportError:
     # Adjust path if needed when running differently
     import sys
     from pathlib import Path
     PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
     sys.path.insert(0, str(PROJECT_ROOT))
     from web import app as flask_app

# --- Pytest Fixtures ---

@pytest.fixture(scope='module')
def app():
    """Create and configure a new Flask app instance for testing."""
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "testing-secret-key",
        "WTF_CSRF_ENABLED": False, # Disable CSRF protection for simpler API testing
    })
    yield flask_app
    # Cleanup if needed after tests run

@pytest.fixture()
def client(app):
    """Provides a test client context for making requests to the app."""
    return app.test_client()

# --- Test Cases ---

@pytest.mark.asyncio
async def test_index_page_loads(client):
    """Test GET / - checks if the index page loads successfully."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Agent System Web UI" in response.data # Verify title or key content

@pytest.mark.asyncio
async def test_prompt_api_no_json(client):
    """Test POST /api/prompt without sending JSON data."""
    response = client.post('/api/prompt')
    assert response.status_code == 400
    assert b"Request must be JSON" in response.data

@pytest.mark.asyncio
async def test_prompt_api_missing_prompt(client):
    """Test POST /api/prompt with JSON data but missing the 'prompt' field."""
    response = client.post('/api/prompt', json={})
    assert response.status_code == 400
    assert b"Missing or invalid 'prompt'" in response.data

@pytest.mark.asyncio
async def test_prompt_api_empty_prompt(client):
    """Test POST /api/prompt with an empty or whitespace-only 'prompt' value."""
    response = client.post('/api/prompt', json={"prompt": "  "})
    assert response.status_code == 400
    assert b"Missing, invalid, or empty 'prompt'" in response.data

@pytest.mark.asyncio
@patch('web.routes.get_session_controller') # Mock agent initialization/retrieval
async def test_prompt_api_success(mock_get_controller, client):
    """Test a successful POST to /api/prompt with valid input."""
    # Setup Mock: Simulate the ControllerAgent and its run method
    mock_controller_instance = AsyncMock()
    mock_run_response = "Test response from mocked agent"
    mock_controller_instance.run = AsyncMock(return_value=mock_run_response)
    mock_get_controller.return_value = mock_controller_instance # Make the getter return our mock

    # Make the request
    user_prompt = "Hello agent!"
    response = client.post('/api/prompt', json={"prompt": user_prompt})

    # Assertions
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data is not None
    assert "response" in json_data
    assert json_data["response"] == mock_run_response

    # Verify mocks were called correctly
    mock_get_controller.assert_called_once()
    mock_controller_instance.run.assert_awaited_once_with(user_prompt, load_state=True, save_state=True)

@pytest.mark.asyncio
@patch('web.routes.get_session_controller')
async def test_prompt_api_agent_exception(mock_get_controller, client):
    """Test POST /api/prompt when the underlying agent 'run' method raises an exception."""
    # Setup Mock: Simulate an exception during agent execution
    mock_controller_instance = AsyncMock()
    test_exception = Exception("Agent simulation failed!")
    mock_controller_instance.run = AsyncMock(side_effect=test_exception)
    mock_get_controller.return_value = mock_controller_instance

    # Make the request
    user_prompt = "Cause an error"
    response = client.post('/api/prompt', json={"prompt": user_prompt})

    # Assertions: Expect Internal Server Error (500)
    assert response.status_code == 500
    json_data = response.get_json()
    assert json_data is not None
    assert "error" in json_data
    assert "An internal server error occurred" in json_data["error"]
    assert str(test_exception) in json_data["error"] # Check original exception is mentioned

    # Verify mocks were called
    mock_get_controller.assert_called_once()
    mock_controller_instance.run.assert_awaited_once_with(user_prompt, load_state=True, save_state=True)

@pytest.mark.asyncio
async def test_session_persistence_mocked(client):
    """
    Tests if the same session is used across multiple requests by mocking
    the controller retrieval to return the same mock instance.
    """
    # Create a shared mock controller instance for the test duration
    mock_controller_instance_shared = AsyncMock()
    mock_controller_instance_shared.run.side_effect = [
        "Response to first prompt (shared)",
        "Response to second prompt (shared)"
    ]

    # Patch the getter function within the test's scope
    with patch('web.routes.get_session_controller', return_value=mock_controller_instance_shared) as shared_mock_getter:
         # First request using the test client (starts a session)
         response1_shared = client.post('/api/prompt', json={"prompt": "Shared Prompt 1"})
         assert response1_shared.status_code == 200
         assert response1_shared.get_json()["response"] == "Response to first prompt (shared)"

         # Second request using the *same* test client (should reuse the session)
         response2_shared = client.post('/api/prompt', json={"prompt": "Shared Prompt 2"})
         assert response2_shared.status_code == 200
         assert response2_shared.get_json()["response"] == "Response to second prompt (shared)"

         # Assert that the mocked getter function was called for each request
         assert shared_mock_getter.call_count == 2
         # Assert that the *single* shared controller mock's run method was called twice
         assert mock_controller_instance_shared.run.call_count == 2
