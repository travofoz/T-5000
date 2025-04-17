import logging
import shlex
import sys
import signal
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async, run_tool_command_sync, ask_confirmation_async
from agent_system.config import settings

@register_tool
async def run_shell_command(command_string: str) -> str:
    """
    Executes a RAW shell command string using shell=True.
    EXTREMELY DANGEROUS. Requires confirmation by default.

    Args:
        command_string: The raw shell command to execute.

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    # Confirmation is handled by the agent before calling this tool
    logging.critical(f"Executing RAW SHELL command: {command_string}")
    return await run_tool_command_async(
        tool_name="run_shell_command",
        command=command_string,
        use_shell=True,
        timeout=300 # Longer default for shell commands
    )

@register_tool
async def run_sudo_command(command_args: List[str]) -> str:
    """
    Executes a command list with sudo. Requires 'sudo' to be available and configured.
    EXTREMELY DANGEROUS. Requires confirmation by default.

    Args:
        command_args: List of command and arguments to run with sudo (e.g., ['apt', 'update']).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    # Confirmation is handled by the agent before calling this tool
    if not command_args:
        return "Error: No command provided to run_sudo_command."
    # Ensure all args are strings
    safe_args = [str(arg) for arg in command_args]
    logging.critical(f"Executing sudo command: {' '.join(safe_args)}")
    # Use -- to prevent sudo parsing args after it, even if command starts with '-'
    command = ["sudo", "--"] + safe_args
    return await run_tool_command_async(
        tool_name="run_sudo_command",
        command=command,
        timeout=300 # Longer timeout for potentially interactive sudo commands (if password prompt needed, though unlikely in automation)
    )

@register_tool
async def list_processes(filter_pattern: Optional[str] = None) -> str:
    """
    Lists running processes using 'ps aux'. Optionally filters the output using 'grep -E'.

    Args:
        filter_pattern: Optional regex pattern to filter processes (passed to grep -E).

    Returns:
        Formatted string listing processes or an error message.
    """
    ps_command = ["ps", "aux"]
    try:
        # Run ps aux first
        ps_success, ps_stdout_bytes, ps_stderr_bytes, ps_rc = await _run_command_async(ps_command)

        if not ps_success:
             ps_stderr = ps_stderr_bytes.decode(sys.stderr.encoding or 'utf-8', errors='replace')
             ps_stdout = ps_stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace')
             return f"Failed to list processes using 'ps aux' (RC={ps_rc}):\nStderr: {ps_stderr}\nStdout: {ps_stdout}"

        ps_output_str = ps_stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace')

        if not filter_pattern:
             # Return all processes if no filter
             num_lines = len(ps_output_str.splitlines())
             header = "All running processes" if num_lines <=1 else f"All running processes ({num_lines-1} lines)"
             return f"{header}:\n```\n{ps_output_str}\n```"
        else:
            # Use grep for filtering - run grep asynchronously as well
            grep_command = ["grep", "-E", "--", filter_pattern] # Use basic regex, ensure pattern isn't treated as option
            logging.info(f"Filtering process list with grep pattern: '{filter_pattern}'")

            grep_success, grep_stdout_bytes, grep_stderr_bytes, grep_rc = await _run_command_async(
                grep_command,
                input_data=ps_stdout_bytes # Pipe ps output bytes directly to grep input
            )

            grep_stdout = grep_stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace')
            grep_stderr = grep_stderr_bytes.decode(sys.stderr.encoding or 'utf-8', errors='replace')

            # grep rc 0=found, 1=not found, >1=error
            if grep_rc == 0:
                 # Filter out the grep process itself from the output
                 filtered_lines = [line for line in grep_stdout.splitlines() if ' grep -E -- ' not in line]
                 if not filtered_lines:
                      return f"No processes found matching pattern: '{filter_pattern}' (excluding grep itself)."
                 # Try to find the header line from original ps output
                 header = ps_output_str.splitlines()[0] if ps_output_str.splitlines() else "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND"
                 return f"Filtered processes matching '{filter_pattern}':\n```\n" + header + "\n" + "\n".join(filtered_lines) + "\n```"
            elif grep_rc == 1:
                 return f"No processes found matching pattern: '{filter_pattern}'"
            else:
                 return f"Error filtering processes with grep (RC={grep_rc}):\nStderr: {grep_stderr}\nStdout: {grep_stdout}"

    except Exception as e:
         logging.exception(f"Error in list_processes tool: {e}")
         return f"An unexpected error occurred while listing processes: {e}"


@register_tool
async def kill_process(pid: int, signal_num: int = signal.SIGTERM) -> str:
    """
    Sends a signal (default 15/SIGTERM) to the specified process ID using 'kill'.
    May attempt to use 'sudo kill' if the initial attempt fails due to permissions.
    HIGH RISK. Requires confirmation by default.

    Args:
        pid: Process ID (PID) to send the signal to.
        signal_num: Signal number to send (e.g., 9 for KILL/SIGKILL, 15 for TERM/SIGTERM). Default is SIGTERM.

    Returns:
        Formatted string indicating success or failure.
    """
    # Confirmation is handled by the agent before calling this tool
    logging.warning(f"Preparing kill command: signal={signal_num}, PID={pid}")
    try:
        # Validate PID and Signal number
        pid_int = int(pid)
        sig_int = int(signal_num)
        if pid_int <= 0: return "Error: Invalid PID provided."
        # Check if signal number is valid on the current platform
        if sig_int not in range(1, signal.NSIG):
             logging.warning(f"Signal number {sig_int} might be invalid on this system (Valid range 1-{signal.NSIG-1}).")
        # Basic check for common signal values
        common_signals = {signal.SIGTERM, signal.SIGKILL, signal.SIGHUP, signal.SIGINT}
        if sig_int not in common_signals:
             logging.warning(f"Using less common signal number: {sig_int}")

    except ValueError:
        return "Error: PID and signal number must be valid integers."
    except Exception as e:
         return f"Error validating kill parameters: {e}"

    # --- Try kill without sudo first ---
    kill_command = ["kill", f"-{sig_int}", str(pid_int)]
    try:
         success, stdout_bytes, stderr_bytes, rc = await _run_command_async(kill_command)
         stdout = stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace')
         stderr = stderr_bytes.decode(sys.stderr.encoding or 'utf-8', errors='replace')

         if success:
             return f"Signal {sig_int} sent successfully to PID {pid_int} (using standard 'kill'). Stdout: {stdout} Stderr: {stderr}".strip()
         else:
             # --- Check if permission denied, then try sudo ---
             permission_errors = ["operation not permitted", "permission denied", "eperm"]
             if rc == 1 and any(p_err in stderr.lower() for p_err in permission_errors):
                 logging.warning(f"'kill' failed without sudo (RC={rc}, Stderr: {stderr}). Attempting with sudo.")
                 # Confirmation for the *sudo* part itself happens here (again) if sudo is high-risk
                 # This assumes run_sudo_command is also decorated or handled appropriately.
                 # Note: The agent already confirmed 'kill_process', but might need to confirm 'run_sudo_command' too.
                 # This might lead to double confirmation depending on HIGH_RISK_TOOLS setup.

                 # Prepare args for run_sudo_command tool
                 sudo_command_args = ["kill", f"-{sig_int}", str(pid_int)]
                 # We need to call the run_sudo_command *tool* function, not just the wrapper
                 # This is tricky as tools shouldn't ideally call other tools directly.
                 # A better approach might be to have the LLM try sudo if kill fails.
                 # For now, let's directly call the wrapper `run_tool_command_async` for sudo.
                 # Re-confirming specifically for sudo:
                 if await ask_confirmation_async("run_sudo_command", {"command_args": sudo_command_args}):
                      sudo_result = await run_tool_command_async(
                           tool_name="run_sudo_command",
                           command=["sudo", "--"] + sudo_command_args,
                           timeout=60
                      )
                      return f"Attempted 'sudo kill' after permission error.\nSudo Result:\n{sudo_result}"
                 else:
                      return f"Standard 'kill' failed with permission error (RC={rc}, Stderr: {stderr}). User cancelled sudo attempt."

             else:
                 # Failed for other reasons
                 cmd_display = ' '.join(shlex.quote(str(c)) for c in kill_command)
                 return f"Tool 'kill_process' failed (RC={rc}). Command: `{cmd_display}`\nStatus: Failed\nStderr:\n```\n{stderr}\n```\nStdout:\n```\n{stdout}\n```"

    except Exception as e:
         logging.exception(f"Unexpected error in kill_process tool for PID {pid}: {e}")
         return f"An unexpected error occurred trying to kill PID {pid}: {e}"


@register_tool
async def get_system_info() -> str:
    """
    Retrieves basic system information (OS, Hostname, Uptime, CPU, Memory)
    by running common command-line tools asynchronously.
    """
    info_commands = {
        "OS": ["uname", "-a"],
        "Hostname": ["hostname"],
        "Uptime": ["uptime"],
        "CPU Info": ["lscpu"], # Linux specific
        "Memory Info": ["free", "-h"], # Linux specific
        # Add platform specific alternatives if needed (e.g., for macOS/Windows)
        # "OS_mac": ["sw_vers"],
        # "CPU_mac": ["sysctl", "-n", "machdep.cpu.brand_string"],
        # "Mem_mac": ["sysctl", "-n", "hw.memsize"], # bytes
    }
    # Select commands based on platform (simple check)
    platform_cmds = {}
    if sys.platform.startswith("linux"):
         platform_cmds = info_commands # Use all default Linux commands
    elif sys.platform == "darwin": # macOS
         platform_cmds = {
             "OS": ["sw_vers"], "Hostname": ["hostname"], "Uptime": ["uptime"],
             "CPU Info": ["sysctl", "-n", "machdep.cpu.brand_string"],
             "Memory Info (RAM Bytes)": ["sysctl", "-n", "hw.memsize"]
         }
    elif sys.platform == "win32": # Windows
         platform_cmds = { # Using WMIC - might require admin sometimes?
              "OS": ["wmic", "os", "get", "Caption,Version,OSArchitecture", "/value"],
              "Hostname": ["hostname"],
              "CPU Info": ["wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors", "/value"],
              "Memory Info (Bytes)": ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/value"],
              # Uptime is harder with a single command, skip for now
         }
    else: # Fallback for other OS
         platform_cmds = {"OS": ["uname", "-a"], "Hostname": ["hostname"], "Uptime": ["uptime"]}


    results = {}
    tasks = []

    # Define a helper coroutine to run one command
    async def run_info_cmd(name: str, cmd: List[str]):
        try:
             success, stdout_bytes, stderr_bytes, rc = await _run_command_async(cmd, timeout=10) # Short timeout
             stdout = stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace').strip()
             stderr = stderr_bytes.decode(sys.stderr.encoding or 'utf-8', errors='replace').strip()
             if success and stdout:
                 results[name] = stdout
             elif stdout: # Include output even if RC != 0 if stdout has content
                 results[name] = f"{stdout}\n(Command finished with RC={rc})"
             elif stderr:
                 results[name] = f"Error (RC={rc}): {stderr}"
             else:
                 results[name] = f"Error (RC={rc}): No output"
        except Exception as e:
             logging.error(f"Error running system info command '{' '.join(cmd)}': {e}")
             results[name] = f"Failed to execute: {e}"

    # Create tasks for all commands
    for name, cmd in platform_cmds.items():
        tasks.append(asyncio.create_task(run_info_cmd(name, cmd)))

    # Wait for all tasks to complete
    await asyncio.gather(*tasks)

    # Format the results
    output = "System Information:\n```\n"
    for name in platform_cmds: # Iterate in original order
         output += f"--- {name} ---\n"
         output += results.get(name, "Error retrieving data.") + "\n\n"
    output = output.strip() + "\n```"
    return output


# Need _run_command_async defined in this file or imported properly
async def _run_command_async(
    command: Union[List[str], str],
    timeout: int = settings.COMMAND_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None,
    input_data: Optional[bytes] = None,
    check: bool = False,
    use_shell: bool = False,
    env: Optional[Dict[str, str]] = None
) -> Tuple[bool, bytes, bytes, int]:
    """Placeholder: Calls the actual implementation from tool_utils"""
    # Avoid circular import by calling the function from tool_utils directly if needed
    # However, the way it's structured now, process.py imports tool_utils which has this function.
    # If tool_utils needed to import process.py, we'd have a problem.
    # For simplicity here, we assume tool_utils._run_command_async is available via import.
    from .tool_utils import _run_command_async as util_run_async
    return await util_run_async(command, timeout, cwd, input_data, check, use_shell, env)
