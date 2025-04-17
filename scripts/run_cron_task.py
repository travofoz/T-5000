#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Example script demonstrating how to run a predefined agent task non-interactively.
Suitable for execution via cron or other scheduling mechanisms.
"""

import asyncio
import logging
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Any, Type

# --- Setup Python Path ---
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- Initialize Settings FIRST ---
from agent_system.config import settings
settings.initialize_settings() # Explicitly initialize settings and logging

# --- Imports after path and settings setup ---
from agent_system.core.agent import BaseAgent
from agent_system.llm_providers import get_llm_provider, LLMProvider, provider_cache
from agent_system.agents.sysadmin import SysAdminAgent
# Add other agent imports here if this script needs them
# from agent_system.agents.coding import CodingAgent


# --- Script Configuration & Argument Parsing ---
def parse_arguments():
    """Parses command-line arguments for the cron task script."""
    # (Implementation unchanged)
    parser = argparse.ArgumentParser(description="Run agent task non-interactively.")
    parser.add_argument("-t", "--task", required=True, help="Task prompt.")
    available_agents_map: Dict[str, Type[BaseAgent]] = { "SysAdminAgent": SysAdminAgent } # Add agents usable by script
    available_agent_names = list(available_agents_map.keys())
    parser.add_argument("-a", "--agent", required=True, choices=available_agent_names, help=f"Agent class name. Available: {', '.join(available_agent_names)}")
    parser.add_argument("-o", "--output-file", default=None, help="Optional file path for output.")
    return parser.parse_args(), available_agents_map

# --- Agent Instantiation Helper ---
async def get_script_agent_instance(agent_class_name: str, session_id: Optional[str] = None) -> Optional[BaseAgent]:
    """Instantiates a specific agent for the script."""
    # (Implementation unchanged)
    agent_classes_map: Dict[str, Type[BaseAgent]] = { "SysAdminAgent": SysAdminAgent } # Ensure map matches arg choices
    AgentClass = agent_classes_map.get(agent_class_name)
    if not AgentClass: logging.error(f"Unknown agent class: {agent_class_name}."); return None
    config = settings.AGENT_LLM_CONFIG.get(agent_class_name)
    if not config: logging.error(f"No config for agent: {agent_class_name}"); return None
    provider_name = config.get('provider'); model_name = config.get('model')
    if not provider_name or not model_name: logging.error(f"Incomplete config for {agent_class_name}."); return None
    try:
        async def get_cached_provider(p_name: str, p_config: Dict[str, Any]) -> LLMProvider:
             global provider_cache; prelim_key_detail = p_config.get("base_url") or p_config.get("api_key") or "default_or_env"; prelim_cache_key = (p_name.lower(), prelim_key_detail)
             if prelim_cache_key in provider_cache: provider = provider_cache[prelim_cache_key]; provider.model_name = p_config.get("model", provider.model_name); return provider
             else:
                 provider_instance = get_llm_provider(p_name, p_config); instance_cache_key = (p_name.lower(), provider_instance.get_identifier())
                 if instance_cache_key != prelim_cache_key and instance_cache_key in provider_cache: provider_instance = provider_cache[instance_cache_key]; provider_instance.model_name = p_config.get("model", provider_instance.model_name)
                 else: provider_cache[instance_cache_key] = provider_instance;
                 if instance_cache_key != prelim_cache_key: provider_cache[prelim_cache_key] = provider_instance
                 return provider_instance
        agent_provider = await get_cached_provider(provider_name, config)
        agent_instance = AgentClass(llm_provider=agent_provider, session_id=session_id)
        return agent_instance
    except Exception as e: logging.exception(f"Failed init agent '{agent_class_name}': {e}"); return None

# --- Main Execution Logic ---
async def main_script(args, agent_classes_map):
    """Main asynchronous logic for the script."""
    # (Implementation unchanged)
    logging.info(f"Starting script task: Agent='{args.agent}', Task='{args.task[:50]}...'")
    agent = await get_script_agent_instance(args.agent, session_id=f"script_{args.agent}_{os.getpid()}") # Give unique ID
    if not agent: print(f"Error: Could not initialize agent '{args.agent}'.", file=sys.stderr); sys.exit(1)
    final_result: Optional[str] = None
    try:
        logging.info(f"Running agent '{args.agent}' with prompt..."); print(f"Executing task: {args.task}\n")
        final_result = await agent.run(args.task, load_state=False, save_state=False) # Cron jobs usually stateless
        logging.info(f"Agent '{args.agent}' completed task.")
    except Exception as e: logging.exception(f"Error running agent '{args.agent}': {e}"); final_result = f"[Script Error: Execution failed: {e}]"; traceback.print_exc(file=sys.stderr)
    finally:
        if final_result is not None:
             if args.output_file:
                 try: output_path = Path(args.output_file).resolve(); output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(final_result, encoding='utf-8'); logging.info(f"Response written to: {output_path}"); print(f"\nOutput written to {output_path}")
                 except Exception as write_e: logging.exception(f"Failed write to '{args.output_file}': {write_e}"); print(f"\nError writing output: {write_e}", file=sys.stderr); print("\n--- Agent Response ---\n", final_result, "\n----------------------", file=sys.stderr)
             else: print("\n--- Agent Response ---\n", final_result, "\n----------------------")
        else: print("\nScript finished; no final result.", file=sys.stderr)
        logging.info("Cleaning up provider connections...")
        close_tasks = []
        for provider in provider_cache.values():
            if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close): close_tasks.append(asyncio.create_task(provider.close()))
        if close_tasks: await asyncio.gather(*close_tasks, return_exceptions=True)
        logging.info("Script cleanup complete.")

# --- Entry Point ---
if __name__ == "__main__":
    # Settings are initialized at the top import level
    script_args, agents_map = parse_arguments()
    exit_code = 0
    try: asyncio.run(main_script(script_args, agents_map))
    except KeyboardInterrupt: print("\nScript interrupted.", file=sys.stderr); exit_code = 1
    except Exception as e: logging.critical(f"Critical script error: {e}", exc_info=True); print(f"\nFATAL SCRIPT ERROR: {e}", file=sys.stderr); traceback.print_exc(file=sys.stderr); exit_code = 1
    finally: sys.exit(exit_code)

