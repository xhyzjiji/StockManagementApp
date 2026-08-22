---
name: adk-sdd-continue
description: "Resume an existing Mobile SDD or Fast-Flow workflow; a Lark URL can reverse-resolve and sync feedback to its local FF plan, or --revise can create a new Plan revision in the same FF spec."
---

# ADK SDD Continue

Codex entrypoint for `/adk:sdd:continue`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action.

## Mission
Resume an existing SDD or Fast-Flow workflow from its last checkpoint. A Lark/Feishu URL may reverse-resolve a local FF Spec and sync document feedback into local `plan.md` before resuming. `--revise "<new bug>"` deterministically creates a new Plan revision inside the same FF spec; it never creates a new workflow.

## Implementation
**CRITICAL: Workflow state uses MCP tools; Lark-backed FF feedback follows the explicit sync-back steps below**

1. Parse `<local-spec | Lark doc URL> [--revise "<new bug>"]` before resolving the spec. A missing/empty revise value is an error. In revise mode, never call `spec_created` or `ff_begin`, never create a spec directory, and never route to fresh `/adk:sdd:ff` based on model judgment.
2. Require `<local-spec | Lark doc URL>` after removing `--revise`. If missing, STOP before any MCP call and show that usage.
3. Resolve exactly one Spec in the current repository:
   - **Lark/Feishu URL** matching a supported `/docx/`, `/wiki/`, `/doc/`, or `/sheets/` path:
     1. Extract the final document token, excluding a query string or trailing slash.
     2. Read the `adk-mobile` server's `--workflow-dir` from `.mcp.json` or `.cursor/mcp.json`; default to `.ttadk/.adk-mobile`.
     3. Search local `{workflow-dir}/approvals/*/lark-approval.json` for the token or URL.
     4. If needed, fall back to local `{workflow-dir}/specs/*/events.jsonl` and match a `phase_approved` event by `data.docId`/`data.docUrl`.
     5. Ask when multiple local Specs match. If none match, STOP with “该飞书文档未关联到任何本地 FF spec” and list local Lark-backed Specs.
     6. Retain the input `docUrl` and matched approval state's `docId`/`docUrl`.
   - **Local Spec name**: call `spec-list` with `specName` first; otherwise match number/prefix or partial name against the full list of current-repository Specs. Ask only when ambiguous and STOP with the local list when no match exists.
4. Call `spec-status` with the resolved local `specName`.
5. **If revise mode**:
   - Require `data.mode === 'ff'`; otherwise STOP.
   - Load the CORE FF guide. Log `custom` / `revision_created`, then `phase_revert` for Plan using the existing spec and the supplied bug as the reason.
   - Update the same `spec.md` with durable clarified context and regenerate the same `plan.md`; do not create a new spec.
   - The Plan must put `本轮 Bug 修复方案` first, followed by `原有内容 Clarify`, `上下文沉淀`, and `审批信息`.
   - Pull `sdd-ff-guide(phase='plan', specName=<resolved>)` and run Artifact Review for the current Plan. Only `pass` permits a new Plan approval request; `needs_revision`, `blocked`, timeout, and error block it.
   - HARD STOP before implementation or business-code edits until this revision receives a new Plan approval. Parent-revision approval is invalid.
   - After approval, load `sdd-ff-guide(phase='implementation', specName=<resolved>)` and continue the same FF spec. Do not run Lark sync-back or the normal resume mapping.

### Lark feedback sync-back

Only in resume mode, when resolution used a Lark URL and `data.mode === 'ff'`:

1. Load `sdd-ff-guide` with no `phase`, then call `lark-doc-fetch` with the resolved URL. Keep fetched markdown and read `data.commentsFile` when present.
2. Determine the next resume phase from `spec-status` and the guide:
   - Before Implementation, fetched body replacement is allowed.
   - In Implementation, never replace the local body because local task checkboxes record progress.
3. Update only local `{workflow-dir}/specs/{specName}/plan.md`: replace the fetched body only when allowed, and apply actionable unresolved comments at their quoted anchors in either case. Track addressed comment IDs.
4. If local `plan.md` changed, push it once with `lark-cli docs +update --doc <docId> --mode overwrite --markdown @{workflow-dir}/specs/{specName}/plan.md`; HARD STOP on `ok === false`.
5. Mark addressed comments solved with `lark-cli drive file.comments patch` using returned `fileToken`/`fileType`. Warn and continue on an individual resolve failure.
6. Persist `lastFetchedAt` and remaining `unresolvedCommentCount` in `approvals/{specName}/lark-approval.json`. Continue silently when nothing changed.

### Resume workflow

6. Resume by mode:
   - FF: load `sdd-ff-guide` with no `phase` unless already loaded, map the resume hint, then call `sdd-ff-guide(phase='plan', specName=<resolved>)` or `sdd-ff-guide(phase='implementation', specName=<resolved>)`. Log `log(event='custom', phase='plan'|'implementation', data={ mode:'ff', eventName:'resumed', resumedFrom:'<data.lastEvent>', resolvedFromDoc:'<input URL>' })`; omit `resolvedFromDoc` when a Spec name was used.
   - Standard SDD: load `sdd-guide` with no `phase`, follow `nextSteps`, then call `sdd-guide(phase='requirements'|'design'|'tasks'|'implementation', specName=<resolved>)`.
   - Every phase-bearing guide call must include the resolved `specName`.

## Examples
- `/adk:sdd:continue 004-profile-ios`
- `/adk:sdd:continue 001`
- `/adk:sdd:continue user-auth`
- `/adk:sdd:continue https://bytedance.larkoffice.com/docx/XXXXXXXX`
- `/adk:sdd:continue 001 --revise "New regression after the first fix"`
