import os
import time
import logging
import json
from typing import List, Dict, Any, Optional, Tuple, Union

# Import base class and core data types
from . import LLMProvider
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult

# Attempt to import Gemini libraries
try:
    import google.generativeai as genai
    import google.ai.generativelanguage as glm
    # Import specific types for clarity
    from google.generativeai.types import ContentDict, PartDict, FunctionCallDict, FunctionResponseDict
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    GEMINI_LIBS_AVAILABLE = True
except ImportError:
    logging.warning("google-generativeai library not found. GeminiProvider will be unavailable.")
    GEMINI_LIBS_AVAILABLE = False
    # Define dummy types if library is missing to avoid runtime errors on class definition
    genai = None
    glm = None
    ContentDict = Dict
    PartDict = Dict
    FunctionCallDict = Dict
    FunctionResponseDict = Dict
    HarmCategory = None
    HarmBlockThreshold = None


class GeminiProvider(LLMProvider):
    """LLM Provider implementation for Google Gemini."""

    # Safety settings - adjust as needed, sensible defaults
    DEFAULT_SAFETY_SETTINGS = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    } if HarmCategory and HarmBlockThreshold else {} # Only set if libs are available


    def __init__(self, model: str = "gemini-1.5-pro-latest", api_key: Optional[str] = None, **kwargs):
        """
        Initializes the Gemini provider.

        Args:
            model: The Gemini model name to use (e.g., "gemini-1.5-pro-latest").
            api_key: Optional API key. If None, attempts to load from GEMINI_API_KEY env var.
            **kwargs: Additional arguments (e.g., safety_settings).
        """
        if not GEMINI_LIBS_AVAILABLE:
            raise ImportError("Gemini libraries (google-generativeai) are not installed or available.")

        super().__init__(model, api_key, **kwargs) # Pass model, api_key to base
        self.safety_settings = kwargs.get("safety_settings", self.DEFAULT_SAFETY_SETTINGS)

        try:
            effective_key = self.api_key or self._get_key_from_env()
            if not effective_key:
                raise ValueError("Gemini API Key not provided and GEMINI_API_KEY environment variable not set.")

            # Configure the genai library. This is a global setting, but necessary.
            # It's okay to call multiple times if the key is the same.
            genai.configure(api_key=effective_key)

            # Initialize a dummy model instance primarily to check API key validity early
            # The actual model used for chat is created in start_chat
            logging.debug(f"Verifying Gemini configuration with model: {self.model_name}")
            _ = genai.GenerativeModel(self.model_name)
            # Consider adding a genai.list_models() call for a more robust check, but it uses API quota.
            logging.info(f"GeminiProvider configured successfully for model: {self.model_name}")

        except Exception as e:
            logging.error(f"Failed to configure or verify Gemini API: {e}", exc_info=True)
            # Improve error message for common issues
            if "API key not valid" in str(e):
                 raise ConnectionError("Gemini API Key is invalid. Please check your key or environment variable.") from e
            else:
                 raise ConnectionError(f"Failed to configure Gemini API: {e}") from e

    def _get_key_from_env(self) -> Optional[str]:
        """Gets the API key from the environment variable."""
        return os.environ.get("GEMINI_API_KEY")

    def _convert_history_to_gemini(self, history: List[ChatMessage]) -> List[ContentDict]:
        """Converts the generic ChatMessage history to Gemini's ContentDict format."""
        gemini_history: List[ContentDict] = []
        for msg in history:
            # Gemini uses 'user' and 'model'. 'tool' role corresponds to 'function' results from the model's perspective,
            # but the API expects ToolResult parts within a 'model' message's response or a subsequent 'user' message
            # containing FunctionResponse parts.
            # The ChatSession object handles this conversion internally more robustly.
            # Here, we primarily focus on converting the *parts* within each message.

            role = msg.role if msg.role != "assistant" else "model" # Map 'assistant' to 'model'
            if role == "system": # Gemini uses system_instruction, skip converting system messages in history
                 continue

            converted_parts: List[Union[str, FunctionCallDict, FunctionResponseDict]] = []

            for part in msg.parts:
                if isinstance(part, str):
                    converted_parts.append(part)
                elif isinstance(part, list) and part and isinstance(part[0], ToolCall):
                    # This represents the *model's* request to call tools
                    if role == "model":
                        for tc in part:
                             # Ensure arguments are serializable (Gemini SDK handles this)
                             try:
                                 # args should already be a dict from core.datatypes
                                 args_dict = tc.arguments
                                 func_call = glm.FunctionCall(name=tc.name, args=args_dict)
                                 # converted_parts.append(PartDict(function_call=func_call)) # SDK uses Part object
                                 converted_parts.append(func_call) # Append the FunctionCall object directly seems to work
                             except Exception as e:
                                 logging.error(f"Failed to format ToolCall arguments for Gemini history: {e}. Args: {tc.arguments}")
                                 # Add a placeholder or skip? Skipping might be safer.
                    else:
                        logging.warning(f"Gemini history: Encountered ToolCall list in non-model message (Role: {role}). Skipping.")

                elif isinstance(part, list) and part and isinstance(part[0], ToolResult):
                    # This represents the results of tool execution, provided back *to* the model
                     if role == "tool": # Results usually come after a 'tool' role message in our generic format
                         for tr in part:
                             try:
                                 # Ensure result/error is JSON serializable or string
                                 response_content: Any
                                 if tr.is_error:
                                     response_content = {"error": tr.error}
                                 else:
                                     # Attempt to parse result as JSON, fallback to string
                                     try: response_content = json.loads(tr.result) if tr.result else ""
                                     except (json.JSONDecodeError, TypeError): response_content = tr.result

                                 func_response = glm.FunctionResponse(name=tr.name, response={"content": response_content}) # API expects 'content' key in response
                                 # converted_parts.append(PartDict(function_response=func_response)) # SDK uses Part object
                                 converted_parts.append(func_response) # Append the FunctionResponse object directly
                             except Exception as e:
                                  logging.error(f"Failed to format ToolResult for Gemini history: {e}. Result: {tr}")
                                  # Add a placeholder or skip?
                     else:
                           logging.warning(f"Gemini history: Encountered ToolResult list in non-tool message (Role: {role}). Skipping.")

                else:
                    logging.warning(f"Gemini history conversion: Unexpected part type {type(part)}, converting to string.")
                    converted_parts.append(str(part)) # Fallback

            # Ensure parts are not empty before appending
            if converted_parts:
                 # Gemini expects 'function_call'/'function_response' directly in parts list for role='model'
                 gemini_history.append({'role': role, 'parts': converted_parts})
            else:
                 logging.debug(f"Skipping empty message in Gemini history conversion (Original Role: {msg.role})")

        return gemini_history

    async def start_chat(self, system_prompt: str, tool_schemas: Optional[List[glm.FunctionDeclaration]], history: Optional[List[ChatMessage]] = None) -> genai.ChatSession:
        """
        Initializes a Gemini ChatSession.

        Args:
            system_prompt: The system prompt.
            tool_schemas: Gemini FunctionDeclaration list for available tools.
            history: The existing conversation history.

        Returns:
            An initialized genai.ChatSession object.
        """
        # Convert generic history to Gemini format *before* starting chat
        gemini_history = self._convert_history_to_gemini(history) if history else []

        try:
            # Create the model instance with system prompt and tools for this session
            # Note: Tool schemas should be pre-translated to Gemini format by config/schemas.py
            model_instance = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt,
                tools=tool_schemas,
                safety_settings=self.safety_settings
            )

            # Start the chat session using the converted history
            logging.debug(f"Starting Gemini chat session with history: {gemini_history}")
            chat = model_instance.start_chat(history=gemini_history)
            return chat
        except Exception as e:
            logging.exception(f"Failed to initialize Gemini chat session (Model: {self.model_name}): {e}")
            # Reraise as a more specific error if possible
            raise ConnectionError(f"Failed to initialize Gemini chat session '{self.model_name}': {e}") from e

    async def send_message(self, chat_session: genai.ChatSession, prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
        """
        Sends a message (prompt text or tool results) to the Gemini model.

        Args:
            chat_session: The active genai.ChatSession object.
            prompt_parts: List containing user text prompt (as str) or ToolResult objects.
            model_name_override: Optional model name override (Gemini SDK doesn't directly support per-message model override via ChatSession.send_message).

        Returns:
            Tuple (text_response, tool_calls_list).
        """
        if model_name_override and model_name_override != self.model_name:
             # Gemini ChatSession is tied to the model it was created with.
             # To use a different model, a new ChatSession would be needed.
             logging.warning(f"GeminiProvider does not support per-message model override via ChatSession. Using session model '{self.model_name}'.")

        text_response: Optional[str] = None
        tool_calls_list: Optional[List[ToolCall]] = None
        prompt_tokens: Optional[int] = None
        completion_tokens: Optional[int] = None

        try:
            # --- Prepare Message Content ---
            message_content: List[Union[str, glm.FunctionResponse]] = []
            contains_tool_results = False
            for part in prompt_parts:
                if isinstance(part, str):
                    message_content.append(part)
                elif isinstance(part, ToolResult):
                    contains_tool_results = True
                    # Format ToolResult into FunctionResponse for sending back to the model
                    try:
                         # Ensure result/error content is suitable
                         response_data: Any
                         if part.is_error:
                             response_data = {"error": part.error} # Send error message
                         else:
                              # Gemini API often expects the result directly as the content value,
                              # rather than nested inside {"result": ...}. Let's try sending raw result.
                              # Attempt to parse if it looks like JSON, otherwise send as string.
                              try:
                                   response_data = json.loads(part.result) if part.result and part.result.startswith(('[','{')) else part.result
                              except (json.JSONDecodeError, TypeError):
                                   response_data = part.result

                         # The API expects the response payload within a 'content' key for the function response part
                         func_response = glm.FunctionResponse(name=part.name, response={"content": response_data})
                         message_content.append(func_response)
                    except Exception as e:
                        logging.error(f"Failed to format ToolResult '{part.name}' (ID: {part.id}) for Gemini request: {e}")
                        # Send an error message back to the model indicating the tool formatting failed
                        error_response = glm.FunctionResponse(
                            name=part.name,
                            response={"content": {"error": f"Internal error processing result for tool {part.name}: {e}"}}
                        )
                        message_content.append(error_response)
                else:
                    logging.warning(f"send_message received unexpected part type: {type(part)}. Skipping.")

            if not message_content:
                 raise ValueError("Cannot send empty message to Gemini.")

            # --- Send Message ---
            logging.debug(f"Sending Gemini message content: {message_content}")
            # Use asyncio.to_thread to run the blocking SDK call in a separate thread
            response = await asyncio.to_thread(
                 chat_session.send_message,
                 message_content # Can be string or list of parts
            )
            logging.debug("Received Gemini response.") # Avoid logging potentially large/sensitive response object

            # --- Extract Token Usage (if available) ---
            # Gemini API response includes usage metadata
            prompt_tokens = response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else None
            completion_tokens = response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else None
            self._update_token_counts(prompt_tokens, completion_tokens) # Update base class trackers
            logging.info(f"Gemini Token Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}")

            # --- Response Parsing ---
            if not response.candidates:
                 logging.error("Gemini response missing candidates.")
                 text_response = "[Error: Gemini response contained no candidates.]"
                 return text_response, None

            # Use the first candidate
            candidate = response.candidates[0]
            finish_reason = getattr(candidate, 'finish_reason', glm.Candidate.FinishReason.UNKNOWN)

            # Check finish reason first
            # Note: Gemini uses integers for finish reasons in some SDK versions/contexts
            # Comparing with enum members is safer if available
            stop_reasons = [glm.Candidate.FinishReason.STOP, glm.Candidate.FinishReason.TOOL_CALLING]
            if hasattr(glm.Candidate.FinishReason, "MAX_TOKENS"): stop_reasons.append(glm.Candidate.FinishReason.MAX_TOKENS)

            if finish_reason not in stop_reasons:
                 logging.warning(f"Gemini response stopped unexpectedly: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}")
                 # Check for safety blocks
                 if finish_reason == glm.Candidate.FinishReason.SAFETY:
                     safety_ratings_str = str(getattr(candidate, 'safety_ratings', 'No safety ratings provided.'))
                     logging.error(f"Gemini response blocked due to safety settings: {safety_ratings_str}")
                     text_response = f"[Response blocked by safety settings: {safety_ratings_str}]"
                 elif finish_reason == glm.Candidate.FinishReason.RECITATION:
                      logging.error("Gemini response blocked due to recitation.")
                      text_response = "[Response blocked due to recitation policy.]"
                 else:
                      text_response = f"[Response generation stopped unexpectedly: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}]"
                 return text_response, None # Return error text, no tool calls

            # Process valid content (can have multiple parts)
            if candidate.content and candidate.content.parts:
                all_text_parts = []
                all_tool_calls = []
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        all_text_parts.append(part.text)
                    if hasattr(part, 'function_call') and part.function_call.name:
                        fc = part.function_call
                        # Generate a unique-enough ID for the tool call
                        # Include timestamp and a hash of args for better uniqueness
                        call_id = f"{fc.name}_{int(time.time()*1000)}_{hash(str(fc.args)) % 10000}"
                        all_tool_calls.append(ToolCall(id=call_id, name=fc.name, arguments=dict(fc.args)))

                if all_text_parts: text_response = "\n".join(all_text_parts).strip()
                if all_tool_calls: tool_calls_list = all_tool_calls

            # Handle case where model stops with STOP but provides no text content
            # (e.g., after processing tool results without further comment)
            elif not candidate.content and finish_reason == glm.Candidate.FinishReason.STOP:
                 logging.info("Gemini response finished with STOP but no text/tool content parts.")
                 text_response = "" # Explicitly empty response is valid

            # If only tool calls, text_response might be None, which is okay
            if tool_calls_list and text_response is None:
                logging.info("Gemini response contains only tool calls.")

            # Handle max_tokens finish reason
            if finish_reason == glm.Candidate.FinishReason.MAX_TOKENS:
                 logging.warning(f"Gemini response truncated due to max_tokens limit (Model: {self.model_name}).")
                 # Append warning to text response if it exists
                 warning_msg = "\n[Warning: Response truncated by model due to token limits]"
                 text_response = (text_response + warning_msg) if text_response else warning_msg


        except Exception as e:
            logging.exception(f"Gemini API error during send_message: {e}")
            # Attempt to classify common errors
            if "API key not valid" in str(e):
                 text_response = "[Error: Invalid Gemini API Key.]"
            elif "quota" in str(e).lower():
                 text_response = "[Error: Gemini API quota exceeded.]"
            elif "Deadline Exceeded" in str(e) or "504" in str(e): # Handle timeouts
                 text_response = "[Error: Request to Gemini timed out.]"
            elif "429" in str(e): # Handle rate limiting
                 text_response = "[Error: Gemini API rate limit exceeded.]"
            else:
                 text_response = f"[Error communicating with Gemini: {e}]"
            # Reset token counts as they are likely invalid
            self._last_prompt_tokens = None
            self._last_completion_tokens = None


        return text_response, tool_calls_list

# Need asyncio for running blocking calls in threads
import asyncio
