"""Tests for ADAPTER_REGISTRY wiring in nexus.adapters.__init__."""

from __future__ import annotations

import pytest

from nexus.adapter_base import AdapterBase
from nexus.adapters import ADAPTER_REGISTRY, ClaudeAdapter, CodexAdapter, ProcessAdapter


def test_registry_contains_all_backends():
    assert set(ADAPTER_REGISTRY.keys()) == {"claude-code-cli", "codex-cli", "process"}


def test_registry_values_are_adapter_subclasses():
    for key, cls in ADAPTER_REGISTRY.items():
        assert issubclass(cls, AdapterBase), f"{key} → {cls} is not an AdapterBase subclass"


def test_registry_maps_to_correct_classes():
    assert ADAPTER_REGISTRY["claude-code-cli"] is ClaudeAdapter
    assert ADAPTER_REGISTRY["codex-cli"] is CodexAdapter
    assert ADAPTER_REGISTRY["process"] is ProcessAdapter


def test_registry_classes_are_instantiable():
    for key, cls in ADAPTER_REGISTRY.items():
        instance = cls()
        assert isinstance(instance, AdapterBase), f"{key} instance is not an AdapterBase"
