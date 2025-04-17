import asyncio
import logging
import argparse
import sys
from typing import Dict, Optional, Tuple

# Import necessary components (similar to interactive main)
from agent_system.core.agent import BaseAgent
from agent_system.core.controller import ControllerAgent
from agent_system.llm_providers import get_llm_provider, LLMProvider
from agent_system.config import settings

# Import agent classes (or use a dynamic loading mechanism if preferred)
from agent_system.agents.coding import CodingAgent
from agent_system.agents.sysadmin import SysAdminAgent
# ... import other agent classes ...

# Placeholder for non-interactive mode.
# This would typically take a prompt via command-line arguments,
# run the controller once, print the result, and exit.

async def run_non_interactive(initial_prompt: str):
    """
    Runs the agent system non-interactively for a single prompt.
    Placeholder implementation.
    """
    logging.info(f"Running non-interactive mode with prompt: '{initial_prompt[:100]}...'")
    print("--- Non-Interactive Mode (Placeholder) ---")

    # NOTE: This setup duplicates the agent instantiation from interactive mode.
    # Consider refactoring into a shared initialization function if complexity grows.
    provider_cache: Dict[Tuple[str, str], LLMProvider] = {}

    async def get_cached_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
         # Simplified cache logic for non-interactive, same principle as interactive
         prelim_key_detail = config.get("base_url") or config.get("api_key") or "default_or_env"
         prelim_cache_key = (provider_name.lower(), prelim_key_detail)
         if prelim_cache_key in provider_cache:
             provider = provider_cache[prelim_cache_key]
             provider.model_name = config.get("model", provider.model_name)
             return provider
         else:
             provider_instance = get_llm_provider(provider_name, config) # Factory handles creation
             instance_cache_key = (provider_name.lower(), provider_instance.get_identifier())
             provider_cache[instance_cache_key] = provider_instance
             if instance_cache_key != prelim_cache_key:
                 provider_cache[prelim_cache_key] = provider_instance # Cache under simple key too
             return provider_instance

    # --- Instantiate Agents (Placeholder - adapt from interactive main) ---
    specialist_agents: Dict[str, BaseAgent] = {}
    controller_agent: Optional[ControllerAgent] = None
    # TODO: Add agent instantiation logic here, similar to instantiate_agents in main_interactive.py
    # For this placeholder, we'll assume failure to demonstrate structure.
    print("Placeholder: Agent instantiation would occur here.")
    # Example: Directly try to create controller (won't work without specialists)
    try:
         controller_config = settings.AGENT_LLM_CONFIG.get("ControllerAgent")
         if controller_config:
              provider = await get_cached_provider(controller_config['provider'], controller_config)
              # controller_agent = ControllerAgent(agents={}, llm_provider=provider) # Needs specialists
              print(f"Placeholder: Controller provider obtained ({type(provider).__name__}).")
         else:
              print("Error: Controller config missing.")

    except Exception as e:
         print(f"Error initializing placeholder controller: {e}")


    if controller_agent is None:
        print("Placeholder: Controller Agent could not be initialized. Cannot run prompt.")
        result = "[Error: Failed to initialize agent system]"
    else:
         # --- Run Controller ---
         print(f"\nRunning controller with prompt: {initial_prompt}\n")
         try:
             # Non-interactive run typically doesn't load/save state unless specified
             # controller_agent.load_state() # Optional: Load state if needed
             result = await controller_agent.run(initial_prompt)
             # controller_agent.save_state() # Optional: Save state if needed
             print("\n--- Controller Execution Complete ---")
         except Exception as e:
              logging.exception("Error during non-interactive controller run.")
              result = f"[Error: An exception occurred during execution: {e}]"

    print("\n--- Final Result ---")
    print(result)
    print("--------------------")

    # --- Cleanup ---
    print("Cleaning up provider connections...")
    for provider in provider_cache.values():
        if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close):
            try: await provider.close()
            except Exception as close_err: logging.error(f"Error closing provider {type(provider).__name__}: {close_err}")
    print("Cleanup complete.")


def main():
    """Parses command line arguments and runs the non-interactive mode."""
    parser = argparse.ArgumentParser(description="Run the multi-agent system non-interactively.")
    parser.add_argument("prompt", help="The initial prompt for the agent system.")
    # Add other arguments as needed (e.g., --model, --config-file, state handling flags)

    args = parser.parse_args()

    # Basic check for prompt
    if not args.prompt.strip():
        print("Error: Prompt cannot be empty.", file=sys.stderr)
        sys.exit(1)

    # Run the async main function
    try:
        asyncio.run(run_non_interactive(args.prompt))
    except Exception as e:
        logging.critical(f"Critical error during non-interactive execution: {e}", exc_info=True)
        print(f"\nFATAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    # Logging is configured by importing settings at the top
    main()
