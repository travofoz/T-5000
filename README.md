# Multi-Agent System Project (V1 Refactored)

**🚨🚨🚨 EXTREME WARNING: HIGH RISK SOFTWARE 🚨🚨🚨**

This project implements a multi-agent system capable of performing a wide range of tasks, including **filesystem manipulation, code execution, network scanning, and system administration**, using Large Language Models (LLMs).

**Crucially, this version intentionally operates WITHOUT standard path safety restrictions.** Agents can potentially read, write, or modify files ANYWHERE on the system the user has access to. Furthermore, it includes tools that can install software, run commands with `sudo`, interact with hardware, and perform potentially disruptive network/security operations.

**RUNNING THIS SOFTWARE CARRIES SIGNIFICANT RISK OF:**
*   **Data Loss**
*   **System Damage or Instability**
*   **Security Vulnerabilities**
*   **Unexpected Costs (API usage)**
*   **Violation of Terms of Service (if used inappropriately)**

**DO NOT RUN THIS CODE UNLESS:**
*   You fully understand the code and its capabilities.
*   You are running it in a completely **isolated and disposable environment** (e.g., a dedicated virtual machine disconnected from sensitive networks/data).
*   You accept **full responsibility** for any and all consequences of its execution.

The system uses user confirmation prompts for tools deemed "high-risk" (configurable in `.env`), but setting `HIGH_RISK_TOOLS` to empty **disables all confirmations**, increasing the risk dramatically.

## Overview

This project provides a framework for building and running a system of collaborating autonomous agents, refactored from an initial single-file script. It features:
*   A modular, multi-file structure.
*   Abstraction for multiple LLM providers (Gemini, OpenAI, Anthropic, Ollama).
*   A diverse set of tools categorized by function (filesystem, process, network, code, build, security, etc.).
*   Dynamic tool discovery and registration via decorators.
*   Asynchronous operation using `asyncio` for core logic and tool execution.
*   Session-aware state management: Agent chat history is persisted to session-specific files.
*   Configuration management via `.env` file.
*   An interactive command-line interface (CLI) with live reload capability.
*   A non-interactive CLI for scripted tasks.
*   A Flask-based Web UI with session persistence for conversations.
*   Basic token/cost monitoring awareness (configuration and tracking).
*   Initial test structure and examples.

## Features

*   **Refactored Structure:** Code organized into logical packages (`agent_system`, `cli`, `web`, `scripts`, `tests`).
*   **LLM Provider Abstraction:** `LLMProvider` ABC and implementations for major providers. Provider instances are cached per entry point.
*   **Dynamic Tool Loading:** Tools defined in `agent_system/tools/` are automatically discovered via `@register_tool` decorator.
*   **Async Execution:** Core agent loop (`BaseAgent.run`), tool execution wrappers (`run_tool_command_async`), and web routes use `asyncio`.
*   **Session State Management:** `BaseAgent` supports `session_id` for loading/saving history to unique files in `agent_state/`. The Web UI leverages Flask sessions to manage this.
*   **Configuration:** API keys, model names, risk settings, timeouts, quotas managed via `.env` and `config/settings.py`.
*   **Cost/Token Monitoring:** Basic token counting in `BaseAgent` and configurable limits in settings.
*   **Interactive CLI:** `cli/main_interactive.py` provides a loop for interacting with the `ControllerAgent`. Includes `!reload` command.
*   **Non-Interactive CLI:** `cli/main_non_interactive.py` allows running specific agents for single tasks.
*   **Web UI:** A functional Flask web application (`web/`) provides a chat interface. Uses in-memory agent storage tied to Flask sessions (Warning: Not suitable for multi-process production).
*   **Directory READMEs:** Added README files within key subdirectories for guidance.

## Project Structure

```
agent_system_project/
├── agent_system/     # Core library code
│   ├── __init__.py
│ # │   ├── app_context.py  # (This was V2 idea, NOT implemented)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py         # Includes session_id handling for state
│   │   ├── controller.py
│   │   ├── datatypes.py
│   │   └── interaction.py # Basic Orchestrator (not fully utilized)
│   ├── llm_providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │ # │   ├── mcp_client.py # (MCP Client idea postponed)
│   │   ├── gemini.py
│   │   ├── openai.py
│   │   ├── anthropic.py     # No MCP context implemented yet
│   │   └── ollama.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── README.md
│   │   ├── tool_utils.py
│   │   ├── filesystem.py # No change_directory tool implemented yet
│   │   ├── ... (other tool files) ...
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── README.md
│   │   ├── ... (agent files) ...
│   └── config/
│       ├── __init__.py
│       ├── settings.py
│       └── schemas.py
├── cli/
│   ├── __init__.py
│   ├── README.md
│   ├── main_interactive.py     # Contains agent/provider init logic
│   └── main_non_interactive.py # Contains agent/provider init logic
├── web/
│   ├── __init__.py
│   ├── README.md
│   └── routes.py             # Contains agent/provider init logic, in-memory session storage
├── templates/
│   └── index.html
├── scripts/
│   ├── __init__.py
│   ├── README.md
│   └── run_cron_task.py      # Contains agent/provider init logic
├── tests/
│   ├── __init__.py
│   ├── README.md
│   ├── tools/
│   │   ├── __init__.py
│   │   └── test_filesystem.py
│   └── web/
│       ├── __init__.py
│       └── test_web_app.py
├── agent_state/
│   └── .gitkeep
├── .env.example
├── requirements.txt
└── README.md         # This file (Corrected for V1 Refactor)
```
*(Structure updated to remove files not actually created/implemented in this session)*

## Setup

1.  **Clone:** `git clone <repository_url>`
2.  **Navigate:** `cd agent_system_project`
3.  **Create Environment:** `python -m venv venv`
4.  **Activate Environment:**
    *   Windows: `.\venv\Scripts\activate`
    *   macOS/Linux: `source venv/bin/activate`
5.  **Install Dependencies:** `pip install -r requirements.txt`
6.  **Configure:**
    *   Copy `.env.example` to `.env`: `cp .env.example .env`
    *   **Edit `.env`**: Fill in API keys. Review `HIGH_RISK_TOOLS`, etc. Set `FLASK_SECRET_KEY` if using web UI frequently.
7.  **Install System Binaries:** Ensure necessary external command-line tools used by agent tools are installed.

## Running

*   **Interactive CLI:**
    ```bash
    python -m cli.main_interactive
    ```
*   **Non-Interactive CLI:**
    ```bash
    python -m cli.main_non_interactive --help
    ```
*   **Web UI (Development):**
    ```bash
    # From project root
    flask --app web run --debug
    ```
    Access at `http://127.0.0.1:5000`. **Warning:** Uses in-memory agent storage per session, not suitable for multi-process production.
*   **Web UI (Production):** Requires refactoring web state management first (see Future Improvements).

## Configuration & State

*   Core configuration (API Keys, model names, tool settings, etc.) is managed via environment variables, typically loaded from the `.env` file in the project root. Default values are defined in `agent_system/config/settings.py`. See `CONFIGURATION.md` for a detailed breakdown of all settings.
*   Agent conversation history is saved to session-specific files in `agent_state/`. The Web UI uses Flask sessions tied to these files.

## Development

*   **Adding Tools/Agents:** Follow instructions in `agent_system/tools/README.md` and `agent_system/agents/README.md`.
*   **Testing:** Use `pytest` from project root. Coverage is low. See `tests/README.md`.

## Future Improvements (Potential V2)

*   **Centralize Initialization:** Refactor agent/provider setup from entry points (CLI, Web, Scripts) into a shared context/service class (e.g., `ApplicationContext`).
*   **Robust Web State:** Replace in-memory web session agent storage with persistent session state (Flask-Session + Redis/Filesystem) or background tasks (Celery).
*   **MCP Integration:** Add support for MCP context passing (`AnthropicProvider`) and/or MCP client capabilities to use external tool servers.
*   **Enhanced Orchestration:** Develop `core/interaction.py` for more complex inter-agent workflows.
*   **Increased Test Coverage:** Significantly expand unit and integration tests.

## Disclaimer

This software is provided "as is". Use with extreme caution in isolated environments only. **You are solely responsible for its actions.**

