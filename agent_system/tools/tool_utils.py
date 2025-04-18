import asyncio
import shlex
import logging
import sys
import subprocess # Need this for CalledProcessError
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import settings module - values will be accessed inside functions
from agent_system.config import settings

# --- Async Command Execution ---

async def _run_command_async(
    command: Union[List[str], str],
    timeout: Optional[int] = None, # Use None as default
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
    # Get timeout from settings if not provided explicitly
    effective_timeout = timeout if timeout is not None else settings.COMMAND_TIMEOUT

    cmd_display: str
    effective_cwd: Optional[Path] = Path(cwd).resolve() if cwd else Path.cwd()
    # Check if effective_cwd is a valid directory *before* proceeding
    if not effective_cwd or not effective_cwd.is_dir():
         err_msg = f"Working directory '{cwd or 'CWD'}' not found or not a directory (Resolved: {effective_cwd})."
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


    logging.info(f"Executing Async: {cmd_display} | CWD: {effective_cwd} | Shell={use_shell} | Timeout: {effective_timeout}")

    process = None # Ensure process is defined in outer scope
    try:
        process = await creator_func(
            program, *args, # Unpack args only for exec
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(effective_cwd), # Pass CWD as string
            env=env, # Pass custom environment if provided
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(input=input_data),
            timeout=effective_timeout # Use effective_timeout here
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
        logging.error(f"Error: Command timed out after {effective_timeout} seconds: {cmd_display}") # Use effective_timeout
        # Attempt to kill the timed-out process
        if process and process.returncode is None:
            try:
                process.kill()
                await process.wait() # Wait briefly for cleanup
                logging.warning(f"Killed timed-out process (PID: {process.pid})")
            except ProcessLookupError:
                 # Process already finished, ignore error
                 logging.warning(f"Timed-out process (PID: {process.pid}) already gone.")
            except Exception as kill_err:
                 # Log error trying to kill, but proceed with timeout result
                 logging.error(f"Error killing PID {process.pid}: {kill_err}")
        return False, b"", f"Error: Command timed out after {effective_timeout} seconds.".encode('utf-8', errors='replace'), -1
    except subprocess.CalledProcessError as e:
         # Raised only if check=True
         logging.error(f"Async command failed (RC {e.returncode}, check=True): {cmd_display}")
         return False, e.output or b"", e.stderr or b"", e.returncode
    except PermissionError as e:
        # Often related to CWD or executable permissions
        logging.error(f"Permission error running async: {cmd_display} in {effective_cwd}. Error: {e}")
        err_msg = f"Error: Permission denied ({effective_cwd}). Details: {e}"
        return False, b"", err_msg.encode('utf-8', errors='replace'), -1
    except Exception as e:
        logging.exception(f"Unexpected error running async command: {cmd_display}")
        return False, b"", f"Unexpected async error: {e}".encode('utf-8', errors='replace'), -1


# --- Sync Command Execution (Legacy/Wrapper) ---

def _run_command_sync_helper(
    command: Union[List[str], str],
    timeout: Optional[int] = None, # Use None as default
    cwd: Optional[Union[str, Path]] = None,
    input_data: Optional[str] = None, # Takes string for subprocess.run text mode
    check: bool = False,
    use_shell: bool = False,
    env: Optional[Dict[str, str]] = None
) -> Tuple[bool, str, str, int]:
    """Synchronous internal helper to run a command in a subprocess."""
    effective_timeout = timeout if timeout is not None else settings.COMMAND_TIMEOUT

    cmd_display: str
    effective_cwd: Optional[Path] = Path(cwd).resolve() if cwd else Path.cwd()
    if not effective_cwd or not effective_cwd.is_dir():
         err_msg = f"Working directory '{cwd or 'CWD'}' invalid (Resolved: {effective_cwd})."
         logging.error(err_msg); return False, "", err_msg, -1

    if use_shell:
        if not isinstance(command, str): err_msg = "Internal Error: Command must be str if use_shell=True."; logging.error(err_msg); return False, "", err_msg, -1
        cmd_display = command
    else:
        if not isinstance(command, list) or not command: err_msg = "Internal Error: Command must be list if use_shell=False."; logging.error(err_msg); return False, "", err_msg, -1
        try: command_str_list = [str(arg) for arg in command]
        except Exception as e: err_msg = f"Internal Error: Bad command parts: {e}"; logging.error(err_msg); return False, "", err_msg, -1
        cmd_display = ' '.join(shlex.quote(arg) for arg in command_str_list); command = command_str_list

    logging.info(f"Executing Sync: {cmd_display} | CWD: {effective_cwd} | Shell={use_shell} | Timeout: {effective_timeout}")
    try:
        process = subprocess.run(
            command, capture_output=True, text=True,
            timeout=effective_timeout, # Use effective_timeout
            cwd=str(effective_cwd), input=input_data, check=check,
            errors='replace', shell=use_shell, env=env
        )
        success = process.returncode == 0; stdout_str = process.stdout or ""; stderr_str = process.stderr or ""
        log_level = logging.getLogger().level
        if log_level <= logging.DEBUG or not success or stderr_str: logging.log(logging.INFO if success else logging.WARNING, f"Sync Finished (RC={process.returncode}). Success: {success}. Stdout: {stdout_str[:200]}... Stderr: {stderr_str[:200]}...")
        else: logging.info(f"Sync Finished (RC={process.returncode}). Success: {success}.")
        return success, stdout_str, stderr_str, process.returncode
    except FileNotFoundError: cmd_name = command.split()[0] if use_shell and isinstance(command, str) else (command[0] if isinstance(command, list) else "Unknown"); logging.error(f"Error: Command not found: {cmd_name}"); return False, "", f"Error: Command not found: {cmd_name}", -1
    except subprocess.TimeoutExpired: logging.error(f"Error: Command timed out after {effective_timeout}s: {cmd_display}"); return False, "", f"Error: Command timed out after {effective_timeout}s.", -1
    except subprocess.CalledProcessError as e: logging.error(f"Sync command failed (RC {e.returncode}, check=True): {cmd_display}"); return False, e.stdout or "", e.stderr or "", e.returncode
    except PermissionError as e: logging.error(f"Permission error running sync: {cmd_display} in {effective_cwd}. Error: {e}"); err_msg = f"Error: Permission denied ({effective_cwd}). Details: {e}"; return False, "", err_msg, -1
    except Exception as e: logging.exception(f"Unexpected error running sync command: {cmd_display}"); return False, "", f"Unexpected sync error: {e}", -1


# --- Async Tool Wrapper ---

async def run_tool_command_async(
    tool_name: str,
    command: Union[List[str], str],
    use_shell: bool = False,
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[int] = None, # Default None
    input_data: Optional[bytes] = None,
    check: bool = False,
    success_rc: Union[int, List[int]] = 0,
    failure_notes: Optional[Dict[int, str]] = None,
    env: Optional[Dict[str, str]] = None
) -> str:
    """Async wrapper for running external commands for tools."""
    effective_timeout = timeout if timeout is not None else settings.COMMAND_TIMEOUT # Get setting inside
    try:
        success, stdout_bytes, stderr_bytes, rc = await _run_command_async(
            command=command, timeout=effective_timeout, cwd=cwd, input_data=input_data,
            check=check, use_shell=use_shell, env=env
        )
        stdout = stdout_bytes.decode(sys.stdout.encoding or 'utf-8', 'replace')
        stderr = stderr_bytes.decode(sys.stderr.encoding or 'utf-8', 'replace')
        success_codes = success_rc if isinstance(success_rc, list) else [success_rc]
        is_successful = rc in success_codes
        cmd_display = command if use_shell and isinstance(command, str) else ' '.join(shlex.quote(str(c)) for c in command)
        result_str = f"Tool '{tool_name}' async execution finished (RC={rc}). Command: `{cmd_display}`\n"
        if is_successful:
            result_str += "Status: Success\n"; result_str += f"Stdout:\n```\n{stdout}\n```\n" if stdout else "Stdout: (empty)\n"
            if stderr: result_str += f"Stderr (Non-fatal):\n```\n{stderr}\n```\n"
        else:
            result_str += "Status: Failed\n"
            if failure_notes and rc in failure_notes: result_str += f"Note: {failure_notes[rc]}\n"
            if stdout: result_str += f"Stdout:\n```\n{stdout}\n```\n"
            if stderr: result_str += f"Stderr:\n```\n{stderr}\n```\n"
            elif not stdout and not stderr: result_str += "(No output on stdout or stderr)\n"
        return result_str.strip()
    except Exception as e: logging.exception(f"Unexpected error in run_tool_command_async for '{tool_name}': {e}"); return f"Tool '{tool_name}' failed: internal async wrapper error: {e}"


# --- Sync Tool Wrapper ---

def run_tool_command_sync(
    tool_name: str,
    command: Union[List[str], str],
    use_shell: bool = False,
    cwd: Optional[Union[str, Path]] = None,
    timeout: Optional[int] = None, # Default None
    input_data: Optional[str] = None,
    check: bool = False,
    success_rc: Union[int, List[int]] = 0,
    failure_notes: Optional[Dict[int, str]] = None,
    env: Optional[Dict[str, str]] = None
) -> str:
    """Synchronous wrapper for running external commands for tools."""
    effective_timeout = timeout if timeout is not None else settings.COMMAND_TIMEOUT # Get setting inside
    try:
        success, stdout, stderr, rc = _run_command_sync_helper(
            command=command, timeout=effective_timeout, cwd=cwd, input_data=input_data,
            check=check, use_shell=use_shell, env=env
        )
        success_codes = success_rc if isinstance(success_rc, list) else [success_rc]
        is_successful = rc in success_codes
        cmd_display = command if use_shell and isinstance(command, str) else ' '.join(shlex.quote(str(c)) for c in command)
        result_str = f"Tool '{tool_name}' sync execution finished (RC={rc}). Command: `{cmd_display}`\n"
        if is_successful:
            result_str += "Status: Success\n"; result_str += f"Stdout:\n```\n{stdout}\n```\n" if stdout else "Stdout: (empty)\n"
            if stderr: result_str += f"Stderr (Non-fatal):\n```\n{stderr}\n```\n"
        else:
            result_str += "Status: Failed\n"
            if failure_notes and rc in failure_notes: result_str += f"Note: {failure_notes[rc]}\n"
            if stdout: result_str += f"Stdout:\n```\n{stdout}\n```\n"
            if stderr: result_str += f"Stderr:\n```\n{stderr}\n```\n"
            elif not stdout and not stderr: result_str += "(No output on stdout or stderr)\n"
        return result_str.strip()
    except Exception as e: logging.exception(f"Unexpected error in run_tool_command_sync for '{tool_name}': {e}"); return f"Tool '{tool_name}' failed: internal sync wrapper error: {e}"


# --- User Confirmation ---

async def ask_confirmation_async(tool_name: str, args: Dict[str, Any]) -> bool:
    """Asynchronously asks the user for confirmation via stdin."""
    # (Implementation remains the same)
    if tool_name not in settings.HIGH_RISK_TOOLS: return True
    args_str = "\n".join([f"  {key}: {repr(value)}" for key, value in args.items()])
    prompt_message = (f"\n🚨 CONFIRMATION REQUIRED FOR HIGH-RISK TOOL 🚨\n" f"Tool: {tool_name}\n" f"Arguments:\n{args_str}\n" f"WARNING: High-risk operation ('{tool_name}' in HIGH_RISK_TOOLS).\n" f"Proceed? (yes/no): ")
    while True:
        try:
            confirm = await asyncio.to_thread(input, prompt_message)
            confirm = confirm.lower().strip()
            if confirm == "yes": print("Proceeding..."); return True
            elif confirm == "no": print("Operation cancelled by user."); return False
            else: print("Invalid input. Please enter 'yes' or 'no'."); prompt_message = "Proceed? (yes/no): "
        except EOFError: print("\nEOF received, cancelling."); return False
        except Exception as e: logging.error(f"Error during confirmation prompt: {e}"); print(f"\nConfirmation error: {e}. Cancelling."); return False
