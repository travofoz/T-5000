# Agent System - Web Interface

This directory contains the Flask web application providing a user interface for interacting with the multi-agent system.

## Files

*   `__init__.py`: Initializes the Flask application (`app`) instance, configures settings (like `SECRET_KEY` for sessions), and potentially sets up extensions (like `Flask-Session`). Imports the routes.
*   `routes.py`: Defines the Flask routes (URL endpoints):
    *   `/`: Renders the main HTML chat interface (`templates/index.html`).
    *   `/api/prompt`: Handles POST requests with user prompts (as JSON), interacts with the `ControllerAgent` for the user's session, and returns the agent's response as JSON.
    *   *(V2 Idea - Currently On Hold)* `/api/parallel`: Handles POST requests to run multiple independent agent tasks concurrently.

## Running the Web UI

1.  **Setup:** Ensure all project dependencies from `requirements.txt` are installed, and the `.env` file is configured.
2.  **Development Server:** Use Flask's built-in development server (suitable for testing, not production):
    ```bash
    # From the project root directory (agent_system_project/)
    flask --app web run --debug
    ```
    *(Note: `--app web` tells Flask to look for the `app` instance inside the `web` package. The `--debug` flag enables debug mode, providing auto-reloading and detailed error pages.)*
    Access the UI in your browser, typically at `http://127.0.0.1:5000`.
3.  **Production Server:** For deployment, use a production-grade WSGI server like Gunicorn or uWSGI.
    ```bash
    # Example using Gunicorn (install with pip install gunicorn)
    gunicorn --workers 4 --bind 0.0.0.0:5000 "web:app"
    ```
    *(This runs 4 worker processes, binding to port 5000 on all interfaces. The `"web:app"` part tells Gunicorn where to find the Flask `app` instance.)*

## State Management

*   The web UI uses Flask sessions to maintain conversation state across requests for different users.
*   A unique session ID is generated for each browser session.
*   The agent system (specifically `BaseAgent`) uses this session ID to store and retrieve conversation history in separate files within the `agent_state/` directory (e.g., `session_XYZ_ControllerAgent_history.json`).
*   **Important:** The current implementation stores agent instances per session *in memory* within `routes.py`. This is **not suitable** for production environments using multiple worker processes. V2 aims to refactor this to use persistent session storage for agent *state* instead of instances, or move execution to background tasks.

## Templates

*   HTML templates are located in the top-level `templates/` directory (e.g., `templates/index.html`).
