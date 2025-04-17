import asyncio
import logging
import json
import sys
import importlib
import traceback
from typing import Dict, Type, Tuple, Any

# Core agent components
from agent_system.core.agent import BaseAgent
from agent_system.core.controller import ControllerAgent

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


# --- Provider Cache ---
# Cache LLMProvider instances to avoid redundant initializations (e.g., same API key/client)
provider_cache: Dict[Tuple[str, str], LLMProvider] = {}

async def get_or_create_cached_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """
    Gets or creates an LLMProvider instance, utilizing a cache.
    Uses the factory function from llm_providers.__init__ and caches based on the
    provider instance's unique identifier after creation.
    Handles potential initialization errors.
    """
    global provider_cache

    # Construct a preliminary cache key based on config name and URL/key if available.
    # This allows checking the cache before potentially creating a new instance.
    prelim_key_detail = config.get("base_url") or config.get("api_key") or "default_or_env"
    prelim_cache_key = (provider_name.lower(), prelim_key_detail)

    if prelim_cache_key in provider_cache:
         logging.info(f"Reusing cached LLM Provider instance for preliminary key: {prelim_cache_key}")
         provider = provider_cache[prelim_cache_key]
         # Ensure the model name is updated for this specific agent use case
         provider.model_name = config.get("model", provider.model_name)
         return provider
    else:
         logging.info(f"Cache miss for LLM Provider preliminary key: {prelim_cache_key}. Attempting creation.")
         try:
             # Use the factory function to get/create the provider
             provider_instance = get_llm_provider(provider_name, config)

             # Use the *instance's* actual identifier for reliable caching
             # This handles cases where keys come from environment variables correctly.
             instance_cache_key = (provider_name.lower(), provider_instance.get_identifier())
             if instance_cache_key != prelim_cache_key and instance_cache_key in provider_cache:
                 # If the actual identifier matches an existing cached instance (e.g. env var loaded same key)
                 logging.info(f"Found existing provider instance via identifier match: {instance_cache_key}. Reusing.")
                 provider_instance = provider_cache[instance_cache_key]
                 # Update model name on the found instance
                 provider_instance.model_name = config.get("model", provider_instance.model_name)
             else:
                 # Cache the newly created instance using its actual identifier
                 logging.info(f"Caching new provider instance with key: {instance_cache_key}")
                 provider_cache[instance_cache_key] = provider_instance
                 # Also cache under the preliminary key to speed up future lookups with same config? Maybe.
                 # Let's keep it simple: only cache under the definitive instance_cache_key.
                 # If the prelim_key was different, store under that too for faster future hits *if* the config matches exactly?
                 if instance_cache_key != prelim_cache_key:
                     provider_cache[prelim_cache_key] = provider_instance # Cache under simple key too

             return provider_instance
         except (ImportError, ValueError, ConnectionError, RuntimeError) as e:
              logging.error(f"Failed to get or create provider '{provider_name}' with config {config}: {e}", exc_info=True)
              raise # Re-raise the exception


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
             # Get potentially cached provider instance
             agent_provider = await get_or_create_cached_provider(provider_name, config)
             # Instantiate the agent
             specialist_agents[agent_name] = AgentClass(llm_provider=agent_provider)
             successful_agents.append(agent_name)
         except (ImportError, ValueError, ConnectionError, RuntimeError) as e:
             print(f"\nERROR: Failed to initialize provider/agent '{agent_name}'. Check config/keys/SDKs/connections. Skipping. Details: {e}")
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
        controller_provider = await get_or_create_cached_provider(controller_provider_name, controller_config)
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
            # Perform the reload
            importlib.reload(module_obj)
            print(f"Successfully reloaded module: {module_path}")
            logging.info(f"Module {module_path} reloaded successfully.")
        else:
             # If not loaded, just load it (first time)
             importlib.import_module(module_path)
             print(f"Successfully loaded module for the first time: {module_path}")
             logging.info(f"Module {module_path} loaded for the first time.")


        # If a tools module was reloaded/loaded, re-run discovery to update the registry
        # Check if the module path corresponds to a file within the tools directory
        tools_pkg_path = Path(sys.modules['agent_system.tools'].__file__).parent
        target_module_file = tools_pkg_path / f"{module_path.split('.')[-1]}.py"

        if module_path.startswith("agent_system.tools.") and target_module_file.exists():
             print("Re-running tool discovery to update registry...")
             logging.info("Tool module reloaded/loaded, re-running tool discovery...")
             # discover_tools() should handle re-registration and updates
             discover_tools()
             print(f"Tool discovery complete. Current registered tools: {len(TOOL_REGISTRY)}")
             logging.info(f"Tool discovery complete after reload. Registered tools: {len(TOOL_REGISTRY)}")

             # Agents need to be updated with the potentially new tool functions/schemas
             print("Updating agents with reloaded tool information...")
             logging.info("Updating agents with potentially new tool definitions...")
             all_agents = [controller] + list(specialists.values())
             for agent in all_agents:
                 agent._prepare_allowed_tools() # Re-filter tools based on updated registry
                 # Re-translate schemas for the provider
                 if agent.agent_tool_schemas:
                      try:
                           allowed_schema_list = list(agent.agent_tool_schemas.keys())
                           agent.provider_tool_schemas = translate_schema_for_provider(
                                provider_name=type(agent.llm_provider).__name__.lower().replace("provider", ""),
                                registered_tools=agent.agent_tool_schemas, # Pass agent's allowed schemas
                                tool_names=allowed_schema_list
                           )
                           logging.debug(f"Agent '{agent.name}': Re-translated provider schema after reload.")
                      except Exception as e:
                           logging.exception(f"Failed to re-translate tool schema for agent {agent.name} after reload: {e}")
                 else:
                      agent.provider_tool_schemas = None # Clear schema if no tools remain/valid

        # Warn about reloading agent or core modules
        elif module_path.startswith("agent_system.agents."):
            print("Agent module reloaded. Existing agent instances might use updated methods,")
            print("but their internal state and __init__ configuration remain unchanged.")
            print("Restart application for full effect or careful state management.")
            logging.warning(f"Agent module {module_path} reloaded, but existing instances not re-initialized.")
        elif module_path.startswith("agent_system.core."):
             print("Core module reloaded. This is highly experimental and may destabilize the system.")
             logging.critical(f"Core module {module_path} reloaded. System stability not guaranteed.")


    except ModuleNotFoundError:
        print(f"Error: Module not found: {module_path}")
        logging.error(f"ModuleNotFoundError during reload: {module_path}")
    except Exception as e:
        print(f"Error during reload: {e}")
        logging.exception(f"Exception during module reload of '{module_path}'")
        traceback.print_exc()


# --- Main Async Function ---
async def async_main():
    """Main asynchronous entry point for the interactive CLI."""
    print("--- Multi-Agent System Interactive CLI ---")
    print("--- WARNING: HIGH-RISK OPERATION MODE ---")
    # Logging is configured by importing settings
    print(f"Settings loaded. Log level: {logging.getLevelName(settings.LOG_LEVEL)}")
    print(f"Agent state directory: {settings.AGENT_STATE_DIR}")
    print(f"High-risk tools requiring confirmation: {settings.HIGH_RISK_TOOLS or 'NONE (Confirmations Disabled!)'}")
    if not settings.HIGH_RISK_TOOLS:
        print("🚨🚨🚨 WARNING: ALL TOOL CONFIRMATIONS ARE DISABLED! EXTREME RISK! 🚨🚨🚨")
    print("Initializing agents...")

    controller, specialists = await instantiate_agents()

    if controller is None:
        print("Exiting due to initialization failure.")
        # Clean up any providers that might have been created before failure
        for provider in provider_cache.values():
             if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close): await provider.close()
        sys.exit(1)

    print("\nInitialization complete. Controller Agent ready.")
    print("Type your requests, 'quit'/'exit' to stop, or '!reload <module.path>' to reload.")

    # --- Interaction Loop ---
    while True:
        try:
            # Run input in a separate thread to avoid blocking asyncio loop
            user_input = await asyncio.to_thread(input, "\nUser > ")
            user_input = user_input.strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit"]:
                print("Exiting agent system...")
                break

            # Handle reload command
            if user_input.startswith("!reload"):
                parts = user_input.split(maxsplit=1)
                module_to_reload = parts[1] if len(parts) > 1 else ""
                await handle_reload_command(module_to_reload, controller, specialists)
                continue

            # --- Run Controller Agent ---
            print("Controller processing...")
            controller_response = await controller.run(user_input) # This handles delegation internally

            # Display final response from controller (which includes specialist result)
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
            # Optionally decide whether to break or continue on general errors
            # continue

    # --- Cleanup ---
    print("Shutting down...")
    # Close provider clients if they have an async close method
    for provider in provider_cache.values():
        if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close):
            try:
                await provider.close()
                logging.info(f"Closed provider client: {type(provider).__name__}")
            except Exception as close_err:
                 logging.error(f"Error closing provider {type(provider).__name__}: {close_err}")
        # Add sync close handling if needed for some providers
        # elif hasattr(provider, 'close'): ...

    print("Shutdown complete.")


if __name__ == "__main__":
    # Logging is configured when settings are imported.
    # No need for additional setup here unless overriding handlers.
    try:
        asyncio.run(async_main())
    except Exception as e:
         # Catch errors during asyncio.run itself
         logging.critical(f"Critical error during asyncio event loop execution: {e}", exc_info=True)
         print(f"\nFATAL ERROR: {e}")
         traceback.print_exc()
