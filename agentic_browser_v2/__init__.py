# ─────────────────────────── agentic_browser_v2 package ───────────────────────────
"""
Modular agentic browser automation package.

Usage:
    python -m agentic_browser_v2
    # or
    from agentic_browser_v2 import BrowserAgent, AgentMemory, main
"""

from .agent import BrowserAgent
from .memory import AgentMemory
from .ai_client import send_prompt
from .main import main

__all__ = ["BrowserAgent", "AgentMemory", "send_prompt", "main"]
