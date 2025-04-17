import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from dotenv import load_dotenv

# --- Load Environment Variables ---
# Load from .env file in the project root (parent directory of this file's parent)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"

# Check if .env exists and load it
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH)
    print(f"Loaded configuration from: {DOTENV_PATH}")
else:
    print(f"Warning: .env file not found at {DOTENV_PATH}. Using defaults and environment variables.")

# --- Helper Function to Get Config Value ---
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
                # Handle boolean strings flexibly
                return value.lower() in ("true", "1", "yes", "t")
            elif var_type == list:
                # Assume comma-separated list
                return [item.strip() for item in value.split(",") if item.strip()]
            elif var_type == dict:
                # Cannot reliably parse dict from env var string, maybe require JSON string?
                # For now, return default or raise error if type is dict
                if default is not None: return default
                raise ValueError(f"Cannot parse dict from environment variable '{var_name}' directly.")
            return var_type(value)
        except ValueError:
            logging.warning(
                f"Could not cast environment variable '{var_name}' value '{value}' to type '{var_type}'. Using default: {default}"
            )
            return default
    return value

# --- Core Defaults ---
DEFAULT_COMMAND_TIMEOUT: int = 120
DEFAULT_HIGH_RISK_TOOLS: List[str] = [
    "run_shell_command", "run_sudo_command", "apt_command", "yum_command",
    "systemctl_command", "kill_process", "edit_file", "esptool_command",
    "openocd_command", "ssh_command", "scp_command", "gdb_mi_command",
    "nmap_scan", "sqlmap_scan", "nikto_scan", "msfvenom_generate",
    "gobuster_scan", "make_command", "gcc_compile",
]
# Default LLM configuration for agents (can be overridden by env vars or other config)
# We keep the structure here, but individual model names can be overridden via env vars like CODING_AGENT_MODEL
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
    # Add potential future agents here with default configs
}
DEFAULT_AGENT_STATE_DIR: Path = PROJECT_ROOT / "agent_state"
DEFAULT_LOG_LEVEL: str = "INFO"

# --- Cost/Token Defaults ---
DEFAULT_MAX_GLOBAL_TOKENS: int = 1_000_000
DEFAULT_WARN_TOKEN_THRESHOLD: int = 800_000 # Approx 80% of default max

# --- Load Actual Configuration ---
COMMAND_TIMEOUT: int = get_env_var("DEFAULT_COMMAND_TIMEOUT", DEFAULT_COMMAND_TIMEOUT, int)
HIGH_RISK_TOOLS: List[str] = get_env_var("HIGH_RISK_TOOLS", DEFAULT_HIGH_RISK_TOOLS, list)

# Load agent-specific model overrides
AGENT_LLM_CONFIG: Dict[str, Dict[str, Any]] = DEFAULT_AGENT_LLM_CONFIG.copy() # Start with defaults
for agent_name in AGENT_LLM_CONFIG.keys():
    model_override = get_env_var(f"{agent_name.upper()}_MODEL", None, str)
    provider_override = get_env_var(f"{agent_name.upper()}_PROVIDER", None, str)
    base_url_override = get_env_var(f"{agent_name.upper()}_BASE_URL", None, str) # Allow per-agent URL? Maybe less common.

    if model_override:
        AGENT_LLM_CONFIG[agent_name]["model"] = model_override
    if provider_override:
        AGENT_LLM_CONFIG[agent_name]["provider"] = provider_override
    if base_url_override:
         AGENT_LLM_CONFIG[agent_name]["base_url"] = base_url_override # Add if found

# Allow global override for Ollama model and URL if agent doesn't have specific setting
OLLAMA_MODEL_GLOBAL = get_env_var("OLLAMA_MODEL", None, str)
OLLAMA_BASE_URL_GLOBAL = get_env_var("OLLAMA_BASE_URL", None, str)
if OLLAMA_BASE_URL_GLOBAL:
    # If global Ollama URL is set, apply it to all agents configured to use Ollama *unless* they have a specific base_url set
    for agent_name in AGENT_LLM_CONFIG:
        if AGENT_LLM_CONFIG[agent_name].get("provider") == "ollama" and "base_url" not in AGENT_LLM_CONFIG[agent_name]:
             AGENT_LLM_CONFIG[agent_name]["base_url"] = OLLAMA_BASE_URL_GLOBAL
if OLLAMA_MODEL_GLOBAL:
    # Apply global model name to Ollama agents unless they have a specific model set
     for agent_name in AGENT_LLM_CONFIG:
        if AGENT_LLM_CONFIG[agent_name].get("provider") == "ollama" and AGENT_LLM_CONFIG[agent_name].get("model") is None: # Check if model wasn't already set
             AGENT_LLM_CONFIG[agent_name]["model"] = OLLAMA_MODEL_GLOBAL

# Ensure agents using Ollama have *some* base URL and model defined eventually
for agent_name, config in AGENT_LLM_CONFIG.items():
    if config.get("provider") == "ollama":
        if "base_url" not in config or not config["base_url"]:
             config["base_url"] = "http://localhost:11434" # Final fallback default
             logging.warning(f"Agent '{agent_name}' uses Ollama but no base URL found in .env or defaults. Using {config['base_url']}.")
        if "model" not in config or not config["model"]:
            # If no model is specified anywhere, we have a problem
            raise ValueError(f"Agent '{agent_name}' is configured for Ollama provider, but no model name was specified globally (OLLAMA_MODEL) or for the agent ({agent_name.upper()}_MODEL).")


# --- API Keys (Loaded directly by providers from env vars or args) ---
# Providers will look for GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY in environment
# We don't store them directly in this settings module.

# --- Cost/Token Quotas ---
MAX_GLOBAL_TOKENS: int = get_env_var("MAX_GLOBAL_TOKENS", DEFAULT_MAX_GLOBAL_TOKENS, int)
WARN_TOKEN_THRESHOLD: int = get_env_var("WARN_TOKEN_THRESHOLD", DEFAULT_WARN_TOKEN_THRESHOLD, int)

# --- State Directory ---
AGENT_STATE_DIR_STR: str = get_env_var("AGENT_STATE_DIR", str(DEFAULT_AGENT_STATE_DIR), str)
AGENT_STATE_DIR: Path = Path(AGENT_STATE_DIR_STR).resolve()
# Ensure state directory exists
try:
    AGENT_STATE_DIR.mkdir(parents=True, exist_ok=True)
except OSError as e:
    logging.error(f"Could not create agent state directory {AGENT_STATE_DIR}: {e}")
    # Fallback or exit? For now, just log error. Behavior will depend on agent load/save logic.


# --- Logging Configuration ---
LOG_LEVEL_STR: str = get_env_var("LOG_LEVEL", DEFAULT_LOG_LEVEL, str).upper()
LOG_LEVEL_MAP: Dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
LOG_LEVEL: int = LOG_LEVEL_MAP.get(LOG_LEVEL_STR, logging.INFO)

# Basic logging setup (can be refined later, e.g., file logging)
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Silence noisy http libraries if they get added
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("google.generativeai").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)


# --- Log loaded settings (optional, be careful with sensitive defaults) ---
logging.info("--- Configuration Loaded ---")
logging.info(f"Log Level: {LOG_LEVEL_STR} ({LOG_LEVEL})")
logging.info(f"Command Timeout: {COMMAND_TIMEOUT}s")
logging.info(f"High-Risk Tools requiring confirmation: {HIGH_RISK_TOOLS if HIGH_RISK_TOOLS else 'NONE (Confirmations Disabled!)'}")
logging.info(f"Agent State Directory: {AGENT_STATE_DIR}")
logging.info(f"Token Quota - Max Global: {MAX_GLOBAL_TOKENS if MAX_GLOBAL_TOKENS > 0 else 'Disabled'}")
logging.info(f"Token Quota - Warn Threshold: {WARN_TOKEN_THRESHOLD if WARN_TOKEN_THRESHOLD > 0 and MAX_GLOBAL_TOKENS > 0 else 'Disabled'}")
logging.debug(f"Agent LLM Config (Defaults + Overrides):\n{json.dumps(AGENT_LLM_CONFIG, indent=2)}")
logging.info("--- End Configuration ---")
