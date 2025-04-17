import functools
import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, Union # <-- Added Union

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
        # Basic validation of provided parameters structure
        if isinstance(parameters, dict):
             tool_schema["parameters"] = parameters
        else:
             logging.error(f"Explicit 'parameters' for tool '{tool_name}' must be a dictionary. Ignoring provided value: {parameters}")
             tool_schema["parameters"] = {} # Set empty params if invalid structure provided
    else:
        # Infer basic parameters from signature
        try:
             sig = inspect.signature(func)
             inferred_params = {}
             type_mapping = {
                 str: "string", int: "integer", float: "number", bool: "boolean",
                 list: "array", List: "array", dict: "object", Dict: "object",
                 # Basic handling for Optional[T] -> T for type mapping
                 Optional[str]: "string", Optional[int]: "integer", Optional[float]: "number",
                 Optional[bool]: "boolean", Optional[list]: "array", Optional[List]: "array",
                 Optional[dict]: "object", Optional[Dict]: "object",
                 Any: "any", # Map Any to a generic 'any' or 'string'? Let's use 'any' for now.
             }

             for param_name, param in sig.parameters.items():
                 param_info: Dict[str, Any] = {}
                 param_type_hint = param.annotation

                 # Determine parameter type string
                 param_type_str = "string" # Default
                 if param_type_hint is not inspect.Parameter.empty:
                     origin_type = getattr(param_type_hint, "__origin__", None)
                     if origin_type is Union: # Handles Optional[T] which is Union[T, None]
                         args = getattr(param_type_hint, "__args__", ())
                         non_none_args = [a for a in args if a is not type(None)]
                         if len(non_none_args) == 1: # Likely Optional[T] or simple Union[T, None]
                              actual_type = non_none_args[0]
                              actual_origin = getattr(actual_type, "__origin__", None)
                              param_type_str = type_mapping.get(actual_origin or actual_type, "string")
                         else: # More complex Union, default to string or Any? Let's use 'any'
                              param_type_str = "any"
                     elif origin_type: # Other generic types like List, Dict
                         param_type_str = type_mapping.get(origin_type, "string")
                     else: # Non-generic types
                         param_type_str = type_mapping.get(param_type_hint, "string")

                 param_info["type"] = param_type_str

                 # Determine if required (no default value)
                 is_required = (param.default == inspect.Parameter.empty)
                 param_info["required"] = is_required
                 if not is_required:
                     # JSON serialize default value if possible, otherwise use string repr
                     try: json_default = json.dumps(param.default); param_info["default"] = param.default
                     except TypeError: param_info["default"] = repr(param.default)

                 # Add basic description
                 param_info["description"] = f"{param_name} parameter" # Can be improved by parsing docstring

                 # Handle array items type if possible (basic)
                 if param_type_str == "array" and hasattr(param_type_hint, "__args__"):
                     item_args = getattr(param_type_hint, "__args__", (Any,))
                     if item_args:
                          item_type_hint = item_args[0] # Use the first type argument
                          item_origin = getattr(item_type_hint, "__origin__", None)
                          item_type_str = type_mapping.get(item_origin or item_type_hint, "string")
                          param_info["items"] = {"type": item_type_str}
                     else: # Handle plain list without specified type
                          param_info["items"] = {"type": "any"} # Or string? 'any' seems safer.

                 inferred_params[param_name] = param_info

             if inferred_params:
                 tool_schema["parameters"] = inferred_params
        except Exception as e:
             logging.exception(f"Failed to infer parameters for tool '{tool_name}' from signature: {e}. Parameters will be empty.")
             tool_schema["parameters"] = {}


    # Store in registry
    TOOL_REGISTRY[tool_name] = {
        "function": func,
        "schema": tool_schema
    }
    logging.debug(f"Registered tool: '{tool_name}' with schema: {tool_schema}")

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # The decorator itself doesn't modify the function's execution here
        return func(*args, **kwargs)
    return wrapper


# --- Accessor Functions ---
# (Accessor functions remain the same)
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
# (Discovery logic remains the same)
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

        if module_name in ("__init__", "tool_utils", "README"): # Skip README too
             skipped_modules += 1
             continue

        full_module_path = f"{package_name}.{module_name}"
        try:
            # Use importlib.invalidate_caches() maybe? Not usually needed unless bytecode is stale.
            importlib.import_module(full_module_path)
            logging.debug(f"Successfully imported tool module: {full_module_path}")
            found_modules += 1
        except ImportError as e:
            # Log clearly but don't stop discovery for other modules
            logging.error(f"Failed to import tool module '{full_module_path}': {e}", exc_info=False) # Less verbose traceback usually needed here
        except Exception as e:
             # Catch other potential errors during module import (e.g., syntax errors in the tool file)
             logging.exception(f"An unexpected error occurred while importing tool module '{full_module_path}': {e}")

    logging.info(f"Tool discovery complete. Imported {found_modules} modules. Skipped {skipped_modules}. Total registered tools: {len(TOOL_REGISTRY)}")

# Need json for default value serialization during inference
import json

# Automatically discover tools when this package is imported for the first time.
discover_tools()
