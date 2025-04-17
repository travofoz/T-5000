import os
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union

# Import base class and core data types
from . import LLMProvider
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult
from agent_system.config.schemas import translate_to_anthropic_schema, GenericToolSchema # Import translator

# Attempt to import Anthropic library
try:
    import anthropic
    from anthropic import AsyncAnthropic # Use the async client
    from anthropic.types import Message, TextBlock, ToolUseBlock, ToolResultBlock
    ANTHROPIC_LIBS_AVAILABLE = True
except ImportError:
    logging.warning("anthropic library not found. AnthropicProvider will be unavailable.")
    ANTHROPIC_LIBS_AVAILABLE = False
    # Define dummy types if library is missing
    AsyncAnthropic = None
    Message = None
    TextBlock = None
    ToolUseBlock = None
    ToolResultBlock = None
    anthropic = None

# Constants for Anthropic API
MAX_TOKENS_DEFAULT = 4096 # Default max_tokens for generation

class AnthropicProvider(LLMProvider):
    """LLM Provider implementation for Anthropic Claude models."""

    def __init__(self, model: str = "claude-3-opus-20240229", api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        """
        Initializes the Anthropic provider.

        Args:
            model: The Anthropic model name (e.g., "claude-3-opus-20240229").
            api_key: Optional API key. If None, loads from ANTHROPIC_API_KEY env var.
            base_url: Anthropic API base URL (usually not needed unless proxying).
            **kwargs: Additional arguments for the Anthropic client (e.g., timeout).
        """
        if not ANTHROPIC_LIBS_AVAILABLE:
            raise ImportError("Anthropic library is not installed or available.")

        # Note: Anthropic client doesn't take base_url directly in constructor as of recent versions.
        # It might need to be configured via environment variables (ANTHROPIC_BASE_URL) or custom http client.
        # We'll store it but won't pass it directly to the client for now.
        super().__init__(model, api_key, base_url, **kwargs)
        if self.base_url:
             logging.warning("AnthropicProvider received base_url, but AsyncAnthropic client may not use it directly. Configure via ANTHROPIC_BASE_URL environment variable if needed.")

        effective_key = self.api_key or self._get_key_from_env()
        if not effective_key:
            raise ValueError("Anthropic API Key not provided and ANTHROPIC_API_KEY environment variable not set.")

        try:
            self.client = AsyncAnthropic(
                api_key=effective_key,
                **self._config_kwargs # Pass other args like timeout
            )
            # No simple verification call available without usage.
            logging.info(f"AnthropicProvider initialized for model: {self.model_name}")
        except Exception as e:
            logging.error(f"Failed to initialize Anthropic AsyncClient: {e}", exc_info=True)
            raise ConnectionError(f"Failed to initialize Anthropic AsyncClient: {e}") from e

        self._translated_tool_schemas: Optional[List[Dict[str, Any]]] = None
        self._system_prompt_cache: Optional[str] = None # Cache system prompt used at session start


    def _get_key_from_env(self) -> Optional[str]:
        """Gets the API key from the environment variable."""
        return os.environ.get("ANTHROPIC_API_KEY")

    def _convert_history_to_anthropic(self, history: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Converts generic ChatMessage history to Anthropic's message list format."""
        anthropic_history = []
        last_role = None

        for msg in history:
            # Anthropic roles: 'user', 'assistant'. Tool results go inside a subsequent 'user' message.
            anthropic_role = msg.role
            if anthropic_role == "model": anthropic_role = "assistant"
            if anthropic_role == "system": continue # Handled separately
            if anthropic_role == "tool":
                 # 'tool' role in our generic history needs careful mapping.
                 # Anthropic expects tool *results* to be in a 'user' message
                 # containing tool_result blocks, following an 'assistant' message
                 # that contained the corresponding tool_use blocks.
                 anthropic_role = "user" # Results always go in a user message.

            content_blocks = []

            # --- Convert Parts to Anthropic Content Blocks ---
            for part in msg.parts:
                if isinstance(part, str):
                    # Ensure non-empty strings
                    if part.strip():
                        content_blocks.append({"type": "text", "text": part})
                elif isinstance(part, list) and part and isinstance(part[0], ToolCall):
                    # This is an assistant requesting tool use(s)
                    if msg.role == "assistant" or msg.role == "model": # Check original role
                        for tc in part:
                            content_blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                    else:
                        logging.warning(f"Anthropic history: Found ToolCall list in non-assistant message (Original Role: {msg.role}). Skipping.")
                elif isinstance(part, list) and part and isinstance(part[0], ToolResult):
                    # This is a tool result, MUST go in a 'user' message
                    if anthropic_role == "user": # Ensure we're building a user message
                        for tr in part:
                            # Content should be a string for Anthropic tool results.
                            # Attempt to serialize if complex, otherwise use string representation.
                            result_content_str: str
                            if tr.is_error:
                                result_content_str = str(tr.error) if tr.error is not None else ""
                            else:
                                result_content_str = str(tr.result) if tr.result is not None else ""

                            content_blocks.append({
                                "type": "tool_result",
                                "tool_use_id": tr.id,
                                "content": result_content_str, # Must be string
                                # Optionally include 'is_error' flag if API supports it or needed for context
                                # As of mid-2024, it's mainly handled via content.
                                # "is_error": tr.is_error # Not standard yet, but maybe useful for model context?
                            })
                    else: # Should have been mapped to 'user' role above
                         logging.error(f"Anthropic history: Internal logic error - ToolResult list found while building non-user message (Role: {anthropic_role}). Skipping results.")

                else: # Handle empty lists or unexpected types
                    if isinstance(part, list) and not part: continue # Skip empty lists
                    logging.warning(f"Anthropic history: Unexpected part type {type(part)}, converting to string.")
                    str_part = str(part).strip()
                    if str_part: # Avoid adding empty strings
                         content_blocks.append({"type": "text", "text": str_part})


            if not content_blocks:
                 logging.debug(f"Skipping message with no content blocks (Original Role: {msg.role}).")
                 continue

            # --- Structure Messages Correctly for Anthropic ---
            # Ensure alternating user/assistant roles. Combine consecutive messages of the same role if necessary.
            if anthropic_history and last_role == anthropic_role:
                 logging.debug(f"Anthropic history: Combining consecutive '{anthropic_role}' messages.")
                 # Check if existing content is a list before extending
                 if isinstance(anthropic_history[-1]["content"], list):
                      anthropic_history[-1]["content"].extend(content_blocks)
                 else: # Should not happen if content is always blocks, but handle defensively
                      logging.warning(f"Anthropic history: Previous message content was not a list ({type(anthropic_history[-1]['content'])}). Overwriting.")
                      anthropic_history[-1]["content"] = content_blocks

            else:
                anthropic_history.append({"role": anthropic_role, "content": content_blocks})
                last_role = anthropic_role

        # Final validation: History must start with 'user' and alternate.
        # If history exists and starts with 'assistant', it's invalid.
        if anthropic_history and anthropic_history[0]['role'] == 'assistant':
             logging.error("Anthropic history conversion resulted in history starting with 'assistant'. This is invalid.")
             # What to do? Return empty? Raise error? Returning empty might be safer.
             return []

        # Check alternation (more thorough check)
        for i in range(len(anthropic_history) - 1):
             if anthropic_history[i]['role'] == anthropic_history[i+1]['role']:
                  logging.error(f"Anthropic history conversion resulted in consecutive roles: '{anthropic_history[i]['role']}'. Invalid.")
                  # This indicates a flaw in the combining logic above or input history.
                  # Return empty or raise error.
                  return []


        return anthropic_history


    async def start_chat(self, system_prompt: str, tool_schemas: Optional[List[Dict[str, Any]]], history: Optional[List[ChatMessage]] = None) -> List[Dict[str, Any]]:
        """
        Prepares the message history list for an Anthropic chat completion call.
        Stores the system prompt and translated tool schemas for use in send_message.

        Args:
            system_prompt: The system prompt.
            tool_schemas: Anthropic-compatible tool schema list (from translate_to_anthropic_schema).
            history: The existing conversation history.

        Returns:
            A list of message dictionaries (converted history) ready for API calls.
        """
        self._system_prompt_cache = system_prompt
        self._translated_tool_schemas = tool_schemas # Already translated by config/schemas.py

        # Convert existing history. Note: system prompt isn't added to the list itself for Anthropic.
        openai_history = self._convert_history_to_anthropic(history) if history else []

        logging.debug(f"Prepared Anthropic chat history with {len(openai_history)} messages.")
        return openai_history


    async def send_message(self, chat_session: List[Dict[str, Any]], prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
        """
        Sends a message (prompt text or tool results) to the Anthropic API.

        Args:
            chat_session: The list of message dictionaries representing the history.
            prompt_parts: List containing user text prompt (as str) or ToolResult objects.
            model_name_override: Optionally override the default model for this call.

        Returns:
            Tuple (text_response, tool_calls_list).
        """
        text_response: Optional[str] = None
        tool_calls_list: Optional[List[ToolCall]] = None
        prompt_tokens: Optional[int] = None
        completion_tokens: Optional[int] = None

        # --- Prepare and Append New Message(s) ---
        new_message_role = "user" # Both user prompts and tool results go in user messages
        new_message_blocks = []

        if not prompt_parts:
             raise ValueError("Cannot send empty prompt parts to Anthropic.")

        first_part = prompt_parts[0]
        if isinstance(first_part, str):
            # Simple user text prompt
            user_content = "\n".join(part for part in prompt_parts if isinstance(part, str))
            if user_content.strip(): # Add only if there's actual text
                new_message_blocks.append({"type": "text", "text": user_content.strip()})
        elif isinstance(first_part, ToolResult):
            # Tool results - create tool_result blocks
            for part in prompt_parts:
                 if isinstance(part, ToolResult):
                     # Content must be a string for Anthropic
                     result_content_str: str
                     if part.is_error:
                         result_content_str = str(part.error) if part.error is not None else ""
                     else:
                         result_content_str = str(part.result) if part.result is not None else ""

                     new_message_blocks.append({
                         "type": "tool_result",
                         "tool_use_id": part.id,
                         "content": result_content_str,
                         # "is_error": part.is_error # Optional, not standard yet
                     })
                 else:
                      logging.warning(f"Mixing ToolResult and other types ({type(part)}) in prompt_parts is not standard. Ignoring non-ToolResult part.")
        else:
             raise ValueError(f"Invalid first prompt part type for AnthropicProvider: {type(first_part)}")

        # Append the new message to the session, ensuring alternating roles if possible
        if not new_message_blocks:
             logging.warning("Prepared Anthropic message has no content blocks. Skipping append.")
        elif chat_session and chat_session[-1]["role"] == new_message_role:
             logging.debug(f"Combining consecutive '{new_message_role}' messages for Anthropic.")
             if isinstance(chat_session[-1]["content"], list):
                  chat_session[-1]["content"].extend(new_message_blocks)
             else: # Defensive coding
                  logging.warning(f"Previous Anthropic message content was not a list ({type(chat_session[-1]['content'])}). Overwriting.")
                  chat_session[-1]["content"] = new_message_blocks
        else:
             chat_session.append({"role": new_message_role, "content": new_message_blocks})


        # --- Make API Call ---
        # Filter out any potentially empty messages before sending
        messages_to_send = [msg for msg in chat_session if msg.get("content")]
        if not messages_to_send:
             logging.error("Cannot send message to Anthropic: History is empty after preparation.")
             return "[Error: Invalid conversation history state (empty).]", None
        # Final check for alternation right before sending
        for i in range(len(messages_to_send) - 1):
             if messages_to_send[i]['role'] == messages_to_send[i+1]['role']:
                  logging.error(f"Anthropic API violation: Consecutive messages with role '{messages_to_send[i]['role']}' detected before sending. History:\n{json.dumps(messages_to_send, indent=2)}")
                  return f"[Error: Invalid history state (consecutive roles '{messages_to_send[i]['role']}'). Cannot send message.]", None

        try:
            logging.debug(f"Sending Anthropic request with {len(messages_to_send)} messages. System Prompt: {self._system_prompt_cache[:100]}... Tools enabled: {bool(self._translated_tool_schemas)}")
            effective_model = model_name_override or self.model_name

            api_response: Message = await self.client.messages.create(
                model=effective_model,
                system=self._system_prompt_cache, # Pass system prompt here
                messages=messages_to_send,
                tools=self._translated_tool_schemas or [], # Pass empty list if no tools
                max_tokens=MAX_TOKENS_DEFAULT, # Required parameter
                # Add other parameters like temperature if needed from config
            )
            # logging.debug(f"Received Anthropic raw response object: {api_response}") # Verbose

            # --- Extract Token Usage ---
            if api_response.usage:
                prompt_tokens = api_response.usage.input_tokens
                completion_tokens = api_response.usage.output_tokens
                self._update_token_counts(prompt_tokens, completion_tokens) # Update base class trackers
                logging.info(f"Anthropic Token Usage - Input: {prompt_tokens}, Output: {completion_tokens}")
            else:
                 logging.warning("Anthropic response did not contain usage metadata.")

            # --- Append Assistant's Response to History ---
            # Important: Store the structured content block(s) from response
            # Ensure content is a list for consistency, even if API returns single block sometimes?
            assistant_response_content = api_response.content if isinstance(api_response.content, list) else [api_response.content]
            assistant_response_msg = {"role": api_response.role, "content": assistant_response_content}
            chat_session.append(assistant_response_msg)


            # --- Parse Response Content Blocks ---
            tool_calls_list = []
            text_parts = []
            for block in assistant_response_content:
                if isinstance(block, TextBlock): # Check type using imported class
                    text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock): # Check type
                    tool_calls_list.append(ToolCall(id=block.id, name=block.name, arguments=block.input)) # Input is already args dict
            if text_parts:
                text_response = "\n".join(text_parts).strip()


            # --- Handle Stop Reason ---
            stop_reason = api_response.stop_reason
            if stop_reason == "end_turn":
                 logging.info("Anthropic response finished normally.")
            elif stop_reason == "tool_use":
                 logging.info("Anthropic response stopped for tool use.")
                 # Keep text response if model provided text before stopping for tools
            elif stop_reason == "max_tokens":
                 logging.warning(f"Anthropic response truncated due to max_tokens (Model: {effective_model}).")
                 warning_msg = "\n[Warning: Response truncated by model due to token limits]"
                 text_response = (text_response + warning_msg) if text_response else warning_msg
            elif stop_reason == "stop_sequence":
                 logging.info("Anthropic response stopped due to stop sequence.")
            else: # Other reasons?
                 logging.warning(f"Anthropic response finished unexpectedly: {stop_reason} (Model: {effective_model})")
                 warning_msg = f"\n[Warning: Response stopped unexpectedly ({stop_reason})]"
                 text_response = (text_response + warning_msg) if text_response else warning_msg

        except anthropic.APIConnectionError as e:
            logging.error(f"Anthropic API connection error: {e}")
            text_response = f"[Error: Failed to connect to Anthropic API: {e}]"
        except anthropic.RateLimitError as e:
            logging.error(f"Anthropic API rate limit exceeded: {e}")
            text_response = "[Error: Anthropic API rate limit exceeded. Please wait and try again.]"
        except anthropic.AuthenticationError as e:
            logging.error(f"Anthropic API authentication error: {e}")
            text_response = "[Error: Invalid Anthropic API Key or Authentication.]"
        except anthropic.BadRequestError as e: # Often context length, invalid request JSON, bad roles
             logging.error(f"Anthropic API Bad Request Error: {e}")
             if "prompt is too long" in str(e).lower() or "context window" in str(e).lower():
                  text_response = "[Error: Request exceeds Anthropic's context length limit.]"
                  # TODO: Implement history truncation strategy here?
             elif "alternate user/assistant" in str(e).lower():
                  text_response = "[Error: Invalid history state (non-alternating roles). Cannot send message.]"
             else:
                  text_response = f"[Error: Invalid request to Anthropic API: {e}]"
        except anthropic.APIStatusError as e: # Catch other non-2xx status codes
             logging.error(f"Anthropic API returned an error status: {e.status_code} {e.response}")
             text_response = f"[Error: Anthropic API Error ({e.status_code}): {e.message}]"
        except asyncio.TimeoutError:
             logging.error("Request to Anthropic API timed out.")
             text_response = "[Error: Request to Anthropic API timed out.]"
        except Exception as e:
            logging.exception(f"Unexpected error during Anthropic communication: {e}")
            text_response = f"[Error communicating with Anthropic: {e}]"
            # Reset token counts as they are likely invalid
            self._last_prompt_tokens = None
            self._last_completion_tokens = None


        # Ensure tool_calls_list is None if empty
        if not tool_calls_list:
            tool_calls_list = None

        return text_response, tool_calls_list
