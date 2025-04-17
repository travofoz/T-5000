# Agent System Tools

This directory contains the implementation of various tools that agents within the system can utilize to interact with the environment, execute commands, process information, and perform actions.

## Tool Structure

Tools are organized into Python modules based on their general category (e.g., `filesystem.py`, `network_diag.py`, `process.py`). Each file contains one or more functions, where each function represents a single executable tool.

## Adding a New Tool

Adding a new tool involves the following steps:

1.  **Choose or Create a Module:** Decide which existing category file (e.g., `security.py`) best fits your new tool. If none fit, create a new `.py` file within this directory (e.g., `my_new_tools.py`).
2.  **Define the Tool Function:**
    *   Create an `async def` function for your tool. Asynchronous execution is preferred, especially for tools involving I/O (network, filesystem, subprocesses). Use `asyncio.to_thread` for wrapping synchronous blocking calls if necessary.
    *   Use clear Python type hints for all function arguments and the return type. The return type **must** be `str`, as the agent system expects textual results from tools.
    *   Write a concise and informative docstring for the function. The **first line** of the docstring is automatically used as the tool's description for the LLM unless overridden in the decorator. Subsequent lines can provide more detail for developers.
    *   Implement the tool's logic. For tools running external commands, use the helper functions from `tool_utils.py` (e.g., `run_tool_command_async`) for consistent execution, error handling, and result formatting.
3.  **Register the Tool:**
    *   Import the decorator: `from . import register_tool`
    *   Apply the `@register_tool` decorator directly above your `async def` function definition.
    *   **Basic Usage:** `@register_tool`
        ```python
        from . import register_tool
        import asyncio

        @register_tool
        async def my_simple_tool(arg1: str, count: int = 1) -> str:
            """This is the tool description used by the LLM."""
            # ... implementation ...
            await asyncio.sleep(0.1) # Example async operation
            return f"Tool finished with arg1={arg1}, count={count}"
        ```
        In this basic usage, the tool name (`my_simple_tool`), description (docstring first line), and parameters (name, type inferred from signature, requirement based on default value) are automatically detected.
    *   **Advanced Usage (Overriding Defaults):** You can provide arguments to the decorator to customize registration:
        *   `name="custom_tool_name"`: Use a different name for the tool than the function name.
        *   `description="A more detailed explicit description."`: Override the docstring description.
        *   `parameters={...}`: Provide an explicit dictionary defining the parameters. This is necessary if type hints are complex (e.g., nested objects, specific array item types beyond simple ones) or if you need more control over descriptions/requirements than basic inference provides. The structure should follow the `GenericToolSchema` pattern used in `config/schemas.py`.
        ```python
        from . import register_tool

        explicit_params = {
            "user_id": {"type": "integer", "description": "The unique ID of the user.", "required": True},
            "options": {"type": "object", "description": "Dictionary of optional settings.", "required": False}
        }

        @register_tool(name="process_user", description="Processes user data with options.", parameters=explicit_params)
        async def process_user_data(user_id: int, options: dict = None) -> str:
            # ... implementation ...
            return "User processed."
        ```
4.  **High-Risk Confirmation:** If your tool performs potentially dangerous actions (modifying files outside a sandbox, running sudo, interacting directly with hardware, executing arbitrary code/commands), consider whether it should require user confirmation. This is **not** handled within the tool function itself. Instead:
    *   The tool's name should be added to the `HIGH_RISK_TOOLS` list in the `.env` file (and documented in `.env.example`).
    *   The `BaseAgent._execute_tool` method automatically checks this list before calling your tool function and uses `tool_utils.ask_confirmation_async` to prompt the user if needed. Your tool implementation generally assumes confirmation has already been granted if it gets called.
5.  **Automatic Discovery:** The `tools/__init__.py` file automatically imports all `.py` modules within this directory when the application starts. This process triggers the `@register_tool` decorators, adding your new tool to the central `TOOL_REGISTRY`. No manual registration steps are needed beyond applying the decorator.

By following these steps, your new tool will be available for use by agents configured with the appropriate permissions (i.e., having the tool name listed in their `allowed_tools`).
