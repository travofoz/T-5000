Okay, here is a prompt designed for initiating the next version (V2) of the refactoring, incorporating the review and suggested architectural improvements.

---

**Prompt for Agent System Refactoring - V2**

**You are an expert Python developer specializing in large-scale refactoring, asynchronous programming (`asyncio`), agent systems, web application architecture (Flask), dependency injection, and robust application design.**

**Context:**
You are given the complete Python code for a multi-agent system project (`agent_system_project`) developed in a previous session (V1). This system features multiple LLM providers, dynamically registered tools, specialized agents, session-based state persistence, an interactive CLI, a non-interactive CLI, a Flask web UI, basic scripts, and initial tests.

A critical review of V1 identified key strengths (modularity, async, dynamic tools, abstraction) but also significant areas for architectural improvement, primarily:

1.  **Duplicated Initialization Logic:** The code for initializing LLM providers (with caching) and instantiating agents (`ControllerAgent`, specialists) is repeated across multiple entry points (`cli/main_interactive.py`, `cli/main_non_interactive.py`, `web/routes.py`, `scripts/run_cron_task.py`). This violates DRY principles and complicates maintenance.
2.  **Fragile Web State Management:** The Flask web UI stores active agent *instances* in a global in-memory dictionary tied to Flask sessions (`active_sessions` in `web/routes.py`). This approach is not scalable or safe for multi-process web server deployments (e.g., gunicorn, uWSGI), leading to inconsistent state or lost sessions.
3.  **Limited Orchestration:** The `Orchestrator` class in `core/interaction.py` provides basic concurrent task execution but is not fully utilized and lacks features for complex inter-agent workflows. (Optional V2 enhancement).
4.  **Low Test Coverage:** Existing tests are minimal and need expansion.

**Task:**
Your primary task is to refactor the V1 project code to address the architectural weaknesses identified, focusing mainly on centralizing initialization logic and improving web state management. You must also implement previously postponed features like MCP context passing for Anthropic and potentially enhance the Orchestrator.

**Inputs:**

1.  The complete V1 file hierarchy and code content (as generated previously).
2.  The target project hierarchy (can be modified based on refactoring needs):
    ```
    agent_system_project/
    ├── agent_system/
    │   ├── __init__.py
    │   ├── app_context.py  # <-- NEW: Central Application Context / Service
    │   ├── core/
    │   │   ├── __init__.py
    │   │   ├── agent.py
    │   │   ├── controller.py
    │   │   ├── datatypes.py
    │   │   └── interaction.py # Orchestrator lives here
    │   ├── llm_providers/
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── mcp_client.py # <-- Optional NEW: If implementing MCP Client
    │   │   ├── gemini.py
    │   │   ├── openai.py
    │   │   ├── anthropic.py
    │   │   └── ollama.py
    │   ├── tools/
    │   │   ├── __init__.py
    │   │   ├── tool_utils.py
    │   │   ├── filesystem.py # Needs change_directory tool
    │   │   ├── ... (other tool files) ...
    │   ├── agents/
    │   │   ├── __init__.py
    │   │   ├── ... (agent files) ...
    │   └── config/
    │       ├── __init__.py
    │       ├── settings.py
    │       └── schemas.py
    ├── cli/
    │   ├── __init__.py
    │   ├── main_interactive.py # To be simplified
    │   └── main_non_interactive.py # To be simplified
    ├── web/
    │   ├── __init__.py         # Flask app init
    │   └── routes.py         # To be simplified, state logic removed/changed
    │   # Optional: Add background task setup (e.g., celery_worker.py) if choosing that route
    ├── templates/
    │   └── index.html
    ├── scripts/
    │   ├── __init__.py
    │   └── run_cron_task.py # To be simplified
    ├── tests/
    │   ├── __init__.py
    │   ├── # ... existing test files ...
    │   └── test_app_context.py # <-- NEW: Test the central context
    ├── agent_state/
    │   └── .gitkeep
    ├── .env.example
    ├── requirements.txt # May need updates (e.g., Flask-Session, Celery/Redis)
    └── README.md        # Needs updates reflecting changes
    ```

**Refactoring Strategy & Requirements:**

1.  **Centralized Initialization (`app_context.py`):**
    *   Create a new file `agent_system/app_context.py`.
    *   Define an `ApplicationContext` class (or similar name).
    *   Move the `provider_cache` dictionary and the `_get_provider` (or `get_or_create_cached_provider`) logic into this class.
    *   Add a method like `async def get_agent(self, agent_name: str, session_id: Optional[str] = None) -> BaseAgent:` to this class. This method will handle:
        *   Getting the agent's configuration from `settings.py`.
        *   Calling the internal provider retrieval method.
        *   Instantiating the correct agent class (using a map or dynamic import) with the provider and `session_id`.
    *   Add a method like `async def get_controller(self, session_id: Optional[str] = None) -> ControllerAgent:` which internally calls `get_agent` for specialists and instantiates the `ControllerAgent`. Consider caching controller instances per session ID within the context *if appropriate for the chosen web state strategy*.
    *   Add an `async def close_providers(self):` method to close all cached provider connections.
2.  **Simplify Entry Points:**
    *   Modify `cli/main_interactive.py`, `cli/main_non_interactive.py`, `web/routes.py`, and `scripts/run_cron_task.py`.
    *   At the start of their main async functions, instantiate the `ApplicationContext` *once*.
    *   Replace the duplicated agent/provider initialization logic in each file with calls to `app_context.get_controller(...)` or `app_context.get_agent(...)`.
    *   Ensure `app_context.close_providers()` is called appropriately on exit/shutdown in each entry point.
3.  **Refactor Web State Management (Choose ONE strategy):**
    *   **Strategy A (Persistent Sessions):**
        *   Use `Flask-Session` with a persistent backend (e.g., filesystem, Redis - update `requirements.txt`). Configure it in `web/__init__.py`.
        *   **Remove** the in-memory `active_sessions` dictionary from `web/routes.py`.
        *   In `web/routes.py`, on each request:
            *   Get the Flask `session_id`.
            *   Use `app_context.get_controller(session_id)` (or `get_agent`) to get a *newly instantiated* agent instance for that request, passing the `session_id`.
            *   The agent's `run` method (with `load_state=True, save_state=True`) will handle loading/saving history from the session-specific file (`agent_state/session_{id}_...`). No agent *instances* are stored between requests.
    *   **Strategy B (Background Tasks - More Complex):**
        *   Integrate a task queue (Celery/Redis, Dramatiq, etc. - update `requirements.txt`).
        *   In `web/routes.py`, on receiving a prompt:
            *   Generate a unique task ID.
            *   Dispatch a background task to run the agent (passing the prompt, session ID, agent name).
            *   Immediately return a response to the user indicating the task is processing (e.g., with the task ID).
            *   The background worker instantiates the `ApplicationContext` and uses `get_controller`/`get_agent` to run the task, saving state to the session file.
            *   Implement separate endpoints/mechanisms (e.g., polling, WebSockets) for the frontend to retrieve the results later using the task ID (results might be stored temporarily alongside the session state file or in Redis/DB). This is significantly more complex.
    *   *(Decision Required)* **Choose Strategy A for this V2 unless explicitly instructed otherwise, as it's a more direct evolution of the current state persistence.**
4.  **Implement MCP Context Passing:**
    *   Add `self.current_working_directory` (defaulting to `Path.cwd()`) and `self.os_info` state to `BaseAgent` initialization.
    *   Implement `_load_state` and `_save_state` updates in `BaseAgent` to persist/load `current_working_directory` (as string).
    *   Create the `change_directory` tool in `tools/filesystem.py` that updates `self.current_working_directory` but does *not* call `os.chdir`. Decorate it with `@register_tool`. Add it to relevant agents' default tools (e.g., CodingAgent, SysAdminAgent).
    *   Modify tools using `cwd` or `working_dir` (e.g., `list_files`, `run_shell_command`, `git_command`, etc. in their respective `.py` files) and/or the `_execute_tool` method in `BaseAgent` to default to using `self.current_working_directory` if no explicit `working_dir`/`cwd` argument is provided by the LLM tool call.
    *   Update the `LLMProvider.send_message` signature in the ABC and all implementations to accept `mcp_context: Optional[Dict[str, Any]] = None` and `mcp_metadata: Optional[Dict[str, Any]] = None`.
    *   In `BaseAgent.run`, gather relevant context (CWD, OS info, recent tools, token status, session ID) into `mcp_context` and `mcp_metadata` dictionaries.
    *   Pass these dictionaries to `self.llm_provider.send_message`.
    *   Update `AnthropicProvider.send_message` to use the received dictionaries for the `context` and `metadata` API parameters. Other providers will ignore them.
5.  **Enhance Orchestrator (Optional):**
    *   Integrate the `Orchestrator` instance into the `ApplicationContext`.
    *   Refactor the `run_concurrent_tasks` example usage in `cli/main_interactive.py` or `web/routes.py` to use the orchestrator instance from the context.
6.  **Testing:**
    *   Add basic tests for the `ApplicationContext` class (`tests/test_app_context.py`).
    *   Update web tests (`tests/web/test_web_app.py`) to work with the chosen web state strategy (e.g., mocking session data if using Strategy A, or testing task submission if Strategy B).
    *   *(Goal)* Aim for slightly increased test coverage, though full coverage is not expected.
7.  **Documentation:** Update `README.md` to reflect the new architecture (ApplicationContext, web state strategy) and any added requirements (e.g., Flask-Session, Redis).

**Output Format:**
Follow the previous session's format:
*   List the full planned directory structure (reflecting changes like `app_context.py`).
*   Generate the content for **each modified or new file** separately.
*   State the **full file path** before each file's content.
*   Write "**--- PAUSE ---**" after **each file's** content.
*   Wait for confirmation ("ok", "next", "proceed") before the next file.
*   Proceed in a logical order (e.g., `app_context.py`, update `BaseAgent`, update tools, update providers, update entry points, update tests, update docs).

Start the V2 refactoring now, beginning with the planned directory structure.
