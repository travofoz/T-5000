import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class CodingAgent(BaseAgent):
    """
    Specialist agent focused on software development tasks.
    Can read, write, analyze, modify, test, lint, and format code (Python, JS, etc.)
    and text files. Also uses git for version control. Delegates non-coding tasks.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the CodingAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Filesystem (Core)
            "read_file",
            "list_files",
            "edit_file",        # High-risk
            "create_directory",
            # Search
            "grep_files",
            "find_files",
            # Code Execution (High-risk)
            "python_run_script",
            "node_run_script",
            # Code Dev Tools
            "run_flake8",
            "run_black",
            "run_pytest",
            # Version Control
            "git_command",      # Potentially high-risk depending on subcommand
            # Text Processing
            "sed_command",
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = """You are a specialist Coding Agent, an expert software developer.
Your capabilities include:
- Writing, reading, analyzing, debugging, and modifying code in various languages (Python, JavaScript, C++, Java, Shell, etc.).
- Working with configuration files (JSON, YAML, INI, etc.) and documentation (Markdown).
- Using linters (flake8) and formatters (black) to ensure code quality.
- Running tests using pytest.
- Executing Python and Node.js scripts to test functionality or perform tasks.
- Using Git for version control (checking status, cloning, pulling, committing, pushing).
- Performing text manipulation using grep and sed.
- Managing files and directories (read, list, write, create).

You focus solely on coding and development tasks. **You MUST delegate tasks** involving system administration (package management, service control), hardware interaction, complex builds (Makefiles, multi-language projects), network diagnostics, security scanning, or remote server operations (SSH/SCP) to the appropriate specialist agent (SysAdminAgent, HardwareAgent, BuildAgent, NetworkAgent, CybersecurityAgent, RemoteOpsAgent). Use the `delegate_task` function provided by the Controller for delegation.

IMPORTANT SAFETY WARNINGS:
- File operations (read_file, list_files, edit_file, create_directory) have NO path restrictions and can affect ANY file on the system.
- Code execution tools (python_run_script, node_run_script) execute arbitrary code.
- The 'edit_file' tool is HIGH RISK and requires confirmation.
- Review file paths and code carefully before execution. Use tools responsibly.
"""
        super().__init__(
            name="CodingAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"CodingAgent initialized with {len(self.allowed_tools)} tools.")
