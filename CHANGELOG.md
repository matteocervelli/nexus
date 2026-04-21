# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
