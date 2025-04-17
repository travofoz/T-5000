#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Example script demonstrating how to run a predefined agent task non-interactively.
Suitable for execution via cron or other scheduling mechanisms.

Usage:
  python -m scripts.run_cron_task --task="Summarize system logs from yesterday" --agent="SysAdminAgent" [--output-file="summary.txt"]

WARNING: Ensure the environment (including .env file access and necessary packages)
is correctly set up for the cron job execution context. Consider using absolute paths
or activating a virtual environment within the cron command. High-risk tools might still
require confirmation depending on settings unless TTY is unavailable.
"""

import asyncio
import logging
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

# --- Setup Python Path ---
# Ensure the 'agent_system_project' directory is in the Python path
# This allows running the script directly using `python scripts/run_cron_task.py`
# or `python -m scripts.run_cron_task` from the project root.
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    print(f"Added {PROJECT_ROOT} to Python path.")

# --- Imports after path setup ---
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import get_llm_provider, LLMProvider, provider_cache # Use shared cache
from agent_system.config import settings # Loads config and sets up logging

# Import specific agent classes needed by this script
from agent_system.agents.sysadmin import SysAdminAgent
# Add other agent imports here if this script needs them

# --- Script Configuration & Argument Parsing ---

def parse_arguments():
    """Parses command-line arguments for the cron task script."""
    parser = argparse.ArgumentParser(description="Run a predefined agent task non-interactively.")
    parser.add_argument(
        "-t", "--task",
        required=True,
        help="The specific task prompt to give to the agent."
    )
    parser.add_argument(
        "-a", "--agent",
        required=True,
        help="The name of the specialist agent class to use (e.g., 'SysAdminAgent', 'CodingAgent')."
    )
    parser.add_argument(
        "-o", "--output-file",
        default=None,
        help="Optional file path to write the agent's final response."
    )
    # Add more arguments if needed (e.g., --session-id, config overrides)
    return parser.parse_args()

# --- Agent Instantiation Helper ---
# (Similar to helpers in CLI, consider refactoring to a shared utility)
async def get_script_agent_instance(agent_class_name: str, session_id: Optional[str] = None) -> Optional[BaseAgent]:
    """Instantiates a specific agent for the script."""
    agent_classes_map: Dict[str, Type[BaseAgent]] = {
         "SysAdminAgent": SysAdminAgent,
         # Add other agents this script might use here
    }

    AgentClass = agent_classes_map.get(agent_class_name)
    if not AgentClass:
        logging.error(f"Unknown agent class specified: {agent_class_name}. Available in script: {list(agent_classes_map.keys())}")
        return None

    config = settings.AGENT_LLM_CONFIG.get(agent_class_name)
    if not config:
        logging.error(f"No LLM configuration found for agent class: {agent_class_name}")
        return None

    provider_name = config.get('provider')
    model_name = config.get('model')
    if not provider_name or not model_name:
        logging.error(f"Missing 'provider' or 'model' in config for {agent_class_name}.")
        return None

    try:
        # Use shared provider cache logic (copied again - needs refactor)
        async def get_cached_provider(p_name: str, p_config: Dict[str, Any]) -> LLMProvider:
             prelim_key_detail = p_config.get("base_url") or p_config.get("api_key") or "default_or_env"
             prelim_cache_key = (p_name.lower(), prelim_key_detail)
             if prelim_cache_key in provider_cache:
                 provider = provider_cache[prelim_cache_key]
                 provider.model_name = p_config.get("model", provider.model_name)
                 return provider
             else:
                 provider_instance = get_llm_provider(p_name, p_config) # Factory handles creation
                 instance_cache_key = (p_name.lower(), provider_instance.get_identifier())
                 if instance_cache_key != prelim_cache_key and instance_cache_key in provider_cache:
                     provider_instance = provider_cache[instance_cache_key]
                     provider_instance.model_name = p_config.get("model", provider_instance.model_name)
                 else:
                     provider_cache[instance_cache_key] = provider_instance
                     if instance_cache_key != prelim_cache_key: provider_cache[prelim_cache_key] = provider_instance # Cache under simple key too
                 return provider_instance

        agent_provider = await get_cached_provider(provider_name, config)
        # Instantiate with specific session_id if provided, otherwise None
        agent_instance = AgentClass(llm_provider=agent_provider, session_id=session_id)
        return agent_instance
    except Exception as e:
        logging.exception(f"Failed to initialize agent '{agent_class_name}': {e}")
        return None


# --- Main Execution Logic ---
async def main_script(args):
    """Main asynchronous logic for the script."""
    logging.info(f"Starting cron task script: Agent='{args.agent}', Task='{args.task[:50]}...'")

    # Instantiate the requested agent
    # Use a fixed session ID or None for non-interactive tasks? Depends on whether state should persist.
    # Using None means it won't load/save history specific to this cron run unless modified.
    agent_session_id = f"cron_{args.agent}_{os.getpid()}" # Example session ID for this run
    agent = await get_script_agent_instance(args.agent, session_id=agent_session_id)

    if not agent:
        print(f"Error: Could not initialize agent '{args.agent}'. Check logs.", file=sys.stderr)
        # Cleanup providers before exiting
        for provider in provider_cache.values():
             if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close): await provider.close()
        sys.exit(1)

    final_result = None
    try:
        # Run the agent with the specified task prompt
        # Disable state loading/saving by default for cron, unless specifically needed/configured
        logging.info(f"Running agent '{args.agent}' with prompt...")
        final_result = await agent.run(args.task, load_state=False, save_state=False)
        logging.info(f"Agent '{args.agent}' completed task.")

    except Exception as e:
        logging.exception(f"An error occurred while running agent '{args.agent}': {e}")
        final_result = f"[Script Error: Exception during agent execution: {e}]"
    finally:
        # --- Output Result ---
        if final_result is not None:
             if args.output_file:
                 try:
                     output_path = Path(args.output_file).resolve()
                     output_path.parent.mkdir(parents=True, exist_ok=True)
                     output_path.write_text(final_result, encoding='utf-8')
                     logging.info(f"Agent response written to: {output_path}")
                     print(f"Output written to {output_path}")
                 except Exception as write_e:
                     logging.exception(f"Failed to write output to file '{args.output_file}': {write_e}")
                     print(f"Error writing output to {args.output_file}: {write_e}", file=sys.stderr)
                     # Print to stdout as fallback
                     print("\n--- Agent Response ---", file=sys.stderr)
                     print(final_result, file=sys.stderr)
                     print("----------------------", file=sys.stderr)
             else:
                 # Print to standard output if no file specified
                 print("\n--- Agent Response ---")
                 print(final_result)
                 print("----------------------")
        else:
             print("Script finished but no final result was captured.", file=sys.stderr)

        # --- Cleanup ---
        logging.info("Cleaning up provider connections...")
        for provider in provider_cache.values():
            if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close):
                try: await provider.close()
                except Exception as close_err: logging.error(f"Error closing provider {type(provider).__name__}: {close_err}")
        logging.info("Script cleanup complete.")

if __name__ == "__main__":
    # Ensure logging is configured by importing settings
    if settings.LOG_LEVEL: # Check if settings loaded properly
         pass # Logging setup done in settings.py

    script_args = parse_arguments()
    try:
        asyncio.run(main_script(script_args))
    except Exception as e:
        logging.critical(f"Critical error running script: {e}", exc_info=True)
        print(f"\nFATAL SCRIPT ERROR: {e}", file=sys.stderr)
        sys.exit(1)
