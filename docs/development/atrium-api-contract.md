# Atrium API Contract — Nexus Phase C

Frozen before Phase C fan-out. Pydantic shapes in `src/nexus/models.py` are authoritative.

## Implementation status

Most endpoints already exist in Atrium as of Phase C kickoff:

| Endpoint                               | Status                                  |
| -------------------------------------- | --------------------------------------- |
| `GET /api/work_items`                  | ✅ exists                               |
| `POST /api/work_items`                 | ✅ exists                               |
| `GET /api/work_items/{id}`             | ✅ exists (UUID)                        |
| `PATCH /api/work_items/{id}`           | ✅ exists (UUID)                        |
| `GET /api/workflows/{id}/steps`        | ✅ exists (UUID)                        |
| `GET /api/agent_registry`              | ✅ exists                               |
| `GET /api/agent_registry/{agent_role}` | ✅ exists (lookup by agent_role string) |
| `GET /api/budget_ledger`               | ❌ missing — must implement             |
| `POST /api/cost_events`                | ❌ missing — must implement             |

The `atrium-api` agent for Phase C implements only the two missing endpoints.

## Base URL

`$ATRIUM_URL` (default `http://localhost:8100`)

## Key schema notes

- All Nexus-domain table PKs are **UUID**, not int.
- `AgentRegistry` lookup key is `agent_role` (string), not id.
- `BudgetLedger` is keyed by `(agent_role, year_month)` where `year_month` is a date.
- Budget cap lives in `AgentRegistry.monthly_token_budget`; usage lives in `BudgetLedger.tokens_consumed`.
- Cost events use `tokens_input` + `tokens_output` + `tokens_total` (not a single `tokens_used`).

## Error envelope (all 4xx / 5xx)

FastAPI default: `{"detail": "<message>"}`. Handle 404 with `raise HTTPException(status_code=404, detail="...")`.

---

## Endpoint specs for existing endpoints (reference)

### `GET /api/work_items`

Query params: `status` (optional), `agent_role` (optional), `limit` (default 100, max 1000).
Response 200: `list[WorkItemRead]` — see `atrium/backend/app/schemas/work_item.py`.

### `POST /api/work_items`

Body: `WorkItemCreate` — `type`, `agent_role`, `priority` (default P2), `context` (default {}).
Response 201: full `WorkItemRead`.

### `PATCH /api/work_items/{id}`

Partial update: `status`, `result`, `token_cost`, `started_at`, `completed_at`.
Response 200: full `WorkItemRead`. 404 if not found.

### `GET /api/agent_registry/{agent_role}`

Returns `AgentRegistryRead` by `agent_role` string. 404 if not found.
Fields include: `monthly_token_budget`, `timeout_seconds`, `execution_backend`, `model`.

---

## Missing endpoints — Phase C atrium-api agent implements these

### `GET /api/budget_ledger`

Query params (both required):

- `agent_role: str`
- `year_month: str` — `YYYY-MM` format (convert to `date` internally: `date(int(y), int(m), 1)`)

Response 200:

```json
{
  "id": "<uuid>",
  "agent_role": "code-agent",
  "year_month": "2026-04-01",
  "tokens_consumed": 5000,
  "cost_usd": 0.015,
  "run_count": 3,
  "paused_at": null,
  "created_at": "2026-04-20T12:00:00Z",
  "updated_at": null
}
```

Response 404 if no ledger row for that `(agent_role, year_month)` pair.
Nexus budget checker treats 404 as "no usage yet → allow spawn".

Implementation notes for Atrium:

- Add `schemas/budget_ledger.py` with `BudgetLedgerRead`.
- Add `services/budget_ledger_service.py` with `get_budget_ledger(session, agent_role, year_month)`.
- Add `routes/budget_ledger.py` with `GET /api/budget_ledger`.
- Register router in `main.py`.
- Follow existing async patterns (SQLAlchemy async session, `async with session.begin()`).
- `year_month` param arrives as string `"2026-04"` → parse to `date(2026, 4, 1)` for DB query.

### `POST /api/cost_events`

Request body:

```json
{
  "agent_role": "code-agent",
  "work_item_id": "<uuid or null>",
  "workflow_step_id": "<uuid or null>",
  "execution_backend": "claude-code-cli",
  "model": "claude-sonnet-4-6",
  "tokens_input": 1000,
  "tokens_output": 500,
  "cost_usd": 0.003,
  "cost_source": "exact",
  "year_month": "2026-04-01",
  "occurred_at": "2026-04-20T12:05:00Z"
}
```

`tokens_total` is computed server-side as `tokens_input + tokens_output`.

Response 201: full `CostEventRead`.

Side effect (CRITICAL): After inserting the cost event, atomically upsert `budget_ledger`:

```sql
INSERT INTO budget_ledger (agent_role, year_month, tokens_consumed, cost_usd, run_count)
VALUES ($1, $2, $3, $4, 1)
ON CONFLICT (agent_role, year_month) DO UPDATE
SET tokens_consumed = budget_ledger.tokens_consumed + EXCLUDED.tokens_consumed,
    cost_usd = budget_ledger.cost_usd + EXCLUDED.cost_usd,
    run_count = budget_ledger.run_count + 1,
    updated_at = now()
```

Implementation notes:

- Add `CostEventCreate` schema to `schemas/cost_event.py`.
- Add `create_cost_event(session, data)` to `services/cost_event_service.py`.
- Add `POST /api/cost_events` route to `routes/cost_events.py`.
- The upsert must be atomic — do both INSERT+UPSERT in the same transaction.
- `year_month` in body is ISO date string `"2026-04-01"` (Pydantic `date` field parses it).

---

## Budget check pattern (for nexus budget.py reference)

```python
# 1. Get current usage
resp = await client.get("/api/budget_ledger", params={"agent_role": role, "year_month": "2026-04"})
if resp.status_code == 404:
    return True  # no usage yet, allow spawn

ledger = BudgetLedger.model_validate(resp.json())
if ledger.is_paused:
    return False

# 2. Get budget cap from agent registry
agent_resp = await client.get(f"/api/agent_registry/{role}")
agent = AgentRegistryEntry.model_validate(agent_resp.json())

# 3. Compare
return not ledger.is_over_budget(agent.monthly_token_budget)
```
