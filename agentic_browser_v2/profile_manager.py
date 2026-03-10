# ─────────────────────────── Profile Manager ───────────────────────────
# Handles browser profile lifecycle — session directories, profile rotation.

import os
from typing import Optional

from .skill_loader import SkillConfig, ProfileConfig


def get_session_dir(config: SkillConfig, profile_name: str = None) -> str:
    """Get the session directory for a profile.
    
    Args:
        config: Loaded skill config
        profile_name: Profile name to use. Defaults to active_profile.
    
    Returns:
        Absolute path to the session directory.
    """
    if profile_name:
        profile = config.get_profile_by_name(profile_name)
    else:
        profile = config.get_active_profile()

    if not profile:
        # Fallback to generic session dir
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            f"session_{config.site.replace('.', '_')}"
        )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, profile.session_dir)


def get_next_profile(config: SkillConfig, current_profile: str) -> Optional[str]:
    """Get the next profile in rotation.
    
    Args:
        config: Loaded skill config
        current_profile: Name of the current profile
    
    Returns:
        Name of the next profile, or None if only one profile exists.
    """
    if len(config.profiles) <= 1:
        return None

    names = [p.name for p in config.profiles]
    try:
        current_idx = names.index(current_profile)
        next_idx = (current_idx + 1) % len(names)
        return names[next_idx]
    except ValueError:
        return names[0] if names else None


def should_switch_profile(config: SkillConfig, answers_count: int) -> bool:
    """Check if it's time to switch profiles.
    
    Args:
        config: Loaded skill config
        answers_count: Number of answers posted in current profile session
    
    Returns:
        True if should switch, False otherwise.
    """
    switch_after = config.rules.switch_profile_after
    if switch_after <= 0:
        return False
    if len(config.profiles) <= 1:
        return False
    return answers_count >= switch_after


def get_all_profile_names(config: SkillConfig) -> list:
    """Get list of all profile names."""
    return [p.name for p in config.profiles]


def get_profile_info(config: SkillConfig) -> str:
    """Get a human-readable summary of all profiles."""
    lines = []
    for p in config.profiles:
        marker = "→ " if p.name == config.active_profile else "  "
        lines.append(f"{marker}{p.name}: {p.description} (session: {p.session_dir})")
    return "\n".join(lines)
