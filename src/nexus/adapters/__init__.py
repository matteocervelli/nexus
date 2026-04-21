"""Adapter implementations — one module per execution backend.

ADAPTER_REGISTRY maps the string key stored in agent_registry.execution_backend
to the concrete AdapterBase subclass that handles that backend.

Scheduler usage:
    adapter_cls = ADAPTER_REGISTRY[entry.execution_backend]
    adapter = adapter_cls()
    result = await adapter.invoke_heartbeat(request)
"""

from __future__ import annotations

from nexus.adapters.claude_adapter import ClaudeAdapter
from nexus.adapters.openai_adapter import CodexAdapter
from nexus.adapters.process_adapter import ProcessAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "claude-code-cli": ClaudeAdapter,
    "codex-sdk": CodexAdapter,
    "process": ProcessAdapter,
}

__all__ = [
    "ADAPTER_REGISTRY",
    "ClaudeAdapter",
    "CodexAdapter",
    "ProcessAdapter",
]
