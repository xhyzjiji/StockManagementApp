# SDT Telemetry Lifecycle (Mobile)

Use this procedure after `<SDT_ASSET_ROOT>` is resolved and before the Skill performs pre-checks, asks a user question, or
hands off to another workflow. The caller must substitute its own logical `SKILL_NAME`.

**The angle-bracket values below are literals you carry in context, not shell variables.** Each Bash call runs in a
fresh shell, so anything exported by one command is gone in the next: `$SDT_ASSET_ROOT` expands to empty — the command
becomes `node /scripts/sdt-track.js` and Node reports `Cannot find module` — and `$RUN_ID` does the same, which skips
`finish` entirely and leaves the round with no telemetry at all. Write every path and id out in full, in every command.

## Runtime value

Determine `<AGENT_RUNTIME>` from the current host:

- Cursor → `cursor`
- Claude Code → `claude_code`
- Codex → `codex`
- Coco → `coco`
- Trae CLI → `trae_cli`
- Unknown host → omit `--agent-runtime`; do not guess.

## Start

Run exactly once. Keep the `run_id` from its JSON output in context — you have to type it back into `finish`:

```bash
node "<SDT_ASSET_ROOT>/scripts/sdt-track.js" start \
  --skill-name "<SKILL_NAME>" \
  --agent-runtime "<AGENT_RUNTIME>"
```

If telemetry cannot run (for example, Node is unavailable), continue the SDT workflow. Telemetry is best-effort and must
never block or alter the user-facing workflow.

## Finish

Immediately before every final response, including a response that stops because a pre-check failed or the user cancelled,
run:

```bash
node "<SDT_ASSET_ROOT>/scripts/sdt-track.js" finish --run-id "<RUN_ID>"
```

Only run `finish` when a run id was obtained from `start`. Do not make telemetry failure a workflow failure.

## Verify-workflow fix confirmation event

Mobile SDT delegates build/lint/E2E fix loops to the platform verification workflow (e.g. harness-workflow). After
`adk-sdt-implement` reads the workflow's final artifacts and has an explicit, confirmed count of test-case failures fixed
by the internal wave fix loop, emit a separate event before the final response:

```bash
node "<SDT_ASSET_ROOT>/scripts/sdt-track.js" event \
  --skill-name "adk-sdt-implement" \
  --event-name fix_confirm \
  --agent-runtime "<AGENT_RUNTIME>" \
  --extra '{"fixed_issue_count":<N>,"remaining_issue_count":<M>,"issue_source":"verify_workflow_wave_fix"}'
```

Do not emit this event when the count is unknown or inferred. It is an independent business event and does not replace the
lifecycle `finish` call. Use only counts known from the workflow's report artifacts. Do not include failure messages, code
excerpts, credentials, tokens, or raw logs in telemetry.
