"""Parse agent CLAUDE.md front-matter into AgentProfile dataclasses."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

REQUIRED_FIELDS = frozenset(
    {
        "agent_role",
        "execution_backend",
        "model",
        "capability_class",
        "timeout_seconds",
        "monthly_token_budget",
    }
)


@dataclass
class AgentProfile:
    agent_role: str
    execution_backend: str
    model: str
    capability_class: str
    timeout_seconds: int
    monthly_token_budget: int
    profile_path: str
    tool_allowlist: list[str] = field(default_factory=list)
    is_active: bool = True


def _parse_yaml_value(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    return raw


def _extract_yaml_block(text: str) -> str | None:
    fence_match = re.search(r"```yaml\n(.*?)\n```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        return fm_match.group(1)
    return None


def _parse_frontmatter(yaml_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in yaml_text.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = _parse_yaml_value(value)
    return result


def load_agent_profiles(agents_dir: pathlib.Path) -> list[AgentProfile]:
    """Find all agents/*/CLAUDE.md, parse front-matter, validate required fields."""
    profiles: list[AgentProfile] = []
    for claude_md in sorted(agents_dir.glob("*/CLAUDE.md")):
        text = claude_md.read_text(encoding="utf-8")
        yaml_block = _extract_yaml_block(text)
        if yaml_block is None:
            continue
        data = _parse_frontmatter(yaml_block)
        missing = REQUIRED_FIELDS - data.keys()
        if missing:
            raise ValueError(f"{claude_md}: missing required fields: {missing}")
        profiles.append(
            AgentProfile(
                agent_role=str(data["agent_role"]),
                execution_backend=str(data["execution_backend"]),
                model=str(data["model"]),
                capability_class=str(data["capability_class"]),
                timeout_seconds=int(data["timeout_seconds"]),
                monthly_token_budget=int(data["monthly_token_budget"]),
                profile_path=str(claude_md.resolve()),
                tool_allowlist=data.get("tool_allowlist", []),
                is_active=bool(data.get("is_active", True)),
            )
        )
    return profiles
