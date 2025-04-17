import os
import logging
import hashlib
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Union, Type

# Import core data types
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult

# --- Base LLM Provider Class ---

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        """
        Initializes the provider. Subclasses should call super().__init__ and
        perform provider-specific setup (like client initialization).

        Args:
            model: The default model name this provider instance will use.
            api_key: Optional API key. If None, subclasses should attempt to load from environment.
            base_url: Optional base URL for the API endpoint (e.g., for local models).
            **kwargs: Additional provider-specific configuration arguments.
        """
        self.model_name = model
        self.api_key = api_key # Store provided key if any
        self.base_url = base_url # Store provided base URL if any
        self._config_kwargs = kwargs # Store other args

        # Internal state for token tracking (optional)
        self._last_prompt_tokens: Optional[int] = None
        self._last_completion_tokens: Optional[int] = None
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0

        logging.info(f"{self.__class__.__name__} base initialized. Target Model: {self.model_name}, Base URL: {self.base_url or 'Default'}")

    def get_identifier(self) -> str:
        """
        Returns a unique identifier for caching provider instances based on essential config.
        Primarily uses Base URL if available, otherwise a hash of the API Key, or a default.
        Avoids logging sensitive keys.
        """
        # Use base_url if it's set (common for local/custom endpoints)
        if self.base_url:
            return f"{self.__class__.__name__}_{self.base_url}"

        # If API key was provided explicitly or found in environment during subclass init
        key_to_hash = self.api_key or self._get_key_from_env()
        if key_to_hash:
            # Use a hash of the key for uniqueness without exposing it
            hasher = hashlib.sha256()
            hasher.update(key_to_hash.encode('utf-8'))
            key_hash = hasher.hexdigest()[:16] # Truncated hash
            return f"{self.__class__.__name__}_key_{key_hash}"
        else:
            # Fallback if neither URL nor Key is available
            return f"{self.__class__.__name__}_local_or_env_key"

    @abstractmethod
    def _get_key_from_env(self) -> Optional[str]:
        """Subclasses must implement this to specify the environment variable name for their API key."""
        pass

    @abstractmethod
    async def start_chat(self, system_prompt: str, tool_schemas: Optional[Any], history: Optional[List[ChatMessage]] = None) -> Any:
        """
        Initializes a chat session object or prepares history context for the provider.
        This method should be asynchronous.

        Args:
            system_prompt: The system prompt for the agent.
            tool_schemas: Provider-specific representation of the available tools.
            history: The existing conversation history (list of ChatMessage).

        Returns:
            A chat session object or formatted history structure specific to the provider.
        """
        pass

    @abstractmethod
    async def send_message(self, chat_session: Any, prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
        """
        Sends a message (prompt text or tool results) to the LLM and gets the response.
        Handles token counting internally if supported by the provider.
        This method should be asynchronous.

        Args:
            chat_session: The session object or history structure from start_chat.
            prompt_parts: A list containing the user's text prompt or ToolResult objects.
                          (Changed from original: now takes list of parts for flexibility).
            model_name_override: Optionally override the default model for this specific call.

        Returns:
            A tuple containing:
                - Optional[str]: The text response from the model.
                - Optional[List[ToolCall]]: A list of tool calls requested by the model.
        """
        # Reset token counts for this specific call before sending
        self._last_prompt_tokens = None
        self._last_completion_tokens = None
        pass # Implementation in subclasses

    def get_last_token_usage(self) -> Dict[str, Optional[int]]:
        """
        Returns the *approximate* token usage for the most recent send_message call.
        Providers should update self._last_prompt_tokens and self._last_completion_tokens
        within their send_message implementation if the API provides this data.

        Returns:
            A dictionary with 'prompt_tokens' and 'completion_tokens'. Values may be None
            if the provider API doesn't return this information.
        """
        return {
            "prompt_tokens": self._last_prompt_tokens,
            "completion_tokens": self._last_completion_tokens,
        }

    def get_total_token_usage(self) -> Dict[str, int]:
        """
        Returns the *approximate* cumulative token usage tracked by this provider instance.
        """
        return {
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
        }

    def _update_token_counts(self, prompt_tokens: Optional[int], completion_tokens: Optional[int]):
        """Helper method for subclasses to update token counts after an API call."""
        self._last_prompt_tokens = prompt_tokens
        self._last_completion_tokens = completion_tokens
        if prompt_tokens is not None:
            self._total_prompt_tokens += prompt_tokens
        if completion_tokens is not None:
            self._total_completion_tokens += completion_tokens

# --- Provider Factory ---
# Avoid circular imports by defining the factory function here,
# but the actual provider classes will be imported lazily or inside the function.

# Placeholder for the map, will be populated lazily or by subclasses registering themselves?
# For now, lazy import within the factory function is simplest.
_PROVIDER_CLASS_MAP: Optional[Dict[str, Type[LLMProvider]]] = None

def get_llm_provider(provider_name: str, config: Dict[str, Any]) -> LLMProvider:
    """
    Factory function to get an instance of a specific LLM provider.
    This function imports provider classes on demand to avoid circular dependencies
    and only loading necessary libraries.

    Args:
        provider_name: The name of the provider (e.g., 'gemini', 'openai').
        config: A dictionary containing configuration for the provider, including
                'model', and optionally 'api_key', 'base_url', etc.

    Returns:
        An initialized instance of the requested LLMProvider subclass.

    Raises:
        ValueError: If the provider name is unknown or required config is missing.
        ImportError: If the required library for the provider is not installed.
        RuntimeError: If the provider fails to initialize.
    """
    global _PROVIDER_CLASS_MAP
    if _PROVIDER_CLASS_MAP is None:
        # Lazy load the map to avoid import issues at module load time
        try:
            from .gemini import GeminiProvider
            from .openai import OpenAIProvider
            from .anthropic import AnthropicProvider
            from .ollama import OllamaProvider
            _PROVIDER_CLASS_MAP = {
                "gemini": GeminiProvider,
                "openai": OpenAIProvider,
                "anthropic": AnthropicProvider,
                "ollama": OllamaProvider,
            }
        except ImportError as e:
             logging.error(f"Failed to import a provider class, some providers may be unavailable: {e}", exc_info=True)
             # Continue if possible, maybe only some providers failed
             if _PROVIDER_CLASS_MAP is None: _PROVIDER_CLASS_MAP = {} # Ensure map exists even if imports fail

    provider_name_lower = provider_name.lower()
    ProviderClass = _PROVIDER_CLASS_MAP.get(provider_name_lower)

    if not ProviderClass:
        # Check if it was an import error that prevented loading
        if provider_name_lower in ['gemini', 'openai', 'anthropic', 'ollama'] : # Add any other expected providers
            raise ImportError(f"Required library for provider '{provider_name}' might be missing or failed to import.")
        else:
            raise ValueError(f"Unknown LLM provider name: '{provider_name}'. Available: {list(_PROVIDER_CLASS_MAP.keys())}")

    if "model" not in config:
         raise ValueError(f"Configuration for provider '{provider_name}' must include a 'model' name.")

    try:
        # Instantiate the provider class with its specific configuration
        # The config dict is expected to contain 'model' and potentially 'api_key', 'base_url', etc.
        instance = ProviderClass(**config)
        logging.info(f"Successfully created provider instance: {instance.get_identifier()}")
        return instance
    except (ImportError, ValueError, ConnectionError) as e:
        # Catch errors specifically related to initialization (missing keys, bad connection)
        logging.error(f"Failed to initialize provider '{provider_name}' with config {config}: {e}", exc_info=True)
        # Re-raise as RuntimeError to indicate failure to create the required provider
        raise RuntimeError(f"Initialization failed for provider '{provider_name}': {e}") from e
    except Exception as e:
        # Catch any other unexpected errors during instantiation
        logging.exception(f"Unexpected error initializing provider '{provider_name}' with config {config}: {e}")
        raise RuntimeError(f"Unexpected error initializing provider '{provider_name}': {e}") from e
