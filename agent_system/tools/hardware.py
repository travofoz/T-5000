import asyncio
import logging
import shlex
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import run_tool_command_async, ask_confirmation_async
from agent_system.config import settings

# Attempt to import serial library, required for serial port tools
try:
    import serial
    import serial.tools.list_ports
    # Consider importing aioserial if fully async serial is desired later
    # import aioserial
    PYSERIAL_AVAILABLE = True
except ImportError:
    logging.warning("pyserial library not found. Serial port tools will be unavailable.")
    PYSERIAL_AVAILABLE = False
    serial = None # Ensure serial is None if import fails
    # aioserial = None

@register_tool
async def esptool_command(args: List[str]) -> str:
    """
    Executes the 'esptool.py' command-line utility for Espressif chips.
    Used for flashing firmware, reading chip info, etc.
    HARDWARE RISK: Can potentially brick devices if used incorrectly.
    Requires confirmation by default.

    Args:
        args: List of arguments to pass to esptool.py (e.g., ['--port', '/dev/ttyUSB0', 'flash_id']).

    Returns:
        Formatted string result including status, stdout, and stderr from esptool.py.
    """
    # Confirmation handled by the agent.
    if not args:
        return "Error: No arguments provided for esptool.py"
    # Ensure args are strings
    safe_args = [str(arg) for arg in args]
    logging.warning(f"Preparing esptool.py command: {' '.join(safe_args)}")
    command = ["esptool.py"] + safe_args

    # esptool.py exit codes: 0=success, 1=warning (e.g. md5 mismatch), 2=error
    return await run_tool_command_async(
        tool_name="esptool_command",
        command=command,
        timeout=300, # Increased timeout for potentially long flash/erase operations
        success_rc=[0, 1], # Treat RC 1 (warnings) as non-fatal for the tool's success status
        failure_notes={
             1: "esptool.py completed with warnings (e.g., MD5 mismatch). Check output.",
             2: "esptool.py failed with an error (e.g., connection failed, bad arguments).",
        }
    )

@register_tool
async def openocd_command(args: List[str]) -> str:
    """
    Executes the 'openocd' (Open On-Chip Debugger) command.
    Used for debugging, programming, and boundary-scan testing of embedded devices.
    HARDWARE RISK: Can halt, modify, or potentially damage connected hardware.
    Requires confirmation by default.

    Args:
        args: List of arguments for openocd (e.g., ['-f', 'interface/stlink.cfg', '-f', 'target/stm32f1x.cfg', '-c', 'program firmware.bin verify reset exit']).
              It's crucial to include commands like '-c exit' for non-interactive use.

    Returns:
        Formatted string result including status, stdout, and stderr from openocd.
    """
    # Confirmation handled by the agent.
    if not args:
        return "Error: No arguments provided for openocd"
    # Ensure args are strings
    safe_args = [str(arg) for arg in args]
    logging.warning(f"Preparing openocd command: {' '.join(safe_args)}")
    command = ["openocd"] + safe_args

    # OpenOCD often runs until explicitly told to exit via '-c exit' or similar.
    # Success/failure depends heavily on the commands executed. RC 0 is typical success.
    return await run_tool_command_async(
        tool_name="openocd_command",
        command=command,
        timeout=180, # Timeout for the OpenOCD process itself
        success_rc=0
        # Failure notes are hard to generalize; rely on stderr.
    )

@register_tool
async def serial_port_list() -> str:
    """
    Lists available serial ports on the system using pyserial.

    Returns:
        A string listing detected serial ports and their descriptions, or an error message.
    """
    if not PYSERIAL_AVAILABLE:
        return "Error: pyserial library not installed or loadable. Cannot list serial ports."

    try:
        # Run the blocking list_ports call in a separate thread
        ports = await asyncio.to_thread(serial.tools.list_ports.comports)
        if not ports:
            return "No serial ports found."

        # Format the output
        port_lines = []
        for p in ports:
             desc = p.description if p.description else "(no description)"
             hwid = p.hwid if p.hwid else "(no hwid)"
             port_lines.append(f"- {p.device}: {desc} [{hwid}]")
        return "Available serial ports:\n" + "\n".join(port_lines)

    except Exception as e:
        logging.exception("Error listing serial ports")
        return f"Error listing serial ports: {e}"

@register_tool
async def serial_port_read_write(
    port: str,
    baudrate: int = 9600,
    bytes_to_read: Optional[int] = None,
    data_to_write: Optional[str] = None,
    read_timeout: float = 1.0,
    write_delay: float = 0.1,
    read_delay: float = 0.1,
    stop_on_newline: bool = False,
    encoding: str = 'utf-8'
) -> str:
    """
    Asynchronously writes data to and/or reads data from a specified serial port using pyserial.
    Uses asyncio.to_thread for the blocking pyserial operations.

    Args:
        port: The device name or path of the serial port (e.g., /dev/ttyUSB0, COM3).
        baudrate: Serial baud rate (default: 9600).
        bytes_to_read: Exact number of bytes to read. If null/omitted, reads available data until timeout or newline (if stop_on_newline=True).
        data_to_write: Text data to write (will be encoded using 'encoding').
        read_timeout: Timeout in seconds for read operations (default: 1.0).
        write_delay: Delay in seconds after writing before attempting to read (default: 0.1).
        read_delay: Delay in seconds after finishing reading before closing/returning (default: 0.1).
        stop_on_newline: If True and bytes_to_read is null/omitted, stop reading when a newline character ('\\n') is encountered (default: False).
        encoding: The encoding to use for writing string data and decoding read bytes (default: 'utf-8').

    Returns:
        A string summarizing the interaction and including any read data, or an error message.
    """
    if not PYSERIAL_AVAILABLE:
        return "Error: pyserial library not installed or loadable. Cannot interact with serial port."

    # --- Parameter Validation ---
    if not port or not isinstance(port, str):
        return "Error: Serial port name must be a non-empty string."
    try:
        baudrate = int(baudrate)
        if baudrate <= 0: raise ValueError("Baudrate must be positive.")
    except ValueError: return f"Error: Invalid baudrate '{baudrate}'. Must be a positive integer."
    try:
        read_timeout = float(read_timeout)
        write_delay = float(write_delay)
        read_delay = float(read_delay)
        if read_timeout < 0 or write_delay < 0 or read_delay < 0: raise ValueError("Timeouts/delays must be non-negative.")
    except ValueError: return "Error: Timeouts/delays must be valid non-negative numbers."
    if bytes_to_read is not None:
         try:
             bytes_to_read = int(bytes_to_read)
             if bytes_to_read < 0: raise ValueError("bytes_to_read cannot be negative.")
         except ValueError: return "Error: bytes_to_read must be a non-negative integer if specified."
    if data_to_write is not None and not isinstance(data_to_write, str):
         return "Error: data_to_write must be a string if specified."
    try:
         # Validate encoding by trying to encode/decode empty string
         "".encode(encoding)
         b"".decode(encoding)
    except (LookupError, UnicodeError):
         return f"Error: Invalid or unsupported encoding specified: '{encoding}'."


    # --- Synchronous Function for Thread ---
    # This function contains all the blocking pyserial calls.
    def sync_serial_io() -> Tuple[str, str, str]:
        ser: Optional[serial.Serial] = None # Define ser here
        sync_write_summary = "No data written."
        sync_read_summary = "No read attempted."
        sync_read_string = ""
        sync_read_bytes_list = [] # To collect bytes read

        try:
            logging.info(f"Opening serial port '{port}' at {baudrate} baud (Read Timeout: {read_timeout}s).")
            # Adjust write_timeout based on potential data size? For now, fixed but reasonable.
            ser = serial.Serial(port, baudrate, timeout=read_timeout, write_timeout=max(2.0, write_delay + 1.0))
            time.sleep(0.1) # Short pause after opening can sometimes help

            # --- Writing ---
            if data_to_write:
                logging.info(f"Writing to serial {port}: {data_to_write!r}")
                try:
                     data_bytes = data_to_write.encode(encoding, errors='replace')
                     bytes_written = ser.write(data_bytes)
                     ser.flush() # Ensure data is sent
                     logging.info(f"Wrote {bytes_written} bytes.")
                     sync_write_summary = f"Wrote {bytes_written} bytes."
                     time.sleep(write_delay) # Delay after writing before potential reading
                except serial.SerialTimeoutException:
                     # Close port on write timeout? Yes, seems reasonable.
                     if ser and ser.is_open: ser.close()
                     raise TimeoutError(f"Timeout writing to serial port {port}.")
                except Exception as write_err:
                     logging.exception(f"Error writing to serial port {port}")
                     raise IOError(f"Error writing to serial port {port}: {write_err}") from write_err

            # --- Reading ---
            read_data = b""
            if bytes_to_read is not None: # Read exact number of bytes requested
                 if bytes_to_read > 0:
                     logging.info(f"Reading exactly {bytes_to_read} bytes from serial port {port} (timeout: {read_timeout}s)...")
                     read_data = ser.read(bytes_to_read)
                     sync_read_bytes_list.append(read_data)
                     sync_read_summary = f"Attempted to read {bytes_to_read} bytes, received {len(read_data)}."
                     if len(read_data) < bytes_to_read:
                         logging.warning(f"Read only {len(read_data)} bytes, expected {bytes_to_read}.")
                 else: # bytes_to_read == 0
                      sync_read_summary = "Read 0 bytes as requested."
            else: # Read until timeout or newline (if requested)
                 logging.info(f"Reading available data from serial port {port} until timeout ({read_timeout}s) or newline (stop_on_newline={stop_on_newline})...")
                 read_start_time = time.time()
                 while time.time() - read_start_time < read_timeout:
                     try:
                          # Read available bytes without blocking indefinitely
                          waiting = ser.in_waiting
                          if waiting > 0:
                               chunk = ser.read(waiting)
                               sync_read_bytes_list.append(chunk)
                               # Check for newline if requested
                               if stop_on_newline and b'\n' in chunk:
                                    logging.info("Newline detected, stopping read.")
                                    break # Stop reading after newline
                          else:
                               # Avoid busy-waiting if timeout is long
                               time.sleep(0.02)
                     except serial.SerialException as read_err:
                          logging.error(f"Serial exception during read on {port}: {read_err}")
                          sync_read_summary = f"Read {len(b''.join(sync_read_bytes_list))} bytes before encountering serial error: {read_err}"
                          raise # Propagate error
                     except Exception as read_loop_err:
                          logging.error(f"Unexpected error during serial read loop: {read_loop_err}")
                          sync_read_summary = f"Read {len(b''.join(sync_read_bytes_list))} bytes before unexpected error: {read_loop_err}"
                          raise # Propagate error
                 else: # Loop finished due to timeout
                      total_read = len(b"".join(sync_read_bytes_list))
                      sync_read_summary = f"Read {total_read} bytes until timeout."

                 time.sleep(read_delay) # Short delay after reading loop finishes

            # --- Process Read Data ---
            read_data = b"".join(sync_read_bytes_list)
            logging.info(f"Read {len(read_data)} bytes total from serial port {port}.")
            try:
                 # Decode collected bytes
                 sync_read_string = read_data.decode(encoding, errors='replace')
            except Exception as decode_err:
                 logging.error(f"Error decoding serial data with encoding '{encoding}': {decode_err}")
                 # Include raw bytes in the summary if decoding fails
                 sync_read_string = f"[Error decoding data with {encoding}, raw bytes: {read_data!r}]"
                 sync_read_summary += f" (Decoding Error: {decode_err})"


            return sync_write_summary, sync_read_summary, sync_read_string

        except serial.SerialException as e:
            # Catch specific serial errors like port not found or access denied
            logging.exception(f"Serial Error on port {port}")
            raise ConnectionError(f"Serial Error on port {port}: {e}") from e
        except TimeoutError as e: # Catch re-raised write timeout
            logging.error(f"Serial write timeout on port {port}")
            raise # Re-raise TimeoutError
        except IOError as e: # Catch re-raised write error
             logging.error(f"Serial write I/O error on port {port}")
             raise # Re-raise IOError
        except Exception as e:
            logging.exception(f"Unexpected synchronous error interacting with serial port {port}")
            raise RuntimeError(f"Unexpected sync error interacting with serial port {port}: {e}") from e
        finally:
            if ser and ser.is_open:
                try:
                    ser.close()
                    logging.info(f"Closed serial port {port}.")
                except Exception as close_err:
                    # Log error but don't prevent returning data read so far
                    logging.error(f"Error closing serial port {port}: {close_err}")

    # --- Execute in Thread ---
    try:
        write_summary, read_summary, read_string = await asyncio.to_thread(sync_serial_io)
        return f"Serial interaction complete for {port}.\nWrite Status: {write_summary}\nRead Status: {read_summary}\nRead Data ({encoding}):\n```\n{read_string}\n```"
    except (ConnectionError, TimeoutError, IOError, RuntimeError) as e:
         # Catch errors raised from the sync function
         return f"Error interacting with serial port {port}: {e}"
    except Exception as e:
         # Catch errors related to asyncio.to_thread itself
         logging.exception(f"Error running sync serial I/O in thread for port {port}")
         return f"Error executing serial I/O task: {e}"


