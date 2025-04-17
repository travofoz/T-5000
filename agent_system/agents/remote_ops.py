import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class RemoteOpsAgent(BaseAgent):
    """
    Specialist agent focused on remote system operations via SSH/SCP and network diagnostics.
    Delegates non-remote tasks.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the RemoteOpsAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Remote Execution/Transfer (High-risk)
            "ssh_command",
            "scp_command",
            # SSH Key Management
            "ssh_agent_command",
            "ssh_add_command",
            # Network Diagnostics (Relevant for connectivity)
            "ping_command",
            "dig_command",
            "openssl_command", # Useful for checking remote ports/certs
            # Basic Filesystem (To manage keys or check local files before SCP)
            "list_files",
            "read_file",
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = f"""You are a specialist Remote Operations Agent.
Your capabilities include:
- Executing commands remotely on servers using `ssh_command` (key authentication only).
- Transferring files/directories to and from remote servers using `scp_command` (key authentication only).
- Managing local SSH keys in the ssh-agent using `ssh_agent_command` (list keys only) and `ssh_add_command`.
- Performing network diagnostics relevant to remote connectivity (`ping_command`, `dig_command`).
- Checking remote server ports or certificates using `openssl_command`.
- Basic local file operations (`list_files`, `read_file`) primarily for managing SSH keys or preparing for SCP.

You focus ONLY on remote interactions via SSH/SCP and related diagnostics. **You MUST delegate tasks** involving local system administration (package management, services), coding, debugging, complex builds, hardware interaction, or security scanning to the appropriate specialist agent (SysAdminAgent, CodingAgent, DebuggingAgent, BuildAgent, HardwareAgent, CybersecurityAgent). Use the `delegate_task` function provided by the Controller for delegation.

IMPORTANT SAFETY WARNINGS:
- `ssh_command` and `scp_command` are HIGH RISK and require confirmation. They operate without path safety restrictions on both local and remote systems. Ensure target host, commands, and paths are correct.
- These tools use non-interactive modes (`BatchMode=yes`, `StrictHostKeyChecking=no`), which bypass some security prompts but require correct key setup. Password authentication is disabled.
"""
        super().__init__(
            name="RemoteOpsAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"RemoteOpsAgent initialized with {len(self.allowed_tools)} tools.")
