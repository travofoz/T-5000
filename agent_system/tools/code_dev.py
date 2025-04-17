import asyncio
import logging
from pathlib import Path
from typing import List, Optional

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async
from agent_system.config import settings

@register_tool
async def run_flake8(path: str = ".") -> str:
    """
    Runs the flake8 Python linter on a specified file or directory path.
    Checks for PEP 8 style violations, programming errors, and complexity.

    Args:
        path: The file or directory path to lint. Defaults to the current working directory.

    Returns:
        Formatted string indicating linting results (no issues found or details of issues/errors).
    """
    try:
        # Resolve path synchronously (low block risk)
        target_path = Path(path).resolve()
        if not target_path.exists():
             return f"Error: Path '{path}' does not exist for flake8."
    except Exception as e:
        return f"Error resolving path '{path}': {e}"

    logging.info(f"Running flake8 on: {target_path}")
    command = ["flake8", str(target_path)]

    # flake8 exit code 0 = no issues, non-zero = issues found or tool error
    result = await run_tool_command_async(
        tool_name="run_flake8",
        command=command,
        success_rc=[0] # Only RC 0 means no linting issues found
    )

    # Add interpretation based on common usage
    if "Status: Success" in result: # Check if RC was 0
        return f"Flake8 found no linting issues in '{path}'."
    elif "RC=0" not in result: # Check if RC was non-zero (indicating issues or tool error)
        return f"Flake8 found issues or encountered an error in '{path}'.\n{result}"
    else: # Should not happen if success_rc=[0], but defensive check
         return f"Flake8 ran, but result interpretation unclear.\n{result}"

@register_tool
async def run_black(path: str = ".", check_only: bool = False) -> str:
    """
    Runs the Black Python code formatter/checker on a specified file or directory path.
    If check_only is False (default), files may be modified.
    WARNING: Modifies files if check_only=False.

    Args:
        path: The file or directory path to format or check. Defaults to the current working directory.
        check_only: If True, check if files would be reformatted without modifying them. If False, applies formatting. Default is False.

    Returns:
        Formatted string indicating formatting/checking results.
    """
    try:
        # Resolve path synchronously
        target_path = Path(path).resolve()
        if not target_path.exists():
            return f"Error: Path '{path}' does not exist for black."
    except Exception as e:
        return f"Error resolving path '{path}': {e}"

    action = '--check' if check_only else 'formatting'
    logging.info(f"Running black {action} on: {target_path}")
    command = ["black", str(target_path)]
    if check_only:
         command.append("--check")
    else:
         # Add warning if actually formatting
         logging.warning(f"Black applying formatting (modifying files) in: {target_path}")

    # Black exit codes: 0=no changes needed/made, 1=changes needed/made, >1=error
    # We treat both 0 and 1 as "successful execution" in terms of the tool running.
    result = await run_tool_command_async(
        tool_name="run_black",
        command=command,
        success_rc=[0, 1] # RC 0 = no changes, RC 1 = formatted/needs formatting
    )

    # Interpret result based on check_only flag and RC implicitly contained in result string
    if check_only:
        if "RC=0" in result: return f"Black check passed (no changes needed) for '{path}'."
        elif "RC=1" in result: return f"Black check failed (reformatting required) for '{path}'.\n{result}"
        else: return f"Black check encountered an error for '{path}'.\n{result}" # Error case (RC > 1)
    else: # Formatting mode
        if "RC=0" in result: return f"Black formatting applied (or files were already compliant) to '{path}'.\n{result}" # RC 0 can mean already formatted
        elif "RC=1" in result: return f"Black formatting applied successfully (files were modified) to '{path}'.\n{result}" # RC 1 means files *were* modified
        else: return f"Black formatting failed for '{path}'.\n{result}" # Error case (RC > 1)

@register_tool
async def run_pytest(path: str = ".") -> str:
    """
    Runs pytest tests discovered within a specified file or directory path.

    Args:
        path: The file or directory path for pytest discovery. Defaults to the current working directory.

    Returns:
        Formatted string indicating test results (pass, fail, errors, no tests found).
    """
    try:
        # Resolve path synchronously
        target_path = Path(path).resolve()
        if not target_path.exists():
            return f"Error: Path '{path}' does not exist for pytest."
    except Exception as e:
        return f"Error resolving path '{path}': {e}"

    logging.info(f"Running pytest, discovering tests in: {target_path}")
    # Run pytest targeting the path. Running from CWD usually helps with module discovery.
    command = ["pytest", str(target_path)]

    # Pytest exit codes:
    # 0: All tests passed
    # 1: Tests were collected and run but some tests failed
    # 2: Test execution was interrupted by the user
    # 3: Internal error occurred during test execution
    # 4: pytest command line usage error
    # 5: No tests were collected
    # We consider 0 (all pass) and 5 (no tests found) as "successful" tool execution states.
    return await run_tool_command_async(
        tool_name="run_pytest",
        command=command,
        cwd=Path.cwd(), # Run from script CWD for potentially better module discovery
        timeout=600, # Allow time for tests to run
        success_rc=[0, 5],
        failure_notes={
            1: "Some tests failed.",
            2: "Test execution interrupted.",
            3: "Internal pytest error.",
            4: "pytest command usage error.",
            5: "No tests were collected in the specified path." # Provide note for RC=5
        }
    )
