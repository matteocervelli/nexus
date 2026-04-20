# Nexus Development Conventions

Frozen before Phase B fans out. All agents working on this repo must follow these.

## Logging

```python
import structlog
logger = structlog.get_logger(__name__)
```

- JSON output in production (`structlog.configure(...)` in `daemon.py`), human-readable in dev.
- Always bind contextual fields at call site: `logger.info("work_item.started", work_item_id=item.id)`.
- Never use `print()` in `src/`. Tests may use it freely.

## HTTP Client

- One `httpx.AsyncClient` per daemon lifetime, injected as a dependency — never created per-call.
- Base URL from `$ATRIUM_URL` (default `http://localhost:8100`).
- All Atrium calls go through a single `AtriumClient` wrapper (to be created in Phase C).
- Timeouts: connect=5s, read=30s, write=10s — always explicit, never unbounded.

## Error Handling

Adapter errors must not leak raw exceptions across the adapter boundary. Wrap in:

```python
AdapterResult(
    status="failed",
    error_code="SPAWN_ERROR",
    error_message=str(exc),
    ...
)
```

Status literals (from ADR-0003 — canonical set):
`succeeded | failed | cancelled | timed_out | budget_blocked | environment_error`

Note: the issue #10 sketch used `success/timeout` — these are **wrong**; use the ADR-0003 values above.

## Pydantic Models

- All cross-boundary shapes are Pydantic v2 `BaseModel` — no plain dataclasses at API boundaries.
- Atrium mirror shapes → `src/nexus/models.py`.
- Adapter I/O shapes → `src/nexus/adapter_base.py`.
- `model_config = ConfigDict(frozen=True)` on request/result types (they are value objects).

## File Size

Hard cap: 500 lines per file. Split by responsibility when approaching the limit.

## Testing

- Marker `integration` → requires live CLI tools (claude, codex). Skip with `-m "not integration"`.
- Marker `e2e` → full daemon + Atrium stack. Skip with `-m "not e2e"`.
- Default `pytest tests/` runs only unmarked tests (unit + mocked).
- `atrium_mock` fixture (respx) and `tmp_profile_path` fixture available from `conftest.py`.

## Subprocess Spawning (preview — detail in Phase C)

Use `asyncio.create_subprocess_exec` (not `asyncio.create_subprocess_shell`) to prevent shell injection.
Pass arguments as a list, never as an interpolated string.
Always set `start_new_session=True` to enable process-group cleanup on timeout.
Timeout via `asyncio.wait_for(proc.communicate(), timeout=seconds)`.
Cleanup via `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` — not just `proc.kill()`.

## Commit Style

Conventional commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
Issue linking: `Fixes #N` in commit body (auto-closes GitHub on merge).
