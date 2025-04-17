import asyncio
import logging
import shlex
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import os # Needed for permission checks

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async, ask_confirmation_async
from agent_system.config import settings

@register_tool
async def gdb_mi_command(executable_path: str, mi_command: str, args: Optional[List[str]] = None) -> str:
    """
    Executes a single GDB Machine Interface (MI) command string on ANY specified executable.
    Uses GDB's '--interpreter=mi2 --batch' mode for non-interactive execution.
    HIGH RISK: Interacts directly with executable code and processes. Requires confirmation by default.

    Args:
        executable_path: Path to the target executable file.
        mi_command: The GDB MI command to execute (e.g., '-break-insert main', '-exec-run', '-data-read-memory 0xADDR length').
        args: Optional list of arguments to pass to the executable when run under GDB.

    Returns:
        Formatted string result including status, GDB MI output (stdout), and any stderr messages.
    """
    # (Implementation remains the same as corrected version)
    logging.warning(f"Preparing GDB MI command: Executable='{executable_path}', MI Command='{mi_command}', Args='{args or []}'")
    try:
        exe_path = Path(executable_path).resolve()
        if not exe_path.is_file(): return f"Error: Executable not found: {executable_path} ({exe_path})"
        if not os.access(exe_path, os.X_OK): return f"Error: Target is not executable: {executable_path} ({exe_path})"
        gdb_cmd = ["gdb", "--interpreter=mi2", "--batch", "-q", "-ex", str(mi_command)]
        gdb_cmd.append("--args"); gdb_cmd.append(str(exe_path))
        if args: safe_args = [str(a) for a in args]; gdb_cmd.extend(safe_args)
        result_str = await run_tool_command_async(
            tool_name="gdb_mi_command", command=gdb_cmd, cwd=exe_path.parent, timeout=120, success_rc=0
        )
        if "^error" in result_str: return f"GDB MI command '{mi_command}' reported an error (see GDB output).\n---\n{result_str}"
        elif "^done" in result_str or "^running" in result_str or "^connected" in result_str or "=breakpoint" in result_str: return f"GDB MI command '{mi_command}' executed (likely succeeded, see GDB output).\n---\n{result_str}"
        elif "^exit" in result_str: return f"GDB MI command '{mi_command}' executed, GDB exited.\n---\n{result_str}"
        else: return f"GDB MI command '{mi_command}' executed. Analyze GDB output:\n---\n{result_str}"
    except FileNotFoundError: return "Error: 'gdb' command not found. Is GDB installed and in PATH?"
    except Exception as e: logging.exception(f"Error running GDB MI command: {e}"); return f"Error running GDB MI command: {e}"
