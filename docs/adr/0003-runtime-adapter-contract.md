# ADR-0003 — Define a Common Runtime Adapter Contract

Date: 2026-04-19
Status: Accepted

## Context

Nexus needs to orchestrate multiple execution backends while keeping a single control model.

The initial runtime targets are:

- `codex`
- `claude`
- `process`
- `http`

ADR-0001 and ADR-0002 already established two constraints:

- `Atrium` is the only persistent state authority
- `Nexus` includes an internal board layer, but runtime execution remains a core concern

Without a common adapter contract, each runtime would force different spawning logic, state handling, cost reporting, retry behavior, and audit semantics inside Nexus itself.

That would create brittle orchestration logic and make multi-runtime scheduling hard to reason about.

## Decision

Nexus will define a **common runtime adapter contract**.

Every adapter must expose the same conceptual interface to `Nexus Core`, regardless of the underlying runtime.

The contract standardizes:

- capability declaration
- environment validation
- heartbeat invocation
- run result normalization
- session handoff
- usage and cost reporting
- timeout and cancellation behavior

Nexus Core will talk only to this contract, not to runtime-specific implementations directly.

## Contract Shape

Each adapter must support these operations:

1. `describe()`
   Returns adapter identity, supported execution mode, supported session model, and declared capabilities.

2. `validate_environment(config)`
   Checks binaries, auth, permissions, network assumptions, and runtime prerequisites before execution.

3. `invoke_heartbeat(request)`
   Executes one unit of work for one agent against one `work_item` or wake context.

4. `resume_session(request)`
   Continues a previously known session when the runtime supports session continuity.

5. `cancel_run(request)`
   Attempts graceful stop first, then force termination when supported.

6. `collect_usage(run_handle)`
   Returns normalized usage and cost information for audit and budget enforcement.

7. `healthcheck(config)`
   Lightweight readiness probe for dashboard and operator visibility.

## Standard Input

`invoke_heartbeat()` must accept a normalized request containing at least:

- `agent_id`
- `agent_profile`
- `work_item_id`
- `work_type`
- `priority`
- `prompt_context`
- `tools_allowlist`
- `workspace_ref`
- `session_ref` if available
- `budget_limit`
- `timeout_seconds`
- `correlation_id`

The adapter may translate this into CLI args, HTTP payloads, env vars, temp files, or process contracts internally.

## Standard Output

Every run must return a normalized result with at least:

- `status`
  `succeeded`, `failed`, `cancelled`, `timed_out`, `budget_blocked`, `environment_error`

- `started_at`
- `finished_at`
- `stdout_excerpt`
- `stderr_excerpt`
- `result_payload`
- `usage`
- `cost`
- `session_before`
- `session_after`
- `external_run_id` if provided by the runtime
- `error_code`
- `error_message`

## Session Model

The adapter contract must support two session modes:

1. `ephemeral`
   No continuity guaranteed across invocations.

2. `resumable`
   The runtime can continue an identified session.

Nexus must not assume resumability.

Session continuity is adapter-specific, but the persisted reference must be normalized in Atrium through:

- `session_kind`
- `session_id`
- `session_metadata`

Adapters may persist richer internal state, but Nexus only relies on the normalized fields above.

## Budget and Timeout Rules

Budget and timeout policy are enforced by `Nexus Core`, not delegated to adapters as the primary control point.

Rules:

1. Budget is checked before spawn.
2. Adapter-level usage must be reported after every run.
3. Timeouts are mandatory for all adapters.
4. Adapters should support graceful cancellation where possible.
5. Missing usage data is treated as an audit incident, not silently ignored.

## Audit Requirements

Every adapter run must produce enough normalized data for:

- run history
- budget ledger updates
- operator visibility
- retry decisions
- incident investigation

At minimum, Nexus must be able to store:

- run lifecycle timestamps
- normalized status
- excerpts or references to logs
- session transition
- usage and cost
- runtime-specific identifiers

## Initial Adapter Set

Phase 1 adapters:

1. `codex`
   Local Codex CLI or equivalent Codex runtime wrapper.

2. `claude`
   Local Claude Code CLI subprocess execution.

3. `process`
   Generic local executable adapter for bounded scripts and tool wrappers.

4. `http`
   Remote runtime adapter over HTTP for controlled service-style agents.

## Non-Goals

This ADR does not define:

- the full Atrium schema
- board-layer UX
- agent capability taxonomy
- per-runtime prompt design
- plugin packaging

## Consequences

Nexus implementation should be separated into:

- `Core scheduler/spawner`
- `Adapter interface`
- `Adapter implementations`
- `Result normalization`
- `Budget and audit integration`

This also means new runtimes can be added only by implementing the contract, not by patching orchestration logic ad hoc.

## References

- [ADR-0001 — Do Not Use Paperclip as Nexus Core](./0001-paperclip-no-go.md)
- [ADR-0002 — Introduce an Internal Nexus Board Layer](./0002-internal-board-layer.md)
- [Nexus Vision](../development/nexus-vision.md)
- [Nexus vs Paperclip](../development/nexus-vs-paperclip.md)
