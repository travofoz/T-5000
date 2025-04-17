import asyncio
import logging
import shlex
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async, ask_confirmation_async
from agent_system.config import settings

# --- SysAdmin Specific Tools ---

@register_tool
async def apt_command(subcommand: str, package: Optional[str] = None, options: Optional[List[str]] = None) -> str:
    """
    Runs an 'apt' subcommand (install, remove, update, etc.) via sudo.
    HIGH RISK. Requires confirmation (handled by agent).

    Args:
        subcommand: apt subcommand (e.g., 'install', 'update', 'remove').
        package: Package name (required for some subcommands like install/remove).
        options: Optional list of flags/options (e.g., ['-y', '--fix-broken']).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    # (Implementation remains the same as corrected version)
    logging.warning(f"Preparing apt command: {subcommand} {package or ''} {' '.join(options or [])}")
    needs_pkg = ["install", "remove", "purge", "reinstall", "show", "download", "source", "depends", "rdepends", "policy"]
    if subcommand in needs_pkg and not package: return f"Error: Package name is required for apt {subcommand}."
    base_command = ["apt", subcommand]
    if package: base_command.append(str(package))
    safe_options = []
    if options:
        if not isinstance(options, list): return "Error: apt 'options' must be a list of strings."
        for opt in options:
            opt_str = str(opt)
            if opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'): safe_options.append(opt_str)
            else: logging.warning(f"Skipping potentially unsafe apt option: {opt_str}")
        base_command.extend(safe_options)
    logging.info("apt command requires root privileges, preparing execute via sudo.")
    return await run_tool_command_async(
         tool_name="run_sudo_command (for apt)", command=["sudo", "--"] + base_command, timeout=600
    )

@register_tool
async def yum_command(subcommand: str, package: Optional[str] = None, options: Optional[List[str]] = None) -> str:
    """
    Runs a 'yum' or 'dnf' subcommand (install, remove, update, etc.) via sudo. Detects yum/dnf automatically.
    HIGH RISK. Requires confirmation (handled by agent).

    Args:
        subcommand: yum/dnf subcommand (e.g., 'install', 'update', 'remove').
        package: Package name (required for some subcommands).
        options: Optional list of flags/options (e.g., ['-y']).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    # (Implementation remains the same as corrected version)
    cmd_base = "dnf" if Path("/usr/bin/dnf").exists() else "yum"
    logging.warning(f"Preparing {cmd_base} command: {subcommand} {package or ''} {' '.join(options or [])}")
    needs_pkg = ["install", "remove", "reinstall", "downgrade", "mark", "erase", "info", "provides", "repoquery", "list", "search"]
    if subcommand in needs_pkg and not package and subcommand not in ["list", "search", "info"]: return f"Error: Package name may be required for {cmd_base} {subcommand}."
    base_command = [cmd_base, subcommand]
    if package: base_command.append(str(package))
    safe_options = []
    if options:
        if not isinstance(options, list): return f"Error: {cmd_base} 'options' must be a list of strings."
        for opt in options:
            opt_str = str(opt)
            if opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'): safe_options.append(opt_str)
            else: logging.warning(f"Skipping potentially unsafe {cmd_base} option: {opt_str}")
        base_command.extend(safe_options)
    logging.info(f"{cmd_base} command requires root privileges, preparing execute via sudo.")
    return await run_tool_command_async(
         tool_name=f"run_sudo_command (for {cmd_base})", command=["sudo", "--"] + base_command, timeout=600
    )

@register_tool
async def systemctl_command(action: str, service: str, use_sudo: bool = True) -> str:
    """
    Runs systemctl commands (start, stop, status, enable, disable, etc.).
    Can optionally run via sudo (default). HIGH RISK if sudo is used.
    Confirmation handled by agent (for the tool itself and potentially sudo).

    Args:
        action: systemctl action (e.g., 'start', 'status', 'enable').
        service: Name of the service unit (e.g., 'nginx.service', 'docker'). Can be omitted for actions like 'list-units'.
        use_sudo: Whether to run the command with sudo (default: True).

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    # (Implementation remains the same as corrected version, slight adjustment for service optionality)
    logging.info(f"Preparing systemctl command: Action='{action}', Service='{service or 'N/A'}', Sudo={use_sudo}")
    allowed_actions = ["status", "start", "stop", "restart", "reload", "enable", "disable", "is-active", "is-enabled", "show", "list-units", "list-unit-files", "daemon-reload"]
    if action not in allowed_actions: return f"Error: Invalid systemctl action '{action}'. Allowed: {', '.join(allowed_actions)}"
    actions_without_service = ["list-units", "list-unit-files", "daemon-reload"]
    base_command = ["systemctl", action]
    if action not in actions_without_service:
         if not service or not isinstance(service, str) or any(c in service for c in ';|&`$()<>'): return f"Error: Invalid or missing service name for action '{action}'."
         base_command.append(service)

    if use_sudo:
        logging.info(f"systemctl {action} requires privileges, preparing execute via sudo.")
        return await run_tool_command_async(
            tool_name=f"run_sudo_command (for systemctl {action})", command=["sudo", "--"] + base_command, timeout=60
        )
    else:
        logging.info(f"Running systemctl without sudo: {' '.join(base_command)}")
        success_codes = [0]
        if action in ["status", "is-active", "is-enabled"]: success_codes.extend([1, 3, 4])
        failure_notes={ 1: f"Service not found or other error.", 3: f"Service inactive or disabled.", 4: f"Service enabling/disabling failed/not found.", 5: f"Invalid arguments or operation.", 6: f"Service not installed or masked."} if action not in actions_without_service else None
        return await run_tool_command_async(
            tool_name="systemctl_command (no-sudo)", command=base_command, success_rc=success_codes, failure_notes=failure_notes
        )
