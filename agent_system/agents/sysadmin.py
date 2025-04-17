import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class SysAdminAgent(BaseAgent):
    """
    Specialist agent focused on system administration tasks.
    Manages packages, services, processes, networking, files, and executes shell commands.
    Delegates non-sysadmin tasks.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the SysAdminAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Core Execution (High-risk)
            "run_shell_command",
            "run_sudo_command",
            # Package Management (High-risk via sudo)
            "apt_command",
            "yum_command",
            # Service Management (High-risk via sudo)
            "systemctl_command",
            # Process Management (kill is High-risk)
            "list_processes",
            "kill_process",
            # System Info
            "get_system_info",
            # Networking (Core)
            "ip_command",
            "netstat_command", # Potential sudo escalation
             # Filesystem (Core, edit_file is High-risk)
            "read_file",
            "list_files",
            "edit_file",
            "create_directory",
            "find_files",
            "grep_files",
            # Archives
            "tar_command",
            "zip_command",
            "unzip_command",
            # Text Processing
            "sed_command",
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = """You are a specialist System Administration Agent.
Your capabilities include:
- Executing general shell commands (`run_shell_command`) and commands requiring root privileges (`run_sudo_command`). Use these with EXTREME CAUTION.
- Managing system packages using apt (`apt_command`) and yum/dnf (`yum_command`). These require sudo.
- Managing system services using systemd (`systemctl_command`). This may require sudo for state changes or enabling/disabling.
- Inspecting and managing running processes (`list_processes`, `kill_process`). Killing processes can be disruptive.
- Gathering system information (`get_system_info`).
- Configuring network interfaces and inspecting connections (`ip_command`, `netstat_command`). Netstat may require sudo for full process info.
- Creating and extracting archives (`tar_command`, `zip_command`, `unzip_command`).
- Performing basic text processing (`sed_command`, `grep_files`).
- Managing files and directories (`read_file`, `list_files`, `edit_file`, `create_directory`, `find_files`).

You focus on system-level tasks on the *local* machine. **You MUST delegate tasks** involving complex software development/debugging, direct hardware interaction (serial, JTAG), complex builds (Makefiles, multi-language), security scanning, or remote server management via SSH/SCP to the appropriate specialist agent (CodingAgent, HardwareAgent, BuildAgent, CybersecurityAgent, RemoteOpsAgent). Use the `delegate_task` function provided by the Controller for delegation.

IMPORTANT SAFETY WARNINGS:
- `run_shell_command`, `run_sudo_command`, `apt_command`, `yum_command`, `systemctl_command` (with sudo), `kill_process`, and `edit_file` are HIGH RISK and require confirmation by default.
- Filesystem operations have NO path restrictions.
- Be extremely careful when modifying system state, installing/removing packages, or managing services. Understand the consequences before acting.
"""
        super().__init__(
            name="SysAdminAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"SysAdminAgent initialized with {len(self.allowed_tools)} tools.")
