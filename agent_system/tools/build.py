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
async def make_command(
    target: Optional[str] = None,
    options: Optional[List[str]] = None,
    working_dir: str = "."
) -> str:
    """
    Runs the 'make' command with optional target and options in a specified directory.
    Looks for 'Makefile' or 'makefile'.
    HIGH RISK: Can execute arbitrary commands defined in the Makefile.
    Requires confirmation by default.

    Args:
        target: Optional make target to build (e.g., 'all', 'install'). Defaults to the default target.
        options: Optional list of make flags or variable assignments (e.g., ['-j4', 'CFLAGS=-O2']).
        working_dir: Directory containing the Makefile. Defaults to CWD.

    Returns:
        Formatted string result including status, stdout, and stderr from make.
    """
    # Confirmation handled by the agent.
    logging.warning(f"Preparing make command: Target='{target or 'default'}', Options='{options or []}', Dir='{working_dir}'")

    try:
        # Resolve working directory synchronously (low block risk)
        build_dir = Path(working_dir).resolve()
        if not build_dir.is_dir():
             return f"Error: Working directory '{working_dir}' not found or not a directory."

        # Check for Makefile (sync OK for file checks)
        makefile_path = build_dir / "Makefile"
        makefile_path_lower = build_dir / "makefile"
        if not makefile_path.is_file() and not makefile_path_lower.is_file():
            return f"Error: Makefile not found in directory '{build_dir}'."
        logging.info(f"Found makefile in: {build_dir}")

        command = ["make"]

        # Validate and add options
        safe_options = []
        if options:
             if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
             for opt in options:
                 opt_str = str(opt)
                 # Allow simple flags (-j4) or assignments (VAR=val), block complex chars
                 if (opt_str.startswith('-') or '=' in opt_str) and not any(c in opt_str for c in ';|&`$()<>'):
                     safe_options.append(opt_str)
                 else:
                     logging.warning(f"Skipping potentially unsafe or invalid make option: {opt_str}")
             command.extend(safe_options)

        # Validate and add target
        safe_target = None
        if target:
            if not isinstance(target, str): return "Error: 'target' argument must be a string."
            # Basic validation for target - avoid obvious shell metacharacters
            if any(c in target for c in ';|&`$()<>*?![]{}'):
                logging.warning(f"Potentially complex make target specified: {target}. Using as is, but be cautious.")
                safe_target = target # Pass potentially complex target, rely on non-shell execution
            else:
                 safe_target = target
            if safe_target:
                 command.append(safe_target)

        # Execute make
        # Make exit code 0 = success, 1 = warnings (GNU make), 2 = errors
        return await run_tool_command_async(
            tool_name="make_command",
            command=command,
            cwd=build_dir, # Run make in the specified directory
            timeout=1800, # Long timeout for potentially complex builds
            success_rc=[0, 1], # Treat RC 1 (warnings) as non-fatal for tool success status
            failure_notes={
                 1: "Make completed with warnings.",
                 2: "Make failed with errors. Check output.",
            }
        )

    except FileNotFoundError: # Should be caught by build_dir check, but as fallback
        return f"Error: Build directory '{working_dir}' not found."
    except Exception as e:
        logging.exception(f"Error running make: {e}")
        return f"Error running make: {e}"

@register_tool
async def cmake_configure(
    source_dir: str,
    build_dir: str = "build",
    options: Optional[List[str]] = None
) -> str:
    """
    Configures a CMake project using 'cmake'. Runs from the specified build directory.
    Creates the build directory if it doesn't exist.

    Args:
        source_dir: Path to the source directory containing CMakeLists.txt.
        build_dir: Path to the build directory. Relative paths are interpreted relative to the CWD *unless* it starts with '../' etc suggesting relation to source. Defaults to 'build' directory inside CWD.
        options: Optional list of CMake options (e.g., ['-DCMAKE_BUILD_TYPE=Release', '-G', 'Ninja']).

    Returns:
        Formatted string result including status, stdout, and stderr from cmake.
    """
    logging.info(f"Preparing cmake configure: Source='{source_dir}', Build='{build_dir}', Options='{options or []}'")

    try:
        # Resolve source directory (must exist)
        src_dir_abs = Path(source_dir).resolve(strict=True)
        if not (src_dir_abs / "CMakeLists.txt").is_file():
            return f"Error: CMakeLists.txt not found in source directory '{src_dir_abs}'."

        # Resolve build directory relative to CWD initially
        build_dir_path = Path(build_dir)
        if build_dir_path.is_absolute():
            build_dir_abs = build_dir_path.resolve()
        else:
            # Assume relative to CWD by default
            build_dir_abs = Path.cwd() / build_dir_path
            build_dir_abs = build_dir_abs.resolve() # Get absolute path

        logging.warning(f"Creating/using CMake build directory: {build_dir_abs}")
        # Create build directory (sync OK)
        try:
            build_dir_abs.mkdir(parents=True, exist_ok=True)
        except PermissionError:
             return f"Error: Permission denied creating CMake build directory '{build_dir_abs}'."
        except Exception as mkdir_e:
             return f"Error creating CMake build directory '{build_dir_abs}': {mkdir_e}"

        command = ["cmake"]

        # Validate and add options
        safe_options = []
        if options:
             if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
             for opt in options:
                 opt_str = str(opt)
                 # Allow -DVAR=VALUE, -G "Generator Name", etc. Block complex chars.
                 # Be cautious with quotes within options, shlex might handle them?
                 if opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'):
                     safe_options.append(opt_str)
                 # Allow generator names which might contain spaces
                 elif safe_options and safe_options[-1] == "-G" and not any(c in opt_str for c in ';|&`$()<>'):
                      safe_options.append(opt_str)
                 else:
                     logging.warning(f"Skipping potentially unsafe or invalid cmake option: {opt_str}")
             command.extend(safe_options)

        # Add source directory path relative to the build directory if possible
        try:
             src_arg = str(src_dir_abs.relative_to(build_dir_abs))
        except ValueError: # Not relative, use absolute path
             src_arg = str(src_dir_abs)
        command.append(src_arg)

        # Execute cmake from the build directory
        return await run_tool_command_async(
            tool_name="cmake_configure",
            command=command,
            cwd=build_dir_abs, # Run cmake *from* the build directory
            timeout=600, # Allow time for configuration checks
            success_rc=0
        )
    except FileNotFoundError:
        return f"Error: Source directory '{source_dir}' not found."
    except Exception as e:
        logging.exception(f"Error running cmake: {e}")
        return f"Error running cmake: {e}"


@register_tool
async def gcc_compile(
    source_files: List[str],
    output_file: str,
    options: Optional[List[str]] = None,
    working_dir: str = "."
) -> str:
    """
    Compiles one or more source files using 'gcc' into an output file.
    Operates within the specified working directory.
    HIGH RISK: Can execute arbitrary code via compiler plugins or complex options.
    Requires confirmation by default.

    Args:
        source_files: List of source file paths (relative to working_dir or absolute).
        output_file: Path for the output executable or object file (relative to working_dir or absolute).
        options: Optional list of GCC compiler/linker flags (e.g., ['-Wall', '-O2', '-lm', '-I/include/path']).
        working_dir: Directory where compilation should happen. Defaults to CWD.

    Returns:
        Formatted string result including status, stdout, and stderr from gcc.
    """
    # Confirmation handled by the agent.
    logging.warning(f"Preparing gcc compile: Sources='{source_files}', Output='{output_file}', Options='{options or []}', Dir='{working_dir}'")

    if not source_files or not isinstance(source_files, list):
        return "Error: 'source_files' must be a non-empty list of strings."
    if not output_file or not isinstance(output_file, str):
        return "Error: 'output_file' must be a non-empty string."

    try:
        # Resolve working directory (sync OK)
        cwd_path = Path(working_dir).resolve()
        if not cwd_path.is_dir():
             return f"Error: Working directory '{working_dir}' not found or not a directory."

        # Resolve and validate source files relative to CWD (sync OK)
        validated_sources = []
        for src_str in source_files:
            if not isinstance(src_str, str): return f"Error: Source file entry is not a string: {src_str}"
            src_path = Path(src_str)
            abs_src = (cwd_path / src_path).resolve() if not src_path.is_absolute() else src_path.resolve()
            if not abs_src.is_file():
                return f"Error: Source file '{src_str}' (resolved to '{abs_src}') not found or not a file."
            # Use path relative to CWD if possible for cleaner command line
            try: src_arg = str(abs_src.relative_to(cwd_path))
            except ValueError: src_arg = str(abs_src)
            validated_sources.append(src_arg)

        if not validated_sources: # Should be caught above, but safety check
             return "Error: No valid source files provided after resolution."

        # Resolve output file path relative to CWD (sync OK)
        output_path_obj = Path(output_file)
        output_path_abs = (cwd_path / output_path_obj).resolve() if not output_path_obj.is_absolute() else output_path_obj.resolve()
        try: output_arg = str(output_path_abs.relative_to(cwd_path))
        except ValueError: output_arg = str(output_path_abs)

        # Ensure output directory exists (sync OK)
        try:
            output_path_abs.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
             return f"Error: Permission denied creating output directory '{output_path_abs.parent}' for gcc."
        except Exception as mkdir_e:
             return f"Error creating output directory '{output_path_abs.parent}' for gcc: {mkdir_e}"

        # Build command
        command = ["gcc"] # Or use 'cc'? gcc is more specific.

        # Validate and add options
        safe_options = []
        if options:
             if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
             for opt in options:
                 opt_str = str(opt)
                 # Allow common flags (-Wall, -O2, -lm, -I/path, -L/path, -o, -c, -g, -shared, -std=...)
                 # Be cautious with flags like -fplugin=, -specs=, @file
                 # Basic check: starts with '-' or is a linker script (-T file.ld), block obvious risks.
                 is_potentially_safe = False
                 if opt_str.startswith(('-I', '-L', '-D', '-U', '-l', '-W', '-O', '-g', '-std=', '-march=', '-mtune=', '-m')): is_potentially_safe = True
                 elif opt_str in ['-c', '-S', '-E', '-shared', '-static', '-pie', '-fPIC', '-pthread']: is_potentially_safe = True
                 elif opt_str.startswith('-T') and len(opt_str) > 2 : is_potentially_safe = True # Linker script
                 # Disallow flags known to be risky for arbitrary execution if possible
                 known_risky = ['-fplugin=', '-specs=', '-wrapper', '-imacros', '-include']
                 if any(opt_str.startswith(risky) for risky in known_risky):
                      logging.error(f"BLOCKING potentially dangerous gcc option: {opt_str}")
                      return f"Error: Potentially dangerous gcc option blocked: {opt_str}"

                 # General check for suspicious characters if not specifically allowed above
                 if is_potentially_safe and not any(c in opt_str for c in ';|&`$()<>'):
                     safe_options.append(opt_str)
                 elif not is_potentially_safe and opt_str.startswith('-'): # Unrecognized flag
                     logging.warning(f"Skipping potentially unsafe or unrecognized gcc option: {opt_str}")
                 elif not opt_str.startswith('-'): # Maybe a source file missed? Or linker input? Allow for now.
                      logging.warning(f"Adding non-flag argument to gcc options: {opt_str}. Ensure this is intended.")
                      safe_options.append(opt_str) # Allow non-flag args? Risky. Maybe block them?

             command.extend(safe_options)

        # Add source files and output flag
        command.extend(validated_sources)
        command.extend(["-o", output_arg])

        # Execute gcc
        return await run_tool_command_async(
            tool_name="gcc_compile",
            command=command,
            cwd=cwd_path, # Run gcc in the specified directory
            timeout=600, # Allow time for compilation
            success_rc=0 # GCC typically returns 0 on success
        )
    except FileNotFoundError: # Should be caught by cwd_path check
        return f"Error: Working directory '{working_dir}' not found."
    except Exception as e:
        logging.exception(f"Error running gcc: {e}")
        return f"Error running gcc: {e}"
