# ADR-0001 — Do Not Use Paperclip as Nexus Core

Date: 2026-04-18
Status: Accepted

## Context

During Nexus discovery, Paperclip was evaluated as a possible base for:

- agent orchestration
- dashboards and visibility
- heartbeat scheduling
- task and budget management
- multi-runtime execution across Claude, Codex, and custom agents

The evaluation confirmed that Paperclip has solid control-plane patterns, especially:

- heartbeat-based execution
- adapter abstraction
- budget and cost reporting
- approval gates
- dashboard-oriented visibility

However, Nexus already has a hard architectural constraint:

`Atrium` is the only persistent state authority. `Nexus` is behavior only.

## Decision

Nexus will **not** use Paperclip as its core platform, control plane, or system of record.

Nexus will instead be built as a **homegrown orchestration layer** that is:

- inspired by selected Paperclip patterns
- integrated directly with `Atrium`
- exposed through `Limen` as the human interface

Paperclip may be used as a reference implementation only.

## Rationale

Using Paperclip as the core would introduce structural problems:

1. State duplication
   Paperclip brings its own database and domain model, conflicting with Atrium-first ownership.

2. Split operational semantics
   Agents, tasks, approvals, and budgets would risk existing in both systems.

3. Product drift
   Nexus would become an integration around Paperclip instead of a coherent product.

4. Interface mismatch
   Paperclip is board-operator-centric, while Nexus must also support personal awareness, accountability, and proactive operating loops.

## Consequences

Nexus should implement, in its own architecture:

- heartbeat protocol
- runtime adapter contract
- work item lifecycle
- budget-aware spawning
- audit log and run records
- lightweight operational dashboard

Nexus should **not** adopt:

- Paperclip database ownership
- Paperclip task/project/goal model as canon
- Paperclip UI as the primary operating surface

## Follow-up

The next design work should define:

1. minimum Atrium schema for Nexus
2. heartbeat contract for agents
3. adapter contract for Codex, Claude, `process`, and `http`
4. morning digest query model
5. first agent profiles to implement

## References

- [Nexus Vision](../development/nexus-vision.md)
- [Paperclip Quickstart](https://docs.paperclip.ing/start/quickstart)
- [Paperclip Architecture](https://docs.paperclip.ing/start/architecture)
- [Paperclip Core Concepts](https://docs.paperclip.ing/start/core-concepts)
