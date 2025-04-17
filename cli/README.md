# Agent System - Command Line Interface (CLI)

This directory contains the entry points for interacting with the multi-agent system via the command line.

## Files

*   `main_interactive.py`: Provides an interactive Read-Eval-Print Loop (REPL) where users can type prompts for the `ControllerAgent`. It handles user input, agent execution, response display, and session management (implicitly via agent state). Includes a `!reload` command for development. Run using `python -m cli.main_interactive`.
*   `main_non_interactive.py`: Allows running a *specific* agent with a single task prompt provided via command-line arguments. Useful for scripting or running predefined tasks. Run using `python -m cli.main_non_interactive --agent <AgentName> --task "<Your Task>"`.

## Usage

See the main project `README.md` for setup instructions.

*   **Interactive:** `python -m cli.main_interactive`
*   **Non-Interactive:** `python -m cli.main_non_interactive --help` for options.

## Notes

*   Both CLI entry points rely on the core agent logic defined in the `agent_system` package.
*   They handle initializing the necessary agent instances and providers (ideally through a central service in V2).
*   Configuration (API keys, models, etc.) is loaded from `.env` via `agent_system.config.settings`.
