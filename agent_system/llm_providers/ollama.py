import os
import logging
import json
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union

# Import base class and core data types
from . import LLMProvider
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult
from agent_system.config.schemas import translate_to_ollama_schema_string, GenericToolSchema # Import translator

# Use httpx for async requests
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    logging.warning("httpx library not found. OllamaProvider will be unavailable.")
    HTTPX_AVAILABLE = False
    httpx = None # Ensure httpx is None if import fails

# Constants for Ollama API
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_REQUEST_TIMEOUT = 180 # Seconds, Ollama can be slow
DEFAULT_CONNECT_TIMEOUT = 10 # Seconds

class OllamaProvider(LLMProvider):
    """
    LLM Provider implementation for local Ollama models using JSON mode and prompt injection for tools.
    Uses httpx for asynchronous requests.
    """

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        """
        Initializes the Ollama provider.

        Args:
            model: The Ollama model name (e.g., "llama3:latest", "mistral").
            api_key: Not used by standard Ollama, but included for consistency.
            base_url: The base URL of the Ollama API. Defaults to http://localhost:11434.
            **kwargs: Additional arguments (e.g., request_timeout, connect_timeout).
        """
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx library is not installed. Required for OllamaProvider.")

        effective_base_url = (base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL).rstrip('/')
        super().__init__(model, api_key, effective_base_url, **kwargs) # Pass model, api_key, base_url to base

        self.request_timeout = kwargs.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)
        self.connect_timeout = kwargs.get("connect_timeout", DEFAULT_CONNECT_TIMEOUT)

        # Create an async HTTP client session
        # Consider adding proxy support, custom headers etc. if needed via kwargs
        self.async_client = httpx.AsyncClient(
             base_url=self.base_url,
             timeout=httpx.Timeout(self.request_timeout, connect=self.connect_timeout)
        )

        self._tool_schema_str_cache: Optional[str] = None # Cache schema JSON string for prompt injection
        self._system_prompt_base: Optional[str] = None # Cache the original system prompt
        self._full_system_prompt_cache: Optional[str] = None # Cache combined prompt

        # Initial check for model availability is deferred to _check_model_availability
        # to allow it to be called asynchronously.
        logging.info(f"OllamaProvider initialized. Target Model: {self.model_name}, API URL: {self.base_url}")
        # Note: Model availability check will run before first use in start_chat.

    def _get_key_from_env(self) -> Optional[str]:
        """Ollama doesn't typically use API keys."""
        return None # Return None as Ollama usually doesn't need a key

    async def _check_model_availability(self):
        """Asynchronously checks if the configured model is available on the Ollama server."""
        api_url = "/api/show"
        payload = {"name": self.model_name}
        try:
            logging.info(f"Checking Ollama model '{self.model_name}' availability at {self.base_url}{api_url}")
            response = await self.async_client.post(api_url, json=payload)
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx
            logging.info(f"Ollama model '{self.model_name}' confirmed available.")
            return True
        except httpx.TimeoutException:
             logging.error(f"Timeout connecting to Ollama at {self.base_url} while checking model '{self.model_name}'.")
             raise ConnectionError(f"Timeout connecting to Ollama at {self.base_url}.")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                 logging.error(f"Ollama model '{self.model_name}' not found at {self.base_url}. Response: {e.response.text[:200]}")
                 raise ValueError(f"Ollama model '{self.model_name}' not found at {self.base_url}. Pull the model first (e.g., `ollama pull {self.model_name}`).") from e
            else:
                 logging.error(f"HTTP error checking Ollama model '{self.model_name}': Status {e.response.status_code}, Response: {e.response.text[:200]}")
                 raise ConnectionError(f"HTTP error {e.response.status_code} checking Ollama model '{self.model_name}'.") from e
        except httpx.RequestError as e:
            logging.error(f"Network error connecting to Ollama at {self.base_url} while checking model '{self.model_name}': {e}")
            raise ConnectionError(f"Network error connecting to Ollama at {self.base_url}: {e}") from e
        except Exception as e:
            logging.exception(f"Unexpected error checking Ollama model '{self.model_name}': {e}")
            raise RuntimeError(f"Unexpected error checking Ollama model availability: {e}") from e

    def _build_tool_prompt_injection(self) -> str:
        """Constructs the tool usage instructions for the system prompt."""
        if not self._tool_schema_str_cache or self._tool_schema_str_cache == "[]":
             return "" # No tools, no instructions needed

        # Updated instructions emphasizing strict JSON format
        # Based on common practices for instructing models like Llama, Mistral for JSON tool calls.
        tool_instructions = f"""
You have access to the following tools:
```json
{self._tool_schema_str_cache}


When you decide to call one or more tools, you MUST respond with ONLY a single, valid JSON object. Do not include ```json markdown delimiters or any other text before or after the JSON object.
The JSON object MUST contain a single key named "tool_calls". The value of "tool_calls" MUST be a list of one or more tool call objects.
Each tool call object in the list MUST have the following structure:
{{
"name": "<tool_name>",
"arguments": {{<arguments_object>}}
}}

Example of a valid response calling ONE tool:
{{
"tool_calls": [
{{
"name": "read_file",
"arguments": {{
"file_path": "/path/to/your/file.txt"
}}
}}
]
}}

Example of a valid response calling MULTIPLE tools:
{{
"tool_calls": [
{{
"name": "list_files",
"arguments": {{
"directory_path": "/some/dir/"
}}
}},
{{
"name": "get_system_info",
"arguments": {{}}
}}
]
}}

If you do not need to use a tool, respond with your answer as plain text, without any JSON structure.
"""
        return tool_instructions

def _get_full_system_prompt(self) -> Optional[str]:
     """Combines base system prompt with tool instructions if tools are available."""
     if self._full_system_prompt_cache: return self._full_system_prompt_cache

     if not self._system_prompt_base: return None

     effective_system_prompt = self._system_prompt_base
     tool_injection = self._build_tool_prompt_injection()

     if tool_injection:
          effective_system_prompt += "\n\n" + tool_injection
          logging.info("Injecting structured tool schema and JSON instruction into Ollama system prompt.")
     else:
          logging.info("No tools available or defined for Ollama, using basic system prompt.")

     self._full_system_prompt_cache = effective_system_prompt
     return self._full_system_prompt_cache

def _convert_history_to_ollama(self, history: List[ChatMessage]) -> List[Dict[str, Any]]:
    """Converts generic ChatMessage history to Ollama's message list format."""
    ollama_history = []
    for msg in history:
        ollama_role = msg.role
        if ollama_role == "model": ollama_role = "assistant"
        # Skip system messages here, handled separately
        if ollama_role == "system": continue

        # Combine parts into a single content string for Ollama history
        content_parts = []
        for part in msg.parts:
             if isinstance(part, str): content_parts.append(part)
             elif isinstance(part, list) and part and isinstance(part[0], ToolCall):
                  # Represent assistant's tool call requests in a readable format for the model's context
                  calls_str = "Assistant requested tool calls:\n"
                  for tc in part:
                       try: args_str = json.dumps(tc.arguments)
                       except TypeError: args_str = str(tc.arguments) # Fallback
                       calls_str += f"- Tool: {tc.name}, Arguments: {args_str}\n"
                  content_parts.append(calls_str.strip())
             elif isinstance(part, list) and part and isinstance(part[0], ToolResult):
                  # Represent tool results clearly for the model
                  results_str = "Tool execution results:\n"
                  for tr in part:
                      status = "Error" if tr.is_error else "Success"
                      output = tr.error if tr.is_error else tr.result
                      # Truncate long results in history? Maybe keep short for context?
                      output_str = str(output)
                      max_len = 500
                      if len(output_str) > max_len: output_str = output_str[:max_len] + f"... (truncated {len(output_str)} bytes)"
                      results_str += f"--- Tool: {tr.name} (ID: {tr.id}) ---\nStatus: {status}\nOutput:\n```\n{output_str}\n```\n---\n"
                  content_parts.append(results_str.strip())
             elif isinstance(part, list) and not part: continue # Skip empty lists
             else: content_parts.append(str(part)) # Fallback for unexpected types

        full_content = "\n".join(content_parts).strip()
        # Add message only if content is not empty
        if full_content:
             ollama_history.append({"role": ollama_role, "content": full_content})
        else:
             logging.debug(f"Skipping message with empty content in Ollama history conversion (Original Role: {msg.role})")

    return ollama_history

async def start_chat(self, system_prompt: str, tool_schemas: Optional[str], history: Optional[List[ChatMessage]] = None) -> List[Dict[str, Any]]:
    """
    Prepares the message history list for an Ollama chat call.
    Stores system prompt and tool schema string. Checks model availability.

    Args:
        system_prompt: The system prompt.
        tool_schemas: JSON string representation of tools (from translate_to_ollama_schema_string).
        history: The existing conversation history.

    Returns:
        A list of message dictionaries (converted history).
    """
    # Perform model check before proceeding
    await self._check_model_availability()

    # Store prompts and schemas
    self._system_prompt_base = system_prompt
    self._tool_schema_str_cache = tool_schemas # Store the schema string provided
    self._full_system_prompt_cache = None # Invalidate combined prompt cache
    self._get_full_system_prompt() # Pre-generate/cache the full system prompt

    # Convert history
    ollama_history = self._convert_history_to_ollama(history) if history else []
    logging.debug(f"Prepared Ollama chat history with {len(ollama_history)} messages.")
    return ollama_history


async def send_message(self, chat_session: List[Dict[str, Any]], prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
    """
    Sends a message (prompt text or tool results) to the Ollama API.

    Args:
        chat_session: The list of message dictionaries representing the history.
        prompt_parts: List containing user text prompt (as str) or ToolResult objects.
        model_name_override: Optionally override the default model for this call.

    Returns:
        Tuple (text_response, tool_calls_list).
    """
    text_response: Optional[str] = None
    tool_calls_list: Optional[List[ToolCall]] = None
    # Ollama API doesn't provide token counts in standard /api/chat response

    # --- Prepare and Append New Message(s) ---
    new_message = {"role": "user"} # Both user prompts and tool results go in user messages for context
    content_parts = []

    if not prompt_parts:
         raise ValueError("Cannot send empty prompt parts to Ollama.")

    first_part = prompt_parts[0]
    if isinstance(first_part, str):
        # Simple user text prompt
        user_content = "\n".join(part for part in prompt_parts if isinstance(part, str))
        content_parts.append(user_content.strip())
    elif isinstance(first_part, ToolResult):
        # Format tool results clearly for the model
        results_str = "Tool execution results:\n"
        for part in prompt_parts:
             if isinstance(part, ToolResult):
                 status = "Error" if part.is_error else "Success"
                 output = part.error if part.is_error else part.result
                 output_str = str(output)
                 max_len = 1000 # Truncate results slightly longer in prompt if needed
                 if len(output_str) > max_len: output_str = output_str[:max_len] + f"... (truncated {len(output_str)} bytes)"
                 results_str += f"--- Tool: {part.name} (ID: {part.id}) ---\nStatus: {status}\nOutput:\n```\n{output_str}\n```\n---\n"
             else:
                  logging.warning(f"Mixing ToolResult and other types ({type(part)}) in prompt_parts. Ignoring non-ToolResult part.")
        content_parts.append(results_str.strip())
    else:
         raise ValueError(f"Invalid first prompt part type for OllamaProvider: {type(first_part)}")

    new_message["content"] = "\n".join(content_parts).strip()

    # Append the new message only if content is not empty
    if new_message["content"]:
         chat_session.append(new_message)
    else:
         logging.warning("Prepared Ollama message has empty content. Not sending.")
         return "[Error: Tried to send empty message]", None

    # --- Make API Call ---
    try:
        effective_model = model_name_override or self.model_name
        payload = {
            "model": effective_model,
            "messages": chat_session,
            "stream": False,
            "system": self._get_full_system_prompt(), # Pass combined system prompt
            "format": "json", # Request JSON output format (critical for tool parsing)
            "options": {"temperature": 0.5} # Adjust options as needed, e.g., temp, top_k, top_p
            # Add other options from self._config_kwargs if needed
        }
        api_url = "/api/chat"
        logging.debug(f"Sending Ollama payload to {api_url} (Model: {effective_model}). Messages: {len(chat_session)}. System prompt length: {len(payload['system'] or '')}")
        logging.debug(f"Ollama request payload (messages omitted): { {k:v for k,v in payload.items() if k != 'messages'} }")

        api_response = await self.async_client.post(api_url, json=payload)
        api_response.raise_for_status() # Check for HTTP errors (4xx, 5xx)
        response_data = api_response.json()
        # logging.debug(f"Received Ollama raw response data: {response_data}")

        # --- Parse Response ---
        message = response_data.get("message", {})
        role = message.get("role") # Should be 'assistant'
        content_str = message.get("content") # Content SHOULD be a JSON string if model follows instructions

        if role == "assistant" and content_str:
             # Append raw assistant response content string to history *before* parsing
             chat_session.append({"role": role, "content": content_str})

             # Attempt to parse the JSON content string for tool calls
             parsed_json = None
             json_error = None
             try:
                 # Models sometimes add ```json markdown, try stripping
                 content_str_cleaned = content_str.strip().removeprefix("```json").removesuffix("```").strip()
                 if not content_str_cleaned:
                     logging.warning("Ollama response content was empty after cleaning markdown.")
                     text_response = "[Warning: Assistant response was empty after cleaning.]"
                 else:
                     parsed_json = json.loads(content_str_cleaned)

                     # Check for the expected tool call structure
                     if isinstance(parsed_json, dict) and "tool_calls" in parsed_json:
                         calls_data = parsed_json["tool_calls"]
                         if isinstance(calls_data, list):
                             tool_calls_list = []
                             invalid_call_found = False
                             for call_data in calls_data:
                                  if isinstance(call_data, dict):
                                       name = call_data.get("name")
                                       args = call_data.get("arguments")
                                       if name and isinstance(args, dict):
                                           # Generate a unique-enough ID
                                           call_id = f"{name}_{int(time.time()*1000)}_{hash(json.dumps(args, sort_keys=True))%10000}"
                                           tool_calls_list.append(ToolCall(id=call_id, name=name, arguments=args))
                                       else:
                                           logging.warning(f"Ollama: Invalid tool call structure inside 'tool_calls' list: Missing 'name' or 'arguments' dict. Call data: {call_data}")
                                           invalid_call_found = True; break # Stop parsing if one call is bad
                                  else:
                                       logging.warning(f"Ollama: Item in 'tool_calls' list is not a dictionary: {call_data}")
                                       invalid_call_found = True; break
                             if invalid_call_found:
                                  tool_calls_list = None # Discard partial list if any call was bad
                                  text_response = content_str # Fallback to raw string
                             elif tool_calls_list:
                                  logging.info(f"Parsed {len(tool_calls_list)} Ollama tool call(s).")
                             else: # List was empty
                                  logging.warning("Ollama: Received 'tool_calls' key with an empty list. Treating as no tool call.")
                                  text_response = content_str # Fallback to raw content if list is empty? Or treat as no response?

                         else: # tool_calls key found but value is not a list
                             logging.warning(f"Ollama: 'tool_calls' key found but value is not a list ({type(calls_data)}). Treating as text.")
                             text_response = content_str
                     else: # Valid JSON, but not the expected tool call structure
                         logging.info("Ollama response was valid JSON but not the expected 'tool_calls' structure.")
                         # Treat as a standard text response, pretty-print if dict/list
                         if isinstance(parsed_json, (dict, list)): text_response = json.dumps(parsed_json, indent=2)
                         else: text_response = content_str_cleaned # Simple value like string/number

             except json.JSONDecodeError as e:
                 # Content was not valid JSON, treat as plain text
                 logging.info(f"Ollama response content was not valid JSON (Error: {e}). Treating as plain text.")
                 text_response = content_str # Return original, uncleaned string
                 json_error = str(e) # Store error for potential reporting later if needed

             # If we parsed tool calls, text_response should be None unless explicitly set above
             if tool_calls_list and text_response is not None:
                 logging.warning("Ollama: Parsed tool calls but also derived text response? Prioritizing tool calls.")
                 text_response = None # Ensure text response is cleared if tools were parsed

             # If no tool calls parsed and no text_response set yet (e.g., empty JSON {} received)
             if not tool_calls_list and text_response is None:
                 if json_error: # Invalid JSON case
                     logging.error(f"Ollama response was invalid JSON: {json_error}. Raw: {content_str}")
                     text_response = f"[Error: Model response was invalid JSON ({json_error})]\nRaw Content:\n{content_str}"
                 else: # Valid JSON but empty or no specific content case
                     logging.warning(f"Ollama assistant response JSON parsed but yielded no text or tools. Parsed: {parsed_json}. Raw: {content_str}")
                     text_response = "[Warning: Assistant response yielded no actionable content]"


        elif response_data.get("done") and not message:
             logging.warning(f"Ollama response indicated 'done=true' but provided no message content. Response: {response_data}")
             text_response = "[Warning: Ollama finished without providing a message response.]"
             # Append an empty assistant message?
             chat_session.append({"role": "assistant", "content": ""})
        else: # Missing 'message' or 'role':'assistant'
             logging.error(f"Ollama response missing assistant message/content: {response_data}")
             text_response = f"[Error: Received unexpected response structure from Ollama: {response_data.get('error', 'Unknown error')}]"
             # Append raw response as assistant message?
             chat_session.append({"role": "assistant", "content": json.dumps(response_data)})


        # Check for explicit top-level errors in response data (less common for /api/chat)
        if response_data.get("error"):
             logging.error(f"Ollama API returned an error field: {response_data['error']}")
             error_msg = f"[Ollama Error: {response_data['error']}]"
             text_response = (error_msg + "\n" + (text_response or "")) if text_response else error_msg

    except httpx.TimeoutException:
        logging.error(f"Ollama request timed out after {self.request_timeout}s.")
        text_response = "[Error: Request to Ollama timed out.]"
        # Append timeout error message?
        chat_session.append({"role": "assistant", "content": text_response})
    except httpx.HTTPStatusError as e:
         # Handle non-2xx responses
         logging.error(f"Ollama API returned HTTP error: Status {e.response.status_code}, Response: {e.response.text[:200]}")
         text_response = f"[Error: Ollama API Error ({e.response.status_code}): {e.response.text[:100]}...]"
         chat_session.append({"role": "assistant", "content": text_response})
    except httpx.RequestError as e:
        # Handle network-level errors (connection refused, DNS error, etc.)
        logging.error(f"Network error communicating with Ollama: {e}")
        text_response = f"[Error: Network error connecting to Ollama: {e}]"
        chat_session.append({"role": "assistant", "content": text_response})
    except Exception as e:
         logging.exception(f"Unexpected error processing Ollama response: {e}")
         text_response = f"[Error processing Ollama response: {e}]"
         chat_session.append({"role": "assistant", "content": text_response})

    # Ensure tool_calls_list is None if empty
    if not tool_calls_list:
        tool_calls_list = None

    return text_response, tool_calls_list

async def close(self):
    """Closes the underlying httpx client."""
    await self.async_client.aclose()
    logging.info("OllamaProvider httpx client closed.")

