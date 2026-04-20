# ADR-0005 — Workflow Engine with Serialized and Branching Sessions

Date: 2026-04-20
Status: Accepted

## Context

The initial Nexus design described a flat `work_items` queue: Nexus polls for a pending item, spawns an agent, writes the result back. Simple, easy to implement.

During discovery it became clear that real tasks require multiple steps with dependencies:

- A code implementation step whose output feeds directly into a test execution step
- A branch point: if tests fail → spawn a bug-fixer agent; if tests pass → spawn a quality audit agent
- Each step runs a different persona with a different model and execution backend

A flat queue cannot express ordering, branching, or step-level context threading. The work item model needs to be extended to a workflow DAG.

## Decision

Nexus is a **workflow engine** for DAGs of agent sessions.

Two new tables are added to the Atrium schema:

**`workflows`**
Represents a named multi-step orchestration. Fields: `id`, `name`, `status` (`pending` / `running` / `done` / `failed`), `dag` (JSON — step IDs and edges), `created_at`, `started_at`, `completed_at`.

**`workflow_steps`**
Represents one node in the DAG. Fields: `id`, `workflow_id`, `step_index`, `depends_on` (JSON list of step IDs), `condition` (expression string or null), `execution_backend`, `model`, `agent_role`, `prompt_context`, `status`, `result`, `started_at`, `completed_at`.

Single-step dispatches continue to use `work_items`. Multi-step orchestration uses `workflows` + `workflow_steps`.

## Rationale

1. **Real tasks are not atomic**
   A "fix this bug" task naturally decomposes into: reproduce → implement fix → run tests → open PR. Each step depends on the previous output.

2. **Branching is not optional**
   The difference between "tests passed, proceed to quality audit" and "tests failed, spawn bug fixer" cannot be expressed in a flat queue without encoding it implicitly in each agent's prompt. Explicit branching in the DAG is cleaner and auditable.

3. **State must survive restarts**
   Storing each step's status in Atrium means a daemon crash does not lose workflow progress. The scheduler re-reads step state on startup and continues from where it left off.

4. **`work_items` is not replaced**
   Simple one-shot dispatches (e.g. "summarize this issue") stay as `work_items`. Workflows are for compound orchestration only. This keeps the common case simple.

## Consequences

- Nexus scheduler must resolve DAG ordering before spawning any step in a workflow
- Branching requires evaluating `condition` expressions against prior step `result` fields
- MVP scope: serialized steps only (linear DAG, no branching). Branching is implemented in the next phase.
- Nexus never stores workflow state in memory — all checkpointing is in Atrium `workflow_steps`
- Atrium migrations must add `workflows` and `workflow_steps` tables before Nexus Step 2

## References

- [ADR-0003](0003-runtime-adapter-contract.md)
- [Nexus Vision](../development/nexus-vision.md)
