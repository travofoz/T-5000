import asyncio
import shlex
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import settings directly
from agent_system.config import settings

# --- Async Command Execution ---

async def _run_command_async(
    command: Union[List[str], str],
    timeout: int = settings.COMMAND_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None,
    input_data: Optional[bytes] = None, # Use bytes for input/output with subprocess
    check: bool = False, # If True, raises exception on non-zero exit
    use_shell: bool = False, # Explicit flag for using shell=True (HIGH RISK)
    env: Optional[Dict[str, str]] = None # Optional environment variables
) -> Tuple[bool, bytes, bytes, int]:
    """
    Asynchronous internal helper to run a command using asyncio.create_subprocess_exec/shell.
    WARNING: PATH SAFETY REMOVED. `cwd` can be anywhere. `use_shell=True` is EXTREMELY DANGEROUS.
    Requires command to be List[str] if use_shell=False.
    Returns stdout/stderr as bytes.
    """
    cmd_display: str
    effective_cwd: Optional[Path] = Path(cwd).resolve() if cwd else Path.cwd()
    if not effective_cwd.is_dir():
         err_msg = f"Working directory '{effective_cwd}' not found or not a directory."
         logging.error(err_msg)
         return False, b"", err_msg.encode('utf-8', errors='replace'), -1

    # Prepare command and display string based on shell usage
    if use_shell:
        if not isinstance(command, str):
            err_msg = "Internal Error: Command must be a string when use_shell=True."
            logging.error(err_msg)
            return False, b"", err_msg.encode('utf-8', errors='replace'), -1
        cmd_display = command # Keep raw string for display
        program = command
        args = () # No separate args when using shell=True with a string command
        creator_func = asyncio.create_subprocess_shell
    else:
        if not isinstance(command, list) or not command:
            err_msg = f"Internal Error: Command must be a non-empty list of strings when use_shell=False. Received: {type(command)}"
            logging.error(err_msg)
            return False, b"", err_msg.encode('utf-8', errors='replace'), -1
        # Ensure all parts are strings for subprocess
        try:
            command_str_list = [str(arg) for arg in command]
        except Exception as e:
            err_msg = f"Internal Error: Could not convert all command parts to strings: {e}"
            logging.error(err_msg)
            return False, b"", err_msg.encode('utf-8', errors='replace'), -1

        program = command_str_list[0]
        args = tuple(command_str_list[1:])
        cmd_display = ' '.join(shlex.quote(str(arg)) for arg in command_str_list) # Safe display string
        creator_func = asyncio.create_subprocess_exec


    logging.info(f"Executing Async: {cmd_display} | CWD: {effective_cwd} | Shell={use_shell}")

    process = None # Ensure process is defined in outer scope
    try:
        process = await creator_func(
            program, *args, # Unpack args only for exec
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(effective_cwd), # Pass CWD as string
            env=env, # Pass custom environment if provided
            # shell=use_shell is implicit in creator_func choice
            # limit= ? # Consider buffer limits for very large output?
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(input=input_data),
            timeout=timeout
        )
        rc = process.returncode
        assert rc is not None # Should be set after communicate

        success = rc == 0
        stdout_str = stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace') if stdout_bytes else ""
        stderr_str = stderr_bytes.decode(sys.stderr.encoding or 'utf-8', errors='replace') if stderr_bytes else ""

        # Log details based on success/output/level
        log_level = logging.getLogger().level
        if log_level <= logging.DEBUG or not success or stderr_bytes:
            logging.log(logging.INFO if success else logging.WARNING,
                        f"Async Finished (RC={rc}). Success: {success}. "
                        f"Stdout: {stdout_str[:200]}... Stderr: {stderr_str[:200]}...")
        else:
             logging.info(f"Async Finished (RC={rc}). Success: {success}.")

        if check and not success:
            raise subprocess.CalledProcessError(rc, cmd_display, output=stdout_bytes, stderr=stderr_bytes)

        return success, stdout_bytes, stderr_bytes, rc

    except FileNotFoundError:
        cmd_name = program # Use the program/string directly
        logging.error(f"Error: Command not found: {cmd_name}")
        return False, b"", f"Error: Command not found: {cmd_name}".encode('utf-8', errors='replace'), -1
    except asyncio.TimeoutError:
        logging.error(f"Error: Command timed out after {timeout} seconds: {cmd_display}")
        # Attempt to kill the timed-out process
        if process and process.returncode is None:
            try:
                process.kill()
                await process.wait() # Wait briefly for cleanup
                logging.warning(f"Killed timed-out process (PID: {process.pid})")
            except ProcessLookupError:
                 logging.warning(f"Timed-out process (PID: {process.pid}) already terminated.")
            except Exception as kill_err:
                 logging.error(f"Error trying to kill timed-out process (PID: {process.pid}): {kill_err}")
        return False, b"", f"Error: Command timed out after {timeout} seconds.".encode('utf-8', errors='replace'), -1
    except subprocess.CalledProcessError as e:
         # Raised only if check=True
         logging.error(f"Async command failed with RC {e.returncode} (check=True): {cmd_display}")
         return False, e.output or b"", e.stderr or b"", e.returncode
    except PermissionError as e:
        # Often related to CWD or executable permissions
        logging.error(f"Permission error running async command: {cmd_display} in {effective_cwd}. Error: {e}")
        err_msg = f"Error: Permission denied. Check permissions for command or working directory ({effective_cwd}). Details: {e}"
        return False, b"", err_msg.encode('utf-8', errors='replace'), -1
    except Exception as e:
        logging.exception(f"An unexpected error occurred while running async command: {cmd_display}")
        return False, b"", f"An unexpected error occurred: {e}".encode('utf-8', errors='replace'), -1

# --- Sync Command Execution (Legacy/Wrapper) ---
# Keep original sync helper for tools not yet migrated to async or needing sync execution.

def _run_command_sync_helper(
    command: Union[List[str], str], # String only allowed if use_shell=True
    timeout: int = settings.COMMAND_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None,
    input_data: Optional[str] = None, # Takes string for subprocess.run text mode
    check: bool = False, # If True, raises CalledProcessError on non-zero exit
    use_shell: bool = False, # Explicit flag for using shell=True
    env: Optional[Dict[str, str]] = None # Optional environment variables
) -> Tuple[bool, str, str, int]:
    """
    Synchronous internal helper to run a command in a subprocess.
    WARNING: PATH SAFETY REMOVED. `cwd` can be anywhere. `use_shell=True` is EXTREMELY DANGEROUS.
    Requires command to be List[str] if use_shell=False.
    Returns stdout/stderr as strings.
    """
    cmd_display: str
    effective_cwd: Optional[Path] = Path(cwd).resolve() if cwd else Path.cwd()
    if not effective_cwd.is_dir():
         err_msg = f"Working directory '{effective_cwd}' not found or not a directory."
         logging.error(err_msg)
         return False, "", err_msg, -1

    # Prepare command and display string based on shell usage
    if use_shell:
        if not isinstance(command, str):
            err_msg = "Internal Error: Command must be a string when use_shell=True."
            logging.error(err_msg)
            return False, "", err_msg, -1
        cmd_display = command # Keep the raw string for display/logging
    else:
        if not isinstance(command, list) or not command:
            err_msg = f"Internal Error: Command must be a non-empty list of strings when use_shell=False. Received: {type(command)}"
            logging.error(err_msg)
            return False, "", err_msg, -1
        # Ensure all parts are strings for subprocess
        try:
            command_str_list = [str(arg) for arg in command]
        except Exception as e:
            err_msg = f"Internal Error: Could not convert all command parts to strings: {e}"
            logging.error(err_msg)
            return False, "", err_msg, -1
        cmd_display = ' '.join(shlex.quote(str(arg)) for arg in command_str_list) # Create safe display string
        command = command_str_list # Use the validated string list

    logging.info(f"Executing Sync: {cmd_display} | CWD: {effective_cwd} | Shell={use_shell}")
    try:
        process = subprocess.run(
            command, # Should be list if shell=False, str if shell=True
            capture_output=True,
            text=True, # Work with strings
            timeout=timeout,
            cwd=str(effective_cwd), # Pass CWD as string
            input=input_data, # Pass input as string
            check=check,
            errors='replace', # How to handle decoding errors
            shell=use_shell, # Pass shell flag
            env=env # Pass custom environment if provided
        )
        success = process.returncode == 0
        stdout_str = process.stdout or ""
        stderr_str = process.stderr or ""

        # Log details based on success/output/level
        log_level = logging.getLogger().level
        if log_level <= logging.DEBUG or not success or stderr_str:
            logging.log(logging.INFO if success else logging.WARNING,
                        f"Sync Finished (RC={process.returncode}). Success: {success}. "
                        f"Stdout: {stdout_str[:200]}... Stderr: {stderr_str[:200]}...")
        else:
             logging.info(f"Sync Finished (RC={process.returncode}). Success: {success}.")

        return success, stdout_str, stderr_str, process.returncode
    except FileNotFoundError:
        # Extract command name more reliably
        cmd_name = command.split()[0] if use_shell and isinstance(command, str) else (command[0] if isinstance(command, list) and command else "Unknown")
        logging.error(f"Error: Command not found: {cmd_name}")
        return False, "", f"Error: Command not found: {cmd_name}", -1
    except subprocess.TimeoutExpired:
        logging.error(f"Error: Command timed out after {timeout} seconds: {cmd_display}")
        return False, "", f"Error: Command timed out after {timeout} seconds.", -1
    except subprocess.CalledProcessError as e:
         # Raised only if check=True
         logging.error(f"Sync command failed with RC {e.returncode} (check=True): {cmd_display}")
         return False, e.stdout or "", e.stderr or "", e.returncode
    except PermissionError as e:
        # Often related to CWD or executable permissions
        logging.error(f"Permission error running sync command: {cmd_display} in {effective_cwd}. Error: {e}")
        err_msg = f"Error: Permission denied. Check permissions for command or working directory ({effective_cwd}). Details: {e}"
        return False, "", err_msg, -1
    except Exception as e:
        logging.exception(f"An unexpected error occurred while running sync command: {cmd_display}")
        return False, "", f"An unexpected error occurred: {e}", -1

# --- Async Tool Wrapper ---

async def run_tool_command_async(
    tool_name: str,
    command: Union[List[str], str],
    use_shell: bool = False,
    cwd: Optional[Union[str, Path]] = None,
    timeout: int = settings.COMMAND_TIMEOUT,
    input_data: Optional[bytes] = None, # Expect bytes for async helper
    check: bool = False,
    success_rc: Union[int, List[int]] = 0, # RC(s) considered success
    failure_notes: Optional[Dict[int, str]] = None, # Map RC to specific failure notes
    env: Optional[Dict[str, str]] = None
) -> str:
    """
    Async wrapper for running external commands for tools.
    Uses _run_command_async, handles result formatting.

    Args:
        tool_name: Name of the tool for logging.
        command: Command list (shell=False) or string (shell=True).
        use_shell: Passed to _run_command_async.
        cwd: Working directory.
        timeout: Timeout in seconds.
        input_data: Input data (bytes) for the command.
        check: Raise exception on non-zero exit code (passed to helper).
        success_rc: Return code(s) considered successful (default: 0).
        failure_notes: Optional dictionary mapping specific non-success RCs to helpful notes.
        env: Optional dictionary of environment variables.

    Returns:
        Formatted string result suitable for LLM consumption.
    """
    try:
        success, stdout_bytes, stderr_bytes, rc = await _run_command_async(
            command=command,
            timeout=timeout,
            cwd=cwd,
            input_data=input_data,
            check=check,
            use_shell=use_shell,
            env=env
        )

        # Decode output using default system encoding or utf-8 fallback
        stdout = stdout_bytes.decode(sys.stdout.encoding or 'utf-8', errors='replace')
        stderr = stderr_bytes.decode(sys.stderr.encoding or 'utf-8', errors='replace')

        # Determine success based on return code(s)
        success_codes = success_rc if isinstance(success_rc, list) else [success_rc]
        is_successful = rc in success_codes
        cmd_display = command if use_shell and isinstance(command, str) else ' '.join(shlex.quote(str(c)) for c in command)

        # Build the result string
        result_str = f"Tool '{tool_name}' async execution finished (RC={rc}). Command: `{cmd_display}`\n"
        if is_successful:
            result_str += "Status: Success\n"
            if stdout: result_str += f"Stdout:\n```\n{stdout}\n```\n"
            else: result_str += "Stdout: (empty)\n"
            # Include stderr even on success if present (e.g., warnings)
            if stderr: result_str += f"Stderr (Non-fatal):\n```\n{stderr}\n```\n"
        else:
            result_str += "Status: Failed\n"
            # Add specific failure notes if available
            if failure_notes and rc in failure_notes:
                 result_str += f"Note: {failure_notes[rc]}\n"
            # Include stdout/stderr for debugging failures
            if stdout: result_str += f"Stdout:\n```\n{stdout}\n```\n"
            if stderr: result_str += f"Stderr:\n```\n{stderr}\n```\n"
            elif not stdout and not stderr: result_str += "(No output on stdout or stderr)\n" # Clarify if no output at all

        return result_str.strip()

    except Exception as e:
        # Catch errors from the wrapper itself or unexpected errors from the helper
        logging.exception(f"Unexpected error in run_tool_command_async for tool '{tool_name}': {e}")
        return f"Tool '{tool_name}' failed due to an internal async wrapper error: {e}"


# --- Sync Tool Wrapper (Legacy/Optional) ---
# Keep the original synchronous wrapper for tools that still use _run_command_sync_helper
# or potentially block otherwise.

def run_tool_command_sync(
    tool_name: str,
    command: Union[List[str], str],
    use_shell: bool = False,
    cwd: Optional[Union[str, Path]] = None,
    timeout: int = settings.COMMAND_TIMEOUT,
    input_data: Optional[str] = None, # Expect string for sync helper
    check: bool = False,
    success_rc: Union[int, List[int]] = 0, # RC(s) considered success
    failure_notes: Optional[Dict[int, str]] = None, # Map RC to specific failure notes
    env: Optional[Dict[str, str]] = None
) -> str:
    """
    Synchronous wrapper for running external commands for tools.
    Uses _run_command_sync_helper, handles result formatting.

    Args:
        tool_name: Name of the tool for logging.
        command: Command list (shell=False) or string (shell=True).
        use_shell: Passed to _run_command_sync_helper.
        cwd: Working directory.
        timeout: Timeout in seconds.
        input_data: Input data (string) for the command.
        check: Raise exception on non-zero exit code (passed to helper).
        success_rc: Return code(s) considered successful (default: 0).
        failure_notes: Optional dictionary mapping specific non-success RCs to helpful notes.
        env: Optional dictionary of environment variables.

    Returns:
        Formatted string result suitable for LLM consumption.
    """
    try:
        success, stdout, stderr, rc = _run_command_sync_helper(
            command=command,
            timeout=timeout,
            cwd=cwd,
            input_data=input_data,
            check=check,
            use_shell=use_shell,
            env=env
        )

        # Determine success based on return code(s)
        success_codes = success_rc if isinstance(success_rc, list) else [success_rc]
        is_successful = rc in success_codes
        cmd_display = command if use_shell and isinstance(command, str) else ' '.join(shlex.quote(str(c)) for c in command)

        # Build the result string (same logic as async wrapper)
        result_str = f"Tool '{tool_name}' sync execution finished (RC={rc}). Command: `{cmd_display}`\n"
        if is_successful:
            result_str += "Status: Success\n"
            if stdout: result_str += f"Stdout:\n```\n{stdout}\n```\n"
            else: result_str += "Stdout: (empty)\n"
            if stderr: result_str += f"Stderr (Non-fatal):\n```\n{stderr}\n```\n"
        else:
            result_str += "Status: Failed\n"
            if failure_notes and rc in failure_notes:
                 result_str += f"Note: {failure_notes[rc]}\n"
            if stdout: result_str += f"Stdout:\n```\n{stdout}\n```\n"
            if stderr: result_str += f"Stderr:\n```\n{stderr}\n```\n"
            elif not stdout and not stderr: result_str += "(No output on stdout or stderr)\n"

        return result_str.strip()

    except Exception as e:
        logging.exception(f"Unexpected error in run_tool_command_sync for tool '{tool_name}': {e}")
        return f"Tool '{tool_name}' failed due to an internal sync wrapper error: {e}"


# --- User Confirmation ---

async def ask_confirmation_async(tool_name: str, args: Dict[str, Any]) -> bool:
    """
    Asynchronously asks the user for confirmation via stdin.
    Handles EOFError gracefully. Runs input() in a separate thread.
    Checks against HIGH_RISK_TOOLS list from settings.
    """
    if tool_name not in settings.HIGH_RISK_TOOLS:
        return True # Auto-confirm if not in the list

    # Format arguments for display
    args_str = "\n".join([f"  {key}: {repr(value)}" for key, value in args.items()]) # Use repr for clarity

    # Construct the prompt message
    prompt_message = (
        f"\n🚨 CONFIRMATION REQUIRED FOR HIGH-RISK TOOL 🚨\n"
        f"Tool: {tool_name}\n"
        f"Arguments:\n{args_str}\n"
        f"WARNING: This operation is configured as high-risk ('{tool_name}' in HIGH_RISK_TOOLS).\n"
        f"It could have significant consequences (e.g., data loss, system changes, security risks).\n"
        f"Proceed? (yes/no): "
    )

    while True:
        try:
            # Run the blocking input() call in a separate thread
            confirm = await asyncio.to_thread(input, prompt_message)
            confirm = confirm.lower().strip()

            if confirm == "yes":
                print("Proceeding...")
                return True
            elif confirm == "no":
                print("Operation cancelled by user.")
                return False
            else:
                print("Invalid input. Please enter 'yes' or 'no'.")
                # Adjust the prompt slightly for retries
                prompt_message = "Proceed? (yes/no): "

        except EOFError:
            print("\nEOF received, cancelling operation.")
            return False
        except Exception as e:
             # Handle potential errors during input() or thread execution
             logging.error(f"Error during confirmation prompt: {e}")
             print(f"\nAn error occurred during confirmation: {e}. Cancelling operation.")
             return False
