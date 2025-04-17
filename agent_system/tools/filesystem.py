import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import os # For permission checks in edit_file/create_directory if needed (though Path methods handle it)
import shlex # For tar/zip command construction

# Import the registration decorator and schema types
from . import register_tool, GenericToolSchema
# Import utility functions
from .tool_utils import run_tool_command_async, _run_command_async as util_run_async

# Note: For truly non-blocking file I/O, consider using the 'aiofiles' library.
# Here, we use asyncio.to_thread to wrap synchronous file operations for simplicity.

# === Core Filesystem Operations ===

@register_tool
async def read_file(file_path: str) -> str:
    """
    Asynchronously reads the content of ANY specified file path accessible by the user.
    WARNING: No path restrictions!

    Args:
        file_path: The path to the file to read.

    Returns:
        A string containing the file content prefixed with metadata, or an error message.
    """
    try:
        target_path = await asyncio.to_thread(Path(file_path).resolve)
        if not await asyncio.to_thread(target_path.is_file):
            return f"Error: File not found: {file_path} (Resolved: {target_path})"

        # Read file content in a separate thread
        content = await asyncio.to_thread(target_path.read_text, errors='replace')
        return f"Content of '{file_path}' (Size: {len(content)} bytes):\n```\n{content}\n```"
    except PermissionError:
        logging.error(f"Permission denied reading file: {file_path}")
        return f"Error: Permission denied reading file '{file_path}'."
    except Exception as e:
        logging.exception(f"Error reading file '{file_path}': {e}")
        return f"Error reading file '{file_path}': {e}"

@register_tool
async def list_files(directory_path: str = ".") -> str:
    """
    Asynchronously lists files and directories in ANY specified path (up to 1000 items).
    WARNING: No path restrictions!

    Args:
        directory_path: The path to the directory to list. Defaults to the current working directory.

    Returns:
        A string listing directory contents or an error message.
    """
    try:
        target_path = await asyncio.to_thread(Path(directory_path).resolve)
        if not await asyncio.to_thread(target_path.is_dir):
            return f"Error: Directory not found: {directory_path} (Resolved: {target_path})"

        # Use asyncio.to_thread for the potentially blocking iterdir() and checks
        def list_dir_sync(path: Path) -> Tuple[List[str], int]:
             sync_items = []
             sync_count = 0
             try:
                 for item in path.iterdir():
                     try:
                         is_dir = item.is_dir() # Check type synchronously within thread
                         item_type = "D" if is_dir else "F"
                         sync_items.append(f"[{item_type}] {item.name}")
                     except OSError as list_err:
                         sync_items.append(f"[E] {item.name} (Error: {list_err.strerror})")
                     sync_count += 1
                     if sync_count >= 1000:
                         sync_items.append("... (listing truncated at 1000 items)")
                         break
             except PermissionError: raise # Re-raise to be caught by outer try-except
             except Exception as e: logging.error(f"Error iterating directory '{path}': {e}"); sync_items.append(f"[ITER_ERROR] {e}")
             return sync_items, sync_count

        items, count = await asyncio.to_thread(list_dir_sync, target_path)

        if not items: return f"Directory '{directory_path}' is empty or inaccessible."
        return f"Contents of '{directory_path}' ({count} items found):\n" + "\n".join(items)
    except PermissionError:
        logging.error(f"Permission denied listing directory: {directory_path}")
        return f"Error: Permission denied listing directory '{directory_path}'."
    except Exception as e:
        logging.exception(f"Error listing directory '{directory_path}': {e}")
        return f"Error listing directory '{directory_path}': {e}"

@register_tool
async def create_directory(directory_path: str) -> str:
    """
    Asynchronously creates a directory (and any necessary parent directories) at ANY specified path.
    WARNING: No path restrictions!

    Args:
        directory_path: The path of the directory to create.

    Returns:
        A success message or an error message.
    """
    try:
        target_path = await asyncio.to_thread(Path(directory_path).resolve)
        # Run the potentially blocking mkdir in a separate thread
        await asyncio.to_thread(target_path.mkdir, parents=True, exist_ok=True)
        return f"Successfully created directory (or it already existed): {directory_path} (Resolved: {target_path})"
    except PermissionError:
        logging.error(f"Permission denied creating directory: {directory_path}")
        return f"Error: Permission denied creating directory '{directory_path}'."
    except Exception as e:
        logging.exception(f"Error creating directory '{directory_path}': {e}")
        return f"Error creating directory '{directory_path}': {e}"

@register_tool
async def edit_file(file_path: str, content: str) -> str:
    """
    Asynchronously writes or overwrites content to ANY specified file.
    This is a HIGH-RISK tool; confirmation is typically required by the calling agent.
    WARNING: No path restrictions!

    Args:
        file_path: The path to the file to write or overwrite.
        content: The full text content to write to the file.

    Returns:
        A success message indicating bytes written or an error message.
    """
    try:
        target_path = await asyncio.to_thread(Path(file_path).resolve)
        # Ensure parent directory exists (run in thread)
        await asyncio.to_thread(target_path.parent.mkdir, parents=True, exist_ok=True)
        # Write content in a separate thread
        await asyncio.to_thread(target_path.write_text, content, encoding='utf-8') # Specify encoding
        return f"Successfully wrote {len(content.encode('utf-8'))} bytes to '{file_path}' (Resolved: {target_path})." # Use encoded length
    except PermissionError:
        logging.error(f"Permission denied writing to file: {file_path}")
        return f"Error: Permission denied writing to file '{file_path}'."
    except Exception as e:
        logging.exception(f"Error writing to file '{file_path}': {e}")
        return f"Error writing to file '{file_path}': {e}"

# === Archive Tools ===

# Helper function (remains internal, no decorator)
def _resolve_paths_for_archive(
    working_dir: Union[str, Path],
    target_paths: List[str],
    archive_file: Optional[str] = None
) -> Tuple[Optional[Path], List[str], Optional[str]]:
    """Helper to resolve CWD and relative paths for archive tools."""
    try:
        cwd_path = Path(working_dir).resolve(strict=True)
        validated_rel_paths = []
        for p_str in target_paths:
            p = Path(p_str)
            abs_p = (cwd_path / p).resolve() if not p.is_absolute() else p.resolve()
            if not abs_p.exists(): return None, [], f"Error: Input path '{p_str}' (resolved to '{abs_p}') not found."
            try: rel_p = abs_p.relative_to(cwd_path); validated_rel_paths.append(str(rel_p))
            except ValueError: logging.warning(f"Path '{abs_p}' outside CWD '{cwd_path}'. Using absolute path."); validated_rel_paths.append(str(abs_p))
        return cwd_path, validated_rel_paths, None
    except FileNotFoundError: return None, [], f"Error: Working directory '{working_dir}' not found."
    except Exception as e: return None, [], f"Error resolving archive paths: {e}"

@register_tool
async def tar_command(action: str, archive_file: str, files_or_dirs: Optional[List[str]] = None, options: Optional[List[str]] = None, working_dir: str = ".") -> str:
    """
    Creates ('create') or extracts ('extract') tar archives using the 'tar' command.
    Auto-detects common compression formats (gz, bz2, xz). Operates relative to working_dir.
    WARNING: No path safety! Requires confirmation if listed as high-risk.

    Args:
        action: Action: 'create' or 'extract'.
        archive_file: Path to the tar archive file.
        files_or_dirs: List of files/directories to add (for 'create'). Ignored for 'extract'.
        options: Optional list of additional tar flags (e.g., ['-v', '--exclude=*.log']).
        working_dir: Directory from which tar operates. Defaults to CWD.

    Returns:
        Formatted string result from tar.
    """
    # (Implementation remains the same as previous version, including decoration)
    try:
        cwd_path, _, error = _resolve_paths_for_archive(working_dir, [])
        if error: return error
        archive_path_obj = Path(archive_file)
        archive_path_abs = (cwd_path / archive_path_obj).resolve() if not archive_path_obj.is_absolute() else archive_path_obj.resolve()
        try: archive_arg = str(archive_path_abs.relative_to(cwd_path))
        except ValueError: archive_arg = str(archive_path_abs)
        logging.info(f"Preparing tar command: Action='{action}', Archive='{archive_arg}', CWD='{cwd_path}'")
        base_cmd: List[str] = []; effective_options = list(options or [])
        if action == "create":
            if not files_or_dirs: return "Error: Must specify files/dirs for tar create."
            _, validated_rel_paths, error = _resolve_paths_for_archive(cwd_path, files_or_dirs)
            if error: return error
            if not validated_rel_paths: return "Error: No valid input files/dirs resolved for tar create."
            archive_path_abs.parent.mkdir(parents=True, exist_ok=True)
            base_cmd = ["tar", "-cf", archive_arg] + validated_rel_paths
        elif action == "extract":
            if not archive_path_abs.is_file(): return f"Error: Archive '{archive_file}' not found at {archive_path_abs}."
            base_cmd = ["tar", "-xf", archive_arg]
        else: return "Error: Invalid tar action. Use 'create' or 'extract'."
        ext = ''.join(archive_path_abs.suffixes).lower()
        if ".gz" in ext or ".tgz" in ext: effective_options.append('-z')
        elif ".bz2" in ext or ".tbz2" in ext: effective_options.append('-j')
        elif ".xz" in ext or ".txz" in ext: effective_options.append('-J')
        flag_chars = set(base_cmd[1][1:])
        for opt in effective_options:
            if opt.startswith('-') and len(opt) > 1 and not opt.startswith('--'): flag_chars.update(opt[1:])
        command = ["tar"]
        action_flag = 'c' if action == 'create' else 'x'; other_flags = sorted(list(flag_chars - {action_flag}))
        command.append(f"-{action_flag}{''.join(other_flags)}")
        command.extend([opt for opt in effective_options if not (opt.startswith('-') and len(opt) > 1 and not opt.startswith('--'))])
        command.extend(base_cmd[2:])
        return await run_tool_command_async(
            tool_name="tar_command", command=command, cwd=cwd_path, timeout=600
        )
    except FileNotFoundError: return f"Error: Working directory '{working_dir}' not found for tar."
    except Exception as e: logging.exception(f"Error running tar: {e}"); return f"Error running tar: {e}"

@register_tool
async def zip_command(archive_file: str, files_or_dirs: List[str], working_dir: str = ".") -> str:
    """
    Creates a zip archive (-r) from files/dirs relative to working_dir.
    WARNING: No path safety! Requires confirmation if listed as high-risk.

    Args:
        archive_file: Path to the zip archive file to create.
        files_or_dirs: List of files/directories to add.
        working_dir: Directory from which zip operates. Defaults to CWD.

    Returns:
        Formatted string result from zip.
    """
    # (Implementation remains the same as previous version, including decoration)
    try:
        if not files_or_dirs or not isinstance(files_or_dirs, list): return "Error: Must specify a list of files/dirs for zip."
        cwd_path, validated_rel_paths, error = _resolve_paths_for_archive(working_dir, files_or_dirs)
        if error: return error
        if not validated_rel_paths: return "Error: No valid input files/dirs resolved for zip."
        archive_path_obj = Path(archive_file)
        archive_path_abs = (cwd_path / archive_path_obj).resolve() if not archive_path_obj.is_absolute() else archive_path_obj.resolve()
        try: archive_arg = str(archive_path_abs.relative_to(cwd_path))
        except ValueError: archive_arg = str(archive_path_abs)
        logging.info(f"Preparing zip command: Archive='{archive_arg}', CWD='{cwd_path}'")
        archive_path_abs.parent.mkdir(parents=True, exist_ok=True)
        command = ["zip", "-r", archive_arg] + validated_rel_paths
        return await run_tool_command_async(
            tool_name="zip_command", command=command, cwd=cwd_path, timeout=600
        )
    except FileNotFoundError: return f"Error: Working directory '{working_dir}' not found for zip."
    except Exception as e: logging.exception(f"Error running zip: {e}"); return f"Error running zip: {e}"

@register_tool
async def unzip_command(archive_file: str, extract_dir: Optional[str] = None, working_dir: str = ".") -> str:
    """
    Extracts a zip archive (-o overwrite) to specified path or working_dir.
    WARNING: No path safety! Requires confirmation if listed as high-risk.

    Args:
        archive_file: Path to the zip archive file to extract.
        extract_dir: Optional directory to extract files into. Defaults to working_dir.
        working_dir: Directory context. Defaults to CWD.

    Returns:
        Formatted string result from unzip.
    """
    # (Implementation remains the same as previous version, including decoration)
    try:
        cwd_path, _, error = _resolve_paths_for_archive(working_dir, [])
        if error: return error
        archive_path_obj = Path(archive_file)
        archive_path_abs = (cwd_path / archive_path_obj).resolve() if not archive_path_obj.is_absolute() else archive_path_obj.resolve()
        if not archive_path_abs.is_file(): return f"Error: Archive '{archive_file}' not found at {archive_path_abs}."
        try: archive_arg = str(archive_path_abs.relative_to(cwd_path))
        except ValueError: archive_arg = str(archive_path_abs)
        target_dir_abs: Path; extract_dest_arg: Optional[str] = None
        if extract_dir:
            extract_path_obj = Path(extract_dir)
            target_dir_abs = (cwd_path / extract_path_obj).resolve() if not extract_path_obj.is_absolute() else extract_path_obj.resolve()
            try: extract_dest_arg = str(target_dir_abs.relative_to(cwd_path))
            except ValueError: extract_dest_arg = str(target_dir_abs)
        else: target_dir_abs = cwd_path
        logging.info(f"Preparing unzip command: Archive='{archive_arg}', Target Dir='{target_dir_abs}', CWD='{cwd_path}'")
        target_dir_abs.mkdir(parents=True, exist_ok=True)
        command = ["unzip", "-o", archive_arg]
        if extract_dest_arg: command.extend(["-d", extract_dest_arg])
        return await run_tool_command_async(
            tool_name="unzip_command", command=command, cwd=cwd_path, timeout=600
        )
    except FileNotFoundError: return f"Error: Working directory '{working_dir}' or archive '{archive_file}' not found for unzip."
    except Exception as e: logging.exception(f"Error running unzip: {e}"); return f"Error running unzip: {e}"
