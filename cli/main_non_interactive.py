#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Runs a specific agent non-interactively for a single task prompt.

Usage:
  python -m cli.main_non_interactive --agent <AgentClassName> --task "Your prompt here" [--output-file <path>]

Example:
  python -m cli.main_non_interactive --agent CodingAgent --task "Refactor the file agent.py to improve readability."
"""

import asyncio
import logging
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Any, Type # Added Type

# --- Setup Python Path ---
# Ensure the 'agent_system_project' directory is in the Python path
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    # logging below ensures this message appears if logging is setup
    # print(f"Added {PROJECT_ROOT} to Python path.") # Can be noisy

# --- Imports after path setup ---
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import get_llm_provider, LLMProvider, provider_cache # Use shared cache
from agent_system.config import settings # Loads config and sets up logging

# Import specific agent classes required
# Alternatively, use dynamic import based on args.agent if preferred
from agent_system.agents.coding import CodingAgent
from agent_system.agents.sysadmin import SysAdminAgent
from agent_system.agents.hardware import HardwareAgent
from agent_system.agents.remote_ops import RemoteOpsAgent
from agent_system.agents.debugging import DebuggingAgent
from agent_system.agents.cybersecurity import CybersecurityAgent
from agent_system.agents.build import BuildAgent
from agent_system.agents.network import NetworkAgent
# Import ControllerAgent if you want to allow running it directly
from agent_system.core.controller import ControllerAgent


# --- Script Configuration & Argument Parsing ---

def parse_arguments():
    """Parses command-line arguments for the non-interactive script."""
    parser = argparse.ArgumentParser(
        description="Run a specific agent non-interactively for a single task.",
        formatter_class=argparse.RawTextHelpFormatter # Preserve formatting in help
    )
    parser.add_argument(
        "-t", "--task",
        required=True,
        help="The specific task prompt to give to the agent."
    )
    # Dynamically list available agents in help message
    available_agents_map: Dict[str, Type[BaseAgent]] = { # Map names to classes
        "CodingAgent": CodingAgent, "SysAdminAgent": SysAdminAgent, "HardwareAgent": HardwareAgent,
        "RemoteOpsAgent": RemoteOpsAgent, "DebuggingAgent": DebuggingAgent,
        "CybersecurityAgent": CybersecurityAgent, "BuildAgent": BuildAgent, "NetworkAgent": NetworkAgent,
        "ControllerAgent": ControllerAgent, # Allow running controller directly too?
    }
    available_agent_names = list(available_agents_map.keys())
    parser.add_argument(
        "-a", "--agent",
        required=True,
        choices=available_agent_names, # Restrict choices
        help=f"The class name of the specialist agent to use.\nAvailable: {', '.join(available_agent_names)}"
    )
    parser.add_argument(
        "-o", "--output-file",
        default=None,
        help="Optional file path to write the agent's final response."
    )
    parser.add_argument(
        "--load-state",
        action='store_true',
        help="Load the agent's previous state/history before running."
    )
    parser.add_argument(
        "--save-state",
        action='store_true',
        help="Save the agent's state/history after running."
    )
    # Add --session-id? For now, non-interactive runs are stateless unless load/save enabled.
    # parser.add_argument("--session-id", default=None, help="Optional session ID for state management.")

    return parser.parse_args(), available_agents_map


# --- Provider Cache Helper ---
# Reusing the refined helper from interactive main
async def _get_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """Retrieves or creates an LLMProvider instance using a cache."""
    global provider_cache
    provider_name_lower = provider_name.lower()
    try:
        temp_provider_instance = get_llm_provider(provider_name, config)
        instance_identifier = temp_provider_instance.get_identifier()
        cache_key = (provider_name_lower, instance_identifier)
        if cache_key in provider_cache:
            cached_provider = provider_cache[cache_key]
            cached_provider.model_name = config.get("model", cached_provider.model_name)
            if temp_provider_instance is not cached_provider and hasattr(temp_provider_instance, 'close'):
                 if asyncio.iscoroutinefunction(temp_provider_instance.close): await temp_provider_instance.close()
                 else: temp_provider_instance.close()
            return cached_provider
        else:
            provider_cache[cache_key] = temp_provider_instance
            return temp_provider_instance
    except (ImportError, ValueError, ConnectionError, RuntimeError) as e:
        logging.error(f"Failed to get or create provider '{provider_name}' with config {config}: {e}", exc_info=False)
        raise


# --- Main Execution Logic ---
async def main_script(args, agent_classes_map):
    """Main asynchronous logic for the script."""
    logging.info(f"Starting non-interactive task: Agent='{args.agent}', Task='{args.task[:50]}...'")
    print(f"--- Running Agent: {args.agent} ---")

    AgentClass = agent_classes_map.get(args.agent)
    if not AgentClass:
         # Should be caught by argparse choices, but defensive check
         print(f"Error: Unknown agent class '{args.agent}' specified.", file=sys.stderr)
         sys.exit(1)

    # Get configuration for the chosen agent
    config = settings.AGENT_LLM_CONFIG.get(args.agent)
    if not config:
        print(f"Error: No LLM configuration found for agent '{args.agent}'.", file=sys.stderr)
        sys.exit(1)

    provider_name = config.get('provider')
    model_name = config.get('model')
    if not provider_name or not model_name:
        print(f"Error: Missing 'provider' or 'model' in config for '{args.agent}'.", file=sys.stderr)
        sys.exit(1)

    agent: Optional[BaseAgent] = None
    final_result: Optional[str] = None

    try:
        # Initialize the provider
        agent_provider = await _get_provider(provider_name, config)

        # Instantiate the specific agent
        # Non-interactive runs typically don't need a persistent session_id unless state is used
        agent_session_id = f"non_interactive_{args.agent}_{os.getpid()}" if (args.load_state or args.save_state) else None
        if AgentClass is ControllerAgent:
             # Controller needs specialist dict, which we don't instantiate here.
             # This script is intended for running specialists directly.
             # Modify if direct controller execution is needed (would require loading specialists).
             print(f"Error: Running ControllerAgent directly is not supported by this script yet.", file=sys.stderr)
             print(f"       Use the interactive CLI or modify this script to instantiate specialists.", file=sys.stderr)
             sys.exit(1)
        else:
             agent = AgentClass(llm_provider=agent_provider, session_id=agent_session_id)

        # Run the agent
        logging.info(f"Running agent '{args.agent}' with prompt...")
        print(f"Executing task: {args.task}\n")
        final_result = await agent.run(
            args.task,
            load_state=args.load_state,
            save_state=args.save_state
        )
        logging.info(f"Agent '{args.agent}' completed task.")

    except (ImportError, ValueError, ConnectionError, RuntimeError) as e:
         print(f"\nERROR: Failed to initialize provider/agent '{args.agent}'. Check config/keys/SDKs/connections. Details: {e}", file=sys.stderr)
         final_result = f"[Script Error: Initialization failed: {e}]"
    except Exception as e:
        logging.exception(f"An error occurred while running agent '{args.agent}': {e}")
        final_result = f"[Script Error: Exception during agent execution: {e}]"
        traceback.print_exc(file=sys.stderr) # Print traceback for script errors
    finally:
        # --- Output Result ---
        if final_result is not None:
             print("\n--- Agent Response ---")
             print(final_result)
             print("----------------------")

             if args.output_file:
                 try:
                     output_path = Path(args.output_file).resolve()
                     output_path.parent.mkdir(parents=True, exist_ok=True)
                     output_path.write_text(final_result, encoding='utf-8')
                     logging.info(f"Agent response written to: {output_path}")
                     print(f"\nOutput successfully written to {output_path}")
                 except Exception as write_e:
                     logging.exception(f"Failed to write output to file '{args.output_file}': {write_e}")
                     print(f"\nError writing output to {args.output_file}: {write_e}", file=sys.stderr)
        else:
             print("\nScript finished but no final result was captured.", file=sys.stderr)

        # --- Cleanup ---
        logging.info("Cleaning up provider connections...")
        close_tasks = []
        for provider in provider_cache.values():
            if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close):
                 close_tasks.append(asyncio.create_task(provider.close(), name=f"close_{type(provider).__name__}"))
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True) # Ignore errors during close
        logging.info("Script cleanup complete.")

# --- Entry Point ---
if __name__ == "__main__":
    # Ensure logging is configured
    if not settings.LOG_LEVEL:
         print("Warning: Settings didn't seem to load correctly, logging might not be configured.", file=sys.stderr)

    script_args, agents_map = parse_arguments()
    exit_code = 0
    try:
        asyncio.run(main_script(script_args, agents_map))
    except KeyboardInterrupt:
        print("\nScript interrupted by user.", file=sys.stderr)
        exit_code = 1
    except Exception as e:
        # Catch errors during asyncio.run or top-level issues
        logging.critical(f"Critical error running script: {e}", exc_info=True)
        print(f"\nFATAL SCRIPT ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        exit_code = 1
    finally:
        # Ensure cleanup runs even if main_script fails mid-way if needed,
        # but the current structure cleans up within main_script's finally block.
        sys.exit(exit_code)
