import os
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union

# Import base class and core data types
from . import LLMProvider
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult
from agent_system.config.schemas import translate_to_openai_schema, GenericToolSchema # Import translator

# Attempt to import OpenAI library
try:
    import openai
    from openai import AsyncOpenAI # Use the async client
    from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall
    OPENAI_LIBS_AVAILABLE = True
except ImportError:
    logging.warning("openai library not found. OpenAIProvider will be unavailable.")
    OPENAI_LIBS_AVAILABLE = False
    # Define dummy types if library is missing
    AsyncOpenAI = None
    ChatCompletionMessage = None
    ChatCompletionMessageToolCall = None
    openai = None # Ensure openai itself is None if import fails

class OpenAIProvider(LLMProvider):
    """LLM Provider implementation for OpenAI and compatible APIs."""

    def __init__(self, model: str = "gpt-4-turbo", api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        """
        Initializes the OpenAI provider.

        Args:
            model: The OpenAI model name (e.g., "gpt-4-turbo", "gpt-3.5-turbo").
            api_key: Optional API key. If None, loads from OPENAI_API_KEY env var.
            base_url: Optional override for the API endpoint (for compatible APIs).
            **kwargs: Additional arguments for the OpenAI client.
        """
        if not OPENAI_LIBS_AVAILABLE:
            raise ImportError("OpenAI library is not installed or available.")

        super().__init__(model, api_key, base_url, **kwargs) # Pass args to base
        # Use the provided or environment variable key
        effective_key = self.api_key or self._get_key_from_env()
        # Use the provided base_url or let the client use the default
        effective_base_url = self.base_url

        # Key is generally required unless using a base_url for a potentially keyless local model
        if not effective_key and not effective_base_url:
            raise ValueError("OpenAI API Key not provided and OPENAI_API_KEY environment variable not set.")
        if not effective_key and effective_base_url:
             logging.warning(f"Initializing OpenAIProvider with base_url ('{effective_base_url}') but no API key. This assumes the endpoint does not require authentication.")

        try:
            self.client = AsyncOpenAI(
                api_key=effective_key,
                base_url=effective_base_url,
                **self._config_kwargs # Pass any other specific args
            )
            # Add a basic check? client.models.list() costs tokens. Maybe rely on first call?
            # For now, assume initialization is successful if no error is raised.
            logging.info(f"OpenAIProvider initialized for model: {self.model_name} (Base URL: {self.client.base_url})")
        except Exception as e:
            logging.error(f"Failed to initialize OpenAI AsyncClient: {e}", exc_info=True)
            raise ConnectionError(f"Failed to initialize OpenAI AsyncClient: {e}") from e

        self._translated_tool_schemas: Optional[List[Dict[str, Any]]] = None # Cache for translated schemas


    def _get_key_from_env(self) -> Optional[str]:
        """Gets the API key from the environment variable."""
        return os.environ.get("OPENAI_API_KEY")

    def _convert_history_to_openai(self, history: List[ChatMessage]) -> List[Dict[str, Any]]:
        """Converts generic ChatMessage history to OpenAI's message dictionary list format."""
        openai_history = []
        for msg in history:
            # OpenAI roles: 'system', 'user', 'assistant', 'tool'
            openai_role = msg.role
            if openai_role == "model": # Map generic 'model' role if used
                openai_role = "assistant"

            # Skip system messages here; they are handled separately in start_chat/send_message
            if openai_role == "system":
                 continue

            openai_msg: Dict[str, Any] = {"role": openai_role}
            text_content = ""
            tool_calls_part = [] # For assistant's tool usage requests (role: assistant)
            tool_results_parts = [] # For tool execution results (role: tool)

            for part in msg.parts:
                if isinstance(part, str):
                    text_content += part + "\n"
                elif isinstance(part, list) and part and isinstance(part[0], ToolCall):
                    # This part represents an assistant requesting one or more tool calls
                    if openai_role == "assistant":
                        for tc in part:
                             try:
                                 # Arguments need to be JSON strings for OpenAI API
                                 args_json = json.dumps(tc.arguments)
                                 tool_calls_part.append({
                                     "id": tc.id,
                                     "type": "function",
                                     "function": {"name": tc.name, "arguments": args_json}
                                 })
                             except TypeError as e:
                                  logging.error(f"Failed to serialize arguments for tool call '{tc.name}' (ID: {tc.id}) to JSON: {e}. Args: {tc.arguments}")
                                  # What to do here? Skip the tool call? Add an error message?
                                  # Let's skip it for history consistency, error should be handled during execution.
                    else:
                        logging.warning(f"OpenAI history: Found ToolCall list in non-assistant message (Role: {openai_role}). Skipping.")

                elif isinstance(part, list) and part and isinstance(part[0], ToolResult):
                    # This part represents the results of tool execution
                    if openai_role == "tool":
                         # OpenAI expects one 'tool' message per result
                         for tr in part:
                              result_content: str
                              try:
                                   # Content should be a string representation of the result/error
                                   result_content = json.dumps({"result": tr.result}) if not tr.is_error else json.dumps({"error": tr.error})
                              except TypeError as e:
                                   logging.error(f"Failed to serialize tool result/error for '{tr.name}' (ID: {tr.id}) to JSON: {e}. Content: {tr.error if tr.is_error else tr.result}")
                                   result_content = json.dumps({"error": f"Internal serialization error: {e}"})

                              # Each result needs its own 'tool' message dict
                              tool_results_parts.append({
                                  "tool_call_id": tr.id,
                                  "role": "tool",
                                  "name": tr.name, # Function name is part of the 'tool' message for OpenAI
                                  "content": result_content
                              })
                    else:
                         logging.warning(f"OpenAI history: Found ToolResult list in non-tool message (Role: {openai_role}). Skipping.")
                else:
                     logging.warning(f"OpenAI history: Unexpected part type {type(part)}, converting to string.")
                     text_content += str(part) + "\n"


            # Assemble message content based on role and parts found
            text_content = text_content.strip()

            if openai_role == "tool":
                # A 'tool' role message *only* contains the result info. Append each result separately.
                openai_history.extend(tool_results_parts)
            elif openai_role == "assistant":
                # Assistant message can have text content and/or tool calls
                openai_msg["content"] = text_content if text_content else None # Use None if no text
                if tool_calls_part:
                    openai_msg["tool_calls"] = tool_calls_part
                # Add message only if it has text content or tool calls
                if openai_msg["content"] is not None or tool_calls_part:
                    openai_history.append(openai_msg)
                else:
                     logging.debug("Skipping empty assistant message in OpenAI history.")
            else: # user role
                openai_msg["content"] = text_content if text_content else "" # Ensure content key exists, even if empty
                openai_history.append(openai_msg)

        return openai_history


    async def start_chat(self, system_prompt: str, tool_schemas: Optional[List[Dict[str, Any]]], history: Optional[List[ChatMessage]] = None) -> List[Dict[str, Any]]:
        """
        Prepares the message history list for an OpenAI chat completion call.
        Includes the system prompt and converted history. Caches translated tool schemas.

        Args:
            system_prompt: The system prompt.
            tool_schemas: OpenAI-compatible tool schema list (output from translate_to_openai_schema).
            history: The existing conversation history.

        Returns:
            A list of message dictionaries ready for the API call.
        """
        # Cache the translated schemas provided for this session
        self._translated_tool_schemas = tool_schemas

        # Prepare history list, starting with system prompt
        openai_history = []
        if system_prompt:
             openai_history.append({"role": "system", "content": system_prompt})

        # Convert and append existing history messages
        if history:
            openai_history.extend(self._convert_history_to_openai(history))

        logging.debug(f"Prepared OpenAI chat history with {len(openai_history)} messages.")
        return openai_history


    async def send_message(self, chat_session: List[Dict[str, Any]], prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
        """
        Sends a message (prompt text or tool results) to the OpenAI API.

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
        new_messages_to_append = []
        contains_tool_results = False
        if not prompt_parts:
             raise ValueError("Cannot send empty prompt parts to OpenAI.")

        first_part = prompt_parts[0]
        if isinstance(first_part, str):
            # Simple user text prompt
            user_content = "\n".join(part for part in prompt_parts if isinstance(part, str))
            new_messages_to_append.append({"role": "user", "content": user_content.strip()})
        elif isinstance(first_part, ToolResult):
            # Tool results - create one 'tool' message per result
            contains_tool_results = True
            for part in prompt_parts:
                 if isinstance(part, ToolResult):
                     result_content: str
                     try:
                         # Content should be a string representation of the result/error
                         result_content = json.dumps({"result": part.result}) if not part.is_error else json.dumps({"error": part.error})
                     except TypeError as e:
                         logging.error(f"Failed to serialize tool result/error for '{part.name}' (ID: {part.id}) to JSON: {e}. Content: {part.error if part.is_error else part.result}")
                         result_content = json.dumps({"error": f"Internal serialization error: {e}"})

                     new_messages_to_append.append({
                         "role": "tool",
                         "tool_call_id": part.id,
                         "name": part.name, # Function name is part of the 'tool' message for OpenAI
                         "content": result_content
                     })
                 else:
                      logging.warning(f"Mixing ToolResult and other types ({type(part)}) in prompt_parts is not standard. Ignoring non-ToolResult part.")
        else:
             raise ValueError(f"Invalid first prompt part type for OpenAIProvider: {type(first_part)}")

        # Append the newly created message(s) to the session history *before* the API call
        chat_session.extend(new_messages_to_append)

        try:
            # --- Make API Call ---
            logging.debug(f"Sending OpenAI request with {len(chat_session)} messages. Tools enabled: {bool(self._translated_tool_schemas)}")
            effective_model = model_name_override or self.model_name
            api_response = await self.client.chat.completions.create(
                model=effective_model,
                messages=chat_session,
                tools=self._translated_tool_schemas if self._translated_tool_schemas else openai.NOT_GIVEN, # Use NOT_GIVEN if no tools
                tool_choice="auto" if self._translated_tool_schemas else openai.NOT_GIVEN,
                # Add other parameters like temperature, max_tokens if needed from config
            )
            # logging.debug(f"Received OpenAI raw response: {api_response}") # Can be very verbose

            # --- Extract Token Usage ---
            if api_response.usage:
                prompt_tokens = api_response.usage.prompt_tokens
                completion_tokens = api_response.usage.completion_tokens
                self._update_token_counts(prompt_tokens, completion_tokens) # Update base class trackers
                logging.info(f"OpenAI Token Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}")
            else:
                 logging.warning("OpenAI response did not contain usage metadata.")


            # --- Parse Response ---
            if not api_response.choices:
                 logging.error("OpenAI response missing 'choices'.")
                 text_response = "[Error: OpenAI response contained no choices.]"
                 return text_response, None

            message: ChatCompletionMessage = api_response.choices[0].message
            finish_reason = api_response.choices[0].finish_reason

            # Append model's response message to history *after* call, *before* parsing/returning
            # Use model_dump to get dict suitable for history list, excluding unset fields like 'name' if not present
            chat_session.append(message.model_dump(exclude_unset=True))


            # Extract text content if present
            if message.content:
                text_response = message.content

            # Extract tool calls if present
            if message.tool_calls:
                tool_calls_list = []
                for tc in message.tool_calls:
                    if tc.type == "function":
                        try:
                            # Arguments are JSON strings, parse them
                            args = json.loads(tc.function.arguments)
                            tool_calls_list.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
                        except json.JSONDecodeError as e:
                            logging.error(f"Failed to decode OpenAI tool args JSON for '{tc.function.name}' (ID: {tc.id}): {e}. Args string: {tc.function.arguments}")
                            # Create an error result to send back? Or just log? Let's log for now.
                            # The agent loop will need to handle the lack of valid args if this happens.
                            # Optionally, add an error ToolResult? This seems complex here.
                        except Exception as e:
                             logging.exception(f"Unexpected error processing OpenAI tool call args for '{tc.function.name}' (ID: {tc.id}): {e}")
                    else:
                         logging.warning(f"Received unsupported tool call type from OpenAI: {tc.type}")

            # --- Handle Finish Reason ---
            if finish_reason == "stop":
                 logging.info("OpenAI response finished normally.")
            elif finish_reason == "tool_calls":
                 logging.info("OpenAI response finished to call tools.")
                 # Keep text_response if the model generated text before deciding to call tools
            elif finish_reason == "length":
                 logging.warning(f"OpenAI response truncated due to length limit (Model: {effective_model}).")
                 warning_msg = "\n[Warning: Response truncated by model due to token limits]"
                 text_response = (text_response + warning_msg) if text_response else warning_msg
            elif finish_reason == "content_filter":
                 logging.error(f"OpenAI response stopped due to content filter (Model: {effective_model}).")
                 text_response = "[Error: Response stopped by content filter.]"
            else: # Other reasons like 'function_call' (deprecated) or unknown
                 logging.warning(f"OpenAI response finished unexpectedly: {finish_reason} (Model: {effective_model})")
                 warning_msg = f"\n[Warning: Response stopped unexpectedly ({finish_reason})]"
                 text_response = (text_response + warning_msg) if text_response else warning_msg

        except openai.APIConnectionError as e:
            logging.error(f"OpenAI API connection error: {e}")
            text_response = f"[Error: Failed to connect to OpenAI API: {e}]"
        except openai.RateLimitError as e:
            logging.error(f"OpenAI API rate limit exceeded: {e}")
            text_response = "[Error: OpenAI API rate limit exceeded. Please wait and try again.]"
        except openai.AuthenticationError as e:
            logging.error(f"OpenAI API authentication error: {e}")
            text_response = "[Error: Invalid OpenAI API Key or Authentication.]"
        except openai.BadRequestError as e: # Often context length, invalid request JSON
             logging.error(f"OpenAI API Bad Request Error: {e}")
             if "context_length_exceeded" in str(e).lower():
                  text_response = "[Error: Request exceeds OpenAI's context length limit.]"
                  # TODO: Implement history truncation strategy here?
             else:
                  text_response = f"[Error: Invalid request to OpenAI API: {e}]"
        except openai.APIStatusError as e: # Catch other non-2xx status codes
             logging.error(f"OpenAI API returned an error status: {e.status_code} {e.response}")
             text_response = f"[Error: OpenAI API Error ({e.status_code}): {e.message}]"
        except asyncio.TimeoutError:
             logging.error("Request to OpenAI API timed out.")
             text_response = "[Error: Request to OpenAI API timed out.]"
        except Exception as e:
            # Handle other potential errors (network, unexpected issues)
            logging.exception(f"Unexpected error during OpenAI communication: {e}")
            text_response = f"[Error communicating with OpenAI: {e}]"
            # Reset token counts as they are likely invalid
            self._last_prompt_tokens = None
            self._last_completion_tokens = None


        # Ensure tool_calls_list is None if it's empty
        if not tool_calls_list:
            tool_calls_list = None

        return text_response, tool_calls_list
