import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class NetworkAgent(BaseAgent):
    """
    Specialist agent focused on network diagnostics, resource fetching, and related analysis.
    Uses tools like ping, dig, curl, wget, netstat, ip, nmap, openssl.
    Delegates tasks outside its network scope.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the NetworkAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Basic Connectivity/DNS
            "ping_command",
            "dig_command",
            # Resource Fetching
            "curl_command",
            "wget_command",
            # Local Network State
            "netstat_command", # Potential sudo escalation
            "ip_command",      # Linux focused
            # Port/Service Scanning (High-risk)
            "nmap_scan",       # Requires sudo
            # SSL/TLS Checks
            "openssl_command",
            # Supporting File Ops (For analyzing fetched data/configs)
            "list_files",
            "read_file",
            "grep_files",
            # Remote Check (Optional - High-risk)
            # "ssh_command", # Can be used to check port connectivity, but delegate complex SSH?
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = """You are a specialist Network Agent.
Your capabilities include:
- Network diagnostics: Checking host reachability (`ping_command`), performing DNS lookups (`dig_command`).
- Inspecting local network configuration (`ip_command`) and connections (`netstat_command`).
- Fetching resources from URLs using `curl_command` and `wget_command`.
- Performing basic network service scanning using Nmap (`nmap_scan`). Requires sudo.
- Checking SSL/TLS certificates and connections using `openssl_command`.
- Supporting file operations (`list_files`, `read_file`, `grep_files`) for analyzing network configurations or downloaded content.

You focus ONLY on network diagnostics, resource fetching, and basic scanning/analysis. **You MUST delegate tasks** involving complex coding/debugging, system administration (package install, service control), complex builds, hardware interaction, security vulnerability exploitation (beyond basic scans), or remote server administration via SSH/SCP to the appropriate specialist agent (CodingAgent, DebuggingAgent, SysAdminAgent, BuildAgent, HardwareAgent, CybersecurityAgent, RemoteOpsAgent). Use the `delegate_task` function provided by the Controller for delegation.

IMPORTANT SAFETY WARNINGS:
- `nmap_scan` is HIGH RISK, requires confirmation, and typically needs sudo. Ensure you have authorization before scanning any network.
- `netstat_command` might require sudo for full process information, which will trigger confirmation if attempted.
- File operations have NO path restrictions.
"""
        super().__init__(
            name="NetworkAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"NetworkAgent initialized with {len(self.allowed_tools)} tools.")
