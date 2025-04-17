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
async def git_command(args: List[str], working_dir: str = ".") -> str:
    """
    Executes a 'git' command with specified arguments in a given directory.
    Handles 'clone' specifically by running in the parent directory.
    WARNING: Can modify files anywhere if not restricted. Confirmation may be required for risky subcommands if configured.

    Args:
        args: List of arguments for the git command (e.g., ['clone', 'https://...'], ['status'], ['commit', '-m', 'msg']).
        working_dir: Directory where the git command should run (or the parent dir for 'clone'). Defaults to CWD.

    Returns:
        Formatted string result including status, stdout, and stderr from git.
    """
    if not args:
        return "Error: No arguments provided for 'git' command."
    # Ensure args are strings
    safe_args = [str(arg) for arg in args]

    try:
        # Resolve target path (repo dir or clone destination)
        target_path = Path(working_dir).resolve()

        # Determine CWD for the command execution
        if safe_args[0] == 'clone':
            # For clone, run in the PARENT directory of the intended destination
            # The last arg of clone is typically the destination directory name
            clone_dest_name = safe_args[-1] if len(safe_args) > 1 else None
            # If a destination name is given, the CWD should be target_path.
            # If no destination name, git clones into a dir named after the repo in target_path.
            # Let's assume target_path IS the directory where the clone should happen / repo should reside.
            # Therefore, for clone, the effective CWD is target_path.parent IF target_path is the destination dir.
            # If target_path is just where the repo *will be* cloned into (using repo name), CWD is target_path.
            # Let's simplify: Assume working_dir is where the command should generally run from.
            # If cloning, git itself handles creating the subdirectory.
            cwd_for_run = target_path
            if not cwd_for_run.is_dir():
                 # Allow creating the parent dir for clone? Let's require it exists for now.
                 return f"Error: Working directory '{working_dir}' resolved to '{cwd_for_run}' which is not a valid directory for git clone."
            logging.warning(f"Running git clone. CWD: {cwd_for_run}. Destination determined by git.")
        else:
             # For other commands, run inside the resolved working_dir (should be repo root usually)
             cwd_for_run = target_path
             if not cwd_for_run.is_dir():
                 return f"Error: Working directory '{working_dir}' resolved to '{cwd_for_run}' which is not a valid directory."
             # Check if it's a git repo? Maybe not necessary, let git fail naturally.
             # if not (cwd_for_run / ".git").is_dir():
             #     logging.warning(f"Directory '{cwd_for_run}' does not appear to be a git repository root.")
             logging.info(f"Running git {' '.join(safe_args)} in: {cwd_for_run}")

        command = ["git"] + safe_args

        # Check if the specific git command requires confirmation
        # Example: Check for 'commit', 'push', 'reset', 'clean', 'merge' ?
        # This is complex as many commands can be destructive.
        # For now, rely on agent-level confirmation or global HIGH_RISK_TOOLS setting.
        # A more granular check could be added here if needed.
        # sub_command = safe_args[0]
        # if sub_command in ['commit', 'push', 'reset', 'clean', 'merge', 'rebase']:
        #      if not await ask_confirmation_async(f"git_{sub_command}", {"args": safe_args, "working_dir": str(cwd_for_run)}):
        #           return f"Git command '{sub_command}' cancelled by user."

        # Execute git command
        return await run_tool_command_async(
            tool_name="git_command",
            command=command,
            cwd=cwd_for_run,
            timeout=600, # Allow time for clones, pushes etc.
            success_rc=0, # Git usually returns 0 on success
            failure_notes={
                # Common git exit codes (can vary slightly)
                1: "Generic error (e.g., conflicts, file not found, bad object).",
                128: "Fatal error (e.g., repository not found, bad revision, permission denied, network issue, merge conflicts during operations like pull/rebase)."
            }
        )
    except Exception as e:
        logging.exception(f"Error running git command: {e}")
        return f"Error running git command: {e}"
