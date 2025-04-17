import asyncio
import logging
import uuid
from typing import Dict, Any, Optional

# Import necessary agent/provider types
from .agent import BaseAgent
from .controller import ControllerAgent
# Assuming agent instantiation logic might be needed here or passed in
# from cli.main_interactive import instantiate_agents # Example import, needs better structure


class Orchestrator:
    """
    Manages the execution of tasks by agents.

    This is a basic structure for managing potentially concurrent agent runs.
    Future enhancements could include complex inter-agent communication,
    dynamic agent loading, task planning, and state management across multiple agents.
    """

    def __init__(self):
        # Stores active agents, potentially mapped by task ID or session ID.
        # For now, let's assume it might hold references if needed, but the
        # primary interaction point will likely remain the Controller for delegation.
        self.active_agents: Dict[str, BaseAgent] = {} # Example: map session_id to Controller
        logging.info("Orchestrator initialized.")
        # In a more complex scenario, the orchestrator might initialize providers/agents itself.

    async def run_agent_task(self, agent: BaseAgent, prompt: str, load_state: bool = True, save_state: bool = True) -> str:
        """
        Runs a specific agent instance with a given prompt.

        Args:
            agent: The initialized BaseAgent instance to run.
            prompt: The prompt to provide to the agent.
            load_state: Whether the agent should load its prior state.
            save_state: Whether the agent should save its state after completion.

        Returns:
            The final string response from the agent.
        """
        logging.info(f"Orchestrator dispatching task to agent '{agent.name}' (Session: {agent.session_id or 'None'})")
        try:
            # Directly call the agent's run method
            result = await agent.run(
                user_prompt=prompt,
                load_state=load_state,
                save_state=save_state
            )
            logging.info(f"Orchestrator received result from agent '{agent.name}' (Session: {agent.session_id or 'None'})")
            return result
        except Exception as e:
            logging.exception(f"Error during orchestrated run of agent '{agent.name}': {e}")
            return f"[Orchestrator Error: Failed to run agent '{agent.name}': {e}]"

    async def run_concurrent_tasks(self, tasks: List[Tuple[BaseAgent, str]], load_state: bool = True, save_state: bool = True) -> List[str]:
        """
        Runs multiple agent tasks concurrently.

        Args:
            tasks: A list of tuples, where each tuple contains (agent_instance, prompt_string).
            load_state: Whether agents should load state before running.
            save_state: Whether agents should save state after running.

        Returns:
            A list of result strings, one for each task, in the order they were provided.
        """
        logging.info(f"Orchestrator running {len(tasks)} tasks concurrently.")
        aws = [
            self.run_agent_task(agent, prompt, load_state, save_state)
            for agent, prompt in tasks
        ]
        results = await asyncio.gather(*aws, return_exceptions=True)

        # Process results, logging any exceptions gathered
        final_results = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                agent_name = tasks[i][0].name
                logging.error(f"Concurrent task for agent '{agent_name}' failed: {res}")
                final_results.append(f"[Orchestrator Error: Task for '{agent_name}' failed: {res}]")
            else:
                final_results.append(res)

        logging.info(f"Orchestrator completed {len(tasks)} concurrent tasks.")
        return final_results

    # Add methods for agent management, inter-agent communication etc. later as needed.
    # def register_agent(self, agent: BaseAgent, agent_id: Optional[str] = None): ...
    # def get_agent(self, agent_id: str) -> Optional[BaseAgent]: ...
    # async def route_message(self, sender_id: str, recipient_id: str, message: Any): ...
