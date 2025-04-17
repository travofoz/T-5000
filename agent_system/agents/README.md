# Agent System Agents

This directory contains the definitions for specialized agents within the multi-agent system. Each agent focuses on a specific domain or set of capabilities.

## Agent Structure

*   **Base Class:** All agents inherit from `agent_system.core.agent.BaseAgent`. This base class provides core functionality:
    *   Interaction loop with LLM providers.
    *   Tool execution logic (including concurrent execution and high-risk confirmation).
    *   Conversation history management.
    *   State persistence (loading/saving history).
    *   Basic token counting integration with providers.
    *   Management of allowed tools and provider-specific schemas.
*   **Specialization:** Each agent class (e.g., `CodingAgent`, `SysAdminAgent`) defines its specific role and capabilities primarily through:
    *   **System Prompt:** A detailed prompt passed during initialization that instructs the LLM on the agent's persona, goals, capabilities, limitations, and safety instructions. This is the primary way to guide the agent's behavior.
    *   **Allowed Tools:** A list of tool names (corresponding to functions registered in `agent_system/tools/`) that the specific agent instance is permitted to use. This restricts the agent's actions to its intended domain.

## Adding a New Agent

1.  **Define Purpose:** Clearly define the specific domain, responsibilities, and capabilities of the new agent. What tasks should it handle? What tasks should it delegate?
2.  **Create Module:** Create a new Python file in this directory (e.g., `my_new_agent.py`).
3.  **Define Class:** Create a class that inherits from `BaseAgent`:
    ```python
    import logging
    from typing import List, Optional
    from agent_system.core.agent import BaseAgent
    from agent_system.llm_providers import LLMProvider # Type hint for provider

    class MyNewAgent(BaseAgent):
        # Optional: Define default tools specific to this agent class
        DEFAULT_TOOLS = [
            "read_file",
            "list_files",
            "my_custom_tool_1", # Assuming this is registered in tools/
            # ... other relevant tools ...
        ]

        def __init__(self, llm_provider: LLMProvider, allowed_tools: Optional[List[str]] = None, session_id: Optional[str] = None):
            # Determine the actual tools to use (override defaults if provided)
            tools_to_use = allowed_tools if allowed_tools is not None else self.DEFAULT_TOOLS

            # --- Define the System Prompt ---
            system_prompt = """You are MyNewAgent, specializing in [Specific Domain].
Your capabilities include:
- [Capability 1 using specific tools like `my_custom_tool_1`]
- [Capability 2 using other tools]

You focus ONLY on [Specific Domain] tasks. **You MUST delegate tasks** involving [Domains handled by other agents, e.g., coding, system administration, etc.] to the appropriate specialist agent ([List other agent names]). Use the `delegate_task` function provided by the Controller for delegation.

[Optional: Add any specific safety warnings or instructions relevant to this agent's tools or domain.]
"""
            # --- Call BaseAgent's __init__ ---
            super().__init__(
                name=self.__class__.__name__, # Use class name as agent name by default
                llm_provider=llm_provider,
                system_prompt=system_prompt,
                allowed_tools=tools_to_use,
                session_id=session_id # Pass session_id for state persistence
            )
            logging.info(f"{self.name} initialized with {len(self.allowed_tools)} tools.")

        # Optional: Override BaseAgent methods if specialized behavior is needed
        # async def run(self, ...) -> str: ... # If different run logic needed
        # async def _execute_tool(self, ...) -> ToolResult: ... # If custom tool handling needed
    ```
4.  **Update Configuration (`config/settings.py`):** Add a default LLM configuration entry for your new agent in the `DEFAULT_AGENT_LLM_CONFIG` dictionary. This allows the system to know which LLM provider and model to use for this agent by default.
    ```python
    DEFAULT_AGENT_LLM_CONFIG = {
        # ... existing agents ...
        "MyNewAgent": {"provider": "gemini", "model": "gemini-1.5-pro-latest"}, # Or desired provider/model
    }
    ```
5.  **Update Instantiation Logic:** Modify the places where agents are instantiated (currently duplicated in CLI/Web/Scripts, but will be centralized in `app_context.py` in V2) to include your new agent class. Add it to the `agent_classes` map.
6.  **Update Controller Prompt:** Modify the `ControllerAgent` system prompt (in `core/controller.py`) to list your new agent as an available specialist for delegation.
7.  **Testing:** Add tests for your new agent, potentially mocking its interactions with the LLM provider and tools to verify its logic or specific overrides (if any).

## Delegation

Agents are designed to be specialized. They should rely on the `ControllerAgent` (via the `delegate_task` tool) to hand off tasks outside their defined scope. The system prompts explicitly instruct agents to do this. Ensure system prompts clearly define the agent's boundaries and list the other agents it should delegate to.
