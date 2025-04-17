# Agent System - Scripts

This directory holds utility scripts related to the development, deployment, maintenance, or operation of the multi-agent system.

## Files

*   `run_cron_task.py`: An example script demonstrating how to run a specific agent with a predefined task non-interactively. It takes the agent class name and task prompt as command-line arguments and can be used for scheduled tasks via tools like `cron`.

## Purpose

Scripts in this directory can serve various purposes, such as:

*   **Batch Processing:** Running agents on multiple inputs or datasets.
*   **Scheduled Tasks:** Automating routine agent actions (e.g., daily summaries, system checks).
*   **Testing Utilities:** Scripts to set up test environments or run specific test scenarios.
*   **Deployment Helpers:** Scripts to assist with deploying or configuring the agent system.
*   **Data Management:** Scripts for managing agent state files or other persistent data.

## Usage

Scripts can typically be run as Python modules from the project root directory:

```bash
# Example for run_cron_task.py
python -m scripts.run_cron_task --agent SysAdminAgent --task "Check disk space on all mounts"
```
Ensure that the necessary environment (Python path, virtual environment activation, .env file access) is correctly configured when running these scripts, especially if executed by external tools like cron. Refer to individual script documentation (docstrings or --help arguments) for specific usage instructions.
