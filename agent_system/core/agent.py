import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union, Set, Callable # Added Callable

# Core data types
from .datatypes import ChatMessage, ToolCall, ToolResult, MessagePart

# Tool registry and schema translation
from agent_system.tools import TOOL_REGISTRY, get_tool_function, get_tool_schema
from agent_system.config.schemas import translate_schema_for_provider, GenericToolSchema
from agent_system.tools.tool_utils import ask_confirmation_async

# LLM Provider abstraction
from agent_system.llm_providers import LLMProvider

# Configuration settings
from agent_system.config import settings


class BaseAgent:
    """
    Base class for all agents in the system. Handles interaction with LLM providers,
    tool execution, history management, state persistence (potentially session-specific),
    and basic token counting.
    """

    def __init__(
        self,
        name: str,
        llm_provider: LLMProvider,
        system_prompt: str = "",
        allowed_tools: Optional[List[str]] = None,
        session_id: Optional[str] = None # <-- For session ID
    ):
        """
        Initializes the BaseAgent.

        Args:
            name: A unique name for the agent instance (e.g., 'ControllerAgent', 'CodingAgent').
            llm_provider: An initialized instance of an LLMProvider subclass.
            system_prompt: The system prompt defining the agent's role and instructions.
            allowed_tools: A list of tool names this agent is explicitly allowed to use.
                           If None or empty, the agent cannot use any registered tools.
            session_id: Optional identifier for the current session (e.g., from a web request).
                        If provided, state persistence will be specific to this session.
        """
        self.name = name
        self.session_id = session_id # Store session ID
        self.llm_provider = llm_provider
        self.agent_model = llm_provider.model_name
        self.system_prompt = system_prompt
        self.allowed_tools: Set[str] = set(allowed_tools) if allowed_tools else set()

        # Agent's conversation history
        self.history: List[ChatMessage] = []

        # State file path - Incorporate session_id if provided
        state_filename: str
        if self.session_id:
            safe_session_id = str(self.session_id).replace('/', '_').replace('\\', '_') # Basic safety
            state_filename = f"session_{safe_session_id}_{self.name}_history.json"
            logging.debug(f"Agent '{self.name}' session '{self.session_id}'. State file: {state_filename}") # Debug level
        else:
            state_filename = f"{self.name}_history.json"
            logging.debug(f"Agent '{self.name}' no session ID. State file: {state_filename}") # Debug level

        self.state_file: Path = settings.AGENT_STATE_DIR / state_filename

        # --- Tool Setup ---
        self.agent_tool_schemas: Dict[str, GenericToolSchema] = {}
        self.agent_tool_functions: Dict[str, Callable] = {}
        self._prepare_allowed_tools() # Populates the above dicts

        # Translate schemas for the specific provider
        self.provider_tool_schemas: Optional[Any] = None
        if self.agent_tool_schemas:
             try:
                  allowed_schema_list = list(self.agent_tool_schemas.keys())
                  provider_name_str = type(llm_provider).__name__.lower().replace("provider", "")
                  self.provider_tool_schemas = translate_schema_for_provider(
                       provider_name=provider_name_str,
                       registered_tools=self.agent_tool_schemas,
                       tool_names=allowed_schema_list
                  )
                  logging.debug(f"Agent '{self.name}': Translated schema for provider {provider_name_str}.")
             except Exception as e:
                  logging.exception(f"Failed to translate tool schema for provider {type(llm_provider).__name__} in agent {self.name}: {e}")

        # Token usage tracked per agent instance
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0

        init_msg = f"Initialized {self.name} (Model: {self.agent_model}, Provider: {type(llm_provider).__name__}"
        if self.session_id: init_msg += f", Session: {self.session_id}"
        init_msg += f"). Allowed Tools: {list(self.allowed_tools)}"
        logging.info(init_msg)


    def _prepare_allowed_tools(self):
        """Filters the global TOOL_REGISTRY based on self.allowed_tools."""
        self.agent_tool_functions.clear()
        self.agent_tool_schemas.clear()
        registered_tools = TOOL_REGISTRY

        for tool_name in self.allowed_tools:
            # Skip special internal tools like delegate_task for ControllerAgent
            if tool_name == "delegate_task" and self.__class__.__name__ == "ControllerAgent":
                logging.debug(f"Agent '{self.name}': Skipping registry lookup for internal tool '{tool_name}'.")
                continue # Controller handles this internally

            if tool_name in registered_tools:
                 tool_data = registered_tools[tool_name]
                 func = tool_data.get("function")
                 schema = tool_data.get("schema")
                 if callable(func) and isinstance(schema, dict):
                      self.agent_tool_functions[tool_name] = func
                      self.agent_tool_schemas[tool_name] = schema
                 else:
                      logging.warning(f"Agent '{self.name}': Allowed tool '{tool_name}' has invalid function/schema in registry. Skipping.")
            else:
                 logging.warning(f"Agent '{self.name}': Allowed tool '{tool_name}' is not found in the tool registry. Skipping.")
        logging.debug(f"Agent '{self.name}': Prepared {len(self.agent_tool_functions)} usable external tools.")


    async def _load_state(self):
        """Loads agent history from its state file (potentially session-specific)."""
        # (Implementation remains the same as corrected version)
        if self.state_file.exists():
            logging.info(f"Loading state for agent '{self.name}' (Session: {self.session_id or 'None'}) from {self.state_file}")
            try:
                def read_and_decode():
                    content = self.state_file.read_text(encoding='utf-8')
                    return json.loads(content)
                history_data = await asyncio.to_thread(read_and_decode)
                if isinstance(history_data, list):
                     valid_history, invalid_count = [], 0
                     for msg_data in history_data:
                          if isinstance(msg_data, dict) and 'role' in msg_data and 'parts' in msg_data:
                               try: valid_history.append(ChatMessage.from_dict(msg_data))
                               except Exception as deser_err: logging.warning(f"Failed to deserialize message: {deser_err}. Data: {msg_data}"); invalid_count += 1
                          else: invalid_count += 1; logging.warning(f"Skipping invalid message structure: {msg_data}")
                     self.history = valid_history
                     log_msg = f"Loaded {len(self.history)} valid messages for agent '{self.name}'."
                     if invalid_count > 0: log_msg += f" Skipped {invalid_count} invalid messages."
                     logging.info(log_msg)
                else:
                     logging.warning(f"State file {self.state_file} for agent '{self.name}' did not contain a list. Starting fresh history."); self.history = []
            except json.JSONDecodeError as e: logging.error(f"Error decoding JSON state file {self.state_file}: {e}. Starting fresh."); self.history = []
            except FileNotFoundError: logging.info(f"State file {self.state_file} not found. Starting fresh."); self.history = []
            except Exception as e: logging.exception(f"Error loading state file {self.state_file}: {e}. Starting fresh."); self.history = []
        else:
            logging.info(f"No state file found for agent '{self.name}' (Session: {self.session_id or 'None'}) at {self.state_file}. Starting fresh.")
            self.history = []

    async def _save_state(self):
        """Saves the current agent history to its state file (potentially session-specific)."""
        # (Implementation remains the same as corrected version)
        if not self.history:
             logging.debug(f"Agent '{self.name}' (Session: {self.session_id or 'None'}) has empty history. Skipping state save.")
             return
        logging.info(f"Saving state ({len(self.history)} messages) for agent '{self.name}' (Session: {self.session_id or 'None'}) to {self.state_file}")
        try:
            history_to_save = [msg.to_dict() for msg in self.history]
            state_data = history_to_save
            def write_encoded():
                 self.state_file.parent.mkdir(parents=True, exist_ok=True)
                 json_string = json.dumps(state_data, indent=2)
                 temp_file = self.state_file.with_suffix(f".tmp_{int(time.time())}")
                 temp_file.write_text(json_string, encoding='utf-8')
                 temp_file.replace(self.state_file)
            await asyncio.to_thread(write_encoded)
            logging.debug(f"Saved {len(history_to_save)} messages for agent '{self.name}' (Session: {self.session_id or 'None'}).")
        except PermissionError as e: logging.error(f"Permission denied saving state file {self.state_file}: {e}")
        except Exception as e: logging.exception(f"Error saving state file {self.state_file}: {e}")


    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        Executes a single tool call asynchronously, performs confirmation check, returns ToolResult.
        """
        # (Implementation remains the same as corrected version)
        tool_name, args, call_id = tool_call.name, tool_call.arguments, tool_call.id
        result: Optional[str] = None; error: Optional[str] = None; is_error: bool = False
        agent_id_log = f"Agent '{self.name}' (Session: {self.session_id or 'None'})"
        tool_function = self.agent_tool_functions.get(tool_name)

        if tool_function is None:
            if tool_name in self.allowed_tools: error = f"Tool '{tool_name}' allowed for {agent_id_log} but no implementation found."
            else: error = f"Tool '{tool_name}' not available or not allowed for {agent_id_log}."
            is_error = True; logging.error(error)
        else:
            if tool_name in settings.HIGH_RISK_TOOLS:
                 if not await ask_confirmation_async(tool_name, args):
                     result = f"Operation cancelled by user for tool: {tool_name}."; is_error = False
                     logging.warning(f"Execution of '{tool_name}' cancelled by user for {agent_id_log}.")
                     return ToolResult(id=call_id, name=tool_name, result=result, error=None, is_error=False)
                 else: logging.info(f"User confirmed execution for high-risk tool '{tool_name}' ({agent_id_log}).")
            logging.info(f"{agent_id_log} executing tool: {tool_name} (ID: {call_id}) with args: {args}")
            start_time = time.monotonic()
            try:
                tool_output = await tool_function(**args)
                duration = time.monotonic() - start_time
                result = str(tool_output)
                logging.info(f"Tool '{tool_name}' executed by {agent_id_log} in {duration:.2f}s. Result length: {len(result)}")
                logging.debug(f"Tool '{tool_name}' Result: {result[:500]}{'...' if len(result)>500 else ''}")
            except TypeError as e:
                duration = time.monotonic() - start_time
                logging.warning(f"TypeError executing tool '{tool_name}' by {agent_id_log} after {duration:.2f}s. Args: {args}. Error: {e}", exc_info=True) # Log traceback for type errors
                error = f"Error executing tool '{tool_name}': Invalid arguments provided by LLM. Details: {e}"; is_error = True
            except Exception as e:
                duration = time.monotonic() - start_time
                logging.exception(f"Error executing tool '{tool_name}' by {agent_id_log} after {duration:.2f}s. Args: {args}. Error: {e}")
                error = f"Error executing tool '{tool_name}': {e}"; is_error = True
        return ToolResult(id=call_id, name=tool_name, result=result, error=error, is_error=is_error)

    async def run(self, user_prompt: str, load_state: bool = True, save_state: bool = True) -> str:
        """
        Core agent execution loop. Handles prompting, tool calls (concurrently),
        history, optional state persistence, and token counting.
        """
        # (Implementation remains the same as corrected version)
        agent_id_log = f"Agent '{self.name}' (Session: {self.session_id or 'None'})"
        logging.info(f"--- {agent_id_log} Received Prompt ---")
        logging.info(f"Prompt: {user_prompt}")
        if load_state: await self._load_state()
        else: self.history = []; logging.info(f"{agent_id_log}: Skipping state load.")
        self.history.append(ChatMessage(role="user", parts=[user_prompt]))
        max_tool_rounds = 10; tool_round = 0
        final_response: str = "[Agent run completed without a final text response]"
        try:
            chat_session = await self.llm_provider.start_chat(
                 system_prompt=self.system_prompt, tool_schemas=self.provider_tool_schemas, history=self.history
            )
        except Exception as start_err: return f"[Error: Failed to start chat session: {start_err}]"
        current_prompt_parts: List[Union[str, ToolResult]] = [user_prompt]
        while tool_round < max_tool_rounds:
            tool_round += 1; logging.info(f"--- {agent_id_log} | LLM Turn {tool_round}/{max_tool_rounds} ---")
            current_total_tokens = self.total_prompt_tokens + self.total_completion_tokens
            quota_exceeded = False
            if settings.MAX_GLOBAL_TOKENS > 0:
                 if current_total_tokens >= settings.MAX_GLOBAL_TOKENS: quota_exceeded = True; final_response = "[Error: Token quota exceeded.]"; logging.critical(f"{agent_id_log}: Token quota EXCEEDED ({current_total_tokens}/{settings.MAX_GLOBAL_TOKENS}).")
                 elif current_total_tokens >= settings.WARN_TOKEN_THRESHOLD: logging.warning(f"{agent_id_log}: Token usage nearing limit ({current_total_tokens}/{settings.MAX_GLOBAL_TOKENS}).")
            if quota_exceeded: break
            try:
                text_response, tool_calls = await self.llm_provider.send_message(chat_session, current_prompt_parts, model_name_override=self.agent_model)
                last_usage = self.llm_provider.get_last_token_usage(); last_prompt = last_usage.get('prompt_tokens'); last_completion = last_usage.get('completion_tokens')
                if last_prompt is not None: self.total_prompt_tokens += last_prompt
                if last_completion is not None: self.total_completion_tokens += last_completion
                logging.info(f"{agent_id_log} Token Usage - Last: P={last_prompt}, C={last_completion} | Cumulative: P={self.total_prompt_tokens}, C={self.total_completion_tokens}")
                model_parts: List[MessagePart] = []
                if text_response is not None: model_parts.append(text_response)
                if tool_calls: model_parts.append(tool_calls)
                if model_parts: self.history.append(ChatMessage(role="assistant", parts=model_parts))
                else: final_response = text_response if text_response is not None else "[Error: LLM provided no response content.]"; logging.warning(f"{agent_id_log}: LLM provided no response content."); break
                if not tool_calls: final_response = text_response if text_response is not None else "[Agent finished without final text response]"; logging.info(f"--- {agent_id_log} Final Response ---"); break
                logging.info(f"{agent_id_log}: Processing {len(tool_calls)} tool call(s) concurrently...")
                tool_tasks = [asyncio.create_task(self._execute_tool(tc)) for tc in tool_calls]
                tool_results: List[ToolResult] = await asyncio.gather(*tool_tasks)
                if tool_results: self.history.append(ChatMessage(role="tool", parts=tool_results))
                current_prompt_parts = tool_results
            except Exception as e: final_response = f"[Error in {agent_id_log} run loop: {e}]"; logging.exception(f"Error in {agent_id_log} run loop:"); break
        if tool_round >= max_tool_rounds:
            logging.warning(f"{agent_id_log} reached max tool rounds ({max_tool_rounds}).")
            if final_response == "[Agent run completed without a final text response]":
                  for msg in reversed(self.history):
                       if msg.role == 'assistant': text_content = msg.get_text_content();
                       if text_content is not None: final_response = text_content + "\n[Warning: Agent reached max tool rounds]"; break
        if save_state: await self._save_state()
        else: logging.info(f"{agent_id_log}: Skipping state save.")
        return final_response
