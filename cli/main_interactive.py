import asyncio
import logging
import json
import sys
import importlib
import traceback
from pathlib import Path
from typing import Dict, Type, Tuple, Any, Optional

# --- Call settings initialization FIRST ---
from agent_system.config import settings
settings.initialize_settings() # Explicitly initialize settings and logging

# --- Now import other modules ---
from agent_system.core.agent import BaseAgent
from agent_system.core.controller import ControllerAgent
from agent_system.core.interaction import Orchestrator
from agent_system.llm_providers import get_llm_provider, LLMProvider
from agent_system.agents.coding import CodingAgent
from agent_system.agents.sysadmin import SysAdminAgent
from agent_system.agents.hardware import HardwareAgent
from agent_system.agents.remote_ops import RemoteOpsAgent
from agent_system.agents.debugging import DebuggingAgent
from agent_system.agents.cybersecurity import CybersecurityAgent
from agent_system.agents.build import BuildAgent
from agent_system.agents.network import NetworkAgent
from agent_system.tools import discover_tools, TOOL_REGISTRY # Tool discovery runs upon import
from agent_system.config.schemas import translate_schema_for_provider


# --- Global Provider Cache ---
provider_cache: Dict[Tuple[str, str], LLMProvider] = {}
orchestrator = Orchestrator() # Instantiate orchestrator

async def _get_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    # (Implementation is correct, uses factory which uses initialized settings)
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

async def instantiate_agents() -> Tuple[Optional[ControllerAgent], Dict[str, BaseAgent]]:
    # (Implementation is correct, uses _get_provider)
    specialist_agents: Dict[str, BaseAgent] = {}; controller_agent: Optional[ControllerAgent] = None
    agent_classes: Dict[str, Type[BaseAgent]] = { "CodingAgent": CodingAgent, "SysAdminAgent": SysAdminAgent, "HardwareAgent": HardwareAgent, "RemoteOpsAgent": RemoteOpsAgent, "DebuggingAgent": DebuggingAgent, "CybersecurityAgent": CybersecurityAgent, "BuildAgent": BuildAgent, "NetworkAgent": NetworkAgent }
    successful_agents = []
    logging.info("--- Initializing Specialist Agents ---")
    for agent_name, AgentClass in agent_classes.items():
         config = settings.AGENT_LLM_CONFIG.get(agent_name)
         if not config: logging.warning(f"No config for {agent_name}. Skipping."); continue
         provider_name = config.get('provider'); model_name = config.get('model')
         if not provider_name or not model_name: logging.error(f"Missing provider/model for {agent_name}. Skipping."); continue
         try:
             agent_provider = await _get_provider(provider_name, config)
             specialist_agents[agent_name] = AgentClass(llm_provider=agent_provider)
             successful_agents.append(agent_name)
         except Exception as e: print(f"\nERROR: Failed init provider/agent '{agent_name}'. Check logs. Skipping. Details: {e}")
    if not specialist_agents: print("\nFATAL ERROR: No specialists initialized."); return None, {}
    logging.info(f"Initialized specialists: {', '.join(sorted(successful_agents))}")
    logging.info("--- Initializing Controller Agent ---")
    controller_config = settings.AGENT_LLM_CONFIG.get("ControllerAgent")
    if not controller_config: print("\nFATAL ERROR: Controller config missing."); return None, specialist_agents
    controller_provider_name = controller_config.get('provider'); controller_model_name = controller_config.get('model')
    if not controller_provider_name or not controller_model_name: print(f"\nFATAL ERROR: Controller config incomplete."); return None, specialist_agents
    try:
        controller_provider = await _get_provider(controller_provider_name, controller_config)
        controller_agent = ControllerAgent(agents=specialist_agents, llm_provider=controller_provider)
        logging.info(f"ControllerAgent initialized successfully.")
    except Exception as e: print(f"\nFATAL ERROR: Failed Controller init. Details: {e}"); return None, specialist_agents
    return controller_agent, specialist_agents

async def handle_reload_command(module_path: str, controller: ControllerAgent, specialists: Dict[str, BaseAgent]):
    # (Implementation is correct)
    if not module_path: print("Usage: !reload <full.module.path>"); return
    logging.warning(f"--- Reloading module: {module_path} ---"); print(f"Reloading: {module_path}...")
    try:
        if module_path in sys.modules: module_obj = sys.modules[module_path]; importlib.reload(module_obj); print(f"Reloaded: {module_path}"); logging.info(f"Module {module_path} reloaded.")
        else: importlib.import_module(module_path); print(f"Loaded module: {module_path}"); logging.info(f"Module {module_path} loaded.")
        tools_pkg_path = Path(sys.modules['agent_system.tools'].__file__).parent; is_tool_module = False
        try: is_tool_module = module_path.startswith("agent_system.tools.") and (tools_pkg_path / f"{module_path.split('.')[-1]}.py").exists()
        except Exception: pass
        if is_tool_module:
             print("Re-running tool discovery..."); logging.info("Re-running tool discovery..."); discover_tools()
             print(f"Tool discovery complete. Registered: {len(TOOL_REGISTRY)}"); logging.info(f"Tool discovery complete. Registered: {len(TOOL_REGISTRY)}")
             print("Updating agents..."); logging.info("Updating agents with new tool info...")
             all_agents = [controller] + list(specialists.values())
             for agent in all_agents:
                 agent._prepare_allowed_tools()
                 if agent.agent_tool_schemas:
                      try:
                           allowed_list = list(agent.agent_tool_schemas.keys()); provider_name_str = type(agent.llm_provider).__name__.lower().replace("provider", "")
                           agent.provider_tool_schemas = translate_schema_for_provider(provider_name=provider_name_str, registered_tools=agent.agent_tool_schemas, tool_names=allowed_list)
                           logging.debug(f"Agent '{agent.name}': Re-translated schema.")
                      except Exception as e: logging.exception(f"Failed re-translating schema for {agent.name}: {e}")
                 else: agent.provider_tool_schemas = None
        elif module_path.startswith("agent_system.agents."): print("Agent module reloaded. Instances not re-initialized."); logging.warning(f"Agent module {module_path} reloaded.")
        elif module_path.startswith("agent_system.core."): print("Core module reloaded. EXPERIMENTAL."); logging.critical(f"Core module {module_path} reloaded.")
    except ModuleNotFoundError: print(f"Error: Module not found: {module_path}"); logging.error(f"ModuleNotFoundError: {module_path}")
    except Exception as e: print(f"Error during reload: {e}"); logging.exception(f"Exception during reload of '{module_path}'"); traceback.print_exc()

async def async_main():
    """Main asynchronous entry point for the interactive CLI."""
    # Settings initialized at top level import
    print("--- Multi-Agent System Interactive CLI ---")
    print("--- WARNING: HIGH-RISK OPERATION MODE ---")
    # Use logging now that it's guaranteed to be configured
    logging.info(f"Effective Log Level: {logging.getLevelName(settings.LOG_LEVEL)}")
    logging.info(f"Agent state directory: {settings.AGENT_STATE_DIR}")
    logging.info(f"High-risk tools: {settings.HIGH_RISK_TOOLS or 'NONE'}")
    if not settings.HIGH_RISK_TOOLS: logging.critical("ALL TOOL CONFIRMATIONS DISABLED!")
    logging.info("Initializing agents...")

    controller, specialists = await instantiate_agents()

    if controller is None:
        logging.critical("Exiting due to agent initialization failure.")
        await close_providers()
        sys.exit(1)

    logging.info("Initialization complete. Controller Agent ready.")
    print("\nInitialization complete. Controller Agent ready.")
    print("Type your requests, 'quit'/'exit' to stop, or '!reload <module.path>' to reload.")

    loop = asyncio.get_running_loop()
    while True:
        try:
            user_input = await loop.run_in_executor(None, input, "\nUser > ")
            user_input = user_input.strip()
            if not user_input: continue
            if user_input.lower() in ["quit", "exit"]: break
            if user_input.startswith("!reload"):
                parts = user_input.split(maxsplit=1); module_to_reload = parts[1] if len(parts) > 1 else ""
                await handle_reload_command(module_to_reload, controller, specialists); continue
            print("Controller processing...") # Give user feedback
            controller_response = await controller.run(user_input, load_state=True, save_state=True)
            print(f"\nController Response:\n{'-'*20}\n{controller_response}\n{'-'*20}")
        except KeyboardInterrupt: print("\nCaught KeyboardInterrupt, exiting."); break
        except EOFError: print("\nCaught EOF, exiting."); break
        except Exception as e: logging.exception("Error in main interactive loop."); print(f"\nUnexpected loop error: {e}"); traceback.print_exc()

    await close_providers()
    print("Shutdown complete.")

async def close_providers():
    """Helper function to close all cached provider connections."""
    # (Implementation is correct)
    global provider_cache; logging.info("Shutting down provider connections...")
    close_tasks = []
    for provider in provider_cache.values():
        if hasattr(provider, 'close') and asyncio.iscoroutinefunction(provider.close):
            close_tasks.append(asyncio.create_task(provider.close(), name=f"close_{type(provider).__name__}"))
    if close_tasks:
        results = await asyncio.gather(*close_tasks, return_exceptions=True)
        for i, result in enumerate(results):
             if isinstance(result, Exception): task_name = close_tasks[i].get_name(); logging.error(f"Error closing provider ({task_name}): {result}")
    logging.info("Provider cleanup finished.")

if __name__ == "__main__":
    # Initialize settings and logging FIRST
    try:
        settings.initialize_settings()
        asyncio.run(async_main())
    except Exception as e:
         # Catch errors during initialization or asyncio.run
         print(f"\nFATAL ERROR: {e}", file=sys.stderr)
         logging.critical(f"Critical error during startup/runtime: {e}", exc_info=True)
         traceback.print_exc(file=sys.stderr)
         sys.exit(1)
