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
| 1    | `codex-cli` / `openai-sdk` subprocess         | Headless bulk work, long-running scans |
| 2    | `claude-code-cli` subprocess with `--profile` | Persona-driven expert work             |
| 3    | `anthropic-sdk` / `openai-sdk` direct client  | Structured programmatic workflows      |

Each persona record in `agent_registry` must declare:

- `execution_backend`: one of `codex-cli`, `claude-code-cli`, `anthropic-sdk`, `openai-sdk`
- `model`: explicit model ID (e.g. `gpt-4o`, `claude-sonnet-4-6`, `claude-haiku-4-5`, `claude-opus-4-6`)

## Rationale

1. **Tier 1 (Codex)** handles bulk work efficiently within the OpenAI bundled subscription. Headless task execution does not require Claude's specialized toolset.

2. **Tier 2 (Claude Code persona)** is the primary execution tier for adlimen agent roles. The `--profile` flag loads a specialized `CLAUDE.md` that shapes tool access, persona, and task focus. This is the pattern already validated in the 7-capability-class design.

3. **Tier 3 (direct SDK)** is necessary for orchestration logic that requires structured JSON output, precise streaming control, or exact token cost tracking. The Nexus scheduler itself is a candidate consumer of this tier.

4. **One adapter interface for all tiers**
   Nexus runtime adapter contract (ADR-0003) must abstract over all three tiers. Callers dispatch a work item; the adapter resolves the right subprocess or API client based on `execution_backend`.

## Consequences

- `spawner.py` implements separate adapters for subprocess-based tiers (1, 2) and API-based tier (3)
- `codex` and `claude-code-cli` adapters inherit the same subprocess management pattern: `asyncio.create_subprocess_exec`, `asyncio.wait_for`, `os.killpg` cleanup
- `anthropic-sdk` and `openai-sdk` adapters use async HTTP client; no subprocess involved
- Token cost tracking: estimation for bundled tiers (1, 2), exact metered cost for API tier (3)
- `agent_registry` schema must include `execution_backend` and `model` as required fields — no defaults

## References

- [ADR-0003](0003-runtime-adapter-contract.md)
- [Nexus Vision](../development/nexus-vision.md)
