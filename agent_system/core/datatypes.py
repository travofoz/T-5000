import time
import json
import logging
from typing import List, Dict, Any, Optional, Union

# Using standard dataclasses for simplicity and type hinting support
from dataclasses import dataclass, field

@dataclass
class ToolCall:
    """Represents a request from the LLM to call a specific tool."""
    id: str  # Unique identifier for this specific call instance
    name: str  # The name of the tool requested
    arguments: Dict[str, Any] # The arguments for the tool, parsed as a dictionary

    def __repr__(self) -> str:
        # Use repr for arguments for potentially cleaner logging
        args_repr = repr(self.arguments)
        if len(args_repr) > 100: # Truncate long args representation
            args_repr = args_repr[:100] + "...}"
        return f"ToolCall(id={self.id!r}, name={self.name!r}, arguments={args_repr})"

    # Helper methods for JSON serialization if needed later
    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolCall':
        return cls(id=data['id'], name=data['name'], arguments=data['arguments'])


@dataclass
class ToolResult:
    """Represents the result of executing a tool call."""
    id: str  # Matches the id of the corresponding ToolCall
    name: str # The name of the tool that was executed
    result: Optional[str] = None # String representation of the tool's successful output
    error: Optional[str] = None # String representation of an error message if execution failed
    is_error: bool = False # Flag indicating if the execution resulted in an error

    def __post_init__(self):
        # Ensure consistency: if error is present, is_error should be True
        if self.error is not None:
            self.is_error = True
        # Ensure result is None if there's an error, and vice versa (optional strictness)
        # if self.is_error and self.result is not None:
        #    logging.warning(f"ToolResult for '{self.name}' (ID: {self.id}) has both error and result set. Clearing result.")
        #    self.result = None
        # elif not self.is_error and self.error is not None:
        #      logging.warning(f"ToolResult for '{self.name}' (ID: {self.id}) has error set but is_error=False. Setting is_error=True.")
        #      self.is_error = True
        # Ensure result and error are strings
        if self.result is not None and not isinstance(self.result, str):
            self.result = str(self.result)
        if self.error is not None and not isinstance(self.error, str):
            self.error = str(self.error)


    def __repr__(self) -> str:
        status = "ERROR" if self.is_error else "OK"
        output = self.error if self.is_error else self.result
        output_repr = repr(output)
        if len(output_repr) > 100: # Truncate long output representation
             output_repr = output_repr[:100] + "...'"
        return f"ToolResult(id={self.id!r}, name={self.name!r}, status={status}, output={output_repr})"

    # Helper methods for JSON serialization
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "result": self.result,
            "error": self.error,
            "is_error": self.is_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolResult':
        return cls(
            id=data['id'],
            name=data['name'],
            result=data.get('result'),
            error=data.get('error'),
            is_error=data.get('is_error', data.get('error') is not None) # Infer is_error if not present
        )


# Union type for content parts within a ChatMessage
# Can be simple text, a list of tool calls (from model), or a list of tool results (from tool execution)
# Note: We use List[ToolCall] and List[ToolResult] to group calls/results from a single turn,
# matching how some APIs (like OpenAI) structure them.
MessagePart = Union[str, List[ToolCall], List[ToolResult]]

@dataclass
class ChatMessage:
    """Represents a single message in the conversation history."""
    role: str # Standard roles: 'user', 'assistant' (or 'model'), 'tool', 'system'
    parts: List[MessagePart] # The content of the message, can have multiple parts
    timestamp: float = field(default_factory=time.time) # Add timestamp for tracking

    def __post_init__(self):
        # Ensure parts is always a list, even if initialized with a single item implicitly
        if not isinstance(self.parts, list):
            # This case should ideally not happen with type hinting, but good robustness check
             logging.warning(f"ChatMessage initialized with non-list parts ({type(self.parts)}). Wrapping in list.")
             self.parts = [self.parts]

    def get_text_content(self) -> str:
        """Helper to extract and concatenate all string parts of the message."""
        return "\n".join(part for part in self.parts if isinstance(part, str))

    def __repr__(self) -> str:
        parts_repr = []
        for part in self.parts:
            if isinstance(part, str):
                parts_repr.append(f"'{part[:70]}{'...' if len(part) > 70 else ''}'")
            elif isinstance(part, list): # List of ToolCall or ToolResult
                 if part:
                      item_type = type(part[0]).__name__
                      parts_repr.append(f"[{len(part)} x {item_type}(s)]")
                 else:
                      parts_repr.append("[]")
            else: # Should not happen with MessagePart typing
                 parts_repr.append(repr(part))
        return f"ChatMessage(role={self.role!r}, parts=[{', '.join(parts_repr)}], ts={self.timestamp:.0f})"

    # --- JSON Serialization Support for History ---
    def to_dict(self) -> Dict[str, Any]:
        """Serializes ChatMessage to a dictionary suitable for JSON."""
        serialized_parts = []
        for part in self.parts:
            if isinstance(part, str):
                serialized_parts.append({"type": "text", "content": part})
            elif isinstance(part, list) and part and isinstance(part[0], ToolCall):
                serialized_parts.append({
                    "type": "tool_calls",
                    "content": [tc.to_dict() for tc in part]
                })
            elif isinstance(part, list) and part and isinstance(part[0], ToolResult):
                 serialized_parts.append({
                     "type": "tool_results",
                     "content": [tr.to_dict() for tr in part]
                 })
            elif isinstance(part, list) and not part: # Handle empty list case
                 serialized_parts.append({"type": "empty_list", "content": []})
            else:
                # Fallback for unexpected types, log warning
                logging.warning(f"Serializing unexpected part type {type(part)} in ChatMessage. Converting to string.")
                serialized_parts.append({"type": "unknown", "content": str(part)})

        return {
            "role": self.role,
            "parts": serialized_parts,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Deserializes a dictionary (from JSON) back into a ChatMessage."""
        deserialized_parts = []
        for part_data in data.get("parts", []):
            part_type = part_data.get("type")
            content = part_data.get("content")
            if part_type == "text":
                deserialized_parts.append(str(content)) # Ensure string
            elif part_type == "tool_calls" and isinstance(content, list):
                deserialized_parts.append([ToolCall.from_dict(tc_data) for tc_data in content])
            elif part_type == "tool_results" and isinstance(content, list):
                 deserialized_parts.append([ToolResult.from_dict(tr_data) for tr_data in content])
            elif part_type == "empty_list":
                 deserialized_parts.append([])
            else:
                # Fallback for unknown types or older formats
                logging.warning(f"Deserializing unknown part type '{part_type}'. Treating content as string.")
                deserialized_parts.append(str(content))

        return cls(
            role=data.get("role", "unknown"),
            parts=deserialized_parts,
            timestamp=data.get("timestamp", time.time()) # Provide default timestamp if missing
        )
