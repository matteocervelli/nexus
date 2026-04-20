# ADR-0007 — Dashboard as Standalone SPA Webapp

Date: 2026-04-20
Status: Accepted

## Context

Early Nexus design assumed a FastAPI + HTMX dashboard embedded in the daemon service, following the "simple and fast" pattern used elsewhere in the adlimen stack.

This assumption was revisited for two reasons:

1. **Real-time requirements.** The dashboard needs live updates: running agent status, active workflows, token budget consumption. HTMX server-sent events work for simple polling, but coordinating multiple live data streams from a single FastAPI server creates tight coupling between the daemon's execution loop and its HTTP layer.

2. **Independent deployment.** The dashboard is a development-time tool, not a production requirement. Embedding it in the daemon couples its lifecycle to the daemon's. A crash in the frontend serving path should not affect agent orchestration.

## Decision

The Nexus operational dashboard is a **standalone SPA project**, separate from the `nexus` daemon repository.

Nexus backend exposes a clean JSON API and WebSocket endpoint:

- `GET /nexus/api/workflows` — list workflows and step status
- `POST /nexus/api/workflows` — create a new workflow
- `GET /nexus/api/agents` — list active agent_registry entries
- `GET /nexus/api/status` — daemon health, concurrency, budget summary
- `WS /nexus/api/ws` — live event stream (agent spawned, step completed, budget alert)

The SPA is a separate project (`nexus-webapp` or equivalent), not part of any existing shared monorepo. Technology stack is deferred to the design phase — the constraint is TypeScript with a lightweight framework suitable for a single developer.

**Non-goals for MVP:**

- Multi-tenant access or auth beyond personal use
- Mobile-first design (Telegram via Limen handles mobile interactions)
- Embedding the SPA build into the daemon's static file serving

## Rationale

1. **Separation of concerns.** The daemon's job is orchestration. Serving a frontend is a separate concern. Coupling them introduces failure modes in both directions.

2. **Real-time is natural in a SPA.** WebSocket or SSE consumption is idiomatic in a frontend JS context. Implementing equivalent push semantics cleanly in HTMX requires more ceremony than it saves.

3. **Dashboard is optional for MVP.** The API exists from day one. The SPA can be built when operational visibility becomes the bottleneck — not before.

4. **HTMX is the right tool for simpler cases.** This decision does not reject HTMX globally. It rejects it for a dashboard with live multi-stream data and independent deployment requirements.

## Consequences

- `src/nexus/` contains no frontend code — pure Python daemon + API routes
- Dashboard deployment is independent of daemon deployment
- The API contract (`/nexus/api/`) must be stable before the SPA project begins
- MVP milestone: daemon + API only. SPA is a separate project tracked separately.
- Limen (Telegram) remains the primary operational interface until the SPA exists

## References

- [ADR-0002](0002-internal-board-layer.md)
- [Nexus Vision](../development/nexus-vision.md)
