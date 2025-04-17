
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
    *   **Edit `.env`**: Fill in your API keys for the LLM providers you intend to use. Review and adjust `HIGH_RISK_TOOLS`, `OLLAMA_BASE_URL` (if using Ollama), and other settings as needed.
7.  **Install System Binaries (Required for many tools):** Ensure tools like `git`, `grep`, `find`, `tar`, `zip`, `unzip`, `ps`, `kill`, `ip`, `netstat`, `make`, `gcc`, `cmake`, `python`, `node`, `nmap`, `sqlmap`, `nikto`, `msfvenom`, `gobuster`, `searchsploit`, `openssl`, `dig`, `ping`, `esptool.py`, `openocd` (depending on the tools you enable/use) are installed and available in your system's `PATH`. Installation methods vary by operating system (e.g., `apt`, `yum`, `brew`, `pacman`).

## Running

*   **Interactive Mode:** Run the main controller loop:
    ```bash
    python -m cli.main_interactive
    ```
    You can then enter prompts for the Controller Agent. Type `quit` or `exit` to stop.
    *   **Reload Command:** While the interactive CLI is running, you can attempt to reload modules using `!reload <module_path>` (e.g., `!reload agent_system.tools.filesystem`). This is useful for development but may lead to inconsistent state.

*   **Non-Interactive Mode (Placeholder):** `cli/main_non_interactive.py` exists but has minimal functionality currently.

## Configuration

*   Primary configuration is done via the `.env` file in the project root. See `.env.example` for available variables.
*   Default values and loading logic are found in `agent_system/config/settings.py`. Environment variables override defaults.

## Development

*   Placeholders are included for future expansion:
    *   `web/`: For a potential Gradio/Flask/FastAPI web interface.
    *   `tests/`: For adding unit and integration tests (highly recommended!).
    *   `scripts/`: For adding helper or automation scripts.
*   New tools can be added by creating functions in the relevant `agent_system/tools/*.py` file and decorating them with `@register_tool`.
*   New agents can be added by creating classes in `agent_system/agents/` inheriting from `BaseAgent`.

## Disclaimer

This software is provided "as is" without warranty of any kind. The authors and contributors are not responsible for any damage or loss caused by its use. **Use at your own extreme risk.**
