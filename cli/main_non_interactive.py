#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Runs a specific agent non-interactively for a single task prompt.
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
from agent_system.agents.coding import CodingAgent
from agent_system.agents.sysadmin import SysAdminAgent
from agent_system.agents.hardware import HardwareAgent
from agent_system.agents.remote_ops import RemoteOpsAgent
from agent_system.agents.debugging import DebuggingAgent
from agent_system.agents.cybersecurity import CybersecurityAgent
from agent_system.agents.build import BuildAgent
from agent_system.agents.network import NetworkAgent
from agent_system.core.controller import ControllerAgent

# --- Script Configuration & Argument Parsing ---
def parse_arguments():
    """Parses command-line arguments for the non-interactive script."""
    # (Implementation unchanged)
    parser = argparse.ArgumentParser(description="Run agent non-interactively.", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-t", "--task", required=True, help="Task prompt for the agent.")
    available_agents_map: Dict[str, Type[BaseAgent]] = {
        "CodingAgent": CodingAgent, "SysAdminAgent": SysAdminAgent, "HardwareAgent": HardwareAgent,
        "RemoteOpsAgent": RemoteOpsAgent, "DebuggingAgent": DebuggingAgent,
        "CybersecurityAgent": CybersecurityAgent, "BuildAgent": BuildAgent, "NetworkAgent": NetworkAgent,
        "ControllerAgent": ControllerAgent,
    }
    available_agent_names = list(available_agents_map.keys())
    parser.add_argument("-a", "--agent", required=True, choices=available_agent_names, help=f"Agent class name.\nAvailable: {', '.join(available_agent_names)}")
    parser.add_argument("-o", "--output-file", default=None, help="Optional file path for output.")
    parser.add_argument("--load-state", action='store_true', help="Load previous agent state.")
    parser.add_argument("--save-state", action='store_true', help="Save agent state after running.")
    return parser.parse_args(), available_agents_map

# --- Provider Cache Helper ---
async def _get_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """Retrieves or creates an LLMProvider instance using a cache."""
    # (Implementation unchanged)
    global provider_cache; provider_name_lower = provider_name.lower()
    try:
        temp_provider_instance = get_llm_provider(provider_name, config)
        instance_identifier = temp_provider_instance.get_identifier(); cache_key = (provider_name_lower, instance_identifier)
        if cache_key in provider_cache:
            cached_provider = provider_cache[cache_key]; cached_provider.model_name = config.get("model", cached_provider.model_name)
            if temp_provider_instance is not cached_provider and hasattr(temp_provider_instance, 'close'):
                 if asyncio.iscoroutinefunction(temp_provider_instance.close): await temp_provider_instance.close()
                 else: temp_provider_instance.close()
            return cached_provider
        else: provider_cache[cache_key] = temp_provider_instance; return temp_provider_instance
    except (ImportError, ValueError, ConnectionError, RuntimeError) as e: logging.error(f"Failed provider '{provider_name}': {e}"); raise

# --- Main Execution Logic ---
async def main_script(args, agent_classes_map):
    """Main asynchronous logic for the script."""
    # (Implementation unchanged)
    logging.info(f"Starting non-interactive task: Agent='{args.agent}', Task='{args.task[:50]}...'")
    print(f"--- Running Agent: {args.agent} ---")
    AgentClass = agent_classes_map.get(args.agent)
    if not AgentClass: print(f"Error: Unknown agent class '{args.agent}'.", file=sys.stderr); sys.exit(1)
    config = settings.AGENT_LLM_CONFIG.get(args.agent)
    if not config: print(f"Error: No config for agent '{args.agent}'.", file=sys.stderr); sys.exit(1)
    provider_name = config.get('provider'); model_name = config.get('model')
    if not provider_name or not model_name: print(f"Error: Incomplete config for '{args.agent}'.", file=sys.stderr); sys.exit(1)
    agent: Optional[BaseAgent] = None; final_result: Optional[str] = None
    try:
        agent_provider = await _get_provider(provider_name, config)
        agent_session_id = f"non_interactive_{args.agent}_{os.getpid()}" if (args.load_state or args.save_state) else None
        if AgentClass is ControllerAgent: print(f"Error: Running ControllerAgent directly not supported.", file=sys.stderr); sys.exit(1)
        else: agent = AgentClass(llm_provider=agent_provider, session_id=agent_session_id)
        logging.info(f"Running agent '{args.agent}' with prompt...")
        print(f"Executing task: {args.task}\n")
        final_result = await agent.run(args.task, load_state=args.load_state, save_state=args.save_state)
        logging.info(f"Agent '{args.agent}' completed task.")
    except Exception as e:
        logging.exception(f"Error running agent '{args.agent}': {e}")
        final_result = f"[Script Error: Execution failed: {e}]"; traceback.print_exc(file=sys.stderr)
    finally:
        if final_result is not None:
             if args.output_file:
                 try:
                     output_path = Path(args.output_file).resolve(); output_path.parent.mkdir(parents=True, exist_ok=True)
                     output_path.write_text(final_result, encoding='utf-8')
                     logging.info(f"Agent response written to: {output_path}"); print(f"\nOutput written to {output_path}")
                 except Exception as write_e: logging.exception(f"Failed write to '{args.output_file}': {write_e}"); print(f"\nError writing output: {write_e}", file=sys.stderr); print("\n--- Agent Response ---\n", final_result, "\n----------------------", file=sys.stderr)
             else: print("\n--- Agent Response ---\n", final_result, "\n----------------------")
        else: print("\nScript finished; no final result captured.", file=sys.stderr)
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
