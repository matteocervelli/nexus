"""Tests for agent_loader.py — parse CLAUDE.md front-matter."""

from __future__ import annotations

import pathlib

import pytest

from nexus.agent_loader import _extract_yaml_block, _parse_frontmatter, load_agent_profiles

SAMPLE_FENCED = """# Code Agent

```yaml
agent_role: code-agent
execution_backend: claude-code-cli
model: claude-sonnet-4-6
capability_class: code
timeout_seconds: 900
monthly_token_budget: 500000
tool_allowlist: [Read, Write, Bash]
```

## Identity
...
"""

SAMPLE_DELIMITER = """---
agent_role: security-agent
execution_backend: claude-code-cli
model: claude-sonnet-4-6
capability_class: security
timeout_seconds: 1200
monthly_token_budget: 200000
---

# Security Agent
"""


def test_extract_yaml_block_fenced():
    block = _extract_yaml_block(SAMPLE_FENCED)
    assert block is not None
    assert "agent_role: code-agent" in block


def test_extract_yaml_block_delimiter():
    block = _extract_yaml_block(SAMPLE_DELIMITER)
    assert block is not None
    assert "agent_role: security-agent" in block


def test_extract_yaml_block_returns_none_when_absent():
    assert _extract_yaml_block("# No YAML here\nJust plain text.") is None


def test_parse_frontmatter_scalars():
    data = _parse_frontmatter("agent_role: code-agent\ntimeout_seconds: 900\nis_active: true")
    assert data["agent_role"] == "code-agent"
    assert data["timeout_seconds"] == 900
    assert data["is_active"] is True


def test_parse_frontmatter_false_bool():
    data = _parse_frontmatter("is_active: false")
    assert data["is_active"] is False


def test_parse_frontmatter_list():
    data = _parse_frontmatter("tool_allowlist: [Read, Write, Bash]")
    assert data["tool_allowlist"] == ["Read", "Write", "Bash"]


def test_parse_frontmatter_empty_list():
    data = _parse_frontmatter("tool_allowlist: []")
    assert data["tool_allowlist"] == []


def test_load_profiles_happy_path(tmp_path):
    agent_dir = tmp_path / "code-agent"
    agent_dir.mkdir()
    (agent_dir / "CLAUDE.md").write_text(SAMPLE_FENCED)
    profiles = load_agent_profiles(tmp_path)
    assert len(profiles) == 1
    p = profiles[0]
    assert p.agent_role == "code-agent"
    assert p.timeout_seconds == 900
    assert p.tool_allowlist == ["Read", "Write", "Bash"]


def test_profile_path_is_absolute(tmp_path):
    agent_dir = tmp_path / "code-agent"
    agent_dir.mkdir()
    (agent_dir / "CLAUDE.md").write_text(SAMPLE_FENCED)
    profiles = load_agent_profiles(tmp_path)
    assert pathlib.Path(profiles[0].profile_path).is_absolute()


def test_load_profiles_multiple_agents(tmp_path):
    for name, content in [("code-agent", SAMPLE_FENCED), ("security-agent", SAMPLE_DELIMITER)]:
        d = tmp_path / name
        d.mkdir()
        (d / "CLAUDE.md").write_text(content)
    profiles = load_agent_profiles(tmp_path)
    assert len(profiles) == 2
    roles = {p.agent_role for p in profiles}
    assert roles == {"code-agent", "security-agent"}


def test_missing_required_field_raises(tmp_path):
    agent_dir = tmp_path / "bad-agent"
    agent_dir.mkdir()
    (agent_dir / "CLAUDE.md").write_text("```yaml\nagent_role: bad-agent\n```")
    with pytest.raises(ValueError, match="missing required fields"):
        load_agent_profiles(tmp_path)


def test_no_yaml_block_skipped(tmp_path):
    agent_dir = tmp_path / "no-yaml"
    agent_dir.mkdir()
    (agent_dir / "CLAUDE.md").write_text("# No YAML here\nJust plain text.")
    profiles = load_agent_profiles(tmp_path)
    assert profiles == []


def test_is_active_defaults_to_true(tmp_path):
    content = SAMPLE_FENCED.replace("tool_allowlist: [Read, Write, Bash]\n", "")
    agent_dir = tmp_path / "code-agent"
    agent_dir.mkdir()
    (agent_dir / "CLAUDE.md").write_text(content)
    profiles = load_agent_profiles(tmp_path)
    assert profiles[0].is_active is True


def test_max_turns_parsed_from_frontmatter(tmp_path):
    content = """# Code Agent

```yaml
agent_role: code-agent
execution_backend: claude-code-cli
model: claude-sonnet-4-6
capability_class: code
timeout_seconds: 900
monthly_token_budget: 500000
max_turns: 80
tool_allowlist: [Read, Write, Bash]
```

## Identity
...
"""
    agent_dir = tmp_path / "code-agent"
    agent_dir.mkdir()
    (agent_dir / "CLAUDE.md").write_text(content)
    profiles = load_agent_profiles(tmp_path)
    assert profiles[0].max_turns == 80


def test_max_turns_defaults_to_none_when_absent(tmp_path):
    agent_dir = tmp_path / "code-agent"
    agent_dir.mkdir()
    (agent_dir / "CLAUDE.md").write_text(SAMPLE_FENCED)
    profiles = load_agent_profiles(tmp_path)
    assert profiles[0].max_turns is None
