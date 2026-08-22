---
name: adk-sdd-spec
description: "Generate a Mobile technical Spec; an optional --add-repo flag start the same requirement in other repositories."
---

# ADK SDD Spec

Codex entrypoint for `/adk:sdd:spec`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action.

## Mission
Generate an initial client technical Spec in the current repository. One optional `--add-repo` flag also starts this requirement in one other initialized repository.

## Implementation
**CRITICAL: This uses MCP tool calls, NOT bash commands**

When invoked:
1. Accept at most one `--add-repo <repo>` occurrence anywhere in the arguments. Remove the pair and store its value as `additionalRepoPath: string`; omit the field when absent.
   - Reject a missing value and show `/adk:sdd:spec --add-repo <repo> <input>`.
   - Reject two or more `--add-repo` flags. STOP and tell the user to add further repositories one at a time with `/adk:sdd:repo --add <repo>`.
   - Do not inspect the target repository yourself; MCP validates its platform and workspace.
2. Require the remaining source input and infer `inputType` as `lark_url`, `local_file`, or `plain_text` when confident.
3. Call `mcp__adk-mobile__prd-to-spec` with:
   - `input`: the remaining source input
   - `inputType`: the inferred type when confident; omit otherwise and never pass `auto`
   - `platform`: only when explicitly known
   - `additionalRepoPath`: the single collected path; omit this field when absent
   - **Fresh start: call it with NO `phase` argument** — it returns the CORE workflow guide (HARD-GATE, Fast Path rules, and a phase index). The workflow is delivered progressively: pull each stage's full steps on demand by calling `prd-to-spec` again with `phase: '<id>'` **plus the same `input`** at the START of that stage, beginning with `phase: 'read-input'`. The CORE phase index lists every stage id and its order.
     - `specName`: once the `init-workspace` stage has named the spec, pass `specName: '<the spec folder name>'` on **every** later pull. Without it the tool re-derives the paths from the numbering on disk, and the spec directory you just created shifts them all by one.
     - `additionalRepoPath`: if this run was started with `--add-repo`, keep passing it on **every** later pull — the `downstream-handoff` stage needs it to render the multi-repo handoff.
     - **If context is lost mid-flow** (compaction, cold start, resume): call `prd-to-spec` again with NO `phase` to reload CORE, then resume the stage you were on.
4. Follow the returned playbook verbatim — pull exactly one stage at a time in phase-index order, and never run a stage from the CORE summary or from memory. It owns local Spec generation and the repository handoff:
   - It creates local `spec.md` and resolves `specName` first.
   - With an additional repository, it asks exactly once using four combined choices: **Fast-Flow/Open now (recommended)**, **Fast-Flow/Later**, **Full SDD/Open now**, or **Full SDD/Later**. It maps that answer to mode and `launchNow`, then calls `spec-group(action="add")` exactly once.
   - Never run a second handoff, call an inspect action, or write repository membership/local Spec state directly.
   - Preserve **auto-reading linked Lark docs** when relevant to template sections (e.g. tracking doc → Event Tracking); use `lark-docs` MCP as instructed.
5. Follow the launch timing already collected by the combined choice; never ask Open now/Later again. When `launchNow` is true, MCP has already handled opening the target repository session. Do not invoke Bash or another launcher; relay `data.launch` output, error, and full Prompt verbatim.

## Examples
- `/adk:sdd:spec https://bytedance.larkoffice.com/docx/xxxxxxxxxxxx`
- `/adk:sdd:spec docs/prd.md`
- `/adk:sdd:spec "Add a shared profile contract" --add-repo ../ios-app`
