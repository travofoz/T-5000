import asyncio
import logging
from pathlib import Path
from typing import Optional

# Import the registration decorator and schema types
from . import register_tool, GenericToolSchema

# Note: For truly non-blocking file I/O, consider using the 'aiofiles' library.
# Here, we use asyncio.to_thread to wrap synchronous file operations for simplicity.

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
            return f"Error: File not found: {file_path}"

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
            return f"Error: Directory not found: {directory_path}"

        items = []
        count = 0
        # Use asyncio.to_thread for the potentially blocking iterdir() and checks
        def list_dir_sync(path: Path) -> Tuple[List[str], int]:
             sync_items = []
             sync_count = 0
             try:
                 for item in path.iterdir():
                     try:
                         item_type = "D" if item.is_dir() else "F"
                         sync_items.append(f"[{item_type}] {item.name}")
                     except OSError as list_err: # Handle potential permission errors listing item types
                         sync_items.append(f"[E] {item.name} (Error: {list_err.strerror})")
                     sync_count += 1
                     if sync_count >= 1000: # Limit listing size
                         sync_items.append("... (listing truncated at 1000 items)")
                         break
             except PermissionError:
                 # Re-raise to be caught by outer try-except
                 raise
             except Exception as e:
                 # Log the specific error during iteration if needed
                 logging.error(f"Error iterating directory '{path}': {e}")
                 sync_items.append(f"[ITER_ERROR] {e}")
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

        return f"Successfully created directory (or it already existed): {directory_path}"
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
        bytes_written = await asyncio.to_thread(target_path.write_text, content)

        return f"Successfully wrote {len(content)} bytes to '{file_path}'." # write_text doesn't return bytes written, use len(content)
    except PermissionError:
        logging.error(f"Permission denied writing to file: {file_path}")
        return f"Error: Permission denied writing to file '{file_path}'."
    except Exception as e:
        logging.exception(f"Error writing to file '{file_path}': {e}")
        return f"Error writing to file '{file_path}': {e}"
