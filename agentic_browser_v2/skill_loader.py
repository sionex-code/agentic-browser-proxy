# ─────────────────────────── Skill Loader ───────────────────────────
# Parses .yaser/<site>.md skill files into structured config.
# Skill files use YAML frontmatter + markdown body.

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProfileConfig:
    name: str
    session_dir: str
    description: str = ""


@dataclass
class RulesConfig:
    answers_per_session: int = 10
    wait_between_posts_seconds: int = 60
    switch_profile_after: int = 0  # 0 = don't switch
    ask_user_to_login: bool = True


@dataclass
class TrackingConfig:
    completed_file: str = ""
    format: str = "one URL per line"


@dataclass
class SkillConfig:
    site: str = ""
    start_url: str = ""
    profiles: List[ProfileConfig] = field(default_factory=list)
    active_profile: str = ""
    rules: RulesConfig = field(default_factory=RulesConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    selectors: Dict[str, str] = field(default_factory=dict)
    instructions: str = ""  # Raw markdown body

    def get_active_profile(self) -> Optional[ProfileConfig]:
        """Return the active profile config, or None."""
        for p in self.profiles:
            if p.name == self.active_profile:
                return p
        return self.profiles[0] if self.profiles else None

    def get_profile_by_name(self, name: str) -> Optional[ProfileConfig]:
        """Return a profile by name."""
        for p in self.profiles:
            if p.name == name:
                return p
        return None


def _parse_frontmatter(content: str):
    """Split YAML frontmatter from markdown body.
    
    Returns (yaml_dict, markdown_body).
    """
    content = content.strip()
    if not content.startswith("---"):
        return {}, content

    # Find closing ---
    end_idx = content.index("---", 3)
    yaml_str = content[3:end_idx].strip()
    body = content[end_idx + 3:].strip()

    try:
        yaml_dict = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError as e:
        print(f"  ⚠ YAML parse error in skill file: {e}")
        yaml_dict = {}

    return yaml_dict, body


def load_skill(site_name: str, yaser_dir: str = None) -> Optional[SkillConfig]:
    """Load a skill file from .yaser/<site_name>.md.
    
    Args:
        site_name: Name of the site (e.g. 'quora', 'twitter')
        yaser_dir: Override .yaser directory path. Defaults to project root.
    
    Returns:
        SkillConfig if found, None if skill file doesn't exist.
    """
    if yaser_dir is None:
        # Default to project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        yaser_dir = os.path.join(project_root, ".yaser")

    skill_path = os.path.join(yaser_dir, f"{site_name}.md")

    if not os.path.exists(skill_path):
        print(f"  ⚠ Skill file not found: {skill_path}")
        return None

    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()

    yaml_dict, body = _parse_frontmatter(content)

    # Parse profiles
    profiles = []
    for p in yaml_dict.get("profiles", []):
        profiles.append(ProfileConfig(
            name=p.get("name", ""),
            session_dir=p.get("session_dir", ""),
            description=p.get("description", ""),
        ))

    # Parse rules
    rules_dict = yaml_dict.get("rules", {})
    rules = RulesConfig(
        answers_per_session=rules_dict.get("answers_per_session", 10),
        wait_between_posts_seconds=rules_dict.get("wait_between_posts_seconds", 60),
        switch_profile_after=rules_dict.get("switch_profile_after", 0),
        ask_user_to_login=rules_dict.get("ask_user_to_login", True),
    )

    # Parse tracking
    tracking_dict = yaml_dict.get("tracking", {})
    tracking = TrackingConfig(
        completed_file=tracking_dict.get("completed_file", ""),
        format=tracking_dict.get("format", "one URL per line"),
    )

    # Build config
    config = SkillConfig(
        site=yaml_dict.get("site", site_name),
        start_url=yaml_dict.get("start_url", ""),
        profiles=profiles,
        active_profile=yaml_dict.get("active_profile", ""),
        rules=rules,
        tracking=tracking,
        selectors=yaml_dict.get("selectors", {}),
        instructions=body,
    )

    print(f"  📋 Loaded skill: {config.site}")
    print(f"  📂 Profiles: {', '.join(p.name for p in config.profiles)}")
    print(f"  🎯 Active: {config.active_profile}")
    print(f"  📊 Rules: {config.rules.answers_per_session} answers/session, "
          f"{config.rules.wait_between_posts_seconds}s between posts")

    return config
