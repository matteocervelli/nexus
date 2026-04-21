"""Regression tests for the shared _profile.read_system_prompt helper."""

from __future__ import annotations

import pathlib

from nexus.adapters._profile import read_system_prompt


def _write(tmp_path: pathlib.Path, content: str) -> str:
    p = tmp_path / "CLAUDE.md"
    p.write_text(content)
    return str(p)


def test_fenced_yaml_stripped(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, "```yaml\nagent_role: test\n```\n\n# Body\n\nContent here.\n")
    result = read_system_prompt(path)
    assert "agent_role" not in result
    assert "# Body" in result
    assert "Content here." in result


def test_delimiter_yaml_stripped(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, "---\nagent_role: test\n---\n\n# Body\n\nContent here.\n")
    result = read_system_prompt(path)
    assert "agent_role" not in result
    assert "# Body" in result


def test_no_front_matter_passthrough(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, "# Just a body\n\nNo front-matter here.\n")
    result = read_system_prompt(path)
    assert "Just a body" in result


def test_leading_newlines_stripped(tmp_path: pathlib.Path) -> None:
    path = _write(tmp_path, "```yaml\nkey: val\n```\n\n\n\nActual content.\n")
    result = read_system_prompt(path)
    assert not result.startswith("\n")
    assert "Actual content." in result
