import logging
import json
from typing import Dict, Any, Optional

# Import the registration decorator and settings
from . import register_tool
from agent_system.config import settings

# NOTE: This initial version provides information about configured limits.
# It does NOT access real-time token usage from providers, as tools
# typically lack direct access to agent/provider state.
# Real-time checking happens within the BaseAgent's run loop before calling the LLM.

@register_tool
async def get_configured_token_limits() -> str:
    """
    Retrieves the configured global token limits and warning threshold from the system settings.

    This tool reports the pre-set configuration values, not the real-time current usage.
    Real-time usage checks are performed internally by the agent system.

    Returns:
        A string summarizing the configured token limits.
    """
    max_tokens = settings.MAX_GLOBAL_TOKENS
    warn_threshold = settings.WARN_TOKEN_THRESHOLD

    limit_status = f"Enabled (Max: {max_tokens:,})" if max_tokens > 0 else "Disabled"
    warn_status = f"Enabled (Threshold: {warn_threshold:,})" if warn_threshold > 0 and max_tokens > 0 else "Disabled"

    if max_tokens > 0 and warn_threshold > 0 and warn_threshold >= max_tokens:
        warn_status += " [Warning: Threshold is >= Max Limit, warning may not trigger effectively]"
    elif max_tokens > 0 and warn_threshold <= 0:
         warn_status = "Disabled (Threshold set to 0 or less)"


    summary = (
        f"Configured Token Limits:\n"
        f"- Global Token Limit Status: {limit_status}\n"
        f"- Warning Threshold Status: {warn_status}"
    )
    logging.info(f"Reporting configured token limits: Max={max_tokens}, Warn={warn_threshold}")
    return summary

# Potential future tool idea (requires architectural changes, e.g., passing agent state):
# @register_tool
# async def get_current_token_usage(agent_context: Optional[Any] = None) -> str:
#     """
#     (Conceptual - Not Implemented) Retrieves the current approximate token usage.
#     Requires access to agent or global state.
#     """
#     if agent_context is None:
#          return "Error: Cannot retrieve current usage without agent context."
#     # Logic to access total tokens from agent_context.llm_provider.get_total_token_usage()
#     # Compare with limits from settings.py
#     # Return summary
#     return "Error: get_current_token_usage is not fully implemented yet."
