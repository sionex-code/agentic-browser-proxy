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
from .skill_loader import load_skill, SkillConfig
from .profile_manager import get_session_dir, get_next_profile, should_switch_profile
from .duplicate_tracker import DuplicateTracker

__all__ = [
    "BrowserAgent", "AgentMemory", "send_prompt", "main",
    "load_skill", "SkillConfig",
    "get_session_dir", "get_next_profile", "should_switch_profile",
    "DuplicateTracker",
]
