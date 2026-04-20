# Repository Guidelines

## Project Structure & Module Organization

This repository is currently documentation-first. Use these paths consistently:

- `docs/development/` — working architecture notes and product decisions such as `nexus-vision.md` and `nexus-paperclip-assessment.md`
- `CLAUDE.md` — canonical implementation direction, target layout, invariants, and service model
- `.claude/memory/local/` — local assistant memory; treat as workspace state, not product source

Target code layout, once implementation starts, is defined in `CLAUDE.md`:

- `src/nexus/` for daemon, scheduler, spawner, and budget logic
- `agents/<capability-class>/CLAUDE.md` for agent profiles
- `atrium/` for schema and migrations owned by Atrium integration
- The dashboard is a **separate SPA webapp project** (not in this repo); Nexus exposes FastAPI JSON API endpoints that the SPA consumes

## Build, Test, and Development Commands

No build or test toolchain is checked in yet. Until code exists, use lightweight validation:

- `rg --files .` — inspect repository contents quickly
- `sed -n '1,200p' CLAUDE.md` — review the current technical contract
- `find docs -maxdepth 3 -type f | sort` — verify documentation placement

When implementation begins, keep the service interface aligned with the planned daemon pattern:

- `nexus start|stop|restart|status|logs|doctor|health|update`

Only document commands in this file after they exist in the repository.

## Coding Style & Naming Conventions

- Prefer Python for the service core, following the architecture in `CLAUDE.md`
- Use 4-space indentation and type hints on all function parameters
- Keep files under 500 lines and functions under 50 lines
- Use `snake_case` for Python modules and functions, `kebab-case` for Markdown filenames
- Write comments only to explain why, not what

## Testing Guidelines

There is no test suite yet. When tests are introduced:

- Mirror the source tree under `tests/`
- Name files `test_<module>.py`
- Cover scheduler behavior, budget enforcement, and agent spawning timeouts first
- Add at least one failure-path test for each new integration with Atrium or agent runtimes

## Commit & Pull Request Guidelines

Git history is not initialized in this workspace, so no project-specific commit pattern can be inferred yet. Use Conventional Commits going forward, for example:

- `feat: add work item scheduler skeleton`
- `docs: refine nexus architecture invariants`

PRs should include:

- a short problem statement
- the architectural impact
- linked issue or decision doc when applicable
- screenshots or log excerpts for dashboard or daemon behavior changes

## Security & Configuration Tips

- `Atrium` is the only persistent state authority; Nexus must not create its own database
- Agent execution uses three tiers: Codex CLI/SDK (headless tasks), Claude Code CLI `--profile` (persona operator), direct Anthropic/OpenAI SDK (programmatic control + exact cost tracking). The `agent_registry` record drives which tier is used per persona.
- Do not commit secrets, API keys, or local memory artifacts
- Keep `.claude/memory/local/` local-only unless explicitly curated into docs
