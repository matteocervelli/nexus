# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `CodexAdapter` rewritten using `openai-codex-sdk` (PyPI) — JSON-RPC subprocess over local `codex` binary; `SessionMode.RESUMABLE`, supports tool use and file system access (#57)
- Intermediate `OpenAIAdapter` (chat.completions) reverted — lacked tool use, session resumption, and filesystem access (#57)
- Registry key renamed `openai-sdk` → `codex-sdk`; `execution_backend` Literal updated; class renamed back to `CodexAdapter` (#57)
- `openai` package removed from dependencies; replaced by `openai-codex-sdk>=0.1.11` (#57)
- ADR-0006 updated: Tier 1 is now `codex-sdk` JSON-RPC binary subprocess, not HTTP chat.completions (#57)
- `ClaudeAdapter` migrated from subprocess to `claude-agent-sdk` streaming — fixes agent_profile path passed as system prompt text (#55)
- `scheduler._build_request` now forwards `entry.model`, `entry.tool_allowlist`, `entry.max_turns` into `AdapterRequest` — registry values previously ignored (#55)
- `ClaudeAdapter` uses per-invocation `env` dict for stream timeout instead of mutating `os.environ` (#55)
- `validate_environment` / `healthcheck` check SDK importability instead of `claude` binary (#55)

### Added

- `dashboard/` — standalone Vite + React 19 + TanStack Router/Query + `@adlimen/ui-react` SPA scaffold; three stub views (WorkflowFeed, AgentStatus, AuditLog), typed API stubs (`src/api/nexus.ts`), WebSocket placeholder (`src/ws/nexus-ws.ts`), MSW handlers, Vitest setup; proxy target `/nexus/api` → Atrium backend (#21)
- `HttpAdapter` — stateless HTTP execution backend for remote agents; supports sync (POST + immediate response) and async (POST + poll) modes, configurable auth headers, timeout enforcement, and `budget_blocked`/`environment_error` as terminal statuses (#14)
- `src/nexus/adapters/_claude_sdk.py`: SDK helpers (`_patch_sdk_message_parser`, `_stderr_handler`, `_is_transient`, `_read_system_prompt`) (#55)
- Optional `max_turns` field in `AgentProfile`, `AgentRegistryEntry`, and `sync-agents` payload (#55)

- `nexus sync-agents` CLI command: upsert agent profiles from CLAUDE.md files into Atrium agent_registry — exits non-zero on any failed upsert, failed role names included in error message (#56)
- Unit tests for `sync-agents` CLI: dry-run, payload shape, multi-profile error aggregation, transport error, idempotency (fixture-based, decoupled from real agent files) (#56)
- Code Agent profile (`agents/code-agent/CLAUDE.md`) with capability class, model, tool_allowlist, timeout, and budget fields (#18 #19)
- Security Agent profile (`agents/security-agent/CLAUDE.md`) — same schema, scoped to security capability class (#18 #19)
- Phase D e2e integration tests for Code Agent (#18 #19)
- Nexus daemon heartbeat with Scheduler.tick() dispatch loop (#9 #15)
- NexusDaemon skeleton with reconcile_orphans for orphaned work_items on startup (#16)
- Budget checker: token ledger checks before agent spawn using Atrium UUID schema (#17)
- Phase B adapters: ClaudeAdapter, CodexAdapter, ProcessAdapter with ADAPTER_REGISTRY and UUID models (#11 #12 #13)
- Phase A scaffold: adapter interface, headless validation, project structure

### Fixed

- ruff format violations and B904 raise-from exceptions in sync-agents (97e405e)
- ClaudeAdapter and CodexAdapter headless flags; agent registry seeding path (6972192)
- AdapterStatus type annotations; scheduler float(None) handling — CI typecheck (e32bd78)

### Changed

- Forgejo CI and GitHub AI review workflows added; ruff/format violations resolved (3dc0e88)
