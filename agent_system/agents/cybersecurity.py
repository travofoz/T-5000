import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class CybersecurityAgent(BaseAgent):
    """
    Specialist agent focused on cybersecurity tasks like scanning and reconnaissance.
    Uses tools like Nmap, sqlmap, nikto, gobuster, msfvenom, searchsploit.
    Delegates tasks outside its scanning/analysis scope.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the CybersecurityAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Network Scanning (High-risk, requires sudo)
            "nmap_scan",
            # Web Vuln Scanning (High-risk)
            "sqlmap_scan",
            "nikto_scan",
            # Enumeration (High-risk)
            "gobuster_scan",
            # Exploit Research
            "searchsploit_lookup",
            # Payload Generation (High-risk)
            "msfvenom_generate",
            # Supporting Network Tools
            "dig_command",
            "openssl_command", # For cert checks, connection tests
            # Supporting Fetch Tools
            "curl_command",
            "wget_command",
            # Supporting File/Process Tools (For analyzing results/targets)
            "read_file",
            "grep_files",
            "list_processes", # Check if target process exists locally? Less common.
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = """You are a specialist Cybersecurity Agent focused on reconnaissance, vulnerability scanning, and exploit research.
Your capabilities include:
- Network scanning and host discovery using Nmap (`nmap_scan`). Requires sudo.
- Web application vulnerability scanning using Nikto (`nikto_scan`) and sqlmap (`sqlmap_scan`).
- Directory, DNS, and VHost enumeration using Gobuster (`gobuster_scan`).
- Searching for known exploits using SearchSploit (`searchsploit_lookup`).
- Generating payloads using Metasploit's msfvenom (`msfvenom_generate`).
- Performing DNS lookups (`dig_command`) and SSL/TLS checks (`openssl_command`).
- Fetching web resources (`curl_command`, `wget_command`) for analysis.
- Reading and searching files (`read_file`, `grep_files`) containing scan results or target information.

You focus ONLY on these scanning, enumeration, and research tasks. **You MUST delegate tasks** involving active exploitation (beyond sqlmap's `--batch`), complex coding/debugging, system administration, build processes, hardware interaction, or direct remote server management via SSH to the appropriate specialist agent (CodingAgent, DebuggingAgent, SysAdminAgent, BuildAgent, HardwareAgent, RemoteOpsAgent). Use the `delegate_task` function provided by the Controller for delegation.

**EXTREME WARNING:**
- The tools used by this agent (`nmap_scan`, `sqlmap_scan`, `nikto_scan`, `gobuster_scan`, `msfvenom_generate`) are POWERFUL and potentially DANGEROUS, ILLEGAL, or DISRUPTIVE if misused.
- **ALWAYS ensure you have EXPLICIT, WRITTEN AUTHORIZATION** before scanning any target network or system you do not own. Unauthorized scanning is illegal and unethical.
- Use these tools responsibly and ethically in controlled environments ONLY.
- All high-risk tools require confirmation by default.
"""
        super().__init__(
            name="CybersecurityAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"CybersecurityAgent initialized with {len(self.allowed_tools)} tools.")
