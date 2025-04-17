import logging
import json
from typing import List, Dict, Any, Optional, Tuple

# Attempt to import Gemini types ONLY for Gemini-specific schema generation
try:
    import google.generativeai as genai
    import google.ai.generativelanguage as glm
    GEMINI_LIBS_AVAILABLE = True
except ImportError:
    # This is informational only, doesn't prevent other translations
    logging.info("google.generativeai library not found. Gemini-specific schema generation will not function.")
    GEMINI_LIBS_AVAILABLE = False
    genai = None
    glm = None # Ensure glm is None if import fails

# Type alias for the generic schema structure expected from tool registration
# Example:
# {
#     "description": "Tool description",
#     "parameters": {
#         "param1": {"type": "string", "description": "Param 1 desc", "required": True},
#         "param2": {"type": "integer", "description": "Param 2 desc", "required": False, "default": 10},
#         "param3": {"type": "array", "items": {"type": "string"}, "description": "List of strings"},
#     }
# }
GenericToolSchema = Dict[str, Any]

# --- Schema Parameter Translation Helper ---

def _translate_params_to_json_schema(
    parameters: Optional[Dict[str, Dict[str, Any]]]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Converts a dictionary of parameter definitions (from tool registration)
    into JSON Schema properties dictionary and a list of required parameter names.

    Operates purely on dictionary inputs, NO dependency on external schema libraries (like glm).
    """
    if not parameters:
        return {}, []

    properties = {}
    required_list = []
    for name, details in parameters.items():
        # Basic validation of details structure
        if not isinstance(details, dict):
             logging.warning(f"Parameter '{name}' has invalid details format (expected dict, got {type(details)}). Skipping.")
             continue

        prop_schema: Dict[str, Any] = {"description": details.get("description", "")}
        param_type = details.get("type", "string") # Default to string if type missing

        # Basic type validation (can be expanded)
        valid_types = ["string", "number", "integer", "boolean", "array", "object"]
        if param_type not in valid_types:
             logging.warning(f"Parameter '{name}' has unsupported type '{param_type}'. Defaulting to 'string'.")
             param_type = "string"
        prop_schema["type"] = param_type

        # Handle array items type definition
        if param_type == "array":
            items_details = details.get("items")
            if isinstance(items_details, dict) and "type" in items_details:
                 # TODO: Add validation for item type if needed
                 prop_schema["items"] = {"type": items_details.get("type", "string")}
            else:
                 # Default to items of type string if not specified correctly
                 prop_schema["items"] = {"type": "string"}
                 if items_details is not None:
                      logging.warning(f"Parameter '{name}' is type 'array' but 'items' definition is invalid or missing 'type'. Defaulting items to type 'string'.")

        # Handle object properties (basic support for additionalProperties)
        elif param_type == "object":
             if "additionalProperties" in details and isinstance(details["additionalProperties"], dict):
                 prop_schema["additionalProperties"] = details["additionalProperties"]
             # Note: Does not recursively process nested 'properties' within objects for simplicity here.
             # LLMs accepting JSON schema usually handle basic 'object' type.

        # Include default value if provided
        if "default" in details:
             # Basic type check for default could be added here if needed
             prop_schema["default"] = details["default"]

        properties[name] = prop_schema
        if details.get("required", False):
            required_list.append(name)

    return properties, required_list

# --- Provider-Specific Translation Functions ---

def translate_to_openai_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Dict[str, Any]]:
    """Generates OpenAI-compatible tool schema list. No glm dependency."""
    openai_tools = []
    for name in tool_names:
        if name not in registered_tools:
            logging.warning(f"Schema requested for tool '{name}' which is not registered or lacks schema (OpenAI). Skipping.")
            continue
        schema = registered_tools[name]
        if not isinstance(schema, dict):
             logging.warning(f"Tool '{name}' has invalid schema format (expected dict). Skipping (OpenAI).")
             continue

        properties, required_list = _translate_params_to_json_schema(schema.get("parameters"))

        openai_tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": schema.get("description", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_list
                }
            }
        })
    return openai_tools

def translate_to_anthropic_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Dict[str, Any]]:
    """Generates Anthropic-compatible tool schema list. No glm dependency."""
    anthropic_tools = []
    for name in tool_names:
        if name not in registered_tools:
            logging.warning(f"Schema requested for tool '{name}' which is not registered or lacks schema (Anthropic). Skipping.")
            continue
        schema = registered_tools[name]
        if not isinstance(schema, dict):
             logging.warning(f"Tool '{name}' has invalid schema format (expected dict). Skipping (Anthropic).")
             continue

        properties, _ = _translate_params_to_json_schema(schema.get("parameters")) # Anthropic doesn't use top-level required list in input_schema

        anthropic_tools.append({
            "name": name,
            "description": schema.get("description", ""),
            "input_schema": {
                "type": "object",
                "properties": properties
                # Required properties are implied by the schema definition for Anthropic
            }
        })
    return anthropic_tools

def translate_to_gemini_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Any]:
    """Generates Gemini-compatible tool schema list (FunctionDeclaration). Requires google.generativeai."""
    if not GEMINI_LIBS_AVAILABLE:
        logging.error("Cannot generate Gemini schema: google.generativeai library not available.")
        return []

    gemini_tools = []
    # Map internal simple types to Gemini Types
    type_mapping = {
        "string": glm.Type.STRING,
        "number": glm.Type.NUMBER,
        "integer": glm.Type.INTEGER,
        "boolean": glm.Type.BOOLEAN,
        "array": glm.Type.ARRAY,
        "object": glm.Type.OBJECT,
    }

    for name in tool_names:
        if name not in registered_tools:
            logging.warning(f"Schema requested for tool '{name}' which is not registered or lacks schema (Gemini). Skipping.")
            continue
        schema = registered_tools[name]
        if not isinstance(schema, dict):
             logging.warning(f"Tool '{name}' has invalid schema format (expected dict). Skipping (Gemini).")
             continue

        parameters = schema.get("parameters")
        gemini_properties = {}
        required_list = []

        if parameters and isinstance(parameters, dict):
            for param_name, details in parameters.items():
                 if not isinstance(details, dict):
                      logging.warning(f"Parameter '{param_name}' for tool '{name}' has invalid details format. Skipping param (Gemini).")
                      continue

                 param_type_str = details.get("type", "string")
                 gemini_type = type_mapping.get(param_type_str, glm.Type.STRING)
                 prop_schema = glm.Schema(
                     type=gemini_type,
                     description=details.get("description", "")
                 )
                 # Handle array items
                 if gemini_type == glm.Type.ARRAY:
                     item_details = details.get("items", {"type": "string"})
                     item_type_str = item_details.get("type", "string") if isinstance(item_details, dict) else "string"
                     item_type = type_mapping.get(item_type_str, glm.Type.STRING)
                     prop_schema.items = glm.Schema(type=item_type)

                 gemini_properties[param_name] = prop_schema
                 if details.get("required", False):
                     required_list.append(param_name)

        # Create FunctionDeclaration
        func_decl = genai.FunctionDeclaration(
            name=name,
            description=schema.get("description", ""),
            parameters=glm.Schema(
                type=glm.Type.OBJECT,
                properties=gemini_properties,
                required=required_list
            ) if gemini_properties else None # Only add parameters schema if properties exist
        )
        gemini_tools.append(func_decl)

    return gemini_tools

def translate_to_ollama_schema_string(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> str:
    """Generates a JSON string representation of the schema for Ollama prompt injection. No glm dependency."""
    ollama_tools = []
    for name in tool_names:
        if name not in registered_tools:
            logging.warning(f"Schema requested for tool '{name}' which is not registered or lacks schema (Ollama). Skipping.")
            continue
        schema = registered_tools[name]
        if not isinstance(schema, dict):
             logging.warning(f"Tool '{name}' has invalid schema format (expected dict). Skipping (Ollama).")
             continue

        properties, required_list = _translate_params_to_json_schema(schema.get("parameters"))

        # Use a structure similar to OpenAI for the prompt injection
        ollama_tools.append({
            "name": name,
            "description": schema.get("description", ""),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_list
            }
        })
    # Return as a JSON string
    return json.dumps(ollama_tools, indent=2) if ollama_tools else "[]"

# --- Generic Schema Translation Dispatcher ---
def translate_schema_for_provider(provider_name: str, registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> Optional[Any]:
    """
    Translates schemas for the specified tools into the format required by the provider.

    Args:
        provider_name: The name of the provider (e.g., 'openai', 'gemini').
        registered_tools: The dictionary of all registered tools and their schemas.
        tool_names: A list of tool names for which to get the translated schema.

    Returns:
        The schema formatted for the provider (List[dict], List[FunctionDeclaration], or str),
        or the provider's expected "empty" format if no tools or an error occurs.
    """
    provider_name = provider_name.lower()

    # Define expected empty formats
    empty_formats = {
        "openai": [],
        "anthropic": [],
        "gemini": [],
        "ollama": "[]"
    }
    empty_format = empty_formats.get(provider_name, None)

    if not tool_names:
        return empty_format

    # Filter the registered_tools dict to only include tools requested AND available AND valid
    relevant_schemas = {}
    for name in tool_names:
        if name in registered_tools and isinstance(registered_tools[name], dict):
             relevant_schemas[name] = registered_tools[name]
        else:
            # Log only if the tool was specifically requested but missing/invalid
            logging.warning(f"Tool '{name}' requested for {provider_name} schema translation, but it's not registered or has an invalid schema format.")

    if not relevant_schemas:
        logging.warning(f"No valid schemas found for requested tools: {tool_names} for provider {provider_name}")
        return empty_format

    # Perform translation using the relevant schemas only
    try:
        if provider_name == "openai":
            return translate_to_openai_schema(relevant_schemas, list(relevant_schemas.keys()))
        elif provider_name == "anthropic":
            return translate_to_anthropic_schema(relevant_schemas, list(relevant_schemas.keys()))
        elif provider_name == "gemini":
            return translate_to_gemini_schema(relevant_schemas, list(relevant_schemas.keys()))
        elif provider_name == "ollama":
            return translate_to_ollama_schema_string(relevant_schemas, list(relevant_schemas.keys()))
        else:
            logging.error(f"Schema translation not implemented for unknown provider: {provider_name}")
            return None # Or raise error? None seems safer for now.
    except Exception as e:
         logging.exception(f"Error during schema translation for provider '{provider_name}': {e}")
         return empty_format # Return empty format on translation error
