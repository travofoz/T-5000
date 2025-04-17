# --- START DEBUG ---
import sys, os, logging # Make sure these are imported for debug
print(f"\n--- DEBUG: ENTERING anthropic.py ---")
print(f"Current sys.path:")
for p in sys.path: print(f"  - {p}")
print(f"Current CWD: {os.getcwd()}")
print(f"--- END DEBUG ---\n")
# --- END DEBUG ---

# import os # Already imported above
# import logging # Already imported above
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Union

# Import base class and core data types
from . import LLMProvider
from agent_system.core.datatypes import ChatMessage, ToolCall, ToolResult
from agent_system.config.schemas import translate_to_anthropic_schema, GenericToolSchema

# Attempt to import Anthropic library
try:
    print("--- DEBUG: Attempting 'import anthropic' ---") # DEBUG
    import anthropic
    print("--- DEBUG: 'import anthropic' SUCCEEDED ---") # DEBUG
    print(f"--- DEBUG: anthropic module location: {anthropic.__file__}") # DEBUG

    print("--- DEBUG: Attempting 'from anthropic import AsyncAnthropic' ---") # DEBUG
    from anthropic import AsyncAnthropic # Use the async client
    print("--- DEBUG: 'from anthropic import AsyncAnthropic' SUCCEEDED ---") # DEBUG

    print("--- DEBUG: Attempting 'from anthropic.types import ...' ---") # DEBUG
    from anthropic.types import Message, TextBlock, ToolUseBlock, ToolResultBlock
    print("--- DEBUG: 'from anthropic.types import ...' SUCCEEDED ---") # DEBUG

    ANTHROPIC_LIBS_AVAILABLE = True
except ImportError as e:
    # This block should now ONLY be hit if the import truly fails
    print(f"--- DEBUG: ImportError caught: {e} ---") # DEBUG
    import traceback # DEBUG
    traceback.print_exc() # DEBUG
    logging.warning("anthropic library not found. AnthropicProvider will be unavailable.") # Keep warning
    ANTHROPIC_LIBS_AVAILABLE = False
    # Define dummy types if library is missing
    AsyncAnthropic = None; Message = None; TextBlock = None; ToolUseBlock = None; ToolResultBlock = None; anthropic = None
except Exception as e_outer:
     # Catch any other exception during import
     print(f"--- DEBUG: UNEXPECTED Exception during import: {e_outer} ---") # DEBUG
     import traceback # DEBUG
     traceback.print_exc() # DEBUG
     logging.exception("Unexpected error during Anthropic library import.")
     ANTHROPIC_LIBS_AVAILABLE = False
     AsyncAnthropic = None; Message = None; TextBlock = None; ToolUseBlock = None; ToolResultBlock = None; anthropic = None


# Constants for Anthropic API
MAX_TOKENS_DEFAULT = 4096

class AnthropicProvider(LLMProvider):
    """LLM Provider implementation for Anthropic Claude models."""
    # (Rest of the AnthropicProvider class implementation remains the same as the correct V1 version)
    def __init__(self, model: str = "claude-3-opus-20240229", api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        if not ANTHROPIC_LIBS_AVAILABLE: raise ImportError("Anthropic library failed to import. Cannot initialize provider.")
        super().__init__(model, api_key, base_url, **kwargs)
        if self.base_url: logging.warning("AnthropicProvider base_url ignored by client. Use ANTHROPIC_BASE_URL env var.")
        effective_key = self.api_key or self._get_key_from_env()
        if not effective_key: raise ValueError("Anthropic API Key not provided or found in env.")
        try:
            self.client = AsyncAnthropic(api_key=effective_key, **self._config_kwargs)
            logging.info(f"AnthropicProvider initialized for model: {self.model_name}")
        except Exception as e: logging.error(f"Failed init Anthropic client: {e}", exc_info=True); raise ConnectionError(f"Failed init Anthropic client: {e}") from e
        self._translated_tool_schemas: Optional[List[Dict[str, Any]]] = None; self._system_prompt_cache: Optional[str] = None
    def _get_key_from_env(self) -> Optional[str]: return os.environ.get("ANTHROPIC_API_KEY")
    def _convert_history_to_anthropic(self, history: List[ChatMessage]) -> List[Dict[str, Any]]:
        # (Implementation unchanged)
        anthropic_history = []; last_role = None
        for msg in history:
            anthropic_role = msg.role;
            if anthropic_role == "model": anthropic_role = "assistant"
            if anthropic_role == "system": continue
            if anthropic_role == "tool": anthropic_role = "user"
            content_blocks = []
            for part in msg.parts:
                if isinstance(part, str):
                    if part.strip(): content_blocks.append({"type": "text", "text": part})
                elif isinstance(part, list) and part and isinstance(part[0], ToolCall):
                    if msg.role in ["assistant", "model"]:
                        for tc in part: content_blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                    else: logging.warning(f"Anthropic history: ToolCall list in non-assistant message (Role: {msg.role}). Skipping.")
                elif isinstance(part, list) and part and isinstance(part[0], ToolResult):
                    if anthropic_role == "user":
                        for tr in part:
                            res_str = str(tr.error) if tr.is_error else str(tr.result); res_str = res_str if res_str is not None else ""
                            content_blocks.append({"type": "tool_result", "tool_use_id": tr.id, "content": res_str})
                    else: logging.error(f"Anthropic history: ToolResult list found while building non-user message (Role: {anthropic_role}). Skipping.")
                elif isinstance(part, list) and not part: continue
                else: str_part = str(part).strip();
                if str_part: content_blocks.append({"type": "text", "text": str_part})
            if not content_blocks: logging.debug(f"Skipping message with no content blocks (Original Role: {msg.role})."); continue
            if anthropic_history and last_role == anthropic_role:
                 if isinstance(anthropic_history[-1]["content"], list): anthropic_history[-1]["content"].extend(content_blocks)
                 else: logging.warning(f"Anthropic history: Prev msg content not list. Overwriting."); anthropic_history[-1]["content"] = content_blocks
            else: anthropic_history.append({"role": anthropic_role, "content": content_blocks}); last_role = anthropic_role
        if anthropic_history and anthropic_history[0]['role'] == 'assistant': logging.error("Anthropic history invalid: starts with 'assistant'."); return []
        for i in range(len(anthropic_history) - 1):
             if anthropic_history[i]['role'] == anthropic_history[i+1]['role']: logging.error(f"Anthropic history invalid: consecutive roles '{anthropic_history[i]['role']}'."); return []
        return anthropic_history
    async def start_chat(self, system_prompt: str, tool_schemas: Optional[List[Dict[str, Any]]], history: Optional[List[ChatMessage]] = None) -> List[Dict[str, Any]]:
        # (Implementation unchanged)
        self._system_prompt_cache = system_prompt; self._translated_tool_schemas = tool_schemas
        openai_history = self._convert_history_to_anthropic(history) if history else []
        logging.debug(f"Prepared Anthropic chat history with {len(openai_history)} messages.")
        return openai_history
    async def send_message(self, chat_session: List[Dict[str, Any]], prompt_parts: List[Union[str, ToolResult]], model_name_override: Optional[str] = None, mcp_context: Optional[Dict[str, Any]] = None, mcp_metadata: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[List[ToolCall]]]:
        # (Implementation unchanged)
        text_response: Optional[str] = None; tool_calls_list: Optional[List[ToolCall]] = None; prompt_tokens: Optional[int] = None; completion_tokens: Optional[int] = None
        new_message_role = "user"; new_message_blocks = []
        if not prompt_parts: raise ValueError("Cannot send empty prompt parts to Anthropic.")
        first_part = prompt_parts[0]
        if isinstance(first_part, str): user_content = "\n".join(part for part in prompt_parts if isinstance(part, str));
        if user_content.strip(): new_message_blocks.append({"type": "text", "text": user_content.strip()})
        elif isinstance(first_part, ToolResult):
            for part in prompt_parts:
                 if isinstance(part, ToolResult): res_str = str(part.error) if part.is_error else str(part.result); res_str = res_str if res_str is not None else ""; new_message_blocks.append({"type": "tool_result", "tool_use_id": part.id, "content": res_str})
                 else: logging.warning(f"Mixing ToolResult and other types ({type(part)}). Ignoring non-ToolResult.")
        else: raise ValueError(f"Invalid first prompt part type: {type(first_part)}")
        if not new_message_blocks: logging.warning("Prepared Anthropic message empty. Skipping append.")
        elif chat_session and chat_session[-1]["role"] == new_message_role:
             if isinstance(chat_session[-1]["content"], list): chat_session[-1]["content"].extend(new_message_blocks)
             else: chat_session[-1]["content"] = new_message_blocks
        else: chat_session.append({"role": new_message_role, "content": new_message_blocks})
        messages_to_send = [msg for msg in chat_session if msg.get("content")]
        if not messages_to_send: logging.error("Cannot send message: History empty."); return "[Error: Invalid history state (empty).]", None
        for i in range(len(messages_to_send) - 1):
             if messages_to_send[i]['role'] == messages_to_send[i+1]['role']: logging.error(f"Anthropic API violation: Consecutive roles '{messages_to_send[i]['role']}'."); return f"[Error: Invalid history state (consecutive roles '{messages_to_send[i]['role']}').]", None
        try:
            effective_model = model_name_override or self.model_name; logging.debug(f"Sending Anthropic request. System Prompt: {self._system_prompt_cache[:100]}... Tools: {bool(self._translated_tool_schemas)}")
            api_response: Message = await self.client.messages.create(model=effective_model, system=self._system_prompt_cache, messages=messages_to_send, tools=self._translated_tool_schemas or [], max_tokens=MAX_TOKENS_DEFAULT, metadata=mcp_metadata, context=mcp_context) # Added metadata/context
            if api_response.usage: prompt_tokens = api_response.usage.input_tokens; completion_tokens = api_response.usage.output_tokens; self._update_token_counts(prompt_tokens, completion_tokens); logging.info(f"Anthropic Token Usage - Input: {prompt_tokens}, Output: {completion_tokens}")
            else: logging.warning("Anthropic response missing usage metadata.")
            assistant_response_content = api_response.content if isinstance(api_response.content, list) else [api_response.content]; assistant_response_msg = {"role": api_response.role, "content": assistant_response_content}; chat_session.append(assistant_response_msg)
            tool_calls_list = []; text_parts = []
            for block in assistant_response_content:
                if isinstance(block, TextBlock): text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock): tool_calls_list.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
            if text_parts: text_response = "\n".join(text_parts).strip()
            stop_reason = api_response.stop_reason
            if stop_reason == "end_turn": logging.info("Anthropic finished normally.")
            elif stop_reason == "tool_use": logging.info("Anthropic stopped for tool use.")
            elif stop_reason == "max_tokens": warning_msg = "\n[Warning: Response truncated]"; text_response = (text_response + warning_msg) if text_response else warning_msg; logging.warning(f"Anthropic truncated (max_tokens).")
            elif stop_reason == "stop_sequence": logging.info("Anthropic stopped due to stop sequence.")
            else: warning_msg = f"\n[Warning: Stopped unexpectedly ({stop_reason})]"; text_response = (text_response + warning_msg) if text_response else warning_msg; logging.warning(f"Anthropic finished unexpectedly: {stop_reason}")
        except anthropic.APIConnectionError as e: text_response = f"[Error: Anthropic connection error: {e}]"
        except anthropic.RateLimitError as e: text_response = "[Error: Anthropic rate limit exceeded.]"
        except anthropic.AuthenticationError as e: text_response = "[Error: Invalid Anthropic API Key.]"
        except anthropic.BadRequestError as e:
             if "prompt is too long" in str(e).lower(): text_response = "[Error: Request exceeds context limit.]"
             elif "alternate user/assistant" in str(e).lower(): text_response = "[Error: Invalid history state (roles).]"
             else: text_response = f"[Error: Invalid request to Anthropic: {e}]"
        except anthropic.APIStatusError as e: text_response = f"[Error: Anthropic API Error ({e.status_code}): {e.message}]"
        except asyncio.TimeoutError: text_response = "[Error: Request to Anthropic timed out.]"
        except Exception as e: logging.exception(f"Unexpected Anthropic error: {e}"); text_response = f"[Error communicating with Anthropic: {e}]"; self._last_prompt_tokens = None; self._last_completion_tokens = None
        if not tool_calls_list: tool_calls_list = None
        return text_response, tool_calls_list
