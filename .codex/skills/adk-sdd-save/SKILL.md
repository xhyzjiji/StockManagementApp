---
name: adk-sdd-save
description: "Save spec artifacts from workflow directory into the codebase. Use when the user wants /adk:sdd:save to persist specs."
---

# ADK SDD Save

Codex entrypoint for `/adk:sdd:save`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action. This mirrors the command at `commands/adk/sdd/save.md` — keep the two in sync.

## Mission

Persist a spec from `{workflow-dir}/specs/` into the codebase so it can be version-controlled with the code. Copies spec.md, requirements.md, design.md, tasks.md, explore.md to the target module's specs directory.

**Note**: Generally save after all tasks are completed. If tasks are incomplete, the tool will ask for confirmation.

## Implementation

**CRITICAL: This uses MCP tool call, NOT bash command**

**Workflow directory**: Determined by `--workflow-dir` arg in `.mcp.json` (e.g., `.ttadk/.adk-mobile`). Source specs are read from `{workflow-dir}/specs/{spec-name}/`.

When invoked:

1. **Resolve spec name and targetDir** from argument:
   - If argument has two parts (e.g. `story-archive src/feature-name/specs`): first is specName, second is targetDir.
   - If argument has one part: use as specName, targetDir omitted (auto-infer).
   - If argument missing: call `spec-list` first to get active specs, then ask user which one to save (or use current context spec if unambiguous).

2. **Run the Spec Optimization Advisory FIRST** (see the section below) — *before* persisting anything. Analyze the just-finished SDD session, show the user **Output A**, and **compute the advisory payload once** (hold it for step 3 — do not re-run discover/export on retries). Informational and **must not block**: continue to step 3 and save regardless of its result (or if it finds nothing).

3. **Find and call** the MCP tool ending with `spec-save`:
   - Tool name pattern: `mcp__*__spec-save`
   - Top-level `success: true` includes "needs confirmation / inference" flows (not an error). Use **`data.saved === true`** to confirm files were written; if `saved` is false, use the `require*` flags below.
   - Parameters:
     - `specName`: (required) the spec to save
     - `targetDir`: (optional) target directory; omit to auto-infer from File Manifest
     - `confirmOverwrite`: (optional) only pass on retry after user confirmed overwrite; do NOT pass on first call
   - `confirmTaskIncomplete`: (optional) only pass on retry after user confirmed save despite incomplete tasks; do NOT pass on first call
     - `optimizationAdvisory`: (optional) the advisory object computed once in the section below (schema there). **Only pass it if the resolved `spec-save` tool's `inputSchema` advertises an `optimizationAdvisory` property.** Older servers use `additionalProperties: false` and would reject an unknown param — which must never break the save — so on an older schema, omit it (the save proceeds; only the advisory telemetry is skipped). This removes any release-order dependency between this skill and the MCP server. When supported, attach the SAME computed object to **every** `spec-save` call in this run (including confirmation/inference retries) so it is present on the call that finally writes; the server reports it once on `data.saved === true`. Omit when the advisory found nothing.

4. **Handle tool responses**:
   - **requirePathConfirmation** (data.requirePathConfirmation): Code inference succeeded. Use AskUserQuestion: "Save to {data.inferredTargetDir}? Confirm or correct the path." If user confirms, call spec-save again with targetDir = data.inferredTargetDir. If user corrects, use the corrected path.
   - **requireModelInference** (data.requireModelInference): Code inference failed. Follow data.modelInferencePrompt: read spec, infer targetDir, confirm with user, then call spec-save with targetDir. If still unclear, use AskUserQuestion to ask user for targetDir.
   - **requireConfirmation** (data.requireConfirmation): Target already exists. Use AskUserQuestion to confirm overwrite. If user confirms, call spec-save again with confirmOverwrite: true.
   - **requireTaskConfirmation** (data.requireTaskConfirmation): Tasks not all completed (data.taskProgress e.g. "3/8"). Use AskUserQuestion: "Tasks not all completed (current {taskProgress}). Save anyway?". If user confirms, call spec-save again with confirmTaskIncomplete: true.
   - **success**: Report the saved path. (The advisory already ran in step 2.)

## Spec Optimization Advisory (runs at the START of save, before persisting)

At the start of `/adk:sdd:save` — **before** calling the `spec-save` MCP tool — look back at the just-finished SDD session and tell the user how the **initial** spec could have been stronger, so they can front-load it next time. This is **advisory only**: never edit the spec, never block or gate the save.

**bash vs MCP**: the `spec-save` action in Implementation is an **MCP tool call (never bash)**. This advisory's trace export, by contrast, **is** a local bash step (`python3 scripts/conversation_miner.py …`) — run it via bash. The "NOT bash" rule applies only to `spec-save`, not to this script.

Gate (best-effort, fast): if the export errors, no SDD session is found, or the trace ran clean (no clarifications / no revisions), emit nothing and continue immediately to the save. Any failure here must be swallowed — it must never stop the save or add noticeable latency.

1. **Export this session's trace** (reuse the kb-update-docs miner; no separate tool). From `.ttadk/plugins/ttadk/mobile-core/skills/kb-update-docs/` as the working directory:
   - Discover the SDD session for this repo (newest-first, SDD-fingerprinted):
     `python3 scripts/conversation_miner.py discover --project-path "<repo_root>" --format json`
   - Pick the session for the spec being saved: try exact `spec_name == <resolved specName>` first; if none, normalize (strip a leading `^\d+-` from either side, or match by suffix), newest first. Then export it **using that discover row's own fields** (do not hand-write placeholders):
     `python3 scripts/conversation_miner.py export --jsonl-path "<row.jsonl_path>" --source "<row.source>" --format json`
   - The export keeps the high-signal trace: `[AskUserQuestion]` + `[User selected]`, the generated `[SDD artifact: ...]` blocks, and human corrections; tool noise is dropped and secrets are redacted.

2. **Find where the flow paid for an under-specified initial spec** (evidence is required — only use what is actually in the trace):
   - every `AskUserQuestion` the flow had to ask → a gap the initial spec could have closed;
   - the **same** question re-asked in a later phase → a decision that wasn't durably locked;
   - approval-revision rounds → placeholder / naming / paraphrased-IDL style fixes;
   - user corrections of a wrong assumption.

3. **Show Output A — initial-spec gaps — to the user** (configured language), as a short, actionable list:
   - one line per gap: what to put in the initial spec next time + a one-line evidence quote from the trace;
   - lead with the cost it would have saved, e.g. "front-loading these would have saved N clarification rounds and M approval rounds on this spec";
   - if the trace ran clean (no clarifications, no revisions), say so and emit nothing — a clean trace is a valid result.
   - Do **not** ask the user to confirm or act; this is informational.
   - **Length budget (keep it tight)**: at most ~6 Output-A items, each a single short line (aim ≤ 25 汉字 / ~40 chars); the lead is one sentence. The same budget applies to B and C. No code blocks, no long quotes.

4. **Build the advisory payload** (only if step 2 found something) using this exact shape — the single source of truth — then hold it for Implementation step 3:

   ```json
   {
     "A": [ { "text": "<one short line>", "evidenceTurns": [21, 22] } ],
     "B": [ { "text": "<one short line>", "evidenceTurns": [59, 60] } ],
     "C": [ { "text": "<one short line>", "evidenceTurns": [19] } ],
     "costSignal": { "specClarifyQuestions": 4, "designReclarifyQuestions": 2, "designApprovalRounds": 3 }
   }
   ```

   camelCase keys. **`evidenceTurns`** = **0-based** indexes into the exported turn list from `conversation_miner.py export --format json` (positions *after* the export's filtering/redaction — do not map to raw logs). **`costSignal`** counts are best-effort (use `0` when undeterminable; handle all three together for comparability):
   - `specClarifyQuestions`: AskUserQuestion turns in the **spec** phase (clarifying spec content, before design/implementation discussion begins);
   - `designReclarifyQuestions`: AskUserQuestion turns in the **design** phase (technical / architecture / interface clarifications after the spec is locked);
   - `designApprovalRounds`: design-approval request→verdict round-trips (each "please approve / request changes" that awaits a user verdict = 1 round; re-phrasing without a new verdict doesn't count; a changes-then-resubmit is the next round).

   Keep `text` within the length budget (no code / long quotes). This shape matches the `optimizationAdvisory` param accepted by ai-sde's `spec-save`; this skill uploads nothing itself — passing the param lets the server report it once.

> The same trace also yields tool-side signals (improvements to `prd-to-spec`, bucket B) and template-side signals (the spec template, bucket C). A is shown to the user; A+B+C ride spec-save's existing telemetry via the `optimizationAdvisory` param (reported server-side as a `spec_optimization_advisory` workflow event). No separate upload channel.

## Examples

- `/adk:sdd:save` — Save current/only spec (or prompt to choose)
- `/adk:sdd:save story-archive` — Save spec named story-archive
- `/adk:sdd:save 1-story-archive` — Save spec with numeric prefix
- `/adk:sdd:save story-archive src/feature-name/specs` — Save to specified directory
