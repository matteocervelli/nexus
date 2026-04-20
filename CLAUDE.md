# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Nexus Is

Nexus is an AI company orchestration layer — a daemon that transforms a single developer into a functional AI organization. It is **not** a chatbot or assistant. It is the scheduling + spawning + budgeting engine that sits between Limen (human interface) and Atrium (data/state).

**Hard constraint**: Nexus has no database of its own. All state lives in Atrium (`:8100`). Nexus is pure behavior.

## Three-Layer Architecture

```
LIMEN  (Telegram + TUI — human interface, notifications, approvals)
  │ events / notifications
NEXUS  (orchestration engine — scheduler, spawner, budget tracker)
  │ read/write work_items
ATRIUM (data + state — work_items, agent_registry, budget_ledger, agent_results)
```

Nexus reads `work_items` and `workflows` from Atrium, spawns ephemeral agent subprocesses, writes results back to Atrium, and notifies Limen.

## Agent Spawning Model

Three execution tiers, selected per persona in `agent_registry`:

1. **Codex CLI/SDK** — headless long-running tasks; bundled subscription; cost estimation acceptable
2. **Claude Code CLI `--profile`** — persona operator with specialized `CLAUDE.md` identity; bundled subscription
3. **Direct Anthropic/OpenAI SDK** — structured workflows needing precise programmatic control, streaming, exact cost tracking

Example (Claude Code CLI tier):

```python
cmd = ["claude", "--profile", profile.config_path, "-p", build_prompt(work_item)]
proc = await asyncio.create_subprocess_shell(cmd, stdout=PIPE, stderr=PIPE)
```

Every agent is ephemeral: born, works, dies. State persists in Atrium, not the process. Agent profiles live under `agents/<capability-class>/CLAUDE.md`.

## Capability Classes (7 archetypes)

All 25+ roles collapse into 7 classes:

| Class              | Default model                 | Key roles                                                                    |
| ------------------ | ----------------------------- | ---------------------------------------------------------------------------- |
| Code Agent         | sonnet-4-6                    | bug finder/fixer, test expert, backend, DB, API/contract, library extraction |
| Security Agent     | sonnet-4-6 (escalate to opus) | hardening, vuln scan, penetration test, zero-day                             |
| Ops Agent          | sonnet-4-6                    | DevOps, hosting, infra, disaster recovery                                    |
| Quality Agent      | haiku-4-5                     | standards, WCAG, step verifiers                                              |
| Product Agent      | sonnet-4-6                    | frontend UX, web dev, designer, native apps                                  |
| Intelligence Agent | opus-4-6                      | ML, data science, agent design/prompting                                     |
| Growth Agent       | sonnet-4-6                    | marketing, social media, coach                                               |

Orchestrator is a meta-agent (no direct execution) — reads all agent state, prioritizes work_items, creates new ones for gaps.

## Atrium Schema (Step 0)

Tables to create in Atrium:

- `work_items` — `id, type, agent_role, priority (P0-P3), status (pending/running/done/failed), context JSON, result JSON, created_at, started_at, completed_at, token_cost`
- `agent_registry` — capability class profiles; fields: `execution_backend` (`codex-cli` | `claude-code-cli` | `anthropic-sdk` | `openai-sdk`), `model` (explicit per persona: gpt-4o, sonnet-4-6, haiku-4-5, opus-4-6…), `profile_path` (CLAUDE.md path or system prompt), `tool_allowlist`, `timeout_seconds`, `monthly_token_budget`
- `workflows` — DAG definitions: `id, name, steps JSON, created_at`
- `workflow_steps` — individual steps: `id, workflow_id, name, agent_role, depends_on (step IDs), condition (branching logic), execution_backend, model`
- `budget_ledger` — token consumption per agent per month; pause agent when budget exceeded
- `agent_results` — immutable audit log of all tool calls and outputs per run

## Implementation Sequence

1. **Step 0** — Atrium schema + CRUD endpoints (1 day)
2. **Step 1** — Code Agent as first citizen + minimal Nexus daemon (2-3 days); test: "find all TODOs in limen-assistant and open GitHub issues"
3. **Step 2** — Dashboard: standalone SPA webapp (separate project); FastAPI provides JSON API endpoints (1-2 days)
4. **Step 3** — `NexusAwarenessSource` in Limen heartbeat → morning digest (1 day)
5. **Step 4** — Security Agent with bandit + semgrep, nightly scheduled scan (2-3 days)
6. **Step 5+** — one capability class at a time when previous is stable

## Proactivity Contract

Nexus has two activation modes:

- **Heartbeat** (every N minutes): polls `work_items` pending and `workflows` ready to advance, spawns available agents
- **Event-driven**: Limen notifies Nexus of new urgent work_items

The morning digest surfaces: critical findings, stale PRs/issues, in-progress agents, suggestions (e.g. library extraction candidates).

## Execution Phases

- **Phase 1 (now)**: homelab (`homelab4change.siamese-dominant.ts.net`), asyncio subprocess; dedicated machine = no hard parallel agent limit
- **Phase 2 (~6 months)**: SSH dispatch to additional runners as needed
- **Phase 3 (overflow)**: Hetzner ephemeral VPS for heavy jobs (ML, large repo scans)

No containers needed in phases 1-2. The agent subprocess IS the isolation unit.

## Service Pattern

Same daemon pattern as `limen-assistant` and `radar-agent`:

```
nexus start|stop|restart|status|logs|doctor|health|update
```

Connects to Atrium at `$ATRIUM_URL` (default `localhost:8100`). No circular dependency with Limen — communicate via Atrium work_items or direct HTTP, never via shared code import.

## Repo Layout (target)

```
agents/
  code-agent/CLAUDE.md
  security-agent/CLAUDE.md
  ... (one dir per capability class)
src/nexus/
  daemon.py          # start/stop, heartbeat loop
  spawner.py         # subprocess management, three execution tiers
  scheduler.py       # work_items + workflow polling + dispatch
  budget.py          # token ledger checks
atrium/              # Alembic migrations for Nexus schema additions
# dashboard is a SEPARATE SPA project (not in this repo)
```

## Key Invariants

- Nexus never writes to disk except logs — all persistent state goes to Atrium
- Agent subprocess timeout is mandatory (set in `agent_registry.timeout_seconds`)
- Budget check BEFORE spawning, not after
- `work_items.status` transitions are append-only in audit log — never UPDATE the log, INSERT new rows
