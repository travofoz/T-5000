# Agent System - Tests

This directory contains automated tests for the multi-agent system project. Maintaining good test coverage is crucial, especially given the complexity and potential risks associated with agent actions.

## Structure

Tests are organized into subdirectories mirroring the `agent_system` package structure where appropriate:

*   `tests/core/`: Tests for base agent logic, controller, data types, etc. (Currently missing)
*   `tests/llm_providers/`: Tests for individual LLM provider implementations (mocking API calls). (Currently missing)
*   `tests/tools/`: Tests for specific tool functions.
    *   `test_filesystem.py`: Example tests for filesystem tools.
*   `tests/agents/`: Tests for specialized agent behaviors (mocking LLM responses and tool executions). (Currently missing)
*   `tests/config/`: Tests for configuration loading and schema handling. (Currently missing)
*   `tests/web/`: Tests for the Flask web application routes and responses.
    *   `test_web_app.py`: Example tests for web API endpoints using `pytest-flask`.

## Running Tests

1.  **Setup:** Ensure all project dependencies, **including testing frameworks** listed in `requirements.txt` (`pytest`, `pytest-flask`, `pytest-asyncio`, `pytest-mock`), are installed in your virtual environment.
2.  **Execution:** Navigate to the project root directory (`agent_system_project/`) in your terminal. Run `pytest`:
    ```bash
    pytest
    ```
    Pytest will automatically discover and run tests found in files named `test_*.py` or `*_test.py`.

## Testing Strategy

*   **Unit Tests:** Focus on testing individual functions and classes in isolation. Use mocking (`unittest.mock` or `pytest-mock`) extensively to isolate dependencies like external API calls (LLM providers, external services used by tools) and filesystem interactions (where appropriate).
*   **Integration Tests:** Test the interaction between different components (e.g., agent calling a tool, controller delegating to a specialist). These may require more setup and potentially limited live interactions (e.g., testing against a local Ollama instance or using carefully sandboxed external commands).
*   **Web Tests:** Use `pytest-flask` to test Flask routes, request handling, response codes, JSON payloads, and session management. Mock the agent execution layer (`ApplicationContext` or specific agent `run` methods) to focus tests on the web application logic itself.
*   **Async Testing:** Use `pytest-asyncio` to correctly handle testing `async` functions and coroutines used throughout the agent system. Mark async test functions with `@pytest.mark.asyncio`.

## Current Status

Test coverage is currently **very low**. The existing files (`test_filesystem.py`, `test_web_app.py`) provide basic examples but need significant expansion to cover more tools, agents, providers, and core logic. Adding comprehensive tests is a high priority for future development to ensure reliability and prevent regressions.
