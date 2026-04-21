# ADR-0006 — Three-Tier Execution Model

Date: 2026-04-20
Status: Accepted

## Context

The original Nexus design assumed a single execution model: spawn a Claude Code CLI subprocess with a `--profile` pointing to a specialized `CLAUDE.md`. This works for persona-driven agent work, but different job types are better served by different runtimes.

Three categories of agent work emerged during discovery:

1. **Headless bulk work** — scan a repo, run linters, grep for patterns, batch analysis. These jobs are long-running, non-interactive, and do not require a persona identity.
2. **Persona-driven expert work** — backend implementation, design review, security audit. These jobs benefit from a specialized CLAUDE.md profile that shapes the agent's expertise and toolset.
3. **Structured programmatic workflows** — orchestration logic, structured output extraction, streaming responses, exact cost tracking. These jobs need precise control over tool calling and response format.

## Decision

Nexus uses **three execution tiers**:

| Tier | Backend                                       | Use case                               |
| ---- | --------------------------------------------- | -------------------------------------- |
| 1    | `codex-sdk` JSON-RPC binary subprocess        | Headless bulk work, long-running scans |
| 2    | `claude-code-cli` subprocess with `--profile` | Persona-driven expert work             |
| 3    | `anthropic-sdk` direct client                 | Structured programmatic workflows      |

Each persona record in `agent_registry` must declare:

- `execution_backend`: one of `codex-sdk`, `claude-code-cli`, `anthropic-sdk`
- `model`: explicit model ID (e.g. `gpt-4o`, `claude-sonnet-4-6`, `claude-haiku-4-5`, `claude-opus-4-6`)

## Rationale

1. **Tier 1 (Codex SDK)** handles bulk work via `openai-codex-sdk` (PyPI) which controls the local `codex` binary over JSON-RPC. Supports session resumption, tool use, filesystem access, and sandbox mode — the correct equivalent of `claude-agent-sdk` for OpenAI. Uses async streaming events (`ThreadStartedEvent`, `ItemCompletedEvent`, `TurnCompletedEvent`). An intermediate implementation using `openai.chat.completions.create` was reverted because it lacked tool use, file system access, and session resumption (see issue #57).

2. **Tier 2 (Claude Code persona)** is the primary execution tier for adlimen agent roles. The `--profile` flag loads a specialized `CLAUDE.md` that shapes tool access, persona, and task focus. This is the pattern already validated in the 7-capability-class design.

3. **Tier 3 (direct SDK)** is necessary for orchestration logic that requires structured JSON output, precise streaming control, or exact token cost tracking. The Nexus scheduler itself is a candidate consumer of this tier.

4. **One adapter interface for all tiers**
   Nexus runtime adapter contract (ADR-0003) must abstract over all three tiers. Callers dispatch a work item; the adapter resolves the right subprocess or API client based on `execution_backend`.

## Consequences

- `spawner.py` implements separate adapters for subprocess-based tiers (1, 2) and API-based tier (3)
- All three tiers implement the same `AdapterBase` interface (ADR-0003)
- `codex-sdk` adapter is `SessionMode.RESUMABLE`; `claude-code-cli` is `SessionMode.RESUMABLE`; `anthropic-sdk` may be ephemeral or resumable depending on implementation
- Token cost tracking: estimated from local pricing table for Tier 1 (`openai-codex-sdk` returns token counts via `TurnCompletedEvent.usage` but not cost); Tier 2 via claude-agent-sdk; Tier 3 exact via direct API response
- `agent_registry` schema must include `execution_backend` and `model` as required fields — no defaults

## References

- [ADR-0003](0003-runtime-adapter-contract.md)
- [Nexus Vision](../development/nexus-vision.md)
