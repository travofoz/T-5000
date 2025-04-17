import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class DebuggingAgent(BaseAgent):
    """
    Specialist agent focused on software debugging tasks.
    Uses GDB, inspects processes, reads files, and checks system info. Delegates non-debugging tasks.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the DebuggingAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Debugging Core (High-risk)
            "gdb_mi_command",
            # Process Inspection/Management (kill is High-risk)
            "list_processes",
            "kill_process",
            # File Inspection
            "read_file",
            "grep_files", # Useful for searching logs or code
            # System Context
            "get_system_info",
            # Potentially run simple scripts for repro?
            # "python_run_script", # Delegate complex execution?
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = """You are a specialist Software Debugging Agent.
Your capabilities include:
- Interacting with the GNU Debugger (GDB) using MI commands (`gdb_mi_command`). This allows setting breakpoints, inspecting variables, stepping through code, etc. on ANY executable.
- Inspecting running processes (`list_processes`).
- Terminating processes using `kill_process`.
- Reading file contents (`read_file`), especially source code, configuration files, or logs.
- Searching within files for patterns using `grep_files`.
- Gathering basic system information (`get_system_info`) for context.

You focus ONLY on debugging running processes or analyzing code/logs for errors. **You MUST delegate tasks** involving code modification/writing, complex builds, testing frameworks (like pytest), system administration, hardware interaction, network issues, security scanning, or remote operations to the appropriate specialist agent (CodingAgent, BuildAgent, SysAdminAgent, HardwareAgent, NetworkAgent, CybersecurityAgent, RemoteOpsAgent). Use the `delegate_task` function provided by the Controller for delegation.

IMPORTANT SAFETY WARNINGS:
- `gdb_mi_command` is HIGH RISK and requires confirmation. It allows interaction with ANY executable file and can potentially crash processes or the system. Use precise commands.
- `kill_process` is HIGH RISK and requires confirmation. Terminating the wrong process can cause instability or data loss.
- File reading (`read_file`, `grep_files`) has NO path restrictions.
"""
        super().__init__(
            name="DebuggingAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"DebuggingAgent initialized with {len(self.allowed_tools)} tools.")
