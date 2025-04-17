import os
import logging
import hashlib
import sys # <-- Added for debug print
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Union, Type

# Import core data types
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult

# --- Base LLM Provider Class ---
class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        self.model_name = model
        self.api_key = api_key
        self.base_url = base_url
        self._config_kwargs = kwargs
        self._last_prompt_tokens: Optional[int] = None
        self._last_completion_tokens: Optional[int] = None
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        logging.info(f"{self.__class__.__name__} base initialized. Target Model: {self.model_name}, Base URL: {self.base_url or 'Default'}")

    def get_identifier(self) -> str:
        if self.base_url: return f"{self.__class__.__name__}_{self.base_url}"
        key_to_hash = self.api_key or self._get_key_from_env()
        if key_to_hash:
            hasher = hashlib.sha256(); hasher.update(key_to_hash.encode('utf-8')); key_hash = hasher.hexdigest()[:16]
            return f"{self.__class__.__name__}_key_{key_hash}"
        else: return f"{self.__class__.__name__}_local_or_env_key"

    @abstractmethod
    def _get_key_from_env(self) -> Optional[str]: pass
    @abstractmethod
    async def start_chat(self, system_prompt: str, tool_schemas: Optional[Any], history: Optional[List[ChatMessage]] = None) -> Any: pass
    @abstractmethod
    async def send_message(self, chat_session: Any, prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None, mcp_context: Optional[Dict[str, Any]] = None, mcp_metadata: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]: pass

    def get_last_token_usage(self) -> Dict[str, Optional[int]]: return {"prompt_tokens": self._last_prompt_tokens, "completion_tokens": self._last_completion_tokens}
    def get_total_token_usage(self) -> Dict[str, int]: return {"total_prompt_tokens": self._total_prompt_tokens, "total_completion_tokens": self._total_completion_tokens}
    def _update_token_counts(self, prompt_tokens: Optional[int], completion_tokens: Optional[int]):
        self._last_prompt_tokens = prompt_tokens; self._last_completion_tokens = completion_tokens
        if prompt_tokens is not None: self._total_prompt_tokens += prompt_tokens
        if completion_tokens is not None: self._total_completion_tokens += completion_tokens

# --- Provider Factory ---
_PROVIDER_CLASS_MAP: Optional[Dict[str, Type[LLMProvider]]] = None

def get_llm_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """Factory function to get an instance of a specific LLM provider."""
    global _PROVIDER_CLASS_MAP
    if _PROVIDER_CLASS_MAP is None:

        # ---- START DEBUG ----
        # Use logging now that it should be configured to DEBUG
        logging.debug("--- DEBUG: Python Path inside get_llm_provider factory ---")
        logging.debug("Python Path before lazy provider import:")
        for p in sys.path: logging.debug(f"  - {p}")
        logging.debug("--- END DEBUG ---")
        # ---- END DEBUG ----

        _PROVIDER_CLASS_MAP = {}
        try:
            from .gemini import GeminiProvider
            _PROVIDER_CLASS_MAP["gemini"] = GeminiProvider
            logging.debug("Successfully imported GeminiProvider")
        except ImportError as e: logging.warning(f"Failed GeminiProvider import: {e}. Unavailable.")
        except Exception as e: logging.error(f"Error during GeminiProvider import: {e}", exc_info=True)
        try:
            from .openai import OpenAIProvider
            _PROVIDER_CLASS_MAP["openai"] = OpenAIProvider
            logging.debug("Successfully imported OpenAIProvider")
        except ImportError as e: logging.warning(f"Failed OpenAIProvider import: {e}. Unavailable.")
        except Exception as e: logging.error(f"Error during OpenAIProvider import: {e}", exc_info=True)
        try:
            from .anthropic import AnthropicProvider
            _PROVIDER_CLASS_MAP["anthropic"] = AnthropicProvider
            logging.debug("Successfully imported AnthropicProvider")
        except ImportError as e: logging.warning(f"Failed AnthropicProvider import: {e}. Unavailable.") # This might still log if import fails
        except Exception as e: logging.error(f"Error during AnthropicProvider import: {e}", exc_info=True)
        try:
            from .ollama import OllamaProvider
            _PROVIDER_CLASS_MAP["ollama"] = OllamaProvider
            logging.debug("Successfully imported OllamaProvider")
        except ImportError as e: logging.warning(f"Failed OllamaProvider import: {e}. Unavailable.")
        except Exception as e: logging.error(f"Error during OllamaProvider import: {e}", exc_info=True)
        if not _PROVIDER_CLASS_MAP: raise RuntimeError("Could not import any LLM provider classes.")

    provider_name_lower = provider_name.lower()
    ProviderClass = _PROVIDER_CLASS_MAP.get(provider_name_lower)
    if not ProviderClass: raise ImportError(f"Provider '{provider_name}' could not be loaded. Check import logs.")
    if "model" not in config: raise ValueError(f"Config for '{provider_name}' missing 'model'.")
    try:
        instance = ProviderClass(**config)
        logging.debug(f"Successfully created provider instance: {instance.get_identifier()}")
        return instance
    except (ImportError, ValueError, ConnectionError) as e: raise RuntimeError(f"Init failed for provider '{provider_name}': {e}") from e
    except Exception as e: raise RuntimeError(f"Unexpected error initializing provider '{provider_name}': {e}") from e
