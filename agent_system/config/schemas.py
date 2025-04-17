import logging
import json
from typing import List, Dict, Any, Optional, Tuple, Union

# Attempt to import Gemini types
try:
    import google.generativeai as genai
    import google.ai.generativelanguage as glm
    # Correctly import FunctionDeclaration from types namespace
    from google.generativeai.types import FunctionDeclaration # <-- Corrected import
    GEMINI_LIBS_AVAILABLE = True
except ImportError:
    logging.info("google.generativeai library not found. Gemini-specific schema generation will be limited.")
    GEMINI_LIBS_AVAILABLE = False
    genai = None
    glm = None
    FunctionDeclaration = Any # Fallback type hint

# Type alias for the generic schema structure expected from tool registration
GenericToolSchema = Dict[str, Any]

# --- Schema Parameter Translation Helper ---

def _translate_params_to_json_schema(
    parameters: Optional[Dict[str, Dict[str, Any]]]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Converts a dictionary of parameter definitions (from tool registration)
    into JSON Schema properties dictionary and a list of required parameter names.
    """
    # (Implementation remains the same as corrected version)
    if not parameters: return {}, []
    properties = {}; required_list = []
    for name, details in parameters.items():
        if not isinstance(details, dict): logging.warning(f"Param '{name}' has invalid details format. Skipping."); continue
        prop_schema: Dict[str, Any] = {"description": details.get("description", "")}
        param_type = details.get("type", "string")
        valid_types = ["string", "number", "integer", "boolean", "array", "object", "any"]
        if param_type not in valid_types: logging.warning(f"Param '{name}' has unsupported type '{param_type}'. Defaulting to 'string'."); param_type = "string"
        prop_schema["type"] = param_type
        if param_type == "array":
            items_details = details.get("items"); item_type = "string" # Default item type
            if isinstance(items_details, dict) and "type" in items_details: item_type = items_details.get("type", "string")
            elif items_details is not None: logging.warning(f"Param '{name}' array 'items' invalid. Defaulting items to type 'string'.")
            prop_schema["items"] = {"type": item_type}
        elif param_type == "object":
             if "additionalProperties" in details and isinstance(details["additionalProperties"], dict): prop_schema["additionalProperties"] = details["additionalProperties"]
        if "default" in details: prop_schema["default"] = details["default"]
        properties[name] = prop_schema
        if details.get("required", False): required_list.append(name)
    return properties, required_list

# --- Provider-Specific Translation Functions ---

def translate_to_openai_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Dict[str, Any]]:
    """Generates OpenAI-compatible tool schema list."""
    # (Implementation remains the same as corrected version)
    openai_tools = []
    for name in tool_names:
        if name not in registered_tools: logging.warning(f"Schema requested for unknown/invalid tool '{name}' (OpenAI). Skipping."); continue
        schema = registered_tools[name]
        if not isinstance(schema, dict): logging.warning(f"Tool '{name}' schema invalid (OpenAI). Skipping."); continue
        properties, required_list = _translate_params_to_json_schema(schema.get("parameters"))
        openai_tools.append({
            "type": "function", "function": {
                "name": name, "description": schema.get("description", ""),
                "parameters": {"type": "object", "properties": properties, "required": required_list}
            }})
    return openai_tools

def translate_to_anthropic_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Dict[str, Any]]:
    """Generates Anthropic-compatible tool schema list."""
    # (Implementation remains the same as corrected version)
    anthropic_tools = []
    for name in tool_names:
        if name not in registered_tools: logging.warning(f"Schema requested for unknown/invalid tool '{name}' (Anthropic). Skipping."); continue
        schema = registered_tools[name]
        if not isinstance(schema, dict): logging.warning(f"Tool '{name}' schema invalid (Anthropic). Skipping."); continue
        properties, _ = _translate_params_to_json_schema(schema.get("parameters"))
        anthropic_tools.append({
            "name": name, "description": schema.get("description", ""),
            "input_schema": {"type": "object", "properties": properties }
            })
    return anthropic_tools

def translate_to_gemini_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Any]:
    """Generates Gemini-compatible tool schema list (FunctionDeclaration)."""
    # (Implementation remains the same as corrected version - uses imported FunctionDeclaration)
    if not GEMINI_LIBS_AVAILABLE: logging.error("Cannot generate Gemini schema: google.generativeai library not available."); return []
    gemini_tools = []
    type_mapping = {"string": glm.Type.STRING, "number": glm.Type.NUMBER, "integer": glm.Type.INTEGER, "boolean": glm.Type.BOOLEAN, "array": glm.Type.ARRAY, "object": glm.Type.OBJECT, "any": glm.Type.STRING}
    for name in tool_names:
        if name not in registered_tools: continue
        schema = registered_tools[name];
        if not isinstance(schema, dict): continue
        parameters = schema.get("parameters"); gemini_properties = {}; required_list = []
        if parameters and isinstance(parameters, dict):
            for param_name, details in parameters.items():
                 if not isinstance(details, dict): continue
                 param_type_str = details.get("type", "string"); gemini_type = type_mapping.get(param_type_str, glm.Type.STRING)
                 prop_schema = glm.Schema(type=gemini_type, description=details.get("description", ""))
                 if gemini_type == glm.Type.ARRAY:
                     item_details = details.get("items", {"type": "string"})
                     item_type_str = item_details.get("type", "string") if isinstance(item_details, dict) else "string"
                     item_type = type_mapping.get(item_type_str, glm.Type.STRING); prop_schema.items = glm.Schema(type=item_type)
                 gemini_properties[param_name] = prop_schema
                 if details.get("required", False): required_list.append(param_name)
        func_decl = FunctionDeclaration( # Use imported FunctionDeclaration
            name=name, description=schema.get("description", ""),
            parameters=glm.Schema(type=glm.Type.OBJECT, properties=gemini_properties, required=required_list) if gemini_properties else None
        )
        gemini_tools.append(func_decl)
    return gemini_tools

def translate_to_ollama_schema_string(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> str:
    """Generates a JSON string representation of the schema for Ollama prompt injection."""
    # (Implementation remains the same as corrected version)
    ollama_tools = []
    for name in tool_names:
        if name not in registered_tools: logging.warning(f"Schema requested for unknown/invalid tool '{name}' (Ollama). Skipping."); continue
        schema = registered_tools[name]
        if not isinstance(schema, dict): logging.warning(f"Tool '{name}' schema invalid (Ollama). Skipping."); continue
        properties, required_list = _translate_params_to_json_schema(schema.get("parameters"))
        ollama_tools.append({
            "name": name, "description": schema.get("description", ""),
            "parameters": {"type": "object", "properties": properties, "required": required_list}
            })
    return json.dumps(ollama_tools, indent=2) if ollama_tools else "[]"

# --- Generic Schema Translation Dispatcher ---
def translate_schema_for_provider(provider_name: str, registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> Optional[Any]:
    """Translates schemas for the specified tools into the format required by the provider."""
    # (Implementation remains the same as corrected version)
    provider_name = provider_name.lower()
    empty_formats = {"openai": [], "anthropic": [], "gemini": [], "ollama": "[]"}; empty_format = empty_formats.get(provider_name, None)
    if not tool_names: return empty_format
    relevant_schemas = {}
    for name in tool_names:
        if name in registered_tools and isinstance(registered_tools[name], dict): relevant_schemas[name] = registered_tools[name]
        else: logging.warning(f"Tool '{name}' requested for {provider_name} schema translation, but not registered or invalid schema.")
    if not relevant_schemas: logging.warning(f"No valid schemas found for requested tools: {tool_names} for provider {provider_name}"); return empty_format
    try:
        schema_list = list(relevant_schemas.keys()) # Use only keys from relevant_schemas
        if provider_name == "openai": return translate_to_openai_schema(relevant_schemas, schema_list)
        elif provider_name == "anthropic": return translate_to_anthropic_schema(relevant_schemas, schema_list)
        elif provider_name == "gemini": return translate_to_gemini_schema(relevant_schemas, schema_list)
        elif provider_name == "ollama": return translate_to_ollama_schema_string(relevant_schemas, schema_list)
        else: logging.error(f"Schema translation not implemented for provider: {provider_name}"); return None
    except Exception as e: logging.exception(f"Error during schema translation for '{provider_name}': {e}"); return empty_format
