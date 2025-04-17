import os
import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from dotenv import load_dotenv

# --- Define Paths and Defaults (Safe at module level) ---
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
DOTENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_COMMAND_TIMEOUT: int = 120
DEFAULT_HIGH_RISK_TOOLS: List[str] = [
    "run_shell_command", "run_sudo_command", "apt_command", "yum_command",
    "systemctl_command", "kill_process", "edit_file", "esptool_command",
    "openocd_command", "ssh_command", "scp_command", "gdb_mi_command",
    "nmap_scan", "sqlmap_scan", "nikto_scan", "msfvenom_generate",
    "gobuster_scan", "make_command", "gcc_compile",
]
DEFAULT_AGENT_LLM_CONFIG: Dict[str, Dict[str, Any]] = {
    "ControllerAgent": {"provider": "gemini", "model": "gemini-1.5-flash-latest"},
    "CodingAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"},
    "SysAdminAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"},
    "HardwareAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"},
    "RemoteOpsAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"},
    "DebuggingAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"},
    "CybersecurityAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"},
    "BuildAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"},
    "NetworkAgent": {"provider": "gemini", "model": "gemini-1.5-flash-latest"},
}
DEFAULT_AGENT_STATE_DIR_STR: str = str(PROJECT_ROOT / "agent_state")
DEFAULT_LOG_LEVEL_STR: str = "INFO"
DEFAULT_MAX_GLOBAL_TOKENS: int = 1_000_000
DEFAULT_WARN_TOKEN_THRESHOLD: int = 800_000

# --- Placeholder Variables (will be assigned in initialize_settings) ---
# Define them at module level so imports don't fail, but assign values later.
COMMAND_TIMEOUT: int = DEFAULT_COMMAND_TIMEOUT
HIGH_RISK_TOOLS: List[str] = DEFAULT_HIGH_RISK_TOOLS
AGENT_LLM_CONFIG: Dict[str, Dict[str, Any]] = DEFAULT_AGENT_LLM_CONFIG
AGENT_STATE_DIR: Path = Path(DEFAULT_AGENT_STATE_DIR_STR)
LOG_LEVEL: int = logging.INFO
MAX_GLOBAL_TOKENS: int = DEFAULT_MAX_GLOBAL_TOKENS
WARN_TOKEN_THRESHOLD: int = DEFAULT_WARN_TOKEN_THRESHOLD

# --- Initialization Function ---
_settings_initialized = False

def initialize_settings():
    """
    Loads .env, calculates final settings values, and configures logging.
    Should be called once at application startup.
    """
    global _settings_initialized
    global COMMAND_TIMEOUT, HIGH_RISK_TOOLS, AGENT_LLM_CONFIG, AGENT_STATE_DIR
    global LOG_LEVEL, MAX_GLOBAL_TOKENS, WARN_TOKEN_THRESHOLD

    if _settings_initialized:
        logging.debug("Settings already initialized.")
        return

    # Load .env file
    loaded_env = load_dotenv(dotenv_path=DOTENV_PATH, verbose=True)
    if loaded_env:
        print(f"Loaded configuration from: {DOTENV_PATH}") # Use print before logging is set
    else:
        print(f"Warning: .env file not found at {DOTENV_PATH}. Using defaults/env vars.")

    # Helper function (defined locally or imported if refactored)
    def get_env_var_local(var_name: str, default: Optional[Any] = None, var_type: Optional[type] = None) -> Any:
        value = os.environ.get(var_name)
        if value is None: return default
        if var_type:
            try:
                if var_type == bool: return value.lower() in ("true", "1", "yes", "t")
                elif var_type == list: return [item.strip() for item in value.split(",") if item.strip()]
                elif var_type == dict:
                    if default is not None: return default
                    raise ValueError(f"Cannot parse dict from env var '{var_name}'.")
                return var_type(value)
            except ValueError: return default
        return value

    # --- Calculate Final Settings ---
    COMMAND_TIMEOUT = get_env_var_local("DEFAULT_COMMAND_TIMEOUT", DEFAULT_COMMAND_TIMEOUT, int)
    HIGH_RISK_TOOLS = get_env_var_local("HIGH_RISK_TOOLS", DEFAULT_HIGH_RISK_TOOLS, list)
    AGENT_LLM_CONFIG = DEFAULT_AGENT_LLM_CONFIG.copy() # Start with defaults
    for agent_name in AGENT_LLM_CONFIG.keys(): # Apply overrides
        model_override = get_env_var_local(f"{agent_name.upper()}_MODEL", None, str)
        provider_override = get_env_var_local(f"{agent_name.upper()}_PROVIDER", None, str)
        base_url_override = get_env_var_local(f"{agent_name.upper()}_BASE_URL", None, str)
        if model_override: AGENT_LLM_CONFIG[agent_name]["model"] = model_override
        if provider_override: AGENT_LLM_CONFIG[agent_name]["provider"] = provider_override
        if base_url_override: AGENT_LLM_CONFIG[agent_name]["base_url"] = base_url_override
    OLLAMA_MODEL_GLOBAL = get_env_var_local("OLLAMA_MODEL", None, str)
    OLLAMA_BASE_URL_GLOBAL = get_env_var_local("OLLAMA_BASE_URL", None, str)
    if OLLAMA_BASE_URL_GLOBAL: # Apply global Ollama URL if needed
        for agent_name in AGENT_LLM_CONFIG:
            if AGENT_LLM_CONFIG[agent_name].get("provider") == "ollama" and "base_url" not in AGENT_LLM_CONFIG[agent_name]:
                 AGENT_LLM_CONFIG[agent_name]["base_url"] = OLLAMA_BASE_URL_GLOBAL
    if OLLAMA_MODEL_GLOBAL: # Apply global Ollama model if needed
         for agent_name in AGENT_LLM_CONFIG:
            if AGENT_LLM_CONFIG[agent_name].get("provider") == "ollama" and AGENT_LLM_CONFIG[agent_name].get("model") is None:
                 AGENT_LLM_CONFIG[agent_name]["model"] = OLLAMA_MODEL_GLOBAL
    # Final check for Ollama config
    for agent_name, config in AGENT_LLM_CONFIG.items():
        if config.get("provider") == "ollama":
            if "base_url" not in config or not config["base_url"]: config["base_url"] = "http://localhost:11434"
            if "model" not in config or not config["model"]: raise ValueError(f"Agent '{agent_name}' needs Ollama model defined.")

    MAX_GLOBAL_TOKENS = get_env_var_local("MAX_GLOBAL_TOKENS", DEFAULT_MAX_GLOBAL_TOKENS, int)
    WARN_TOKEN_THRESHOLD = get_env_var_local("WARN_TOKEN_THRESHOLD", DEFAULT_WARN_TOKEN_THRESHOLD, int)
    AGENT_STATE_DIR_STR = get_env_var_local("AGENT_STATE_DIR", DEFAULT_AGENT_STATE_DIR_STR, str)
    AGENT_STATE_DIR = Path(AGENT_STATE_DIR_STR).resolve()
    try: AGENT_STATE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e: print(f"ERROR: Creating agent state dir {AGENT_STATE_DIR} failed: {e}")

    # --- Configure Logging ---
    LOG_LEVEL_STR = get_env_var_local("LOG_LEVEL", DEFAULT_LOG_LEVEL_STR, str).upper()
    LOG_LEVEL_MAP = { "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL }
    LOG_LEVEL = LOG_LEVEL_MAP.get(LOG_LEVEL_STR, logging.INFO)

    # Use force=True to reset any handlers possibly added during failed imports
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True
    )
    # Silence library loggers
    libs_to_silence = ["httpx", "httpcore", "openai", "google", "anthropic", "urllib3"]
    for lib_name in libs_to_silence: logging.getLogger(lib_name).setLevel(logging.WARNING)

    # --- Log Final Settings ---
    logging.info("--- Settings Initialized ---")
    logging.info(f"Project Root: {PROJECT_ROOT}")
    logging.info(f".env Path: {DOTENV_PATH} (Loaded: {DOTENV_PATH.exists()})")
    logging.info(f"Effective Log Level: {logging.getLevelName(LOG_LEVEL)}")
    logging.info(f"Command Timeout: {COMMAND_TIMEOUT}s")
    logging.info(f"High-Risk Tools: {HIGH_RISK_TOOLS if HIGH_RISK_TOOLS else 'NONE'}")
    logging.info(f"Agent State Directory: {AGENT_STATE_DIR}")
    logging.info(f"Token Quota - Max Global: {MAX_GLOBAL_TOKENS if MAX_GLOBAL_TOKENS > 0 else 'Disabled'}")
    logging.info(f"Token Quota - Warn Threshold: {WARN_TOKEN_THRESHOLD if WARN_TOKEN_THRESHOLD > 0 and MAX_GLOBAL_TOKENS > 0 else 'Disabled'}")
    logging.debug(f"Agent LLM Config (Final):\n{json.dumps(AGENT_LLM_CONFIG, indent=2)}")
    logging.info("--- End Settings Initialization ---")

    _settings_initialized = True

# Note: We don't call initialize_settings() here automatically.
# It must be called explicitly by the application entry point.
