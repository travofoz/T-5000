# Agent System Usage Guide

This document provides instructions and examples for using the various interfaces of the multi-agent system.

**🚨 IMPORTANT SAFETY PRECAUTIONS 🚨**

*   **ISOLATED ENVIRONMENT:** Always run this system in a completely isolated environment (like a dedicated VM) where potential data loss, system instability, or security issues are acceptable.
*   **NO PATH SAFETY:** Tools that interact with the filesystem (`read_file`, `edit_file`, `list_files`, `scp_command`, etc.) have **NO restrictions** and can potentially access or modify **ANY** file the executing user has permissions for. Be extremely careful with paths.
*   **HIGH-RISK TOOLS:** Many tools can execute arbitrary code (`run_shell_command`, `python_run_script`), modify system state (`apt_command`, `systemctl_command`), interact with hardware (`esptool_command`), or perform sensitive network actions (`nmap_scan`, `sqlmap_scan`). These are marked as high-risk and require user confirmation by default. Review the `HIGH_RISK_TOOLS` setting in your `.env` file. **Disabling confirmation significantly increases risk.**
*   **API KEYS & COSTS:** Ensure your API keys in `.env` are correct and secure. Be mindful of potential costs associated with LLM API usage, especially with powerful models or long conversations.

## Prerequisites

1.  **Installation:** Follow the setup instructions in `README.md` (clone repo, create venv, `pip install -r requirements.txt`).
2.  **Configuration (`.env`):**
    *   Copy `.env.example` to `.env`.
    *   Fill in required API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
    *   Set `OLLAMA_BASE_URL` if using Ollama locally.
    *   Review and **understand** the `HIGH_RISK_TOOLS` list. Add or remove tools cautiously. Leave empty only if you fully accept the risks of disabling confirmation.
    *   Set a strong, unique `FLASK_SECRET_KEY` if you plan to use the Web UI, especially if exposing it beyond localhost.
3.  **External Tools:** Ensure command-line tools required by specific agent tools (e.g., `git`, `nmap`, `grep`, `ps`, `kill`, `esptool.py`, `openocd`, etc.) are installed and accessible in your system's `PATH`.

## Interaction Methods

There are several ways to interact with the agent system:

1.  [Interactive Command Line (CLI)](#1-interactive-command-line-cli)
2.  [Non-Interactive Command Line (CLI)](#2-non-interactive-command-line-cli)
3.  [Web User Interface (Web UI)](#3-web-user-interface-web-ui)
4.  [Scheduled Tasks / Scripting](#4-scheduled-tasks--scripting)

---

### 1. Interactive Command Line (CLI)

This mode provides a live chat interface where you interact directly with the `ControllerAgent`. The Controller analyzes your requests and delegates them to the appropriate specialist agent. Conversation history is maintained for the duration of the session and saved upon exit.

**How to Run:**

Navigate to the project root (`agent_system_project/`) in your terminal (with your virtual environment activated) and run:

```bash
python -m cli.main_interactive
```

**Interaction Flow:**

1.  The system initializes, loading configuration and setting up agents.
2.  You will see a `User >` prompt.
3.  Type your request for the agent system (e.g., "List files in the current directory", "Write a python script to parse a CSV file", "Check if google.com is reachable").
4.  The `ControllerAgent` receives your prompt.
5.  It decides which specialist agent is best suited (e.g., `SysAdminAgent`, `CodingAgent`, `NetworkAgent`).
6.  It calls the internal `delegate_task` function.
7.  The chosen specialist agent loads its state (history), processes the prompt (potentially calling tools), and generates a response.
8.  If a high-risk tool is needed, you will see a confirmation prompt like:
    ```
    🚨 CONFIRMATION REQUIRED FOR HIGH-RISK TOOL 🚨
    Tool: edit_file
    Arguments:
      file_path: 'my_script.py'
      content: '#!/usr/bin/env python\n\nprint("Hello")\n'
    WARNING: This operation is configured as high-risk ('edit_file' in HIGH_RISK_TOOLS).
    It could have significant consequences (e.g., data loss, system changes, security risks).
    Proceed? (yes/no):
    ```
    Type `yes` to proceed or `no` to cancel that specific tool execution.
9.  The final result from the specialist (or an error message) is displayed prefixed by `Controller Response:`.
10. The `User >` prompt reappears for your next request.

**Special Commands:**

*   `quit` or `exit`: Terminates the interactive session gracefully, saving agent state.
*   `!reload <full.module.path>`: Attempts to reload a specific Python module (e.g., `!reload agent_system.tools.filesystem`). This is useful for development to test changes without restarting the entire application. **Warning:** Reloading can lead to inconsistent states, especially for core modules or agent classes. Use with caution. If a tools module is reloaded, tool discovery is re-run, and agents are updated with the new tool definitions.

**Example Session:**

```
(venv) $ python -m cli.main_interactive
--- Multi-Agent System Interactive CLI ---
--- WARNING: HIGH-RISK OPERATION MODE ---
... (Initialization logs) ...
Initialization complete. Controller Agent ready.
Type your requests, 'quit'/'exit' to stop, or '!reload <module.path>' to reload.

User > List the python files in the current directory.

Controller processing...
INFO - Controller delegating task to 'SysAdminAgent'...
INFO - Agent 'SysAdminAgent' (Session: None) executing tool: find_files (ID: find_files_...) with args: {'name_pattern': '*.py', 'path': '.'}
INFO - Executing Async: find . -maxdepth 5 -name \*.py | CWD: /path/to/agent_system_project | Shell=False
... (tool execution logs) ...
INFO - Agent 'SysAdminAgent' (Session: None) Received LLM response.
--- Agent 'SysAdminAgent' Final Response (Turn 2) ---
Okay, I found the following Python files:```
./web/__init__.py
./web/routes.py
./scripts/run_cron_task.py
./scripts/__init__.py
... (etc) ...
```

Controller Response:
--------------------
Okay, I found the following Python files:
```
./web/__init__.py
./web/routes.py
./scripts/run_cron_task.py
./scripts/__init__.py
... (etc) ...
```
--------------------

User > Create a simple python script named hello.py that prints "Hello from agent!".

Controller processing...
INFO - Controller delegating task to 'CodingAgent'...
INFO - Agent 'CodingAgent' (Session: None) executing tool: edit_file (ID: edit_file_...) with args: {'file_path': 'hello.py', 'content': '#!/usr/bin/env python\n\nprint("Hello from agent!")\n'}

🚨 CONFIRMATION REQUIRED FOR HIGH-RISK TOOL 🚨
Tool: edit_file
Arguments:
  file_path: 'hello.py'
  content: '#!/usr/bin/env python\n\nprint("Hello from agent!")\n'
WARNING: This operation is configured as high-risk ('edit_file' in HIGH_RISK_TOOLS).
It could have significant consequences (e.g., data loss, system changes, security risks).
Proceed? (yes/no): yes
Proceeding...
INFO - User confirmed execution for high-risk tool 'edit_file'.
INFO - Tool 'edit_file' executed by CodingAgent (Session: None) in 0.01s. Result length: 47
... (LLM interaction logs) ...
INFO - --- Agent 'CodingAgent' Final Response (Turn 2) ---
I have created the script `hello.py` with the requested content.

Controller Response:
--------------------
I have created the script `hello.py` with the requested content.
--------------------

User > quit
Exiting agent system...
INFO - Saving state (X messages) for agent 'ControllerAgent' (Session: None) to ...
INFO - Saving state (Y messages) for agent 'CodingAgent' (Session: None) to ...
... (State saving logs for agents used) ...
INFO - Shutting down provider connections...
INFO - Shutdown complete.
(venv) $
```

---

### 2. Non-Interactive Command Line (CLI)

This mode is designed for running a **single task** with a **specific specialist agent** directly from the command line, without going through the `ControllerAgent`. It's useful for automated scripts or testing individual agent capabilities.

**How to Run:**

Navigate to the project root (`agent_system_project/`) and run:

```bash
python -m cli.main_non_interactive --agent <AgentClassName> --task "<Your Task Prompt>" [options]
```

**Required Arguments:**

*   `--agent <AgentClassName>` or `-a <AgentClassName>`: Specifies the exact class name of the agent to use (e.g., `CodingAgent`, `SysAdminAgent`). Use `--help` to see the list of available agents configured in the script.
*   `--task "<Your Task Prompt>"` or `-t "<Your Task Prompt>"`: The prompt containing the task for the specified agent. Enclose in quotes if it contains spaces.

**Optional Arguments:**

*   `--output-file <path>` or `-o <path>`: Write the agent's final response to the specified file instead of printing it to standard output.
*   `--load-state`: If included, the agent will attempt to load its previous history from its default state file (`agent_state/<AgentClassName>_history.json`) before executing the task. **Use with caution** if multiple non-interactive runs target the same agent without session IDs, as state might become inconsistent.
*   `--save-state`: If included, the agent will save its history (including the current task) back to its default state file after execution.

**Interaction Flow:**

1.  The script parses arguments.
2.  It instantiates *only* the specified agent class and its required LLM provider.
3.  If `--load-state` is used, the agent loads history.
4.  The agent processes the `--task` prompt (potentially calling tools, which might trigger confirmation prompts if high-risk and running in an interactive terminal).
5.  The final response is either printed to standard output or written to the file specified by `--output-file`.
6.  The script exits.

**Example Usage:**

```bash
# Run CodingAgent to generate a file, print result to console
(venv) $ python -m cli.main_non_interactive -a CodingAgent -t "Create a python function in 'utils.py' that adds two numbers."

# Run SysAdminAgent to check disk space, save result to a file
(venv) $ python -m cli.main_non_interactive -a SysAdminAgent -t "Show disk usage for the root filesystem." -o disk_usage.log

# Run NetworkAgent to ping a host, load/save state (use cautiously)
(venv) $ python -m cli.main_non_interactive -a NetworkAgent -t "Ping 1.1.1.1 three times." --load-state --save-state```

---

### 3. Web User Interface (Web UI)

This provides a browser-based chat interface to interact with the `ControllerAgent`. It uses Flask sessions to maintain conversation history separately for each user/browser session.

**How to Run (Development):**

1.  Navigate to the project root (`agent_system_project/`).
2.  Ensure Flask is installed (`pip install Flask`).
3.  Run the Flask development server:
    ```bash
    flask --app web run --debug
    ```
4.  Open your web browser and go to the address shown (usually `http://127.0.0.1:5000`).

**How to Run (Production):**

*   Use a production WSGI server like Gunicorn. See `web/README.md` for details.
*   **Crucially**, set a strong `FLASK_SECRET_KEY` environment variable.
*   **Warning:** The current implementation stores active agent instances in memory per Flask session ID, which is **not safe** for multi-process production environments (like using multiple Gunicorn workers). The web state management needs refactoring (e.g., using persistent sessions + state loading per request, or background tasks) before serious production use.

**Interaction Flow:**

1.  Open the web UI in your browser. A unique session is started.
2.  Type your request into the input box at the bottom and click "Send" or press Enter.
3.  Your prompt is displayed on the right side of the chatbox.
4.  A loading spinner appears while the backend processes the request.
5.  The backend API (`/api/prompt`) receives the request.
6.  It retrieves (or initializes for the first time in the session) the `ControllerAgent` associated with your session ID.
7.  The `ControllerAgent` runs, loading previous history for your session, processing the prompt, potentially delegating to specialists (which also load/save their session-specific state), and handling tool calls (confirmation prompts appear in the *terminal* where Flask is running, not in the browser).
8.  The final response is sent back to the browser and displayed on the left side of the chatbox.
9.  The input box is re-enabled for your next prompt. Subsequent prompts in the same browser session will maintain the conversation history.

---

### 4. Scheduled Tasks / Scripting

You can automate agent tasks using the non-interactive CLI (`cli/main_non_interactive.py`) or the example script (`scripts/run_cron_task.py`) called from system scheduling tools like `cron` (Linux/macOS) or Task Scheduler (Windows).

**How to Run:**

*   Adapt the `scripts/run_cron_task.py` script for your specific needs or use `cli/main_non_interactive.py`.
*   Configure your system scheduler to execute the Python script.

**Key Considerations:**

*   **Environment:** The scheduler must run the script within the correct environment. This usually involves:
    *   Specifying the full path to the Python interpreter inside your virtual environment (e.g., `/path/to/agent_system_project/venv/bin/python`).
    *   Ensuring the script can find the project root to import modules (the example scripts handle this).
    *   Making sure the `.env` file is accessible and loaded correctly from the execution context (you might need absolute paths or to `cd` into the project directory within the cron command).
*   **Confirmation:** High-risk tools requiring confirmation might block execution if the script is run non-interactively without a TTY (terminal). Either disable confirmation for specific tools needed by the script (by modifying `HIGH_RISK_TOOLS` - **use extreme caution**) or ensure the script only uses tools that don't require confirmation.
*   **State:** By default, `run_cron_task.py` runs statelessly. If you need a scheduled task to remember previous runs, use the `--load-state` and `--save-state` flags (or modify the script), but be mindful of potential race conditions if multiple jobs target the same agent's state file concurrently. Using unique session IDs per job might be safer if state is needed.

**Example `cron` Job (Linux/macOS - Illustrative):**

```crontab
# Run system check every hour using SysAdminAgent, append output to a log file
# Ensure paths are correct for your system!
0 * * * * cd /home/user/agent_system_project && /home/user/agent_system_project/venv/bin/python -m scripts.run_cron_task --agent SysAdminAgent --task "Run basic system health check: check disk usage /, uptime, and memory usage." >> /var/log/agent_health.log 2>&1
```

---

## Key Concepts Notes

*   **Delegation:** The standard way to perform complex tasks is via the Interactive CLI or Web UI, interacting with the `ControllerAgent`, which routes tasks to specialists. Running specialists directly via the non-interactive CLI bypasses delegation.
*   **State:** Agent history is saved per `(session_id, agent_name)` pair in `agent_state/`. The Web UI manages `session_id` automatically. CLI sessions run without a `session_id` by default, sharing the base `<AgentName>_history.json` file unless `--load-state`/`--save-state` are used in non-interactive mode with care.
*   **Tools & Configuration:** Understand which tools are available (`agent_system/tools/`) and which are high-risk (`.env`). Tool behavior can sometimes be influenced by environment variables loaded via `settings.py`.

