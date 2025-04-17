import os
import time
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union

# Import base class and core data types
from . import LLMProvider
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult

# Attempt to import Gemini libraries - This should now succeed if env is correct
try:
    import google.generativeai as genai
    import google.ai.generativelanguage as glm
    from google.generativeai.types import ContentDict, PartDict, FunctionCallDict, FunctionResponseDict
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    GEMINI_LIBS_AVAILABLE = True
except ImportError as e:
    # This block should ideally NOT be hit if installation is correct
    logging.error(f"ImportError: Failed to import google-generativeai. Is it installed in the correct environment? Error: {e}", exc_info=True)
    GEMINI_LIBS_AVAILABLE = False
    genai = None
    glm = None
    ContentDict = Dict # Fallback type hint
    FunctionDeclaration = Any # Fallback type hint
    ChatSession = Any # Fallback type hint
    FunctionResponse = Any # Fallback type hint
    HarmCategory = None
    HarmBlockThreshold = None


class GeminiProvider(LLMProvider):
    """LLM Provider implementation for Google Gemini."""

    DEFAULT_SAFETY_SETTINGS = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    } if GEMINI_LIBS_AVAILABLE and HarmCategory and HarmBlockThreshold else {}


    def __init__(self, model: str = "gemini-1.5-pro-latest", api_key: Optional[str] = None, **kwargs):
        """Initializes the Gemini provider."""
        if not GEMINI_LIBS_AVAILABLE:
             # If import failed at top level, raise error immediately
            raise ImportError("Gemini libraries (google-generativeai) failed to import. Ensure it's installed correctly in the active environment.")

        super().__init__(model, api_key, **kwargs)
        self.safety_settings = kwargs.get("safety_settings", self.DEFAULT_SAFETY_SETTINGS)

        try:
            effective_key = self.api_key or self._get_key_from_env()
            if not effective_key:
                raise ValueError("Gemini API Key not provided and GEMINI_API_KEY environment variable not set.")

            genai.configure(api_key=effective_key)
            logging.debug(f"Verifying Gemini configuration with model: {self.model_name}")
            _ = genai.GenerativeModel(self.model_name)
            logging.info(f"GeminiProvider configured successfully for model: {self.model_name}")

        except Exception as e:
            logging.error(f"Failed to configure or verify Gemini API: {e}", exc_info=True)
            if "API key not valid" in str(e):
                 raise ConnectionError("Gemini API Key is invalid.") from e
            else:
                 raise ConnectionError(f"Failed to configure Gemini API: {e}") from e

    def _get_key_from_env(self) -> Optional[str]:
        return os.environ.get("GEMINI_API_KEY")

    def _convert_history_to_gemini(self, history: List[ChatMessage]) -> List[ContentDict]:
        """Converts the generic ChatMessage history to Gemini's ContentDict format."""
        # (Conversion logic remains the same - uses glm.* types directly now)
        gemini_history: List[ContentDict] = []
        for msg in history:
            role = msg.role if msg.role != "assistant" else "model"
            if role == "system": continue
            converted_parts: List[Union[str, glm.FunctionCall, glm.FunctionResponse]] = [] # Use direct types
            for part in msg.parts:
                if isinstance(part, str): converted_parts.append(part)
                elif isinstance(part, list) and part and isinstance(part[0], ToolCall):
                    if role == "model":
                        for tc in part:
                             try: converted_parts.append(glm.FunctionCall(name=tc.name, args=tc.arguments))
                             except Exception as e: logging.error(f"Failed to format ToolCall args for Gemini history: {e}. Args: {tc.arguments}")
                    else: logging.warning(f"Gemini history: ToolCall list in non-model message (Role: {role}). Skipping.")
                elif isinstance(part, list) and part and isinstance(part[0], ToolResult):
                     if role == "tool":
                         for tr in part:
                             try:
                                 if tr.is_error: response_content = {"error": tr.error}
                                 else:
                                     try: response_content = json.loads(tr.result) if tr.result and tr.result.startswith(('[','{')) else tr.result
                                     except (json.JSONDecodeError, TypeError): response_content = tr.result
                                 converted_parts.append(glm.FunctionResponse(name=tr.name, response={"content": response_content}))
                             except Exception as e: logging.error(f"Failed to format ToolResult for Gemini history: {e}. Result: {tr}")
                     else: logging.warning(f"Gemini history: ToolResult list in non-tool message (Role: {role}). Skipping.")
                else: converted_parts.append(str(part))
            if converted_parts: gemini_history.append({'role': role, 'parts': converted_parts})
            else: logging.debug(f"Skipping empty message in Gemini history conversion (Original Role: {msg.role})")
        return gemini_history

    # Use direct type hints now - should work if import succeeds
    async def start_chat(self, system_prompt: str, tool_schemas: Optional[List[glm.FunctionDeclaration]], history: Optional[List[ChatMessage]] = None) -> genai.ChatSession:
        """Initializes a Gemini ChatSession."""
        gemini_history = self._convert_history_to_gemini(history) if history else []
        try:
            model_instance = genai.GenerativeModel(
                model_name=self.model_name, system_instruction=system_prompt,
                tools=tool_schemas, safety_settings=self.safety_settings
            )
            logging.debug(f"Starting Gemini chat session with history: {gemini_history}")
            return model_instance.start_chat(history=gemini_history)
        except Exception as e:
            logging.exception(f"Failed to initialize Gemini chat session (Model: {self.model_name}): {e}")
            raise ConnectionError(f"Failed to initialize Gemini chat session '{self.model_name}': {e}") from e

    async def send_message(self, chat_session: genai.ChatSession, prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
        """Sends a message (prompt text or tool results) to the Gemini model."""
        # (Rest of send_message implementation remains the same as the corrected V1 version)
        if model_name_override and model_name_override != self.model_name:
             logging.warning(f"GeminiProvider does not support per-message model override via ChatSession. Using session model '{self.model_name}'.")
        text_response: Optional[str] = None; tool_calls_list: Optional[List[ToolCall]] = None
        prompt_tokens: Optional[int] = None; completion_tokens: Optional[int] = None
        try:
            message_content: List[Union[str, glm.FunctionResponse]] = []
            for part in prompt_parts:
                if isinstance(part, str): message_content.append(part)
                elif isinstance(part, ToolResult):
                    try:
                         if part.is_error: response_data = {"error": part.error}
                         else:
                              try: response_data = json.loads(part.result) if part.result and part.result.startswith(('[','{')) else part.result
                              except (json.JSONDecodeError, TypeError): response_data = part.result
                         message_content.append(glm.FunctionResponse(name=part.name, response={"content": response_data}))
                    except Exception as e:
                        logging.error(f"Failed to format ToolResult '{part.name}' (ID: {part.id}) for Gemini request: {e}")
                        message_content.append(glm.FunctionResponse(name=part.name, response={"content": {"error": f"Internal error: {e}"}}))
                else: logging.warning(f"send_message received unexpected part type: {type(part)}. Skipping.")
            if not message_content: raise ValueError("Cannot send empty message to Gemini.")
            logging.debug(f"Sending Gemini message content: {message_content}")
            response = await asyncio.to_thread(chat_session.send_message, message_content)
            logging.debug("Received Gemini response.")
            if hasattr(response, 'usage_metadata'):
                prompt_tokens = response.usage_metadata.prompt_token_count
                completion_tokens = response.usage_metadata.candidates_token_count
                self._update_token_counts(prompt_tokens, completion_tokens)
                logging.info(f"Gemini Token Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}")
            else: logging.warning("Gemini response missing usage_metadata.")
            if not response.candidates:
                 text_response = "[Error: Gemini response contained no candidates.]"; return text_response, None
            candidate = response.candidates[0]; finish_reason = getattr(candidate, 'finish_reason', glm.Candidate.FinishReason.UNKNOWN)
            stop_reasons = [glm.Candidate.FinishReason.STOP, glm.Candidate.FinishReason.TOOL_CALLING]
            if hasattr(glm.Candidate.FinishReason, "MAX_TOKENS"): stop_reasons.append(glm.Candidate.FinishReason.MAX_TOKENS)
            if finish_reason not in stop_reasons:
                 logging.warning(f"Gemini response stopped unexpectedly: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}")
                 if finish_reason == glm.Candidate.FinishReason.SAFETY: text_response = f"[Response blocked by safety settings: {getattr(candidate, 'safety_ratings', 'N/A')}]"
                 elif finish_reason == glm.Candidate.FinishReason.RECITATION: text_response = "[Response blocked due to recitation policy.]"
                 else: text_response = f"[Response generation stopped unexpectedly: {finish_reason.name if hasattr(finish_reason, 'name') else finish_reason}]"
                 return text_response, None
            if candidate.content and candidate.content.parts:
                all_text_parts, all_tool_calls = [], []
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text: all_text_parts.append(part.text)
                    if hasattr(part, 'function_call') and part.function_call.name:
                        fc = part.function_call; call_id = f"{fc.name}_{int(time.time()*1000)}_{hash(str(fc.args)) % 10000}"
                        all_tool_calls.append(ToolCall(id=call_id, name=fc.name, arguments=dict(fc.args)))
                if all_text_parts: text_response = "\n".join(all_text_parts).strip()
                if all_tool_calls: tool_calls_list = all_tool_calls
            elif not candidate.content and finish_reason == glm.Candidate.FinishReason.STOP: text_response = ""
            if tool_calls_list and text_response is None: logging.info("Gemini response contains only tool calls.")
            if finish_reason == glm.Candidate.FinishReason.MAX_TOKENS:
                 warning_msg = "\n[Warning: Response truncated by model due to token limits]"
                 text_response = (text_response + warning_msg) if text_response else warning_msg
        except Exception as e:
            logging.exception(f"Gemini API error during send_message: {e}")
            if "API key not valid" in str(e): text_response = "[Error: Invalid Gemini API Key.]"
            elif "quota" in str(e).lower(): text_response = "[Error: Gemini API quota exceeded.]"
            elif "Deadline Exceeded" in str(e) or "504" in str(e): text_response = "[Error: Request to Gemini timed out.]"
            elif "429" in str(e): text_response = "[Error: Gemini API rate limit exceeded.]"
            else: text_response = f"[Error communicating with Gemini: {e}]"
            self._last_prompt_tokens = None; self._last_completion_tokens = None
        return text_response, tool_calls_list
