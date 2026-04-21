"""Shared agent-profile helpers for Nexus adapters."""

from __future__ import annotations

import re

_FENCED_YAML_RE = re.compile(r"^```yaml\n.*?\n```\n?", re.DOTALL)
_DELIMITER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def read_system_prompt(profile_path: str) -> str:
    """Read a CLAUDE.md file, strip YAML front-matter, return the markdown body."""
    with open(profile_path, encoding="utf-8") as fh:
        text = fh.read()
    body = _FENCED_YAML_RE.sub("", text, count=1)
    if body == text:
        body = _DELIMITER_RE.sub("", text, count=1)
    return body.lstrip("\n")
