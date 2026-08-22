---
name: adk-sdd-list
description: "Show repository progress and Spec synchronization for local and multi-repository requirements."
---

# ADK SDD List

Codex entrypoint for `/adk:sdd:list`. Follow this workflow when the user invokes the matching slash command or asks for Mobile SDD status.

## Mission
Use `/adk:sdd:list` as the only status command for standalone and multi-repository requirements.

## Implementation
**CRITICAL: This uses MCP tool calls, NOT bash commands**

1. Parse at most one optional exact local Spec name. Do not accept status flags.
2. Call `spec-list` without parameters for the default summary, or with `specName: <spec>` for detail.
3. Default output: present each multi-repository requirement once and show every returned repository's platform, local Spec name, `specDir`, reachability, workflow mode, phase/status, task progress, and Spec synchronization status relative to the current repository (`in-sync`, `ahead`, or `behind`). Keep standalone Specs in the server's standalone summary form.
4. Exact-Spec detail: show the same per-member fields. For `behind`, also show returned added/deleted counts and summary diff chunks. Show standalone detail when the exact Spec is not grouped.
5. Ask only if the server reports ambiguity. Preserve server ordering, reachability, progress, and status; never read another repository to derive or enrich them. Treat returned `specDir` paths as informational/read-only.
6. If none exist, respond: **"No specs found. Run `/adk:sdd:new` to create one."**

## Examples
- `/adk:sdd:list`
- `/adk:sdd:list 004-profile-ios`

