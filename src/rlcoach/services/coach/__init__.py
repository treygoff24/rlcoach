# src/rlcoach/services/coach/__init__.py
"""AI Coach service using Claude Opus 4.5 with extended thinking."""

from .prompts import build_system_prompt
from .tools import get_data_tools, execute_tool
from .budget import check_budget, update_budget, get_budget_status

__all__ = [
    "build_system_prompt",
    "get_data_tools",
    "execute_tool",
    "check_budget",
    "update_budget",
    "get_budget_status",
]
