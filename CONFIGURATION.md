# Agent System Configuration Guide

This document details the configuration options available for the multi-agent system, primarily managed through the `.env` file and default values set in `agent_system/config/settings.py`.

## Configuration Hierarchy

The system uses the following priority for settings:

1.  **Environment Variables:** Variables set directly in the environment where the application runs.
2.  **.env File:** Variables defined in the `.env` file located in the project root (`agent_system_project/.env`). This file is loaded automatically if it exists.
3.  **Default Values:** Default values defined within `agent_system/config/settings.py`.

Environment variables (including those loaded from `.env`) will always override the defaults set in the Python code.

## The `.env` File

*   Create a `.env` file in the project root by copying `.env.example`.
*   Fill in your specific secrets (like API keys) and adjust settings as needed in this file.
*   The `.env` file should **NOT** be committed to version control (ensure it's listed in your `.gitignore` file).

## Configuration Variables

Here are the main configuration variables recognized by the system (typically set in `.env`):

---

### LLM Provider Settings

*   **`GEMINI_API_KEY`**:
    *   **Purpose:** Your API key for Google AI Studio (Gemini models).
    *   **Required:** If using the `GeminiProvider`.
    *   **Default:** None (must be set).
*   **`OPENAI_API_KEY`**:
    *   **Purpose:** Your API key for OpenAI (GPT models).
    *   **Required:** If using the `OpenAIProvider` with the standard OpenAI endpoint.
    *   **Default:** None (must be set).
*   **`ANTHROPIC_API_KEY`**:
    *   **Purpose:** Your API key for Anthropic (Claude models).
    *   **Required:** If using the `AnthropicProvider`.
    *   **Default:** None (must be set).
*   **`OLLAMA_BASE_URL`**:
    *   **Purpose:** The base URL for your running Ollama instance.
    *   **Required:** If using the `OllamaProvider`.
    *   **Default:** `http://localhost:11434` (set in `settings.py`).
*   **`OPENAI_BASE_URL`**:
    *   **Purpose:** Optional. Overrides the default OpenAI API URL. Useful for connecting to OpenAI-compatible APIs (like local models via LiteLLM, vLLM, etc.).
    *   **Required:** No.
    *   **Default:** OpenAI's standard API URL (handled by the `openai` library).

---

### Agent-Specific Model/Provider Overrides

You can override the default LLM provider and model used for specific agents defined in `settings.DEFAULT_AGENT_LLM_CONFIG`. Use the agent's class name in uppercase, followed by `_MODEL` or `_PROVIDER`.

*   **`<AGENT_NAME>_MODEL`** (e.g., `CODING_AGENT_MODEL`, `SYSADMIN_AGENT_MODEL`)
    *   **Purpose:** Specifies the exact model name (e.g., `gpt-4o`, `claude-3-haiku-20240307`, `gemini-1.5-flash-latest`, `llama3:latest`) to be used by that specific agent, overriding the default in `settings.py`.
    *   **Required:** No.
    *   **Default:** Defined per agent in `settings.DEFAULT_AGENT_LLM_CONFIG`.
*   **`<AGENT_NAME>_PROVIDER`** (e.g., `CODING_AGENT_PROVIDER`)
    *   **Purpose:** Specifies the provider name (`gemini`, `openai`, `anthropic`, `ollama`) for a specific agent, overriding the default.
    *   **Required:** No.
    *   **Default:** Defined per agent in `settings.DEFAULT_AGENT_LLM_CONFIG`.
*   **`<AGENT_NAME>_BASE_URL`** (e.g., `SYSADMIN_AGENT_BASE_URL`)
    *   **Purpose:** Specifies a provider base URL specifically for one agent, overriding any global setting (`OLLAMA_BASE_URL`, `OPENAI_BASE_URL`) or provider defaults.
    *   **Required:** No.
    *   **Default:** Uses global provider URL settings or provider library defaults.
*   **`OLLAMA_MODEL`**:
    *   **Purpose:** Sets a default model name specifically for *any* agent configured to use the `OllamaProvider` if that agent doesn't have its own `<AGENT_NAME>_MODEL` override.
    *   **Required:** No (but agents using Ollama need *some* model defined either via this or agent-specific overrides).
    *   **Default:** None.

---

### Tool Settings

*   **`HIGH_RISK_TOOLS`**:
    *   **Purpose:** A comma-separated list of tool function names that require user confirmation before execution in the interactive CLI.
    *   **Required:** No.
    *   **Default:** A predefined list in `settings.py` (see `settings.DEFAULT_HIGH_RISK_TOOLS`).
    *   **WARNING:** Setting this to an empty value (e.g., `HIGH_RISK_TOOLS=`) **disables all confirmations**, which is extremely risky.
*   **`DEFAULT_COMMAND_TIMEOUT`**:
    *   **Purpose:** Default timeout in seconds for external commands executed by tools using the `run_tool_command_async` / `run_tool_command_sync` wrappers. Individual tools may override this.
    *   **Required:** No.
    *   **Default:** `120` (seconds, defined in `settings.py`).

---

### Token / Cost Monitoring

*   **`MAX_GLOBAL_TOKENS`**:
    *   **Purpose:** An *approximate* global token limit for a single agent run (cumulative prompt + completion tokens tracked by the `BaseAgent` instance). If usage exceeds this limit, the agent run will stop. Set to `0` or omit to disable the limit check.
    *   **Required:** No.
    *   **Default:** `1_000_000` (defined in `settings.py`).
    *   **Note:** This limit is checked *before* each LLM call based on the *current* agent instance's tracked usage. It's not a precise real-time global counter across all concurrent agents/sessions.
*   **`WARN_TOKEN_THRESHOLD`**:
    *   **Purpose:** An *approximate* token usage threshold. If cumulative usage tracked by the `BaseAgent` instance meets or exceeds this value, a warning is logged. Set to `0` or omit to disable warnings.
    *   **Required:** No.
    *   **Default:** `800_000` (defined in `settings.py`).

---

### Agent State

*   **`AGENT_STATE_DIR`**:
    *   **Purpose:** The directory path where agent history/state files are saved.
    *   **Required:** No.
    *   **Default:** `./agent_state` relative to the project root (defined in `settings.py`).

---

### Logging

*   **`LOG_LEVEL`**:
    *   **Purpose:** Sets the logging level for the application.
    *   **Required:** No.
    *   **Options:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Case-insensitive.
    *   **Default:** `INFO` (defined in `settings.py`).

---

### Web UI

*   **`FLASK_SECRET_KEY`**:
    *   **Purpose:** A secret key used by Flask to sign session cookies, protecting them from tampering. **Crucial for security.**
    *   **Required:** Yes, for running the Web UI securely, especially in production.
    *   **Default:** A temporary, insecure key is generated at runtime if not set (a warning will be printed).
    *   **Recommendation:** Generate a strong random key (e.g., using `python -c 'import secrets; print(secrets.token_hex(16))'`) and set it as an environment variable or in `.env` for production.

---

See `agent_system/config/settings.py` for how these environment variables are loaded and how default values are defined.
