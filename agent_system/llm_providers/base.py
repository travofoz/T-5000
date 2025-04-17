# This file is intended as an optional place for base classes or shared utilities
# specific to LLM providers, beyond the main ABC defined in __init__.py.

# For example, if multiple providers shared a complex tokenization approach or
# a common way to handle certain API error patterns, that logic could reside here.

# Currently, no additional base classes are required beyond the LLMProvider ABC
# defined in llm_providers/__init__.py. This file can remain empty or be removed
# if not needed.

import logging

logging.debug("llm_providers/base.py loaded (currently no shared base classes defined here).")
