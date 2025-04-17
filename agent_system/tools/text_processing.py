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
async def grep_files(pattern: str, path: str = ".") -> str:
    """
    Searches for a pattern recursively within files in a specified directory using 'grep'.
    Ignores binary files (-I), shows line numbers (-n), and suppresses filesystem errors (-s).
    WARNING: No path restrictions! Operates on ANY specified directory path.

    Args:
        pattern: The regex pattern (ERE) to search for.
        path: Directory path to search within. Defaults to the current working directory.

    Returns:
        Formatted string result including status, stdout (matching lines), and stderr.
    """
    try:
        # Resolve path synchronously (low block risk)
        search_path = Path(path).resolve()
        if not search_path.is_dir():
             return f"Error: Search path '{path}' is not a valid directory or is inaccessible."
    except Exception as e:
        return f"Error resolving search path '{path}': {e}"

    logging.info(f"Grepping for pattern '{pattern}' in directory: {search_path}")

    # Build command using grep -E for extended regex, and other flags
    # Use -- to handle patterns starting with -
    # Use -r for recursive, -n for line numbers, -I to ignore binaries, -s to suppress file errors
    command = ["grep", "-E", "-r", "-n", "-I", "-s", "--", pattern, str(search_path)]

    # grep exit codes: 0 = found, 1 = not found, >1 = error
    return await run_tool_command_async(
        tool_name="grep_files",
        command=command,
        success_rc=[0, 1], # Treat "not found" (RC 1) as a successful execution of the tool
        failure_notes={
            1: "No lines matching the pattern were found.", # Provide specific note for RC=1
            # Other RCs (>1) indicate errors like bad regex or filesystem issues not suppressed by -s.
        }
    )


@register_tool
async def find_files(name_pattern: Optional[str] = None, path: str = ".") -> str:
    """
    Finds files matching a name pattern within a specified directory using 'find'.
    Searches recursively up to a maximum depth of 5 levels by default.
    WARNING: No path restrictions! Operates on ANY specified directory path.

    Args:
        name_pattern: Glob pattern for the filename (e.g., '*.txt', 'my_file.*'). If omitted, lists all files/dirs.
        path: Directory path to start the search from. Defaults to the current working directory.

    Returns:
        Formatted string result including status, stdout (list of found paths), and stderr.
    """
    try:
        # Resolve path synchronously
        search_path = Path(path).resolve()
        if not search_path.is_dir():
            return f"Error: Search path '{path}' is not a valid directory or is inaccessible."
    except Exception as e:
        return f"Error resolving search path '{path}': {e}"

    logging.info(f"Finding files matching '{name_pattern or '*'}' in directory: {search_path}")

    # Build base command
    command = ["find", str(search_path), "-maxdepth", "5"] # Limit depth

    # Add name pattern if provided
    if name_pattern:
        if not isinstance(name_pattern, str):
             return "Error: 'name_pattern' argument must be a string."
        # Basic validation: prevent obvious shell metacharacters beyond globs?
        potentially_unsafe = ';|&`$()<>{}\\!' # Exclude *?[] which are valid for -name
        if any(c in name_pattern for c in potentially_unsafe):
            logging.warning(f"Potentially complex/unsafe find pattern detected: {name_pattern}. Proceeding with caution.")
            # Let find handle it, but log warning. Non-shell execution prevents direct injection.
        command.extend(["-name", name_pattern])

    # find exit code 0 = success (even if nothing found), >0 = error
    return await run_tool_command_async(
        tool_name="find_files",
        command=command,
        success_rc=0
        # Failure notes aren't very specific for find errors, rely on stderr.
    )


@register_tool
async def sed_command(script: str, file_path: Optional[str] = None, input_text: Optional[str] = None) -> str:
    """
    Processes text using a 'sed' script. Operates either on input text provided directly
    or by reading from a specified file (read-only mode).

    Args:
        script: The sed script to execute (e.g., 's/foo/bar/g', '/^#/d').
        file_path: Path to the input file. Cannot be used if input_text is provided. The file itself is NOT modified.
        input_text: Text content to process directly. Cannot be used if file_path is provided.

    Returns:
        Formatted string result including status, stdout (processed text), and stderr.
    """
    if file_path and input_text:
        return "Error: Cannot provide both file_path and input_text to sed_command."
    if not file_path and input_text is None: # Check for None explicitly as empty string is valid input
        return "Error: Must provide either file_path or input_text to sed_command."
    if not script or not isinstance(script, str):
        return "Error: A non-empty sed 'script' string is required."

    command = ["sed", script]
    input_bytes: Optional[bytes] = None
    cwd: Optional[Path] = None
    target_desc = "input text"

    if file_path:
        if not isinstance(file_path, str): return "Error: file_path must be a string."
        try:
             # Resolve file path synchronously
             file_target_path = Path(file_path).resolve(strict=True) # Ensure exists
             if not file_target_path.is_file():
                  return f"Error: Input path is not a file: {file_path}"
             # Pass absolute path to sed command for clarity
             command.append(str(file_target_path))
             target_desc = f"file '{file_path}'"
             # Run from script's CWD, not necessarily file's CWD, for consistency
             cwd = Path.cwd()
             logging.info(f"Running sed script on file: {file_target_path}")
        except FileNotFoundError:
             return f"Error: Input file not found: {file_path}"
        except Exception as e:
             return f"Error resolving file path '{file_path}': {e}"
    else: # Use input_text
         if not isinstance(input_text, str): return "Error: input_text must be a string."
         try:
              # Encode input text to bytes for async helper
              input_bytes = input_text.encode('utf-8')
              logging.info(f"Running sed script on provided input text (length: {len(input_bytes)} bytes).")
              cwd = Path.cwd()
         except Exception as e:
              return f"Error encoding input_text for sed: {e}"

    # Execute sed command
    return await run_tool_command_async(
        tool_name="sed_command",
        command=command,
        input_data=input_bytes, # Pass encoded bytes if using input_text
        cwd=cwd, # Run from consistent CWD
        success_rc=0 # sed usually returns 0 on success
    )
