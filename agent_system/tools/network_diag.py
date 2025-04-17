import asyncio
import logging
import shlex
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async, run_tool_command_sync, ask_confirmation_async
from agent_system.config import settings

@register_tool
async def ip_command(args: List[str]) -> str:
    """
    Runs the 'ip' command (common on Linux) with specified arguments to query network configuration.

    Args:
        args: List of arguments for the 'ip' command (e.g., ['addr', 'show']).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    if not args:
        return "Error: No arguments provided for 'ip' command."
    # Ensure args are strings
    safe_args = [str(arg) for arg in args]
    return await run_tool_command_async(
        tool_name="ip_command",
        command=["ip"] + safe_args
    )

@register_tool
async def netstat_command(options: List[str] = ["-tulnp"]) -> str:
    """
    Runs 'netstat' to display network connections, listening ports, routing tables, etc.
    Attempts to run without sudo first, then retries with sudo if permission errors occur.
    Requires confirmation by default if sudo attempt is needed.

    Args:
        options: List of options for netstat. Defaults to ['-tulnp'] (TCP, UDP, Listening, Numeric, Process).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    # Ensure options are strings
    safe_options = [str(opt) for opt in options]
    cmd = ["netstat"] + safe_options
    logging.info(f"Running netstat with options: {' '.join(safe_options)}")

    # --- Try without sudo first ---
    try:
        # Use internal helper directly to check stderr before formatting output
        success, stdout_bytes, stderr_bytes, rc = await _run_command_async(cmd)
        stdout = stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace')
        stderr = stderr_bytes.decode(sys.stderr.encoding or 'utf-8', errors='replace')

        if success:
            return f"Netstat successful (no sudo):\nOptions: {' '.join(safe_options)}\nOutput:\n```\n{stdout}\n```"
        else:
            # --- Check if permission denied, then try sudo ---
            permission_errors = ["permission denied", "operation not permitted"]
            if rc != 0 and any(p_err in stderr.lower() for p_err in permission_errors):
                logging.warning(f"netstat failed without sudo (RC={rc}, Stderr: {stderr}). Attempting with sudo.")
                # Confirmation for run_sudo_command itself is handled by agent if it's high risk
                # Ask confirmation *specifically* for escalating netstat via sudo:
                sudo_args = {"command_args": cmd}
                if await ask_confirmation_async("netstat_command_sudo", sudo_args):
                     # Directly call run_tool_command_async for sudo execution
                     sudo_result = await run_tool_command_async(
                          tool_name="run_sudo_command (for netstat)",
                          command=["sudo", "--"] + cmd,
                          timeout=60 # Reasonable timeout for sudo netstat
                     )
                     return f"Attempted 'sudo netstat' after permission error.\nSudo Result:\n{sudo_result}"
                else:
                     return f"Standard 'netstat' failed with permission error (RC={rc}, Stderr: {stderr}). User cancelled sudo attempt."
            else:
                # Failed for other reasons, format using standard wrapper logic
                cmd_display = ' '.join(shlex.quote(str(c)) for c in cmd)
                status_msg = 'Success (non-zero RC)' if stdout else 'Failed' # Consider it success if there's output?
                result_str = f"Tool 'netstat_command' finished (RC={rc}). Command: `{cmd_display}`\nStatus: {status_msg}\n"
                if stdout: result_str += f"Stdout:\n```\n{stdout}\n```\n"
                if stderr: result_str += f"Stderr:\n```\n{stderr}\n```\n"
                elif not stdout and not stderr: result_str += "(No output on stdout or stderr)\n"
                return result_str.strip()

    except Exception as e:
        logging.exception(f"Unexpected error running netstat: {e}")
        return f"An unexpected error occurred while running netstat: {e}"


@register_tool
async def ping_command(host: str, count: int = 4) -> str:
    """
    Sends ICMP ECHO_REQUEST packets to a network host using the 'ping' command.

    Args:
        host: Hostname or IP address to ping.
        count: Number of packets to send (default: 4).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    try:
        count_int = max(1, int(count))
    except ValueError:
        return "Error: 'count' parameter must be an integer."

    # Basic input validation for host - avoid letting it be misinterpreted as options
    if not host or host.startswith('-'):
        return f"Error: Invalid host for ping: '{host}'"

    # Platform specific count option
    if sys.platform == "win32":
        count_flag = "-n"
        cmd = ["ping", count_flag, str(count_int), host]
    else: # Linux, macOS, etc.
        count_flag = "-c"
        cmd = ["ping", count_flag, str(count_int), host]

    # Ping exit codes vary: 0=success, 1=host unreachable/error (common), 2=other error/unknown host (common)
    return await run_tool_command_async(
        tool_name="ping_command",
        command=cmd,
        timeout=20, # Allow reasonable time for pings
        success_rc=[0], # Strictly, only 0 is success, but output often useful on failure
        failure_notes={
            1: "Host unreachable or network error (common).",
            2: "Unknown host or other network error (common).",
        }
    )

@register_tool
async def dig_command(domain: str, record_type: str = "A", server: Optional[str] = None) -> str:
    """
    Performs DNS lookups using the 'dig' command.

    Args:
        domain: The domain name to query.
        record_type: DNS record type (e.g., A, MX, TXT, ANY). Default is A.
        server: Optional DNS server IP or hostname to query (prepended with '@').

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    # Basic validation
    if not domain or domain.startswith('-'): return f"Error: Invalid domain name: '{domain}'"
    # Allow various record types, basic check for flags
    if record_type.startswith('-') and len(record_type) > 1: return f"Error: Invalid record type format: '{record_type}'"
    if server and server.startswith('-'): return f"Error: Invalid server address format: '{server}'"

    cmd = ["dig"]
    if server:
        server_arg = server if server.startswith('@') else f"@{server}"
        cmd.append(server_arg)
    cmd.append(domain)
    cmd.append(record_type)
    # Add options for non-interactive use
    cmd.extend(["+noall", "+answer", "+stats"]) # Show answer and stats, less verbose than default

    return await run_tool_command_async(
        tool_name="dig_command",
        command=cmd,
        success_rc=0, # RC 0 is primary success (even for NXDOMAIN which is in output)
        failure_notes={
             9: "Query failed (e.g., NXDOMAIN, SERVFAIL, REFUSED). Check output for details.",
        }
    )

@register_tool
async def openssl_command(args: List[str], input_data: Optional[str] = None) -> str:
    """
    Executes an 'openssl' command with specified arguments.
    Useful for cryptographic tasks, certificate checking, connection testing etc.
    BE CAUTIOUS with commands that handle private keys or modify state.

    Args:
        args: List of arguments for the 'openssl' command (e.g., ['s_client', '-connect', 'example.com:443']).
        input_data: Optional text data to pipe as standard input to openssl (will be UTF-8 encoded).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    if not args:
        return "Error: No arguments provided for 'openssl' command."
    # Ensure args are strings
    safe_args = [str(arg) for arg in args]
    cmd = ["openssl"] + safe_args

    # Convert string input_data to bytes for async helper
    input_bytes: Optional[bytes] = None
    if input_data is not None:
        try:
            input_bytes = input_data.encode('utf-8')
        except Exception as e:
            return f"Error encoding input_data for openssl: {e}"

    # Success for openssl depends heavily on the subcommand. RC 0 is generally good.
    return await run_tool_command_async(
        tool_name="openssl_command",
        command=cmd,
        input_data=input_bytes
        # Let the wrapper report RC and output, as success interpretation is complex.
    )


# Helper placeholder (needed for netstat direct call to _run_command_async)
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
    from .tool_utils import _run_command_async as util_run_async
    return await util_run_async(command, timeout, cwd, input_data, check, use_shell, env)
