# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nexus dashboard SPA with three live views: Workflow Feed, Agent Status, Audit Log (#24)
- Run detail view (`/audit/$runId`) with event timeline, cost, token counts, stdout/stderr excerpts (#24)
- SSE EventSource client (`NexusEventSource`) with exponential backoff reconnect; React hook `useNexusEvents` for TanStack Query cache invalidation (#23)
- Proxy routes: `GET /nexus/api/work_items`, `/nexus/api/runs`, `/nexus/api/runs/{id}`, `/nexus/api/runs/{id}/events` (#24)
- Dashboard API layer: `GET /nexus/api/workflows`, `/nexus/api/workflows/{id}`, `/nexus/api/agents`, `/nexus/api/status` (#22)
- Playwright configuration for Chromium browser (#21)
- `HttpAdapter` for remote HTTP agent execution backend (#14)
- Forgejo CI and GitHub AI review workflows

### Changed
- `ClaudeAdapter` migrated to `claude-agent-sdk` (#55)
- `CodexAdapter` migrated to `openai-codex-sdk` (#57)
- Atrium `agent_registry` seed + hardened `sync-agents` CLI

### Fixed
- Multi-status filter in `/nexus/api/work_items` now forwards repeated query params correctly (#24)
- Transport errors in proxy routes now return 502 instead of 500
- `AdapterStatus` type annotations; scheduler `float(None)` guard
- Adapter headless flags and agent registry seeding
