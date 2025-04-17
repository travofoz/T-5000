from flask import render_template, request, jsonify, current_app, session as flask_session # Renamed to avoid conflict
import logging
import asyncio
import uuid # For generating session IDs
from typing import Dict, Any, Optional, Tuple, Type # Added Type

# Import the app instance created in web/__init__.py
from . import app

# Core agent components & factory
from agent_system.core.agent import BaseAgent
from agent_system.core.controller import ControllerAgent
from agent_system.llm_providers import get_llm_provider, LLMProvider, provider_cache # Use shared cache
from agent_system.config import settings

# Import agent classes (needed for type hints and instantiation)
# This approach assumes agents are defined and importable.
from agent_system.agents.coding import CodingAgent
from agent_system.agents.sysadmin import SysAdminAgent
from agent_system.agents.hardware import HardwareAgent
from agent_system.agents.remote_ops import RemoteOpsAgent
from agent_system.agents.debugging import DebuggingAgent
from agent_system.agents.cybersecurity import CybersecurityAgent
from agent_system.agents.build import BuildAgent
from agent_system.agents.network import NetworkAgent


# --- Session and Agent Management ---

# Store active agent controller instances mapped to session IDs.
# WARNING: In a production environment with multiple web workers/processes,
# storing agent instances in memory like this is NOT scalable or robust.
# Consider using external storage (Redis, DB) or background task queues (Celery)
# to manage agent state and execution across requests/workers.
active_sessions: Dict[str, ControllerAgent] = {}

async def get_or_create_cached_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """
    Shared helper to get or create cached LLM providers.
    (Copied from CLI main - Ideally refactor into a shared utility module)
    """
    global provider_cache
    prelim_key_detail = config.get("base_url") or config.get("api_key") or "default_or_env"
    prelim_cache_key = (provider_name.lower(), prelim_key_detail)
    if prelim_cache_key in provider_cache:
        provider = provider_cache[prelim_cache_key]
        provider.model_name = config.get("model", provider.model_name)
        return provider
    else:
        provider_instance = get_llm_provider(provider_name, config) # Factory handles creation
        instance_cache_key = (provider_name.lower(), provider_instance.get_identifier())
        if instance_cache_key != prelim_cache_key and instance_cache_key in provider_cache:
           provider_instance = provider_cache[instance_cache_key]
           provider_instance.model_name = config.get("model", provider_instance.model_name)
        else:
           provider_cache[instance_cache_key] = provider_instance
           if instance_cache_key != prelim_cache_key: provider_cache[prelim_cache_key] = provider_instance # Cache under simple key too
        return provider_instance

async def get_session_controller(session_id: str) -> ControllerAgent:
    """
    Gets the ControllerAgent instance for the given session ID from memory cache.
    If not found, initializes the agent system (controller + specialists) for this session.
    """
    global active_sessions
    if session_id in active_sessions:
        logging.debug(f"Found active controller for session: {session_id}")
        return active_sessions[session_id]
    else:
        logging.info(f"Initializing new agent system for session: {session_id}")
        # --- Instantiate Agents for this Session ---
        specialist_agents: Dict[str, BaseAgent] = {}
        controller_agent: Optional[ControllerAgent] = None

        agent_classes: Dict[str, Type[BaseAgent]] = {
            "CodingAgent": CodingAgent, "SysAdminAgent": SysAdminAgent, "HardwareAgent": HardwareAgent,
            "RemoteOpsAgent": RemoteOpsAgent, "DebuggingAgent": DebuggingAgent,
            "CybersecurityAgent": CybersecurityAgent, "BuildAgent": BuildAgent, "NetworkAgent": NetworkAgent
        }

        # Instantiate Specialists with session_id
        for agent_name, AgentClass in agent_classes.items():
            config = settings.AGENT_LLM_CONFIG.get(agent_name)
            if not config: continue
            provider_name = config.get('provider')
            model_name = config.get('model')
            if not provider_name or not model_name: continue

            try:
                agent_provider = await get_or_create_cached_provider(provider_name, config)
                # Pass the session_id when creating specialist agents
                specialist_agents[agent_name] = AgentClass(llm_provider=agent_provider, session_id=session_id)
            except Exception as e:
                logging.error(f"Failed to initialize specialist '{agent_name}' for session '{session_id}': {e}", exc_info=True)

        # Instantiate Controller
        controller_config = settings.AGENT_LLM_CONFIG.get("ControllerAgent")
        if controller_config:
            provider_name = controller_config.get('provider')
            model_name = controller_config.get('model')
            if provider_name and model_name:
                 try:
                     controller_provider = await get_or_create_cached_provider(provider_name, controller_config)
                     # Controller itself might not need session_id for its own state, but pass for consistency
                     controller_agent = ControllerAgent(
                         agents=specialist_agents,
                         llm_provider=controller_provider
                         # session_id=session_id # Optional for Controller
                     )
                     active_sessions[session_id] = controller_agent # Store the new controller instance
                     logging.info(f"Successfully initialized controller and {len(specialist_agents)} specialists for session {session_id}.")
                 except Exception as e:
                      logging.exception(f"Failed to initialize Controller for session '{session_id}': {e}")
                      raise RuntimeError(f"Failed to initialize ControllerAgent for session {session_id}") from e
            else:
                 raise ValueError("ControllerAgent configuration missing provider or model.")
        else:
            raise ValueError("ControllerAgent configuration not found.")

        return controller_agent


# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main chat interface page."""
    # Ensure a session ID exists using Flask's session handling
    if 'session_id' not in flask_session:
        flask_session['session_id'] = str(uuid.uuid4())
        logging.info(f"Generated new Flask session ID: {flask_session['session_id']}")
    else:
         logging.debug(f"Using existing Flask session ID: {flask_session['session_id']}")

    # Assumes 'templates/index.html' exists relative to configured template_folder
    try:
        return render_template('index.html', title='Agent System Web UI')
    except Exception as e:
        logging.exception("Error rendering index.html")
        return f"Error loading template: {e}", 500


@app.route('/api/prompt', methods=['POST'])
async def handle_prompt():
    """API endpoint to receive user prompts and return agent responses using session state."""
    if 'session_id' not in flask_session:
        # Should ideally not happen if user visited '/' first, but handle defensively
        return jsonify({"error": "Session not initialized. Please refresh the page."}), 400

    session_id = flask_session['session_id']

    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    prompt = data.get('prompt')

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "Missing, invalid, or empty 'prompt' in request body"}), 400

    logging.info(f"API request received (Session: {session_id}). Prompt: {prompt[:100]}...")

    try:
        # Get or initialize the controller for this session
        # This now retrieves/creates the agent instances associated with the session_id
        controller = await get_session_controller(session_id)

        # Run the controller - it will use its session_id internally for state
        # Always load/save state for web sessions to maintain conversation history
        response_text = await controller.run(prompt, load_state=True, save_state=True)

        return jsonify({"response": response_text})

    except Exception as e:
        logging.exception(f"Error processing API prompt request for session {session_id}")
        return jsonify({"error": f"An internal server error occurred: {e}"}), 500
