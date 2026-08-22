---
name: adk-sdd-revert
description: "Revert a spec to the start of a target phase. Use when the user wants /adk:sdd:revert to roll back workflow artifacts and recorded generated code."
---

# ADK SDD Revert

Codex entrypoint for `/adk:sdd:revert`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action.

## Mission

Roll back a spec's workflow to the beginning of a specified phase, removing all intermediate artifacts from that phase onward, safely reverting implementation-generated code recorded by the workflow manifest, cleaning up associated approval records, and recording the revert event for traceability. Requires explicit user confirmation before any destructive action.

## Implementation

**CRITICAL: This uses MCP tool call, NOT bash command**

When invoked:

### Step 1 — Resolve Target Spec

`spec name` is OPTIONAL. Resolution order:

1. **Argument provided** → use it directly.
2. **No argument** → infer from current conversation context (the spec being actively worked on in this session).
3. **Cannot infer** → ask the user which spec to revert.

### Step 2 — Determine Target Phase

Parse the `target phase` argument. Accept both singular and plural forms: `requirement`/`requirements`, `design`, `task`/`tasks`, `implementation`.

- If not provided or invalid: ask the user which phase to revert to.
- **Normalize for logging**: When calling the `log` tool in Step 6, always use the internal phase names: `requirements`, `design`, `tasks`, `implementation`. This applies to both the `phase` field and `data.revertedTo`.

### Step 3 — Assess Current State

1. **Find and call** the available MCP tool ending with `spec-status` to retrieve the current workflow state for the resolved spec.
2. Read existing artifact files in `{workflow-dir}/specs/{spec-name}/` (check `.mcp.json` for the `--workflow-dir` argument to determine the actual workflow directory) to confirm what currently exists:
   - `requirements.md`
   - `design.md`
   - `tasks.md`
   - `explore.md`
   - `spec.md` (from prd-to-spec flow)
3. Determine what will be affected based on the target phase:

   | Revert to | Preserved | Deleted / Reset |
   |-----------|-----------|-----------------|
   | `requirement` | `spec.md`, `events.jsonl` | `requirements.md`, `design.md`, `explore.md`, `tasks.md`, task implementation progress, recorded implementation-generated code, `d2c-output/` |
   | `design` | `requirements.md`, `spec.md`, `events.jsonl` | `design.md`, `explore.md`, `tasks.md`, task implementation progress, recorded implementation-generated code, `d2c-output/` |
   | `task` | `requirements.md`, `design.md`, `explore.md`, `spec.md`, `events.jsonl` | `tasks.md`, task implementation progress, recorded implementation-generated code |
   | `implementation` | `requirements.md`, `design.md`, `explore.md`, `tasks.md`, `spec.md`, `events.jsonl` | Reset all task checkboxes in `tasks.md` from `[x]`/`[-]` back to `[ ]`, recorded implementation-generated code |

   - `spec.md` is NEVER deleted (it originates from prd-to-spec and serves as the upstream source of truth).
   - `events.jsonl` is NEVER deleted (append-only audit log).
   - Recorded implementation-generated code is read from `{workflow-dir}/specs/{spec-name}/implementation-manifest.json`, which is maintained by the `log` tool during implementation.
   - `d2c-output/` is workflow-owned; the `sdd-code-revert` tool deletes it automatically when the target phase is `requirements` or `design` (reported as `d2cOutput.action="delete-dir"` in its result) — do not delete it manually.

4. If the target phase has no existing artifact (e.g., reverting to design but `design.md` doesn't exist yet), inform the user there is nothing to revert and STOP.

### Step 4 — Generated-Code Dry Run (REQUIRED)

**Find and call** the available MCP tool ending with `sdd-code-revert` with:

- `specName`: `{spec-name}`
- `targetPhase`: `{target phase}` normalized to `requirements`, `design`, `tasks`, or `implementation`
- `dryRun`: `true`

This returns the exact recorded source/resource file actions (`restore`, `delete`, `noop`) and any conflicts.

- If the tool reports conflicts or fails, STOP before confirmation/logging/deleting. Show the conflicts (or the error) and ask the user to resolve them manually before retrying.
- If the tool is unavailable, STOP and tell the user their ADK Mobile MCP package is too old for safe generated-code revert.
- Do this dry-run before `phase_revert` logging even if the user already included "confirm" in the same prompt. User confirmation authorizes execution; it does not permit skipping or reordering the dry-run. The dry-run result is the `codeRevertPlan` that must be recorded in the `phase_revert` audit event (Step 6).
- The tool retains `implementation-manifest.json` after a successful apply, marking it `revertedAt` and storing the applied result in `lastRevert` — do NOT delete the manifest manually.
- If the dry-run returns an empty plan (no recorded generated code, "0 file action(s)"), proceed normally — but say "no recorded generated code to revert" explicitly in the Step 5 confirmation instead of omitting the section.

### Step 5 — Confirmation (REQUIRED)

Present a clear, explicit summary of what will happen and **wait for user confirmation**. Format:

```
⚠️ Revert spec "{spec-name}" to the start of "{target phase}" phase.

Will be DELETED:
  - {workflow-dir}/specs/{spec-name}/design.md
  - {workflow-dir}/specs/{spec-name}/tasks.md
  - {workflow-dir}/specs/{spec-name}/explore.md
  - Related approval records for the above files
  - Implementation progress (task checkboxes reset)

Recorded code revert:
  - IMPORTANT: recorded implementation code changes WILL be reverted. For example, reverting from implementation to design restores/deletes the listed source/resource files before deleting design/tasks artifacts.
  - restore: {project-relative file}
  - delete: {project-relative file}
  - noop: {project-relative file}
  - delete-dir: {workflow-dir}/specs/{spec-name}/d2c-output/ (tool-reported; only when reverting to requirements/design and it exists)

Will be PRESERVED:
  - {workflow-dir}/specs/{spec-name}/requirements.md
  - {workflow-dir}/specs/{spec-name}/spec.md
  - {workflow-dir}/specs/{spec-name}/events.jsonl

This action cannot be undone. Type "confirm" to proceed or "cancel" to abort.
```

- Only proceed if user explicitly replies "confirm" (or clear equivalent like "yes", "go ahead").
- Any other response (including silence, ambiguity, or "wait") → abort and inform the user nothing was changed.
- The confirmation must explicitly mention recorded code revert when the dry-run contains any `restore` or `delete` action; do not hide it behind generic "implementation progress" wording.

### Step 6 — Log Revert Event (MUST succeed before Step 7)

**BLOCKING**: Call `log` first. Do NOT proceed to revert/delete until log returns success. If log fails (e.g. missing data.revertedTo), fix the parameters and retry — do NOT skip.

**Find and call** the MCP tool ending with `log`:

- `specName`: `{spec-name}`
- `event`: `phase_revert`
- `phase`: `{current phase}` — from Step 3 spec-status (e.g., implementation if reverting from impl to design)
- `data`: **REQUIRED**. `{ "revertedTo": "{target phase}", "deletedArtifacts": ["design.md", "tasks.md", ...], "codeRevertPlan": <dry-run data from sdd-code-revert>, "reason": "<user-stated reason or 'user-initiated revert'>" }`
  - `revertedTo` = target phase; status derivation uses this only
  - `codeRevertPlan` MUST be the exact dry-run result from Step 4. Do not call `phase_revert` before Step 4. (The tool also persists the applied plan into `implementation-manifest.json` as `lastRevert`; `codeRevertPlan` keeps the audit record local to `events.jsonl`.)

### Step 7 — Execute Revert

Only after Step 6 log succeeds, perform **in order**:

1. **Revert recorded generated code**: Call the MCP tool ending with `sdd-code-revert` again with the same `specName` and `targetPhase`, now with `dryRun=false`. If it reports conflicts or failure, STOP immediately; do not delete approvals or artifacts, do not reset tasks, and report to the user that generated-code rollback was blocked and no artifact deletion was attempted. This call also removes `d2c-output/` when applicable (reported in its result).
2. **Clean up approvals**: Call the MCP tool ending with `approvals` with action `delete` for each artifact file that will be removed.
3. **Delete artifact files**: Remove each file identified in Step 3 from `{workflow-dir}/specs/{spec-name}/` (excluding `d2c-output/` — the tool already removed it in sub-step 1 when applicable).
4. **Reset implementation progress** (when revert target is `implementation`): Reset all task checkboxes in `tasks.md` from `[x]` or `[-]` to `[ ]`.

### Step 8 — Completion Report

After successful revert:

1. **Confirm** what was deleted and what was preserved.
2. **Confirm generated-code revert result**: list restored/deleted files and any `d2c-output/` cleanup.
3. **Current state**: The spec is now at the start of `{target phase}` with no artifacts for that phase or beyond.
4. **Next step**: Suggest the user resume the workflow:
   - `/adk:sdd:continue {spec-name}` to re-enter the target phase and regenerate artifacts from scratch.

## Examples

- `/adk:sdd:revert design` — Revert the current spec to the start of design phase (deletes design.md, explore.md, tasks.md; reverts recorded generated code; tool removes d2c-output/)
- `/adk:sdd:revert 001-user-auth requirement` — Revert user-auth spec all the way back to requirement phase
- `/adk:sdd:revert task` — Revert to task phase (deletes tasks.md, implementation progress, and recorded implementation-generated code; preserves requirements + design)
- `/adk:sdd:revert implementation` — Redo implementation from scratch (resets all task checkboxes to `[ ]` and reverts recorded generated source files, keeps all spec documents intact)
