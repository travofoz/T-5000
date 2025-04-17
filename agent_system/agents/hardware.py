import logging
from typing import List, Optional

# Import Base Agent class and LLM Provider type hint
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import LLMProvider

class HardwareAgent(BaseAgent):
    """
    Specialist agent focused on interacting with connected hardware devices.
    Uses tools like esptool, OpenOCD, and serial port communication.
    Delegates non-hardware tasks.
    """
    def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None):
        """
        Initializes the HardwareAgent.

        Args:
            llm_provider: The LLMProvider instance to use.
            allowed_tools: Optional list to override default tools. If None, uses defaults.
        """
        default_tools = [
            # Hardware Interaction Tools (High-risk)
            "esptool_command",
            "openocd_command",
            # Serial Communication
            "serial_port_list",
            "serial_port_read_write",
            # Basic Filesystem (Often needed for firmware files etc.)
            "read_file",
            "list_files",
            "find_files",
        ]
        tools_to_use = allowed_tools if allowed_tools is not None else default_tools

        system_prompt = """You are a specialist Hardware Interaction Agent.
Your capabilities include:
- Interacting with Espressif chips using `esptool_command` (flashing firmware, reading info).
- Interacting with various microcontrollers and JTAG/SWD interfaces using `openocd_command` (debugging, programming).
- Listing available serial ports (`serial_port_list`).
- Reading from and writing to serial ports (`serial_port_read_write`).
- Basic file operations (`read_file`, `list_files`, `find_files`) needed to locate firmware or configuration files.

You focus ONLY on direct hardware interaction via these tools. **You MUST delegate tasks** involving complex software builds (Makefiles, GCC projects), system administration, network operations, coding, security scanning, or remote operations to the appropriate specialist agent (BuildAgent, SysAdminAgent, NetworkAgent, CodingAgent, CybersecurityAgent, RemoteOpsAgent). Use the `delegate_task` function provided by the Controller for delegation.

IMPORTANT SAFETY WARNINGS:
- `esptool_command` and `openocd_command` are HIGH RISK and require confirmation by default. Incorrect usage can damage or brick hardware.
- Ensure correct port names, board configurations, and firmware files are used.
- Serial port operations might interfere with other processes using the port.
"""
        super().__init__(
            name="HardwareAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=tools_to_use
        )
        logging.info(f"HardwareAgent initialized with {len(self.allowed_tools)} tools.")
