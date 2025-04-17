import logging
from typing import List, Dict, Any, Optional, Tuple

# Import base agent and data types
from .agent import BaseAgent
from .datatypes import ChatMessage, ToolCall, ToolResult

# Import LLM Provider type hint
from agent_system.llm_providers import LLMProvider

# Import tool utils if needed (e.g., confirmation, although unlikely for controller)
# from agent_system.tools.tool_utils import ask_confirmation_async

class ControllerAgent(BaseAgent):
    """
    Controller Agent responsible for receiving user requests and delegating
    tasks to the appropriate specialist agents.
    """
    SPECIALIST_TOOL_NAME = "delegate_task" # The name of the internal delegation tool

    def __init__(self, agents: Dict[str, BaseAgent], llm_provider: LLMProvider):
        """
        Initializes the ControllerAgent.

        Args:
            agents: A dictionary mapping specialist agent names to their instances.
            llm_provider: An initialized LLMProvider instance for the Controller.
        """
        specialist_names = list(agents.keys())
        system_prompt = f"""
You are the Controller Agent, the central router for a multi-agent system.
Your primary role is to understand the user's request, determine which specialist agent is best suited, and delegate the *entire original task* using the '{self.SPECIALIST_TOOL_NAME}' function ONLY.

Available Specialist Agents:
{', '.join(specialist_names)}

Analyze the user's prompt carefully. You MUST use the '{self.SPECIALIST_TOOL_NAME}' function with the correct 'agent_name' from the list above and the exact original 'user_prompt'.
Do NOT attempt to answer the user's request or perform tasks yourself.
Do NOT ask the user for clarification; make your best choice for delegation based on the available specialists.
If the request seems ambiguous or could fit multiple agents, choose the one that seems most central to the request's core action or goal.
Respond ONLY with the '{self.SPECIALIST_TOOL_NAME}' function call. Your response should contain nothing else.
"""
        # Controller only needs the delegate_task tool defined.
        # The schema for delegate_task is implicitly defined here and handled by _execute_tool.
        # We pass the tool name to BaseAgent's init for awareness, but override execution.
        super().__init__(
            name="ControllerAgent",
            llm_provider=llm_provider,
            system_prompt=system_prompt,
            allowed_tools=[self.SPECIALIST_TOOL_NAME] # Only allow the delegation tool
        )
        self.specialist_agents = agents
        logging.info(f"ControllerAgent initialized. Specialists: {specialist_names}")

        # Override the schema definition specifically for the delegate_task tool within this instance
        # This ensures the LLM knows the expected parameters for delegation.
        # We define it here as it's internal to the controller's function.
        delegate_schema = {
            "description": "Delegate the user's original task to a specialist agent.",
            "parameters": {
                "agent_name": {
                    "type": "string",
                    "description": f"The name of the specialist agent to delegate the task to. Must be one of: {', '.join(specialist_names)}",
                    "required": True
                    # Could add "enum": specialist_names here if provider supports it well
                 },
                "user_prompt": {
                    "type": "string",
                    "description": "The original, unmodified user prompt containing the task.",
                    "required": True
                }
            }
        }
        # Update the schema and re-translate for the provider
        self.agent_tool_schemas[self.SPECIALIST_TOOL_NAME] = delegate_schema
        self.provider_tool_schemas = translate_schema_for_provider(
             provider_name=type(llm_provider).__name__.lower().replace("provider", ""),
             registered_tools=self.agent_tool_schemas, # Pass only the delegate schema
             tool_names=[self.SPECIALIST_TOOL_NAME]
        )
        logging.debug(f"ControllerAgent: Updated provider schema for delegation tool: {self.provider_tool_schemas}")


    async def _delegate_task_impl(self, agent_name: str, user_prompt: str) -> str:
        """
        Internal logic for handling the delegation. Runs the specialist agent.
        This is called by the overridden _execute_tool.

        Args:
            agent_name: Name of the specialist agent to run.
            user_prompt: The user prompt to pass to the specialist.

        Returns:
            The result string from the specialist agent's run, or an error message.
        """
        specialist = self.specialist_agents.get(agent_name)
        if specialist:
            logging.info(f"Controller delegating task to '{agent_name}'...")
            try:
                 # Specialist runs with its own provider/history/model config/state
                 # The specialist's run method will handle its own state loading/saving.
                 result = await specialist.run(user_prompt)
                 # Format result slightly for clarity from controller's perspective?
                 # Or return raw specialist result? Let's return raw for now.
                 logging.info(f"Delegation to '{agent_name}' completed.")
                 # Maybe wrap result for clarity?
                 # return f"--- Result from {agent_name} ---\n{result}\n--- End Result from {agent_name} ---"
                 return result # Return raw result
            except Exception as e:
                 logging.exception(f"Error running specialist agent '{agent_name}' during delegation.")
                 return f"[Error: An unexpected error occurred while running specialist agent '{agent_name}': {e}]"
        else:
            available_agents = list(self.specialist_agents.keys())
            logging.error(f"Controller attempted delegate to unknown agent: '{agent_name}'. Available: {available_agents}")
            # Provide helpful error message back to the Controller LLM if it hallucinates an agent
            return f"[Error: Specialist agent '{agent_name}' not found. Please choose one of: {', '.join(available_agents)}]"

    # Override BaseAgent's _execute_tool to handle the special delegate_task tool internally
    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        Controller's specific tool execution logic. Only handles 'delegate_task'.
        """
        tool_name = tool_call.name
        args = tool_call.arguments
        call_id = tool_call.id

        if tool_name == self.SPECIALIST_TOOL_NAME:
            # No confirmation needed for internal delegation logic itself
            logging.info(f"Controller executing internal delegation via '{tool_name}' with args: {args}")
            try:
                agent_name = args.get("agent_name")
                user_prompt = args.get("user_prompt")

                if not isinstance(agent_name, str) or not agent_name:
                     raise TypeError("Missing or invalid 'agent_name' argument for delegation.")
                if not isinstance(user_prompt, str): # Allow empty prompt? Let specialist handle it.
                     # For controller's purpose, prompt should generally exist.
                     raise TypeError("Missing or invalid 'user_prompt' argument for delegation.")

                # Call the internal implementation directly
                result_str = await self._delegate_task_impl(agent_name=agent_name, user_prompt=user_prompt)

                # Check if the delegation *itself* resulted in an error message (e.g., agent not found)
                # Distinguish between errors *during* specialist run vs errors *finding/calling* specialist
                is_delegation_error = result_str.startswith("[Error:")

                return ToolResult(
                    id=call_id,
                    name=tool_name, # Use the tool name for consistency
                    result=result_str if not is_delegation_error else None, # Result from specialist or None if delegation failed
                    error=result_str if is_delegation_error else None, # Error message from delegation attempt
                    is_error=is_delegation_error
                )
            except TypeError as e:
                 # Handle case where LLM provided wrong args to delegate_task structure
                 logging.exception(f"TypeError during internal delegation execution: {e}. Args: {args}")
                 return ToolResult(id=call_id, name=tool_name, error=f"Internal delegation error: Invalid arguments provided. {e}", is_error=True)
            except Exception as e:
                logging.exception(f"Unexpected error during internal delegation execution: {e}")
                return ToolResult(id=call_id, name=tool_name, error=f"Unexpected delegation error: {e}", is_error=True)
        else:
             # Controller should ONLY receive delegate_task calls based on its prompt and allowed tools.
             err_msg = f"Controller received unexpected tool call '{tool_name}'. Only '{self.SPECIALIST_TOOL_NAME}' is supported."
             logging.error(err_msg)
             return ToolResult(id=call_id, name=tool_name, error=err_msg, is_error=True)


# Need translate_schema_for_provider from config.schemas
from agent_system.config.schemas import translate_schema_for_provider
