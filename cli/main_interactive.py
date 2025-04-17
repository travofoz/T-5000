import asyncio
import logging
import json
import sys
import importlib
import traceback
from pathlib import Path # Added Path
from typing import Dict, Type, Tuple, Any, Optional # Added Any, Optional

# Core agent components
from agent_system.core.agent import BaseAgent
from agent_system.core.controller import ControllerAgent
from agent_system.core.interaction import Orchestrator # Keep orchestrator import

# LLM Provider factory and base class
from agent_system.llm_providers import get_llm_provider, LLMProvider

# Agent class definitions (import specific classes)
from agent_system.agents.coding import CodingAgent
from agent_system.agents.sysadmin import SysAdminAgent
from agent_system.agents.hardware import HardwareAgent
from agent_system.agents.remote_ops import RemoteOpsAgent
from agent_system.agents.debugging import DebuggingAgent
from agent_system.agents.cybersecurity import CybersecurityAgent
from agent_system.agents.build import BuildAgent
from agent_system.agents.network import NetworkAgent

# Tool discovery mechanism and registry (needed for reload)
from agent_system.tools import discover_tools, TOOL_REGISTRY
from agent_system.config.schemas import translate_schema_for_provider # Needed after reload

# Configuration
from agent_system.config import settings # Ensures settings are loaded, including logging

# --- Global Provider Cache ---
# Cache LLMProvider instances to avoid redundant initializations.
# Key: Tuple[str, str] = (provider_name_lower, instance_identifier)
provider_cache: Dict[Tuple[str, str], LLMProvider] = {}

# --- Orchestrator Instance ---
# Instantiate the orchestrator for potential use (e.g., future parallel commands)
orchestrator = Orchestrator()

async def _get_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """
    Retrieves or creates an LLMProvider instance using a cache.
    The cache key is derived from the provider name and its unique identifier
    (based on API key hash or base URL) after successful initialization.

    Args:
        provider_name: Name of the provider (e.g., "gemini").
        config: Configuration dictionary for the provider (must include 'model').

    Returns:
        An initialized LLMProvider instance.

    Raises:
        ImportError, ValueError, ConnectionError, RuntimeError on failure.
    """
    global provider_cache
    provider_name_lower = provider_name.lower()

    # Attempt to create/initialize first using the factory
    # The factory handles initial checks and instantiation logic.
    try:
        # The factory function will raise exceptions on failure (e.g., missing key, bad connection)
        temp_provider_instance = get_llm_provider(provider_name, config)
        instance_identifier = temp_provider_instance.get_identifier()
        cache_key = (provider_name_lower, instance_identifier)

        # Check cache using the reliable identifier *after* successful init
        if cache_key in provider_cache:
            logging.info(f"Provider cache hit for key: {cache_key}. Reusing instance.")
            cached_provider = provider_cache[cache_key]
            # Ensure the model name is set correctly for this specific agent request
            cached_provider.model_name = config.get("model", cached_provider.model_name)
            # Clean up the temporary instance if it wasn't the cached one
            if temp_provider_instance is not cached_provider and hasattr(temp_provider_instance, 'close'):
                 # Close temporary client if it was created unnecessarily
                 if asyncio.iscoroutinefunction(temp_provider_instance.close): await temp_provider_instance.close()
                 else: temp_provider_instance.close() # Handle sync close just in case
            return cached_provider
        else:
            # Instance was newly created by get_llm_provider, cache it
            logging.info(f"Caching new provider instance with key: {cache_key}")
            provider_cache[cache_key] = temp_provider_instance
            # Model name is already set correctly by the factory/init process
            return temp_provider_instance

    except (ImportError, ValueError, ConnectionError, RuntimeError) as e:
        # Log the specific error from the factory/provider init
        logging.error(f"Failed to get or create provider '{provider_name}' with config {config}: {e}", exc_info=False) # Log less verbosely here
        raise # Re-raise the caught exception


# --- Agent Instantiation ---
async def instantiate_agents() -> Tuple[Optional[ControllerAgent], Dict[str, BaseAgent]]:
    """Instantiates all specialist agents and the controller agent based on settings."""
    specialist_agents: Dict[str, BaseAgent] = {}
    controller_agent: Optional[ControllerAgent] = None

    agent_classes: Dict[str, Type[BaseAgent]] = {
        "CodingAgent": CodingAgent, "SysAdminAgent": SysAdminAgent, "HardwareAgent": HardwareAgent,
        "RemoteOpsAgent": RemoteOpsAgent, "DebuggingAgent": DebuggingAgent,
        "CybersecurityAgent": CybersecurityAgent, "BuildAgent": BuildAgent, "NetworkAgent": NetworkAgent
    }
    successful_agents = []

    # Instantiate Specialists
    logging.info("--- Initializing Specialist Agents ---")
    for agent_name, AgentClass in agent_classes.items():
         config = settings.AGENT_LLM_CONFIG.get(agent_name)
         if not config:
             logging.warning(f"No LLM config found for {agent_name}. Skipping.")
             continue

         provider_name = config.get('provider')
         model_name = config.get('model')
         if not provider_name or not model_name:
              logging.error(f"Missing 'provider' or 'model' in config for {agent_name}. Skipping.")
              continue

         try:
             # Use the refactored helper to get the provider
             agent_provider = await _get_provider(provider_name, config)
             # Instantiate the agent (controller doesn't need session_id from CLI)
             specialist_agents[agent_name] = AgentClass(llm_provider=agent_provider)
             successful_agents.append(agent_name)
         except (ImportError, ValueError, ConnectionError, RuntimeError) as e:
             # Error already logged by _get_provider or agent init
             print(f"\nERROR: Failed to initialize provider/agent '{agent_name}'. Check logs. Skipping. Details: {e}")
         except Exception as e:
             logging.exception(f"Unexpected error initializing specialist agent '{agent_name}'")
             print(f"\nERROR: Unexpected error initializing agent '{agent_name}'. Skipping. Details: {e}")

    if not specialist_agents:
         print("\nFATAL ERROR: No specialist agents were successfully initialized. Cannot proceed.")
         return None, {}

    logging.info(f"Successfully initialized specialist agents: {', '.join(sorted(successful_agents))}")

    # Instantiate Controller
    logging.info("--- Initializing Controller Agent ---")
    controller_config = settings.AGENT_LLM_CONFIG.get("ControllerAgent")
    if not controller_config:
        print("\nFATAL ERROR: ControllerAgent LLM config missing in AGENT_LLM_CONFIG. Cannot proceed.")
        return None, specialist_agents

    controller_provider_name = controller_config.get('provider')
    controller_model_name = controller_config.get('model')
    if not controller_provider_name or not controller_model_name:
        print(f"\nFATAL ERROR: Missing 'provider' or 'model' in config for ControllerAgent. Cannot proceed.")
        return None, specialist_agents

    try:
        controller_provider = await _get_provider(controller_provider_name, controller_config)
        # Pass the successfully instantiated specialist agents
        controller_agent = ControllerAgent(agents=specialist_agents, llm_provider=controller_provider)
        logging.info(f"ControllerAgent initialized successfully.")
    except (ImportError, ValueError, ConnectionError, RuntimeError) as e:
        print(f"\nFATAL ERROR: Failed to initialize Controller provider/agent. Cannot proceed. Details: {e}")
        return None, specialist_agents
    except Exception as e:
        logging.exception(f"Unexpected error initializing ControllerAgent")
        print(f"\nFATAL ERROR: Unexpected error initializing ControllerAgent. Cannot proceed. Details: {e}")
        return None, specialist_agents

    return controller_agent, specialist_agents


# --- Module Reload Logic ---
async def handle_reload_command(module_path: str, controller: ControllerAgent, specialists: Dict[str, BaseAgent]):
    """
    Handles the !reload command to dynamically reload specified modules.
    Attempts to update agent tool definitions if a tools module is reloaded.
    """
    if not module_path:
        print("Usage: !reload <full.module.path> (e.g., agent_system.tools.filesystem)")
        return

    logging.warning(f"--- Attempting to reload module: {module_path} ---")
    print(f"Attempting to reload module: {module_path}...")
    print("WARNING: Reloading may lead to inconsistent state, especially for core components or agent state.")

    try:
        # Check if module is already loaded
        if module_path in sys.modules:
            module_obj = sys.modules[module_path]
            importlib.reload(module_obj) # Perform the reload
            print(f"Successfully reloaded module: {module_path}")
            logging.info(f"Module {module_path} reloaded successfully.")
        else:
             importlib.import_module(module_path) # Load if not already loaded
             print(f"Successfully loaded module for the first time: {module_path}")
             logging.info(f"Module {module_path} loaded for the first time.")

        # If a tools module was reloaded/loaded, re-run discovery and update agents
        tools_pkg_path = Path(sys.modules['agent_system.tools'].__file__).parent
        try:
             # Check if the path corresponds to a file within the tools package directory
             is_tool_module = module_path.startswith("agent_system.tools.") and \
                              (tools_pkg_path / f"{module_path.split('.')[-1]}.py").exists()
        except Exception:
             is_tool_module = False # Handle potential errors if path check fails

        if is_tool_module:
             print("Re-running tool discovery to update registry...")
             logging.info("Tool module reloaded/loaded, re-running tool discovery...")
             discover_tools() # Re-runs importlib on modules, triggering decorators
             print(f"Tool discovery complete. Current registered tools: {len(TOOL_REGISTRY)}")
             logging.info(f"Tool discovery complete after reload. Registered tools: {len(TOOL_REGISTRY)}")

             print("Updating agents with reloaded tool information...")
             logging.info("Updating agents with potentially new tool definitions...")
             all_agents = [controller] + list(specialists.values())
             for agent in all_agents:
                 agent._prepare_allowed_tools() # Re-filter tools based on updated registry
                 if agent.agent_tool_schemas:
                      try:
                           allowed_schema_list = list(agent.agent_tool_schemas.keys())
                           provider_name_str = type(agent.llm_provider).__name__.lower().replace("provider", "")
                           agent.provider_tool_schemas = translate_schema_for_provider(
                                provider_name=provider_name_str,
                                registered_tools=agent.agent_tool_schemas,
                                tool_names=allowed_schema_list
                           )
                           logging.debug(f"Agent '{agent.name}': Re-translated provider schema after reload.")
                      except Exception as e:
                           logging.exception(f"Failed to re-translate tool schema for agent {agent.name} after reload: {e}")
                 else:
                      agent.provider_tool_schemas = None # Clear schema if no tools remain/valid

        # Add warnings for reloading agent or core modules
        elif module_path.startswith("agent_system.agents."):
            print("Agent module reloaded. Existing instances may use updated methods, but state/init config unchanged.")
            logging.warning(f"Agent module {module_path} reloaded, existing instances not re-initialized.")
        elif module_path.startswith("agent_system.core."):
             print("Core module reloaded. HIGHLY EXPERIMENTAL - may destabilize the system.")
             logging.critical(f"Core module {module_path} reloaded. System stability not guaranteed.")

    except ModuleNotFoundError:
        print(f"Error: Module not found: {module_path}")
        logging.error(f"ModuleNotFoundError during reload attempt: {module_path}")
    except Exception as e:
        print(f"Error during reload of '{module_path}': {e}")
        logging.exception(f"Exception during module reload of '{module_path}'")
        traceback.print_exc()


# --- Main Async Function ---
async def async_main():
    """Main asynchronous entry point for the interactive CLI."""
    print("--- Multi-Agent System Interactive CLI ---")
    print("--- WARNING: HIGH-RISK OPERATION MODE ---")
    print(f"Settings loaded. Log level: {logging.getLevelName(settings.LOG_LEVEL)}")
    print(f"Agent state directory: {settings.AGENT_STATE_DIR}")
    print(f"High-risk tools requiring confirmation: {settings.HIGH_RISK_TOOLS or 'NONE (Confirmations Disabled!)'}")
    if not settings.HIGH_RISK_TOOLS:
        print("🚨🚨🚨 WARNING: ALL TOOL CONFIRMATIONS ARE DISABLED! EXTREME RISK! 🚨🚨🚨")
    print("Initializing agents...")

    controller, specialists = await instantiate_agents()

    if controller is None:
        print("Exiting due to initialization failure.")
        await close_providers() # Attempt cleanup even on init fail
        sys.exit(1)

    print("\nInitialization complete. Controller Agent ready.")
    print("Type your requests, 'quit'/'exit' to stop, or '!reload <module.path>' to reload.")

    # --- Interaction Loop ---
    loop = asyncio.get_running_loop()
    while True:
        try:
            # Use loop.run_in_executor for truly non-blocking input
            user_input = await loop.run_in_executor(None, input, "\nUser > ")
            user_input = user_input.strip()

            if not user_input: continue
            if user_input.lower() in ["quit", "exit"]: break

            if user_input.startswith("!reload"):
                parts = user_input.split(maxsplit=1)
                module_to_reload = parts[1] if len(parts) > 1 else ""
                await handle_reload_command(module_to_reload, controller, specialists)
                continue

            # --- Run Controller Agent ---
            print("Controller processing...")
            # Run controller task, which will handle delegation and specialist runs
            # State loading/saving happens within the agent's run method now
            controller_response = await controller.run(user_input, load_state=True, save_state=True)

            print(f"\nController Response:\n{'-'*20}\n{controller_response}\n{'-'*20}")

        except KeyboardInterrupt:
            print("\nCaught KeyboardInterrupt, exiting.")
            break
        except EOFError:
             print("\nCaught EOF, exiting.")
             break
        except Exception as e:
            logging.exception("Error in main interactive loop.")
            print(f"\nAn unexpected error occurred in the main loop: {e}")
            traceback.print_exc()

    await close_providers()
    print("Shutdown complete.")


async def close_providers():
    """Helper function to close all cached provider connections."""
    global provider_cache
    logging.info("Shutting down provider connections...")
    close_tasks = []
    for provider in provider_cache.values():
        if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close):
            close_tasks.append(asyncio.create_task(provider.close(), name=f"close_{type(provider).__name__}"))
        # Add sync close handling here if necessary for some providers

    if close_tasks:
        results = await asyncio.gather(*close_tasks, return_exceptions=True)
        for i, result in enumerate(results):
             if isinstance(result, Exception):
                  task_name = close_tasks[i].get_name() if hasattr(close_tasks[i], 'get_name') else f"Task {i}"
                  logging.error(f"Error closing provider during shutdown ({task_name}): {result}")
    logging.info("Provider cleanup finished.")


if __name__ == "__main__":
    # Logging is configured when settings are imported.
    try:
        asyncio.run(async_main())
    except Exception as e:
         logging.critical(f"Critical error during asyncio event loop execution: {e}", exc_info=True)
         print(f"\nFATAL ERROR: {e}")
         traceback.print_exc()
