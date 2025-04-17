import asyncio
import logging
import shlex
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async, ask_confirmation_async
from agent_system.config import settings

# Note: These tools execute external commands (curl, wget).
# For purely async Python HTTP requests, consider using httpx or aiohttp directly
# within tool implementations if preferred over subprocess calls.

@register_tool
async def curl_command(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[str] = None,
    output_file: Optional[str] = None
) -> str:
    """
    Makes HTTP requests via the 'curl' command. Supports various methods, headers, data,
    and optional output to ANY specified file path (WARNING: No path restrictions!).

    Args:
        url: The URL to request.
        method: HTTP method (GET, POST, PUT, DELETE, HEAD, OPTIONS, PATCH). Default is GET.
        headers: Optional dictionary of request headers (e.g., {"Authorization": "Bearer ..."}).
        data: Optional request body data (for POST, PUT, etc.). Use @filename to load data from a file.
        output_file: Optional path to save the response body to. If omitted, stdout is returned.

    Returns:
        Formatted string result including status, stdout/stderr, or success/failure message if saving to file.
    """
    if not url or url.startswith('-'):
        return f"Error: Invalid URL provided for curl: '{url}'"

    # Validate HTTP method
    safe_method = method.upper()
    allowed_methods = ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"]
    if safe_method not in allowed_methods:
         logging.warning(f"Invalid HTTP method '{method}' provided to curl_command. Defaulting to GET.")
         safe_method = "GET"

    logging.info(f"Preparing curl request: {safe_method} {url}")

    # Build command list safely
    command: List[str] = [
        "curl",
        "-sS", # Silent (-s) but show errors (-S)
        "-L", # Follow redirects
        "-X", safe_method
    ]

    # Add headers safely
    if headers:
        if not isinstance(headers, dict):
             return "Error: 'headers' argument must be a dictionary (object)."
        for k, v in headers.items():
            # Basic validation on header names/values to prevent command injection via headers
            if not isinstance(k, str) or not isinstance(v, str) or \
               any(c in k for c in ':\r\n') or any(c in v for c in '\r\n'):
                logging.warning(f"Skipping potentially invalid curl header: {k}: {v}")
                continue
            command.extend(["-H", f"{k}: {v}"])

    # Add data payload
    if data is not None:
        if not isinstance(data, str):
             # Data could be complex, try converting to string
             try: data = str(data)
             except Exception: return "Error: Could not convert 'data' argument to string."
        # Curl handles encoding. We pass it directly.
        # Using --data-raw might be slightly safer than --data to prevent @file interpretation if not intended
        # but let's stick to --data for broader compatibility/expectation.
        command.extend(["--data", data])

    # Handle output file
    resolved_output_path: Optional[Path] = None
    if output_file:
        if not isinstance(output_file, str):
            return "Error: 'output_file' argument must be a string path."
        try:
            # Resolve path and ensure parent directory exists (run synchronously for path ops)
            # Using Path operations directly as they are less likely to block significantly
            resolved_output_path = Path(output_file).resolve()
            resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
            logging.warning(f"curl saving output to: {resolved_output_path}")
            command.extend(["-o", str(resolved_output_path)])
        except PermissionError:
             return f"Error: Permission denied creating directory for curl output '{resolved_output_path.parent}'."
        except Exception as e:
            logging.exception(f"Error preparing curl output file path '{output_file}': {e}")
            return f"Error preparing curl output file path: {e}"

    # URL must be the last argument if options like -o are used
    command.append(url)

    # Execute the command
    result_str = await run_tool_command_async(
        tool_name="curl_command",
        command=command,
        timeout=120 # Reasonable timeout for most requests
    )

    # Check status and potentially remove incomplete file if output was specified
    # This relies on parsing the result string, which is fragile. A better approach
    # might return structured data from run_tool_command_async including the RC.
    # For now, use string parsing as per the original logic intent.
    is_success = "Status: Success" in result_str # Simple check
    if resolved_output_path:
        if is_success:
             # Add confirmation message about saved file
             return f"curl successful. Output saved to '{resolved_output_path}'.\n---\n{result_str}"
        else:
             # Attempt to remove potentially incomplete file on failure
             try:
                 resolved_output_path.unlink(missing_ok=True)
                 logging.info(f"Removed potentially incomplete curl output file: {resolved_output_path}")
                 return f"curl failed. Incomplete output file '{resolved_output_path}' removed (if it existed).\n---\n{result_str}"
             except OSError as unlink_err:
                 logging.warning(f"Could not remove potentially incomplete curl output file '{resolved_output_path}': {unlink_err}")
                 return f"curl failed. Could not remove incomplete output file '{resolved_output_path}'.\n---\n{result_str}"
    else:
        # No output file, just return the result string (contains stdout/stderr)
        return result_str


@register_tool
async def wget_command(url: str, output_directory: str = ".") -> str:
    """
    Downloads files via the 'wget' command to ANY specified directory.
    WARNING: No path restrictions!

    Args:
        url: URL of the file or resource to download.
        output_directory: Directory where the file(s) will be saved. Defaults to CWD.

    Returns:
        Formatted string result including status, stdout, and stderr.
    """
    if not url or url.startswith('-'):
        return f"Error: Invalid URL provided for wget: '{url}'"
    if not isinstance(output_directory, str):
        return "Error: 'output_directory' argument must be a string path."

    try:
        # Resolve target directory path (sync path ops are ok here)
        target_dir = Path(output_directory).resolve()
        logging.warning(f"wget downloading '{url}' to directory: {target_dir}")

        # Ensure directory exists (run sync mkdir, low block risk)
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return f"Error: Permission denied creating output directory '{target_dir}' for wget."
        except Exception as mkdir_e:
            logging.exception(f"Error creating output directory '{target_dir}' for wget: {mkdir_e}")
            return f"Error creating output directory for wget: {mkdir_e}"

        # Build command list
        # Use --directory-prefix for potentially safer path handling than -P
        # Add common options: -nv (non-verbose), --show-progress (if possible in non-tty?)
        # Let's use -nv for less noisy output by default.
        command = ["wget", "--nv", "--directory-prefix=" + str(target_dir), url]

        # Wget exit codes: 0=success, others indicate various errors (network, file, server, etc.)
        # Rely on wrapper output which includes stderr for error details.
        return await run_tool_command_async(
            tool_name="wget_command",
            command=command,
            timeout=600, # Long timeout for downloads
            success_rc=0 # Only 0 is guaranteed success
            # No specific failure notes, stderr usually explains wget errors well.
        )
    except Exception as e:
        logging.exception(f"Error preparing or running wget: {e}")
        return f"Error running wget: {e}"
