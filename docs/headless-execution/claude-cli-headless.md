# Claude CLI — Headless Execution Findings

Empirically verified on **2026-04-20** with `claude 2.1.114 (Claude Code)` on Linux x86-64.

## Recommended Invocation

```
claude -p "<prompt>" --output-format json
```

Use `--output-format json` for all Nexus adapter calls. It gives you cost, session_id, and usage
in a single parseable envelope without extra stderr noise.

## Output Modes

### Plain text (`-p` only)

```
claude -p "your prompt"
```

- stdout: raw response text, trailing newline
- stderr: **empty** (no diagnostic noise)
- No ANSI escape codes in any condition (verified empirically)
- Useful for piped consumption when you don't need cost/session tracking

### JSON envelope (`-p --output-format json`)

```
claude -p "your prompt" --output-format json
```

stdout is a single JSON object:

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "result": "<plain text response>",
  "session_id": "uuid-here",
  "total_cost_usd": 0.064,
  "duration_ms": 3468,
  "duration_api_ms": 3038,
  "num_turns": 1,
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 3,
    "cache_creation_input_tokens": 14572,
    "cache_read_input_tokens": 32088,
    "output_tokens": 14
  },
  "uuid": "...",
  "fast_mode_state": null
}
```

stderr is **empty**.

## Useful Flags

| Flag                              | Effect                          | Notes                                            |
| --------------------------------- | ------------------------------- | ------------------------------------------------ |
| `-p` / `--print`                  | Non-interactive, print and exit | Required for all headless use                    |
| `--output-format json`            | JSON envelope output            | Recommended — gives cost + session_id            |
| `--output-format text`            | Plain text (default)            | No metadata                                      |
| `--output-format stream-json`     | Streaming JSON chunks           | Useful for long outputs                          |
| `--resume <session_id>`           | Resume a previous session       | session_id from prior `--output-format json` run |
| `--system-prompt "<text>"`        | Override system prompt          | How to apply agent personas                      |
| `--append-system-prompt "<text>"` | Append to default               | Less disruptive than --system-prompt             |
| `--model <alias>`                 | Model override                  | e.g. `sonnet`, `opus`, `haiku`                   |
| `--max-budget-usd <n>`            | Spend cap                       | Only works with `-p`                             |
| `--allowedTools <list>`           | Restrict tool use               | Space or comma-separated                         |
| `--no-session-persistence`        | Ephemeral — no save             | Faster for stateless tasks                       |

## Flags That Do NOT Exist

- `--profile` — **does not exist** (CLAUDE.md was aspirational). Use `--system-prompt` instead.
- `--bare` — exists but **exits with code 1** in headless `-p` mode; do not use.
- `--no-color` — does not exist as a flag. ANSI is never emitted in headless mode anyway.

## Exit Code Taxonomy

| Code | Meaning                                                                          |
| ---- | -------------------------------------------------------------------------------- |
| 0    | Success                                                                          |
| 1    | CLI error (bad flag, auth failure, API error)                                    |
| 143  | SIGTERM received (128 + 15). Process group kill via `os.killpg` works correctly. |

## Session Resumption

Works in headless mode. Capture `session_id` from the JSON envelope of turn 1, then pass
`--resume <session_id>` on turn 2. Verified empirically: specific values recalled correctly
across process boundaries.

## Applying Agent Personas (Profile Substitute)

Since `--profile` doesn't exist, inject persona via `--system-prompt`:

```text
Read CLAUDE.md from the agent profile directory, pass its contents as --system-prompt.
```

Or use `--append-system-prompt` to layer on top of the default system prompt.

## Process Group Cleanup

Always set `start_new_session=True` when spawning. On timeout, send SIGTERM to the
process group (`os.killpg`) and wait up to 5s before escalating to SIGKILL.
Exit code 143 indicates SIGTERM was received.

---

# Codex SDK — Migration Note

> **Note:** The former `codex-cli` subprocess adapter was replaced by the `codex-sdk` adapter
> in issue #57 (2026-04-21), using `openai-codex-sdk` (PyPI) which controls the local `codex`
> binary over JSON-RPC. An intermediate approach using `openai.chat.completions.create` was
> reverted because it lacked tool use, file system access, and session resumption.
>
> The `codex-sdk` adapter uses `openai_codex_sdk.Codex` — async streaming events
> (`ThreadStartedEvent`, `ItemCompletedEvent`, `TurnCompletedEvent`), `SessionMode.RESUMABLE`.
>
> Empirical Codex CLI findings from this section were used to inform mock design during
> Phase A and are preserved here for historical reference only.
