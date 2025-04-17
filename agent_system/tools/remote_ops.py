import asyncio
import logging
import shlex
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async, ask_confirmation_async
from agent_system.config import settings

@register_tool
async def ssh_command(host: str, command: str, user: Optional[str] = None, key_path: Optional[str] = None) -> str:
    """
    Executes a command string on a remote host via SSH using key-based authentication only.
    Uses BatchMode=yes and StrictHostKeyChecking=no for non-interactive execution (less secure).
    EXTREME RISK. Requires confirmation by default.

    Args:
        host: Hostname or IP address of the remote server.
        command: The command string to execute remotely.
        user: Optional username for SSH connection.
        key_path: Optional path to the private SSH key file (~/.ssh/id_* defaults used if omitted).

    Returns:
        Formatted string result including status, stdout, and stderr from the remote command.
    """
    # Confirmation is handled by the agent before calling this tool
    target = f"{user}@{host}" if user else host
    logging.warning(f"Preparing SSH command for {target}: '{command}'")
    ssh_cmd_list = ["ssh"]

    # Handle key path
    resolved_key_path_str: Optional[str] = None
    if key_path:
         if not isinstance(key_path, str): return "Error: ssh key_path must be a string."
         try:
             # Resolve path synchronously (low block risk)
             resolved_key_path = Path(key_path).expanduser().resolve(strict=True) # Check existence
             if not resolved_key_path.is_file(): return f"Error: SSH key file not found or not a file: {key_path}"
             resolved_key_path_str = str(resolved_key_path)
             ssh_cmd_list.extend(["-i", resolved_key_path_str])
             logging.info(f"Using SSH key: {resolved_key_path_str}")
         except FileNotFoundError: return f"Error: SSH key file not found: {key_path}"
         except Exception as e: return f"Error resolving SSH key path '{key_path}': {e}"

    # Add options for non-interactive execution
    ssh_cmd_list.extend([
        "-o", "ConnectTimeout=15",      # Connection timeout
        "-o", "BatchMode=yes",          # Never ask for password or other interaction
        "-o", "PasswordAuthentication=no", # Ensure password auth is disabled
        "-o", "StrictHostKeyChecking=no", # DANGEROUS: Auto-accept new host keys (avoids prompt)
        # Consider adding "-o UserKnownHostsFile=/dev/null" for extreme isolation, but very risky.
        "--", # Prevent misinterpretation of host/command as options
        target,
        command # The command to execute remotely
    ])

    return await run_tool_command_async(
        tool_name="ssh_command",
        command=ssh_cmd_list,
        timeout=300, # Command execution timeout (adjust as needed)
        success_rc=0, # Assume RC 0 from remote command is success
        failure_notes={
            # Common SSH exit codes
            1: "Generic error (e.g., bad command/args, file I/O error).",
            2: "Misuse of shell builtins (according to Bash documentation).",
            126: "Command invoked cannot execute (permission problem).",
            127: "Command not found.",
            128: "Invalid argument to exit.",
            # 128+N: Fatal error signal N. e.g. 130=Ctrl-C, 137=SIGKILL
            # 255 usually indicates a connection failure (timeout, refused, auth failed, host key issue).
            255: "SSH connection error (e.g., connection refused/timed out, permission denied/auth failed, host key verification failed)."
        }
    )


@register_tool
async def scp_command(source: str, destination: str, key_path: Optional[str] = None) -> str:
    """
    Copies files/directories via SCP using key-based authentication only.
    Uses BatchMode=yes and StrictHostKeyChecking=no. Recursive copy enabled (-r).
    EXTREME RISK. Requires confirmation by default.
    WARNING: No path restrictions for local or remote paths!

    Args:
        source: Source path (local or remote format user@host:path).
        destination: Destination path (local or remote format user@host:path).
        key_path: Optional path to the private SSH key file (~/.ssh/id_* defaults used if omitted).

    Returns:
        Formatted string result including status, stdout, and stderr from scp.
    """
    # Confirmation is handled by the agent before calling this tool
    logging.warning(f"Preparing SCP from '{source}' to '{destination}'. LOCAL/REMOTE PATH SAFETY DISABLED.")
    if not isinstance(source, str) or not isinstance(destination, str):
         return "Error: scp source and destination must be strings."

    scp_cmd_list = ["scp"]

    # Handle key path
    resolved_key_path_str: Optional[str] = None
    if key_path:
         if not isinstance(key_path, str): return "Error: scp key_path must be a string."
         try:
             resolved_key_path = Path(key_path).expanduser().resolve(strict=True)
             if not resolved_key_path.is_file(): return f"Error: SSH key file not found or not a file: {key_path}"
             resolved_key_path_str = str(resolved_key_path)
             scp_cmd_list.extend(["-i", resolved_key_path_str])
             logging.info(f"Using SSH key: {resolved_key_path_str}")
         except FileNotFoundError: return f"Error: SSH key file not found: {key_path}"
         except Exception as e: return f"Error resolving SSH key path '{key_path}': {e}"

    # Add options for non-interactive, recursive copy
    scp_cmd_list.extend([
        "-r", # Recursive copy
        "-B", # Batch mode (non-interactive)
        "-o", "ConnectTimeout=15",
        "-o", "PasswordAuthentication=no",
        "-o", "StrictHostKeyChecking=no", # DANGEROUS
        "--", # Prevent misinterpretation of source/dest as options
        source,
        destination
    ])

    return await run_tool_command_async(
        tool_name="scp_command",
        command=scp_cmd_list,
        timeout=600, # Longer timeout for potentially large transfers
        success_rc=0, # scp returns 0 on success
        failure_notes={
            1: "General scp error (e.g., file not found, permission denied, connection issue, network error)."
            # Other codes might indicate specific issues, but 1 is common.
        }
    )

@register_tool
async def ssh_agent_command(command_string: str) -> str:
    """
    Interacts with ssh-agent using 'ssh-add'. Only allows safe listing commands ('-l', '-L').

    Args:
        command_string: The command to run (must be 'ssh-add -l' or 'ssh-add -L').

    Returns:
        Formatted string result including status, stdout (key list), and stderr.
    """
    logging.info(f"Running ssh-agent command request: '{command_string}'")
    try:
        # Basic parsing, avoid complex shell features
        cmd_parts = shlex.split(command_string.strip())
    except ValueError as e:
        return f"Error parsing agent command string: {e}"

    # Validate command structure
    if not cmd_parts or cmd_parts[0] != "ssh-add":
        return f"Error: Unsupported agent command base: '{cmd_parts[0] if cmd_parts else ''}'. Only 'ssh-add' is supported."

    allowed_args = {"-l", "-L"}
    if len(cmd_parts) != 2 or cmd_parts[1] not in allowed_args:
         return f"Error: Unsupported or invalid arguments for ssh-add. Only '-l' or '-L' (list keys) are allowed by this tool. Received: '{command_string}'"

    # Execute the validated command
    return await run_tool_command_async(
        tool_name="ssh_agent_command",
        command=cmd_parts, # Pass the validated list ['ssh-add', '-l' or '-L']
        timeout=15, # Short timeout for listing keys
        success_rc=[0, 1], # RC 0 = keys listed, RC 1 = agent running but no keys (treat as success)
        failure_notes={
            1: "The agent has no identities (keys).", # Specific note for RC=1
            2: "Error connecting to agent (e.g., agent not running, permissions, communication error)."
        }
    )

@register_tool
async def ssh_add_command(key_path: Optional[str] = None) -> str:
    """
    Adds SSH keys (expected to be without passphrases) to ssh-agent via 'ssh-add'.
    Adds default keys (~/.ssh/id_*) if key_path is omitted.

    Args:
        key_path: Optional path to the specific private key file to add.

    Returns:
        Formatted string result including status, stdout (usually confirmation), and stderr.
    """
    logging.warning(f"Preparing ssh-add for key: {key_path or 'default keys (~/.ssh/id_*)'}")
    command = ["ssh-add"]
    resolved_key_path_str: Optional[str] = None

    if key_path:
         if not isinstance(key_path, str): return "Error: ssh_add key_path must be a string."
         try:
             # Resolve path synchronously (low block risk)
             resolved_key_path = Path(key_path).expanduser().resolve(strict=True)
             if not resolved_key_path.is_file(): return f"Error: SSH key file not found or not a file: {key_path}"
             resolved_key_path_str = str(resolved_key_path)
             command.append(resolved_key_path_str)
             logging.info(f"Targeting SSH key: {resolved_key_path_str}")
         except FileNotFoundError: return f"Error: SSH key file not found: {key_path}"
         except Exception as e: return f"Error resolving SSH key path '{key_path}': {e}"
    else:
         logging.info("Attempting to add default SSH keys.")
         # No specific path argument needed, ssh-add checks defaults.

    # Execute ssh-add
    # It will fail (RC 1) if the key requires a passphrase, which this tool doesn't support prompting for.
    # RC 2 indicates connection error or bad key format.
    return await run_tool_command_async(
        tool_name="ssh_add_command",
        command=command,
        timeout=20, # Slightly longer timeout in case agent is slow
        success_rc=0, # Only RC 0 means key was added successfully
        failure_notes={
            1: "Error adding identity: Key requires a passphrase (not supported by this tool) or agent refused operation.",
            2: "Error connecting to agent OR could not read key file (bad format/permissions)."
        }
    )
