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

# Codex CLI — Headless Execution Findings

Empirically verified on **2026-04-20** with `codex-cli 0.121.0` on Linux x86-64.

## Recommended Invocation

```
NO_COLOR=1 codex exec "<prompt>"
```

## Key Differences from Claude

| Dimension         | claude                  | codex                                          |
| ----------------- | ----------------------- | ---------------------------------------------- |
| stdout            | response text or JSON   | response text only                             |
| stderr            | empty                   | diagnostic header (version, model, session_id) |
| ANSI              | never                   | suppressed by `NO_COLOR=1`                     |
| SIGTERM exit code | 143                     | 0 (graceful)                                   |
| JSON mode         | `--output-format json`  | no equivalent                                  |
| Session resume    | `--resume <session_id>` | `codex exec resume` subcommand                 |
| Profile/persona   | `--system-prompt`       | `-c` config override                           |

## Output Structure

stdout: pure result text (no envelope)
stderr: human-readable diagnostic header containing session_id, model, workdir

```
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /path/to/project
model: gpt-5.4
session id: 019dabea-75a7-78b1-8e38-c1c3fd09e7a6
--------
```

Parse `session id:` line from stderr to extract session_id.

## Exit Code Taxonomy

| Code | Meaning                                        |
| ---- | ---------------------------------------------- |
| 0    | Success **or** graceful SIGTERM                |
| 1    | Error (unsupported model, API error, bad args) |

Note: codex returns exit code 0 on SIGTERM, unlike claude's 143. The adapter must not rely on
exit code alone to detect cancellation.

## Model Constraints

- Default model: `gpt-5.4` (ChatGPT account)
- `-m gpt-4o-mini` fails with ChatGPT auth ("model not supported")
- Only models approved for the connected account work with `codex exec`
- Do not assume arbitrary model strings will work

## ANSI Suppression

Set `NO_COLOR=1` in the subprocess environment. Verified to eliminate all ANSI from stdout.

## Implications for Nexus Adapters (Phase B)

1. **Claude adapter**: use `--output-format json` — cost, session_id, usage parsed directly.
2. **Codex adapter**: parse `session_id` from stderr, not stdout.
3. **Cancellation detection**: cannot rely on exit code for codex — track wall-clock timeout separately.
4. **Profile injection** for claude: read CLAUDE.md from profile dir, pass as `--system-prompt`.
