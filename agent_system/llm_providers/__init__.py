import os
import logging
import hashlib
import sys
import importlib # Ensure importlib is imported
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
        """Returns unique identifier for caching provider instances."""
        if self.base_url: return f"{self.__class__.__name__}_{self.base_url}"
        key = self.api_key or self._get_key_from_env()
        if key:
            h = hashlib.sha256(key.encode()).hexdigest()[:16]
            return f"{self.__class__.__name__}_key_{h}"
        else:
            return f"{self.__class__.__name__}_local_or_env_key"

    @abstractmethod
    def _get_key_from_env(self) -> Optional[str]:
        """Subclasses must implement this to specify the environment variable name for their API key."""
        pass

    @abstractmethod
    async def start_chat(self, system_prompt: str, tool_schemas: Optional[Any], history: Optional[List[ChatMessage]] = None) -> Any:
        """Initializes a chat session object or prepares history context for the provider."""
        pass

    @abstractmethod
    async def send_message(self, chat_session: Any, prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None, mcp_context: Optional[Dict[str, Any]] = None, mcp_metadata: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
        """Sends message, handles tokens. Accepts optional MCP context/metadata (ignored by default)."""
        pass # Implementation in subclasses

    def get_last_token_usage(self) -> Dict[str, Optional[int]]:
        """Returns approximate token usage for the most recent send_message call."""
        return {"prompt_tokens": self._last_prompt_tokens, "completion_tokens": self._last_completion_tokens}

    def get_total_token_usage(self) -> Dict[str, int]:
        """Returns approximate cumulative token usage tracked by this provider instance."""
        return {"total_prompt_tokens": self._total_prompt_tokens, "total_completion_tokens": self._total_completion_tokens}

    def _update_token_counts(self, prompt_tokens: Optional[int], completion_tokens: Optional[int]):
        """Helper method for subclasses to update token counts after an API call."""
        self._last_prompt_tokens = prompt_tokens; self._last_completion_tokens = completion_tokens
        if prompt_tokens is not None: self._total_prompt_tokens += prompt_tokens
        if completion_tokens is not None: self._total_completion_tokens += completion_tokens

# --- Provider Factory ---
_PROVIDER_CLASS_MAP: Optional[Dict[str, Type[LLMProvider]]] = None

def get_llm_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """Factory function to get an instance of a specific LLM provider (Lazy Loading)."""
    global _PROVIDER_CLASS_MAP
    if _PROVIDER_CLASS_MAP is None:
        _PROVIDER_CLASS_MAP = {}
        # Map is populated lazily below when a provider is first requested

    provider_name_lower = provider_name.lower()
    ProviderClass = _PROVIDER_CLASS_MAP.get(provider_name_lower)

    if not ProviderClass:
        # --- LAZY IMPORT PROVIDER CLASS ---
        module_name: Optional[str] = None
        class_name: Optional[str] = None

        if provider_name_lower == "gemini": module_name, class_name = ".gemini", "GeminiProvider"
        elif provider_name_lower == "openai": module_name, class_name = ".openai", "OpenAIProvider"
        elif provider_name_lower == "anthropic": module_name, class_name = ".anthropic", "AnthropicProvider"
        elif provider_name_lower == "ollama": module_name, class_name = ".ollama", "OllamaProvider"
        else: raise ValueError(f"Unknown LLM provider name: '{provider_name}'")

        try:
            logging.debug(f"Attempting lazy import for: {module_name}.{class_name}")
            # Use importlib (imported at the top)
            provider_module = importlib.import_module(module_name, package=__package__) # Relative import
            ProviderClass = getattr(provider_module, class_name)
            _PROVIDER_CLASS_MAP[provider_name_lower] = ProviderClass # Cache the class itself
            logging.debug(f"Successfully imported {class_name}")
        except ImportError as e:
            # Log detailed error including traceback if import fails
            logging.error(f"Failed to import module or class for provider '{provider_name}': {e}", exc_info=True)
            # Raise a clear error indicating the provider cannot be loaded
            raise ImportError(f"Provider '{provider_name}' could not be loaded. Check installation ({module_name}) and import logs.") from e
        except Exception as e:
            # Catch other potential errors during import process
            logging.error(f"Unexpected error during lazy import for provider '{provider_name}': {e}", exc_info=True)
            raise RuntimeError(f"Failed to load provider '{provider_name}' due to unexpected import error.") from e
        # --- END LAZY IMPORT ---

    if not ProviderClass: # Should be caught above, but defensive check
        raise RuntimeError(f"Provider class for '{provider_name}' not found after import attempt.")

    if "model" not in config:
         raise ValueError(f"Configuration for provider '{provider_name}' must include 'model' name.")

    try:
        # Instantiate the provider class
        instance = ProviderClass(**config)
        logging.debug(f"Successfully created provider instance: {instance.get_identifier()}")
        return instance
    # Catch specific, expected init errors
    except (ValueError, ConnectionError) as e:
        logging.error(f"Failed to initialize provider '{provider_name}' with config {config}: {e}", exc_info=True)
        raise RuntimeError(f"Initialization failed for provider '{provider_name}': {e}") from e
    # Catch any other unexpected errors during instantiation
    except Exception as e:
        logging.exception(f"Unexpected error initializing provider '{provider_name}' with config {config}: {e}")
        raise RuntimeError(f"Unexpected error initializing provider '{provider_name}': {e}") from e
