# ... (imports: logging, json, typing, Optional fallbacks for google libs) ...
import logging
import json
from typing import List, Dict, Any, Optional, Tuple, Union

try:
    import google.generativeai as genai
    import google.ai.generativelanguage as glm
    # Only import FunctionDeclaration from types for now
    from google.generativeai.types import FunctionDeclaration
    GEMINI_LIBS_AVAILABLE = True
except ImportError:
    # ... (fallback definitions) ...
    logging.info("google.generativeai library not found...")
    GEMINI_LIBS_AVAILABLE = False
    genai = None; glm = None; FunctionDeclaration = Any

GenericToolSchema = Dict[str, Any]

def _translate_params_to_json_schema(#...
    parameters: Optional[Dict[str, Dict[str, Any]]]
) -> Tuple[Dict[str, Any], List[str]]:
    # (Implementation unchanged)
    # ... (same as previous correct version) ...
    if not parameters: return {}, []
    properties = {}; required_list = []
    for name, details in parameters.items():
        if not isinstance(details, dict): logging.warning(f"Param '{name}' invalid details. Skipping."); continue
        prop_schema: Dict[str, Any] = {"description": details.get("description", "")}
        param_type = details.get("type", "string")
        valid_types = ["string", "number", "integer", "boolean", "array", "object", "any"]
        if param_type not in valid_types: logging.warning(f"Param '{name}' bad type '{param_type}'. Defaulting to 'string'."); param_type = "string"
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
# (translate_to_openai_schema, translate_to_anthropic_schema unchanged) ...
def translate_to_openai_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Dict[str, Any]]:
    openai_tools = []
    for name in tool_names:
        if name not in registered_tools: continue
        schema = registered_tools[name];
        if not isinstance(schema, dict): continue
        properties, required_list = _translate_params_to_json_schema(schema.get("parameters"))
        openai_tools.append({"type": "function", "function": {"name": name, "description": schema.get("description", ""),"parameters": {"type": "object", "properties": properties, "required": required_list}}})
    return openai_tools

def translate_to_anthropic_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Dict[str, Any]]:
    anthropic_tools = []
    for name in tool_names:
        if name not in registered_tools: continue
        schema = registered_tools[name];
        if not isinstance(schema, dict): continue
        properties, _ = _translate_params_to_json_schema(schema.get("parameters"))
        anthropic_tools.append({"name": name, "description": schema.get("description", ""),"input_schema": {"type": "object", "properties": properties }})
    return anthropic_tools

def translate_to_gemini_schema(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> List[Any]:
    """
    Generates Gemini-compatible tool schema list (FunctionDeclaration).
    Constructs parameter schema as a dictionary matching the proto structure.
    """
    if not GEMINI_LIBS_AVAILABLE:
        logging.error("Cannot generate Gemini schema: google.generativeai library not available.")
        return []

    gemini_tools = []
    # Mapping from simple types to google.ai.generativelanguage.Type enum values
    # Ensure glm is available before accessing its attributes
    type_mapping_proto = {
        "string": glm.Type.STRING, "number": glm.Type.NUMBER, "integer": glm.Type.INTEGER,
        "boolean": glm.Type.BOOLEAN, "array": glm.Type.ARRAY, "object": glm.Type.OBJECT,
        "any": glm.Type.STRING, # Map 'any' to string as a fallback
    } if glm else {}

    for name in tool_names:
        if name not in registered_tools: continue
        schema = registered_tools[name]
        if not isinstance(schema, dict): continue

        parameters_dict: Optional[Dict[str, Any]] = None # This will be the dict passed to FunctionDeclaration
        gemini_properties_dict: Dict[str, Dict[str, Any]] = {} # Dict for 'properties' field within parameters_dict
        required_list: List[str] = []
        raw_parameters = schema.get("parameters")

        if raw_parameters and isinstance(raw_parameters, dict):
            for param_name, details in raw_parameters.items():
                 if not isinstance(details, dict): continue
                 param_type_str = details.get("type", "string")
                 # Use the integer enum value from the mapping
                 gemini_type_enum_val = type_mapping_proto.get(param_type_str, glm.Type.STRING if glm else 1) # Default to STRING's value

                 # Build the property dictionary matching the Schema proto structure
                 prop_dict: Dict[str, Any] = {
                      "type_": gemini_type_enum_val, # Note the underscore for 'type' proto field
                      "description": details.get("description", "")
                 }

                 # Handle array items
                 if gemini_type_enum_val == (glm.Type.ARRAY if glm else -1): # Use enum value for comparison
                     item_details = details.get("items", {"type": "string"})
                     item_type_str = item_details.get("type", "string") if isinstance(item_details, dict) else "string"
                     item_type_enum_val = type_mapping_proto.get(item_type_str, glm.Type.STRING if glm else 1)
                     # The 'items' field in the proto expects a Schema message/dict
                     prop_dict["items"] = {"type_": item_type_enum_val}

                 gemini_properties_dict[param_name] = prop_dict
                 if details.get("required", False): required_list.append(param_name)

            # Construct the main parameters dictionary only if properties exist
            if gemini_properties_dict:
                 parameters_dict = {
                      "type_": glm.Type.OBJECT if glm else 5, # Type.OBJECT enum value
                      "properties": gemini_properties_dict,
                      "required": required_list
                 }

        # --- Create FunctionDeclaration using the dictionary for parameters ---
        try:
             # Pass the constructed dictionary directly to the parameters argument
             func_decl = FunctionDeclaration(
                 name=name,
                 description=schema.get("description", ""),
                 parameters=parameters_dict # Pass the dictionary, or None if no params
             )
             gemini_tools.append(func_decl)
        except Exception as e:
             # Catch errors during FunctionDeclaration creation itself
             logging.exception(f"Unexpected error creating Gemini FunctionDeclaration for tool '{name}'. Parameters Dict: {parameters_dict}")
             # Skip this tool if declaration fails

    return gemini_tools

# ...(translate_to_ollama_schema_string and translate_schema_for_provider remain the same)...
def translate_to_ollama_schema_string(registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> str:
    ollama_tools = []
    for name in tool_names:
        if name not in registered_tools: continue
        schema = registered_tools[name];
        if not isinstance(schema, dict): continue
        properties, required_list = _translate_params_to_json_schema(schema.get("parameters"))
        ollama_tools.append({"name": name, "description": schema.get("description", ""),"parameters": {"type": "object", "properties": properties, "required": required_list}})
    return json.dumps(ollama_tools, indent=2) if ollama_tools else "[]"

def translate_schema_for_provider(provider_name: str, registered_tools: Dict[str, GenericToolSchema], tool_names: List[str]) -> Optional[Any]:
    provider_name = provider_name.lower()
    empty_formats = {"openai": [], "anthropic": [], "gemini": [], "ollama": "[]"}; empty_format = empty_formats.get(provider_name, None)
    if not tool_names: return empty_format
    relevant_schemas = {}
    for name in tool_names:
        if name in registered_tools and isinstance(registered_tools[name], dict): relevant_schemas[name] = registered_tools[name]
        else: logging.warning(f"Tool '{name}' requested for {provider_name} schema translation, but not registered or invalid schema.")
    if not relevant_schemas: logging.warning(f"No valid schemas found for requested tools: {tool_names} for provider {provider_name}"); return empty_format
    try:
        schema_list = list(relevant_schemas.keys())
        if provider_name == "openai": return translate_to_openai_schema(relevant_schemas, schema_list)
        elif provider_name == "anthropic": return translate_to_anthropic_schema(relevant_schemas, schema_list)
        elif provider_name == "gemini": return translate_to_gemini_schema(relevant_schemas, schema_list)
        elif provider_name == "ollama": return translate_to_ollama_schema_string(relevant_schemas, schema_list)
        else: logging.error(f"Schema translation not implemented for provider: {provider_name}"); return None
    except Exception as e: logging.exception(f"Error during schema translation for '{provider_name}': {e}"); return empty_format
