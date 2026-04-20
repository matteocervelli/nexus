# ADR-0004 — Python asyncio as Daemon Runtime

Date: 2026-04-20
Status: Accepted

## Context

Three runtime candidates were evaluated for the Nexus daemon:

- **Python asyncio** — same language as the rest of the adlimen stack
- **TypeScript/Node.js** — strong async model, natural fit if the dashboard were coupled to the daemon
- **Go** — purpose-built for daemons; strong subprocess management and low resource overhead

The core requirement is a long-running daemon that:

- polls Atrium for pending work items on a heartbeat
- spawns 3–10 concurrent agent subprocesses (Claude Code CLI, Codex CLI)
- enforces per-agent timeouts and cleans up orphaned processes
- communicates with Atrium and Limen over HTTP

## Decision

Nexus daemon (`src/nexus/`) is built in **Python 3.12+ asyncio**.

## Rationale

1. **Stack consistency**
   Limen, Atrium, and Fabrica are all Python. A solo maintainer cannot sustain two runtime ecosystems. Shared patterns — HTTP client, config loading, error handling — transfer directly.

2. **Proven pattern**
   `limen-assistant` already implements the heartbeat daemon loop in Python asyncio. That codebase is the direct template for Nexus.

3. **Subprocess management is sufficient**
   `asyncio.create_subprocess_exec` + `asyncio.wait_for` covers the required use case. Process group cleanup via `os.killpg` handles orphan cleanup on timeout or cancellation.

4. **Go is overkill**
   Go's daemon and subprocess management is superior, but introduces a second runtime with no shared patterns, no shared dependencies, and no reuse of existing adlimen tooling.

5. **TypeScript has no advantage here**
   The dashboard is a separate SPA project (see ADR-0007). Without dashboard coupling, there is no reason to use TypeScript for the daemon.

## Consequences

- All daemon code lives under `src/nexus/` as Python 3.12+
- Agent subprocess spawning uses `asyncio.create_subprocess_exec` with explicit timeout via `asyncio.wait_for`
- Orphan cleanup uses `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` — not just `proc.kill()`
- Atrium HTTP client: `httpx` async (already in the stack)
- Project uses `uv` for dependency management, consistent with other adlimen services

## References

- [ADR-0001](0001-paperclip-no-go.md)
- [ADR-0002](0002-internal-board-layer.md)
- [ADR-0003](0003-runtime-adapter-contract.md)
- [Nexus Vision](../development/nexus-vision.md)
