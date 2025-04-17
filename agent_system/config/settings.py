import os
import logging
import json # <-- Added missing import
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from dotenv import load_dotenv

# --- Load Environment Variables ---
# Correct calculation for project root (parent of agent_system directory)
PROJECT_ROOT = Path(__file__).parent.parent.parent # <-- Corrected path calculation
DOTENV_PATH = PROJECT_ROOT / ".env"

# Check if .env exists and load it
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH)
    print(f"Loaded configuration from: {DOTENV_PATH}")
else:
    # Use print for initial feedback as logging might not be fully configured yet
    print(f"Warning: .env file not found at {DOTENV_PATH}. Using defaults and environment variables.")

# --- Helper Function to Get Config Value ---
# (Helper function remains the same)
def get_env_var(
    var_name: str, default: Optional[Any] = None, var_type: Optional[type] = None
) -> Any:
    """Gets environment variable, casts to type if specified, returns default if not found."""
    value = os.environ.get(var_name)
    if value is None:
        return default
    if var_type:
        try:
            if var_type == bool:
                return value.lower() in ("true", "1", "yes", "t")
            elif var_type == list:
                return [item.strip() for item in value.split(",") if item.strip()]
            elif var_type == dict:
                if default is not None: return default
                raise ValueError(f"Cannot parse dict from environment variable '{var_name}' directly.")
            return var_type(value)
        except ValueError:
            # Use logging here as it should be configured below soon
            logging.warning(
                f"Could not cast environment variable '{var_name}' value '{value}' to type '{var_type}'. Using default: {default}"
            )
            return default
    return value

# --- Core Defaults ---
# (Defaults remain the same)
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
DEFAULT_AGENT_STATE_DIR: Path = PROJECT_ROOT / "agent_state"
DEFAULT_LOG_LEVEL: str = "INFO"
DEFAULT_MAX_GLOBAL_TOKENS: int = 1_000_000
DEFAULT_WARN_TOKEN_THRESHOLD: int = 800_000

# --- Load Actual Configuration ---
# (Loading logic remains the same)
COMMAND_TIMEOUT: int = get_env_var("DEFAULT_COMMAND_TIMEOUT", DEFAULT_COMMAND_TIMEOUT, int)
HIGH_RISK_TOOLS: List[str] = get_env_var("HIGH_RISK_TOOLS", DEFAULT_HIGH_RISK_TOOLS, list)
AGENT_LLM_CONFIG: Dict[str, Dict[str, Any]] = DEFAULT_AGENT_LLM_CONFIG.copy()
for agent_name in AGENT_LLM_CONFIG.keys():
    model_override = get_env_var(f"{agent_name.upper()}_MODEL", None, str)
    provider_override = get_env_var(f"{agent_name.upper()}_PROVIDER", None, str)
    base_url_override = get_env_var(f"{agent_name.upper()}_BASE_URL", None, str)
    if model_override: AGENT_LLM_CONFIG[agent_name]["model"] = model_override
    if provider_override: AGENT_LLM_CONFIG[agent_name]["provider"] = provider_override
    if base_url_override: AGENT_LLM_CONFIG[agent_name]["base_url"] = base_url_override
OLLAMA_MODEL_GLOBAL = get_env_var("OLLAMA_MODEL", None, str)
OLLAMA_BASE_URL_GLOBAL = get_env_var("OLLAMA_BASE_URL", None, str)
if OLLAMA_BASE_URL_GLOBAL:
    for agent_name in AGENT_LLM_CONFIG:
        if AGENT_LLM_CONFIG[agent_name].get("provider") == "ollama" and "base_url" not in AGENT_LLM_CONFIG[agent_name]:
             AGENT_LLM_CONFIG[agent_name]["base_url"] = OLLAMA_BASE_URL_GLOBAL
if OLLAMA_MODEL_GLOBAL:
     for agent_name in AGENT_LLM_CONFIG:
        if AGENT_LLM_CONFIG[agent_name].get("provider") == "ollama" and AGENT_LLM_CONFIG[agent_name].get("model") is None:
             AGENT_LLM_CONFIG[agent_name]["model"] = OLLAMA_MODEL_GLOBAL
for agent_name, config in AGENT_LLM_CONFIG.items():
    if config.get("provider") == "ollama":
        if "base_url" not in config or not config["base_url"]:
             config["base_url"] = "http://localhost:11434"
             # Use print here as logging might not be set up yet when this check happens
             print(f"Warning: Agent '{agent_name}' uses Ollama but no base URL found. Using default: {config['base_url']}.")
        if "model" not in config or not config["model"]:
            raise ValueError(f"Agent '{agent_name}' uses Ollama provider, but no model name specified globally (OLLAMA_MODEL) or for the agent ({agent_name.upper()}_MODEL).")

MAX_GLOBAL_TOKENS: int = get_env_var("MAX_GLOBAL_TOKENS", DEFAULT_MAX_GLOBAL_TOKENS, int)
WARN_TOKEN_THRESHOLD: int = get_env_var("WARN_TOKEN_THRESHOLD", DEFAULT_WARN_TOKEN_THRESHOLD, int)
AGENT_STATE_DIR_STR: str = get_env_var("AGENT_STATE_DIR", str(DEFAULT_AGENT_STATE_DIR), str)
AGENT_STATE_DIR: Path = Path(AGENT_STATE_DIR_STR).resolve()
try:
    AGENT_STATE_DIR.mkdir(parents=True, exist_ok=True)
except OSError as e:
    print(f"ERROR: Could not create agent state directory {AGENT_STATE_DIR}: {e}") # Print error early

# --- Logging Configuration ---
LOG_LEVEL_STR: str = get_env_var("LOG_LEVEL", DEFAULT_LOG_LEVEL, str).upper()
LOG_LEVEL_MAP: Dict[str, int] = {
    "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING,
    "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL,
}
LOG_LEVEL: int = LOG_LEVEL_MAP.get(LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Silence overly verbose loggers from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("google.generativeai").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- Log loaded settings (using logging now) ---
logging.info("--- Configuration Loaded ---")
logging.info(f"Project Root: {PROJECT_ROOT}")
logging.info(f".env Path: {DOTENV_PATH} (Loaded: {DOTENV_PATH.exists()})")
logging.info(f"Log Level: {LOG_LEVEL_STR} ({LOG_LEVEL})")
logging.info(f"Command Timeout: {COMMAND_TIMEOUT}s")
logging.info(f"High-Risk Tools requiring confirmation: {HIGH_RISK_TOOLS if HIGH_RISK_TOOLS else 'NONE (Confirmations Disabled!)'}")
logging.info(f"Agent State Directory: {AGENT_STATE_DIR}")
logging.info(f"Token Quota - Max Global: {MAX_GLOBAL_TOKENS if MAX_GLOBAL_TOKENS > 0 else 'Disabled'}")
logging.info(f"Token Quota - Warn Threshold: {WARN_TOKEN_THRESHOLD if WARN_TOKEN_THRESHOLD > 0 and MAX_GLOBAL_TOKENS > 0 else 'Disabled'}")
# Use json import which is now present
logging.debug(f"Agent LLM Config (Defaults + Overrides):\n{json.dumps(AGENT_LLM_CONFIG, indent=2)}")
logging.info("--- End Configuration ---")
