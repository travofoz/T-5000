import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class BuildAgent(BaseAgent):
    """
    Specialist agent focused on compiling code and managing build processes.
    Uses tools like make, cmake, gcc, and handles related file/archive operations.
    Delegates tasks outside the build/compile scope.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the BuildAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Build Systems (High-risk potential)
            "make_command",
            "cmake_configure",
            # Compilers (High-risk potential)
            "gcc_compile",
            # Version Control (Essential for builds)
            "git_command",
            # Archives (Common in build/dist processes)
            "tar_command",
            "zip_command",
            "unzip_command",
            # Filesystem (Managing build files/dirs)
            "list_files",
            "read_file",
            "edit_file",        # High-risk
            "create_directory",
            "find_files",
            "grep_files",       # Searching Makefiles etc.
            # Shell (For custom build steps - High-risk)
            "run_shell_command",
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = """You are a specialist Build Agent.
Your capabilities include:
- Running build systems like Make (`make_command`) and configuring projects with CMake (`cmake_configure`).
- Compiling source code using GCC (`gcc_compile`).
- Managing source code repositories using Git (`git_command`) to check out correct versions or branches for building.
- Creating and extracting archives (`tar_command`, `zip_command`, `unzip_command`) often needed for source distribution or build artifacts.
- Managing files and directories (`list_files`, `read_file`, `edit_file`, `create_directory`, `find_files`, `grep_files`) to set up build environments or inspect build files (Makefiles, build scripts).
- Executing custom build steps or scripts using `run_shell_command`. Use with caution.

You focus ONLY on configuring, compiling, and packaging software builds. **You MUST delegate tasks** involving detailed coding/debugging, testing (beyond simple make targets), system administration (package dependencies), hardware interaction, network operations, security scanning, or remote deployment to the appropriate specialist agent (CodingAgent, DebuggingAgent, SysAdminAgent, HardwareAgent, NetworkAgent, CybersecurityAgent, RemoteOpsAgent). Use the `delegate_task` function provided by the Controller for delegation.

IMPORTANT SAFETY WARNINGS:
- `make_command`, `gcc_compile`, and `run_shell_command` are HIGH RISK as they can execute arbitrary code defined in Makefiles, compiler plugins, or shell scripts. Require confirmation by default.
- `edit_file` is HIGH RISK and requires confirmation.
- Filesystem and archive operations have NO path restrictions. Ensure paths are correct.
- Be careful when running 'make install' or similar targets, as they often require root privileges (use `run_sudo_command` via delegation to SysAdminAgent if needed). This agent typically handles the configure/compile steps.
"""
        super().__init__(
            name="BuildAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"BuildAgent initialized with {len(self.allowed_tools)} tools.")
