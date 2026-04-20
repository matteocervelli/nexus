# ADR-0002 — Introduce an Internal Nexus Board Layer

Date: 2026-04-19
Status: Accepted

## Context

ADR-0001 established that Nexus will not use Paperclip as its core platform or system of record.

That decision avoids:

- database duplication
- domain duplication
- a second external control plane

However, the underlying need remains valid: Nexus still needs a paperclip-like surface for:

- org and role visibility
- approvals and governance
- budget tracking
- heartbeat supervision
- work status and auditability
- operational awareness for Matteo

Without such a layer, Nexus would be only a scheduler/spawner and would miss the management surface that makes an AI organization usable in practice.

## Decision

Nexus will introduce an **internal board layer**: a paperclip-like control surface implemented inside the Nexus architecture.

This layer:

- is part of `Nexus`, not a separate product
- reads and writes canonical state in `Atrium`
- exposes governance, visibility, and operator workflows
- does not own an independent database or domain model

Working formulation:

- `Limen` = human interface
- `Nexus Core` = scheduler, spawner, runtime adapters, policy enforcement
- `Nexus Board Layer` = board, governance, visibility, approvals, digest surface
- `Atrium` = canonical state, audit, work registry, documents, cost data

## Rationale

This resolves the apparent tension between two truths:

1. Nexus should not adopt Paperclip as an external core.
2. Nexus still benefits from having paperclip-like control-plane capabilities.

The correct move is therefore not "no Paperclip semantics at all".

It is:

- no external Paperclip dependency
- yes to an internal board/control-plane surface

This preserves architectural coherence while still giving Nexus the features required to operate an AI company rather than a pile of detached agents.

## Scope of the Board Layer

The internal board layer should cover:

- agent registry views
- role and reporting visibility
- work queue visibility
- approval workflows
- budget and cost summaries
- run history and audit summaries
- stale work and blocked work surfacing
- morning digest generation
- suggestion and escalation views

It may also provide lightweight organizational concepts such as:

- capability classes
- reporting lines
- escalation paths
- execution policies

## Non-Goals

The board layer must not:

- create its own persistent database
- replace `Atrium` as source of truth
- introduce a second task system outside Atrium
- fork a separate product identity from Nexus
- copy Paperclip schema or UI 1:1

## Consequences

Nexus is no longer described only as "scheduler + spawner".

It should now be described as:

- a core orchestration engine
- plus an internal board layer for management, governance, and visibility

This implies that future design work should explicitly separate:

- `Core runtime concerns`
  scheduling, adapter execution, timeout, budget enforcement, retries

- `Board concerns`
  digest, approvals, dashboards, org visibility, operating cues

## Implementation Guidance

Initial implementation should stay minimal.

Phase 1 board primitives:

1. `agent_registry`
2. `work_items`
3. `run_log`
4. `cost_events`
5. `approvals`
6. `digest_views`

Initial UI shape:

- FastAPI + HTMX
- operational tables and summaries
- no broad React platform required

## References

- [ADR-0001 — Do Not Use Paperclip as Nexus Core](./0001-paperclip-no-go.md)
- [Nexus Vision](../development/nexus-vision.md)
- [Nexus vs Paperclip](../development/nexus-vs-paperclip.md)
