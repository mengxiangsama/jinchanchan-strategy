#!/usr/bin/env python3
"""Validate metadata and portable local links; not a strategy-quality evaluation."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "jinchanchan-strategy"


def validate(skill=SKILL):
    skill = Path(skill).resolve()
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("Missing YAML frontmatter")
    metadata = yaml.safe_load(parts[1])
    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter must be a mapping")
    name = metadata.get("name", "")
    if name != skill.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise ValueError("Invalid skill name")
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError("Invalid description")
    interface = yaml.safe_load((skill / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    ui = interface["interface"]
    if not 25 <= len(ui["short_description"]) <= 64:
        raise ValueError("Invalid short description length")
    if f"${name}" not in ui["default_prompt"]:
        raise ValueError("Invocation prompt does not reference the skill")
    if interface.get("policy", {}).get("allow_implicit_invocation", True) is not True:
        raise ValueError("Automatic discovery unexpectedly disabled")
    for file in skill.rglob("*.md"):
        body = file.read_text(encoding="utf-8")
        if "[TODO:" in body:
            raise ValueError(f"Unfinished scaffold: {file.name}")
        for target in re.findall(r"\]\(([^\s)]+)\)", body):
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("#"):
                continue
            resolved = (file.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(skill) or not resolved.exists():
                raise ValueError(f"Broken/nonportable reference: {file.name}: {target}")
    return True


if __name__ == "__main__":
    try:
        validate()
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        sys.exit(f"Validation failed: {error}")
    print("Skill metadata and local references valid. Strategy and gameplay not evaluated.")
