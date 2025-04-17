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

# WARNING: These tools interact with potentially sensitive security scanning software.
# Ensure you have authorization and are operating in a legal and ethical manner.
# High-risk tools require confirmation by default.

@register_tool
async def nmap_scan(target: str, scan_type: str = "-sV", options: Optional[List[str]] = None) -> str:
    """
    Runs an Nmap scan against the specified target(s).
    Typically requires root privileges for many scan types (e.g., -sS, -O) and is executed via sudo.
    HIGH RISK. Requires confirmation by default (for both the tool and the sudo execution).

    Args:
        target: Target specification (IP address, hostname, network range).
        scan_type: Nmap scan type flag(s) (e.g., '-sV' for version detection, '-sS' for SYN scan, '-A' for aggressive). Default is '-sV'.
        options: Optional list of additional nmap flags (e.g., ['-p-', '-T4', '--script=vuln']).

    Returns:
        Formatted string result including status, stdout (scan results), and stderr.
    """
    # Confirmation for 'nmap_scan' itself is handled by the agent.
    logging.warning(f"Preparing nmap scan: Type='{scan_type}', Target='{target}', Options='{options or []}'")

    # Basic sanitation/validation of target and options
    if not target or target.startswith('-'):
        return f"Error: Invalid target specified for nmap: '{target}'"
    # Allow scan_type to have flags, but check for obvious command injection chars
    if any(c in scan_type for c in ';|&`$()<>'):
        return f"Error: Invalid characters detected in scan_type: '{scan_type}'"

    command = ["nmap"]
    # Split scan_type in case multiple flags are passed together (e.g., "-sS -O")
    command.extend(shlex.split(scan_type))

    safe_options = []
    if options:
        if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
        for opt in options:
             opt_str = str(opt)
             # Allow flags and simple key=value assignments (e.g., --script=default), block complex chars
             if opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'):
                 safe_options.append(opt_str)
             # Allow script arguments like 'http-title.useHEAD=true' if they look safe-ish
             elif '=' in opt_str and not any(c in opt_str for c in ';|&`$()<>'):
                  safe_options.append(opt_str)
             else:
                  logging.warning(f"Skipping potentially unsafe or invalid nmap option: {opt_str}")
        command.extend(safe_options)

    # Add target last
    command.append(target)

    # Nmap often requires root. Execute via sudo.
    # Confirmation for run_sudo_command will be triggered if it's in HIGH_RISK_TOOLS.
    logging.info("Nmap scan typically requires root privileges, preparing to execute via sudo.")
    sudo_args = {"command_args": command}
    if await ask_confirmation_async("nmap_scan_sudo", sudo_args):
         # Directly call run_tool_command_async for sudo execution
         return await run_tool_command_async(
              tool_name="run_sudo_command (for nmap)",
              command=["sudo", "--"] + command,
              timeout=1800 # Nmap scans can take a very long time
              # Nmap success codes vary, 0 is typical success. Wrapper handles output.
         )
    else:
         return f"Nmap scan requires sudo privileges. User cancelled sudo attempt for command: {' '.join(command)}"

@register_tool
async def sqlmap_scan(url: str, level: int = 1, risk: int = 1, options: Optional[List[str]] = None) -> str:
    """
    Runs sqlmap automatic SQL injection and database takeover tool against a URL.
    Uses '--batch' mode for non-interactive execution.
    EXTREMELY DANGEROUS. Requires confirmation by default.

    Args:
        url: Target URL to scan (e.g., "http://example.com/vuln.php?id=1").
        level: Level of tests to perform (1-5). Default is 1.
        risk: Risk of tests to perform (1-3). Default is 1.
        options: Optional list of additional sqlmap flags (e.g., ['--dbs', '--technique=U']). Highly dangerous options like '--os-shell' are blocked.

    Returns:
        Formatted string result including status, stdout (scan findings), and stderr.
    """
    # Confirmation handled by the agent.
    logging.critical(f"Preparing sqlmap scan: URL='{url}', Level={level}, Risk={risk}, Options='{options or []}'")
    try:
        level_int = int(level)
        risk_int = int(risk)
    except ValueError:
        return "Error: Level and Risk must be integers."

    if not (1 <= level_int <= 5): return "Error: Level must be between 1 and 5."
    if not (1 <= risk_int <= 3): return "Error: Risk must be between 1 and 3."
    if not isinstance(url, str) or not url or url.startswith('-'):
         return f"Error: Invalid URL provided for sqlmap: {url}"

    # Build command, always include --batch
    command = ["sqlmap", "-u", url, f"--level={level_int}", f"--risk={risk_int}", "--batch"]

    # Block extremely dangerous options explicitly
    blocked_options = ["--os-shell", "--sql-shell", "--eval", "--file-write", "--file-read"]
    safe_options = []
    if options:
        if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
        for opt in options:
             opt_str = str(opt)
             # Check against blocked options (check if the option *starts* with a blocked one, e.g., --os-shell=...)
             if any(opt_str.startswith(blocked) for blocked in blocked_options):
                 logging.error(f"DANGEROUS sqlmap option BLOCKED: {opt_str}")
                 return f"Error: Dangerous sqlmap option blocked: {opt_str}. Blocked list: {blocked_options}"
             # Allow flags and simple key=value, block complex chars
             if opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'):
                 safe_options.append(opt_str)
             else:
                 logging.warning(f"Skipping potentially unsafe or invalid sqlmap option: {opt_str}")
        command.extend(safe_options)

    # sqlmap usually doesn't need sudo
    return await run_tool_command_async(
        tool_name="sqlmap_scan",
        command=command,
        timeout=1800, # Long timeout for potentially extensive scans
        # sqlmap often returns non-zero even on finding vulns. Rely on output.
        success_rc=[0] # Treat only 0 as full success run, but wrapper shows output regardless.
    )

@register_tool
async def nikto_scan(host: str, options: Optional[List[str]] = None) -> str:
    """
    Runs Nikto web server scanner against the specified host.
    HIGH RISK. Requires confirmation by default.

    Args:
        host: Target host (hostname, IP, or full URL). Nikto uses '-h' flag.
        options: Optional list of additional nikto flags (e.g., ['-p', '80,443', '-Tuning', 'x']).

    Returns:
        Formatted string result including status, stdout (scan findings), and stderr.
    """
    # Confirmation handled by the agent.
    logging.warning(f"Preparing nikto scan: Host='{host}', Options='{options or []}'")
    if not isinstance(host, str) or not host or host.startswith('-'):
        return f"Error: Invalid host specified for nikto: '{host}'"

    command = ["nikto", "-h", host] # Use -h for host specification

    safe_options = []
    if options:
         if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
         for opt in options:
             opt_str = str(opt)
             # Allow flags (e.g., -p, -Tuning) and simple values, block complex chars
             if opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'):
                 safe_options.append(opt_str)
             # Allow simple non-flag args like port numbers or tuning options if they look safe
             elif not opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'):
                  safe_options.append(opt_str)
             else:
                 logging.warning(f"Skipping potentially unsafe or invalid nikto option: {opt_str}")
         command.extend(safe_options)

    # Nikto doesn't usually need sudo
    return await run_tool_command_async(
        tool_name="nikto_scan",
        command=command,
        timeout=600, # Nikto scans can take some time
        success_rc=0 # Nikto usually returns 0 on completion, findings are in stdout.
    )

@register_tool
async def msfvenom_generate(
    payload: str,
    output_file: str = "payload",
    lhost: Optional[str] = None,
    lport: Optional[int] = None,
    format: str = "elf",
    options: Optional[List[str]] = None
) -> str:
    """
    Generates payloads using 'msfvenom'. Writes payload to ANY specified output file path.
    HIGH RISK. Requires confirmation by default.

    Args:
        payload: Metasploit payload name (e.g., 'windows/meterpreter/reverse_tcp').
        output_file: Path where the generated payload will be saved. WARNING: No path restrictions! Default is 'payload'.
        lhost: Listener host IP or hostname (required for reverse payloads).
        lport: Listener port number (required for reverse payloads).
        format: Output format (e.g., 'elf', 'exe', 'py', 'raw'). Default is 'elf'.
        options: Optional list of payload options as key=value strings (e.g., ['EXITFUNC=thread', 'EnableUnicodeEncoding=true']).

    Returns:
        Formatted string result indicating success or failure, including output file path.
    """
    # Confirmation handled by the agent.
    logging.critical(f"Preparing msfvenom: Payload='{payload}', Format='{format}', Output='{output_file}', LHOST={lhost}, LPORT={lport}, Options='{options or []}'")

    # Resolve output path and ensure parent exists (sync OK for path ops)
    try:
        resolved_output_path = Path(output_file).resolve()
        resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return f"Error: Permission denied creating directory for msfvenom output file '{resolved_output_path.parent}'."
    except Exception as mkdir_e:
        return f"Error creating directory for msfvenom output file '{resolved_output_path.parent}': {mkdir_e}"

    # Basic validation of payload/format names (alphanumeric, /, _, -, .)
    safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_-.')
    if not isinstance(payload, str) or not all(c in safe_chars for c in payload):
        return f"Error: Invalid characters in payload name ('{payload}'). Use alphanumeric, '/', '_', '-', '.' only."
    if not isinstance(format, str) or not all(c.isalnum() for c in format): # Format usually simpler
        return f"Error: Invalid characters in format ('{format}'). Use alphanumeric only."

    command = ["msfvenom", "-p", payload, "-f", format, "-o", str(resolved_output_path)]

    # Validate and add LHOST/LPORT if provided
    if lhost:
        if not isinstance(lhost, str) or not all(c.isalnum() or c in '.-' for c in lhost): # Allow IPs and hostnames
            return f"Error: Invalid characters in LHOST: {lhost}"
        command.append(f"LHOST={lhost}")
    if lport:
        try:
            port_int = int(lport)
            if not (1 <= port_int <= 65535): raise ValueError("Port out of range")
            command.append(f"LPORT={port_int}")
        except ValueError:
            return f"Error: Invalid LPORT value: {lport}. Must be an integer between 1 and 65535."

    # Validate and add options (expect VAR=VAL format)
    if options:
        if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
        for opt in options:
             opt_str = str(opt)
             if '=' not in opt_str:
                 logging.warning(f"Skipping invalid msfvenom option (missing '='): {opt_str}")
                 continue
             var, val = opt_str.split('=', 1)
             # Basic validation for var/val - allow reasonably safe characters
             var_safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
             # Allow more characters in value, but block highly problematic ones
             val_unsafe_chars = set(';|"`$()<>')
             if not var.isalnum() or not all(c in var_safe_chars for c in var):
                  logging.warning(f"Skipping potentially unsafe msfvenom option variable name: {var}")
                  continue
             if any(c in val for c in val_unsafe_chars):
                  logging.warning(f"Skipping potentially unsafe msfvenom option value: Contains unsafe characters {val_unsafe_chars}")
                  continue
             command.append(opt_str) # Add validated VAR=VAL string

    # Execute msfvenom
    result_str = await run_tool_command_async(
        tool_name="msfvenom_generate",
        command=command,
        timeout=300 # Increased timeout for payload generation
    )

    # Check result and try cleaning up output file on failure
    is_success = "Status: Success" in result_str # Basic check
    if is_success:
        return f"msfvenom successful. Payload '{payload}' saved to '{resolved_output_path}'.\n---\n{result_str}"
    else:
        # Try removing the potentially incomplete output file
        try:
            await asyncio.to_thread(resolved_output_path.unlink, missing_ok=True)
            logging.info(f"Removed potentially incomplete msfvenom output file: {resolved_output_path}")
            return f"msfvenom failed. Incomplete output file '{resolved_output_path}' removed (if it existed).\n---\n{result_str}"
        except OSError as unlink_err:
            logging.warning(f"Could not remove potentially incomplete msfvenom output file '{resolved_output_path}': {unlink_err}")
            return f"msfvenom failed. Could not remove incomplete output file '{resolved_output_path}'.\n---\n{result_str}"


@register_tool
async def gobuster_scan(
    target: str,
    wordlist_path: str,
    mode: str = "dir",
    options: Optional[List[str]] = None
) -> str:
    """
    Runs Gobuster for directory/file, DNS, or VHost brute-forcing using a specified wordlist.
    Requires wordlist file to exist at the specified path.
    HIGH RISK. Requires confirmation by default.

    Args:
        target: Target URL (for dir/vhost) or domain (for dns).
        wordlist_path: Path to the wordlist file.
        mode: Gobuster mode ('dir', 'dns', 'vhost'). Default is 'dir'. ('s3' mode omitted for now).
        options: Optional list of additional gobuster flags (e.g., ['-x', 'php,txt', '-t', '50']).

    Returns:
        Formatted string result including status, stdout (findings), and stderr.
    """
    # Confirmation handled by the agent.
    logging.warning(f"Preparing gobuster: Mode='{mode}', Target='{target}', Wordlist='{wordlist_path}', Options='{options or []}'")

    # Validate mode
    safe_mode = mode.lower() if isinstance(mode, str) else "dir"
    allowed_modes = ["dir", "dns", "vhost"] # Limit modes for simplicity/safety initially
    if safe_mode not in allowed_modes:
        return f"Error: Unsupported gobuster mode: {mode}. Allowed: {', '.join(allowed_modes)}."

    # Validate target
    if not isinstance(target, str) or not target or target.startswith('-'):
         return f"Error: Invalid URL/domain target specified for gobuster: '{target}'"

    # Validate and resolve wordlist path (sync OK for path ops)
    if not isinstance(wordlist_path, str): return "Error: wordlist_path must be a string."
    try:
        resolved_wordlist_path = Path(wordlist_path).expanduser().resolve(strict=True)
        if not resolved_wordlist_path.is_file(): return f"Error: Wordlist file not found or not a file: {wordlist_path}"
        resolved_wordlist_path_str = str(resolved_wordlist_path)
        logging.info(f"Using wordlist: {resolved_wordlist_path_str}")
    except FileNotFoundError: return f"Error: Wordlist file not found: {wordlist_path}"
    except Exception as e: return f"Error resolving wordlist path '{wordlist_path}': {e}"


    command = ["gobuster", safe_mode]

    # Mode specific required flags (target specification)
    if safe_mode == "dir": command.extend(["-u", target])
    elif safe_mode == "dns": command.extend(["-d", target])
    elif safe_mode == "vhost": command.extend(["-u", target]) # Vhost also uses -u for base URL

    # Add wordlist flag
    command.extend(["-w", resolved_wordlist_path_str])

    # Validate and add options
    safe_options = []
    if options:
         if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
         for opt in options:
             opt_str = str(opt)
             # Allow flags and simple values, block complex chars
             if opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'):
                 safe_options.append(opt_str)
             # Allow simple non-flag args like extensions or thread counts if they look safe
             elif not opt_str.startswith('-') and not any(c in opt_str for c in ';|&`$()<>'):
                  safe_options.append(opt_str)
             else:
                 logging.warning(f"Skipping potentially unsafe or invalid gobuster option: {opt_str}")
         command.extend(safe_options)

    # Gobuster doesn't usually need sudo
    return await run_tool_command_async(
        tool_name="gobuster_scan",
        command=command,
        timeout=1800, # Long timeout for potentially large wordlists
        success_rc=0 # Gobuster usually returns 0 on completion. Findings are in stdout.
    )

@register_tool
async def searchsploit_lookup(term: str, options: Optional[List[str]] = None) -> str:
    """
    Searches the local Exploit-DB copy using 'searchsploit' for exploits related to the given term(s).

    Args:
        term: Search term(s) (e.g., 'WordPress 4.0', ' καρδιακή αιμορραγία').
        options: Optional list of searchsploit flags (e.g., ['-j' for JSON, '-w' for web URL, '--nmap' for Nmap XML file]).

    Returns:
        Formatted string result including status, stdout (search results), and stderr.
    """
    logging.info(f"Running searchsploit lookup: Term='{term}', Options='{options or []}'")
    if not isinstance(term, str) or not term:
        return "Error: Search term cannot be empty."

    # Basic sanitation for term - avoid letting it be treated as a flag unless intended with options
    # If term starts with '-' and no options are given, it's likely an error.
    # If options ARE given, term starting with '-' might be valid (e.g., searching for '-p')
    safe_term = term
    if term.startswith('-') and not options:
         # Use '--' to signal end of options if term looks like a flag but no options were intended
         logging.warning(f"Search term '{term}' starts with '-'. Using '--' prefix for safety.")
         safe_term = "-- " + term

    command = ["searchsploit"]

    # Validate and add allowed/safe options
    safe_options = []
    if options:
         if not isinstance(options, list): return "Error: 'options' argument must be a list of strings."
         # Allow common/safe options explicitly, filter others cautiously
         allowed_opts_prefixes = ['-j', '--json', '-w', '--www', '-t', '--title', '--id', '-c', '--case', '--nmap', '--exclude=', '--include=', '--ignore', '--overflow']
         for opt in options:
             opt_str = str(opt)
             is_safe = False
             # Check against known safe prefixes
             if any(opt_str.startswith(safe_prefix) for safe_prefix in allowed_opts_prefixes):
                 is_safe = True
             # Allow simple single-letter flags
             elif opt_str.startswith('-') and len(opt_str) == 2 and opt_str[1].isalpha():
                  is_safe = True

             # Final check for problematic characters
             if is_safe and not any(c in opt_str for c in ';|&`$()<>'):
                 safe_options.append(opt_str)
             else:
                 logging.warning(f"Skipping potentially unsafe or complex searchsploit option: {opt_str}")
         command.extend(safe_options)

    # Add the search term(s)
    command.append(safe_term) # Add the (potentially prefixed) term

    # searchsploit rc 0 = found, non-zero = not found or error
    return await run_tool_command_async(
        tool_name="searchsploit_lookup",
        command=command,
        success_rc=0, # Only RC 0 means something was found
        failure_notes={
            1: "No results found matching the search term(s).", # Map specific RC if known (often 1 for not found)
            # Other RCs indicate errors (e.g., bad options, exploit-db not updated/found)
        }
    )

# Helper placeholder
async def _run_command_async(
    command: Union[List[str], str],
    timeout: int = settings.COMMAND_TIMEOUT,
    cwd: Optional[Union[str, Path]] = None,
    input_data: Optional[bytes] = None,
    check: bool = False,
    use_shell: bool = False,
    env: Optional[Dict[str, str]] = None
) -> Tuple[bool, bytes, bytes, int]:
    """Placeholder: Calls the actual implementation from tool_utils"""
    from .tool_utils import _run_command_async as util_run_async
    return await util_run_async(command, timeout, cwd, input_data, check, use_shell, env)
