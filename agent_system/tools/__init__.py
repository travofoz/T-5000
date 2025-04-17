import functools
import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

# --- Tool Registry ---
# Stores registered tool functions and their associated metadata (schema)
# Format: { "tool_name": {"function": callable, "schema": GenericToolSchema} }
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}

# Type alias for the schema structure used internally
GenericToolSchema = Dict[str, Any]

# --- Tool Registration Decorator ---

def register_tool(func: Optional[Callable] = None, *, name: Optional[str] = None, description: Optional[str] = None, parameters: Optional[Dict[str, Dict[str, Any]]] = None):
    """
    Decorator to register a function as an available tool.

    Automatically extracts description and basic parameters from the function's
    docstring and signature if not explicitly provided.

    Args:
        func: The function being decorated (passed implicitly).
        name: Explicit name for the tool. If None, uses the function's name.
        description: Explicit description. If None, uses the first line of the docstring.
        parameters: Explicit dictionary defining parameters following a simplified JSON schema
                    structure (e.g., {"param_name": {"type": "string", "description": "...", "required": True}}).
                    If None, attempts to infer from type hints and defaults.
    """
    if func is None:
        # Called as @register_tool(...)
        return functools.partial(register_tool, name=name, description=description, parameters=parameters)

    tool_name = name or func.__name__
    if tool_name in TOOL_REGISTRY:
        logging.warning(f"Tool '{tool_name}' is being re-registered. Overwriting previous definition.")

    # --- Extract Schema Information ---
    tool_schema: GenericToolSchema = {}

    # 1. Description
    if description:
        tool_schema["description"] = description
    else:
        docstring = inspect.getdoc(func)
        if docstring:
            tool_schema["description"] = docstring.split('\n')[0] # Use first line
        else:
            tool_schema["description"] = f"Executes the {tool_name} operation." # Fallback

    # 2. Parameters
    if parameters is not None:
        tool_schema["parameters"] = parameters
    else:
        # Infer basic parameters from signature
        sig = inspect.signature(func)
        inferred_params = {}
        type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            List: "array", # Handle typing.List
            dict: "object",
            Dict: "object", # Handle typing.Dict
            Optional[str]: "string", # Handle Optionals simply for now
            Optional[int]: "integer",
            Optional[float]: "number",
            Optional[bool]: "boolean",
            Optional[list]: "array",
            Optional[List]: "array",
            Optional[dict]: "object",
            Optional[Dict]: "object",
        }

        for param_name, param in sig.parameters.items():
            param_info: Dict[str, Any] = {}
            param_type_hint = param.annotation

            # Determine parameter type string
            param_type_str = "string" # Default
            if param_type_hint is not inspect.Parameter.empty:
                 # Handle Optional types by getting the inner type if possible
                 origin_type = getattr(param_type_hint, "__origin__", None)
                 if origin_type is Union:
                      args = getattr(param_type_hint, "__args__", ())
                      # Check if it's Optional[T] (Union[T, NoneType])
                      is_optional = any(a is type(None) for a in args)
                      if is_optional and len(args) == 2:
                           actual_type = next(a for a in args if a is not type(None))
                           param_type_str = type_mapping.get(actual_type, "string")
                      else: # Other Unions, default to string for simplicity
                           param_type_str = "string"
                 elif origin_type: # Other generic types like List, Dict
                     param_type_str = type_mapping.get(origin_type, "string")
                 else: # Non-generic types
                     param_type_str = type_mapping.get(param_type_hint, "string")


            param_info["type"] = param_type_str

            # Determine if required (no default value)
            is_required = (param.default == inspect.Parameter.empty)
            param_info["required"] = is_required
            if not is_required:
                param_info["default"] = param.default

            # Add basic description (can be enhanced by parsing docstring further)
            param_info["description"] = f"{param_name} parameter"

            # Handle specific types like list items if possible (basic)
            if param_type_str == "array" and hasattr(param_type_hint, "__args__"):
                 item_type_hint = getattr(param_type_hint, "__args__", (str,))[0] # Default item type to str
                 item_type_str = type_mapping.get(item_type_hint, "string")
                 param_info["items"] = {"type": item_type_str}

            inferred_params[param_name] = param_info

        if inferred_params:
             tool_schema["parameters"] = inferred_params

    # Store in registry
    TOOL_REGISTRY[tool_name] = {
        "function": func,
        "schema": tool_schema
    }
    logging.debug(f"Registered tool: '{tool_name}'")

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # The decorator itself doesn't modify the function's execution here
        return func(*args, **kwargs)
    return wrapper


# --- Accessor Functions ---

def get_tool_function(name: str) -> Optional[Callable]:
    """Retrieves the callable function for a registered tool."""
    return TOOL_REGISTRY.get(name, {}).get("function")

def get_tool_schema(name: str) -> Optional[GenericToolSchema]:
    """Retrieves the schema dictionary for a registered tool."""
    return TOOL_REGISTRY.get(name, {}).get("schema")

def get_all_tool_schemas() -> Dict[str, GenericToolSchema]:
    """Retrieves schemas for all registered tools."""
    return {name: data["schema"] for name, data in TOOL_REGISTRY.items() if "schema" in data}

def get_all_tools() -> Dict[str, Dict[str, Any]]:
    """Retrieves the complete tool registry."""
    return TOOL_REGISTRY.copy()


# --- Dynamic Tool Discovery ---

def discover_tools():
    """
    Automatically imports all modules in the 'tools' directory
    (except __init__.py and tool_utils.py) to trigger @register_tool decorators.
    """
    tools_package_path = Path(__file__).parent
    package_name = __name__ # Should be 'agent_system.tools'

    logging.info(f"Discovering tools in package: '{package_name}' at path: {tools_package_path}")
    found_modules = 0
    skipped_modules = 0

    for _, module_name, is_pkg in pkgutil.iter_modules([str(tools_package_path)]):
        if is_pkg: # Don't try to import sub-packages automatically for now
            skipped_modules += 1
            continue

        # Skip __init__ and utility modules
        if module_name in ("__init__", "tool_utils"):
             skipped_modules += 1
             continue

        full_module_path = f"{package_name}.{module_name}"
        try:
            importlib.import_module(full_module_path)
            logging.debug(f"Successfully imported tool module: {full_module_path}")
            found_modules += 1
        except ImportError as e:
            logging.error(f"Failed to import tool module '{full_module_path}': {e}", exc_info=True)
        except Exception as e:
             logging.exception(f"An unexpected error occurred while importing tool module '{full_module_path}': {e}")

    logging.info(f"Tool discovery complete. Found and imported {found_modules} tool modules. Skipped {skipped_modules}. Total registered tools: {len(TOOL_REGISTRY)}")

# Automatically discover tools when this package is imported for the first time.
# This ensures that tools defined in separate files are registered upon import.
discover_tools()
