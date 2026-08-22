---
name: adk-sdd-repo
description: "Start or stop this requirement's development in another repository, optionally opening the added repository's session."
---

# ADK SDD Repo

Codex entrypoint for `/adk:sdd:repo`. Follow this workflow when the user invokes the matching slash command or explicitly asks to add or remove repositories for the current Mobile requirement.

## Mission
Manage one repository membership change for the current local Spec. Add may open the new repository's Agent session and copy its Prompt. Remove never opens a session.

## Implementation
**CRITICAL: Repository membership changes use MCP tools, never direct file or shell writes**

1. Parse exactly one mutually exclusive operation:
   - `--add <repo>`
   - `--remove <repo>`
   Reject neither/both operations, missing or multiple repository paths, or any other flags/positional arguments. The current repository cannot be removed; surface canonical-path validation from MCP for equivalent paths.
2. Resolve exactly one existing local Spec:
   - Use conversation context when it identifies exactly one local Spec.
   - Otherwise call `spec-list` without parameters, use the sole viable local Spec, and ask only when multiple local candidates remain.
   - STOP when none exist and suggest `/adk:sdd:spec`, `/adk:sdd:new`, or `/adk:sdd:ff`. Never choose the most recent Spec automatically.
3. For `--add`:
   - Resolve workflow mode from server-returned state. If unset, ask exactly once with four combined choices: **Fast-Flow/Open now (recommended)**, **Fast-Flow/Later**, **Full SDD/Open now**, or **Full SDD/Later**. Store both mode and launch timing; never default silently.
   - If mode is already known, ask **Open now / Later** before calling MCP. Store the answer as `launchNow`; never ask after the tool call.
   - Call `spec-group(action="add", specName=<resolved>, repoPath=<single target>, workflowMode=<resolved or selected>, launchNow=<selected timing>)` directly. Do not call an inspect action or inspect target files yourself.
   - Present `data.target`, its local Spec, and idempotent/already-added status.
     - **Open now**: MCP has already handled `data.launch`. Do not invoke Bash or another launcher. Relay its output, error, and full Prompt verbatim. Launch failures never undo MCP state.
     - **Later**: show `launchPromptFile`. Rerunning the same `repo --add` operation is the idempotent reopen path.
   - Add further repositories by repeating this command once per repository against the same Spec; repeating the same target is idempotent.
4. For `--remove`:
   - Call `spec-group(action="remove", specName=<resolved>, repoPath=<single target>)`.
   - Report whether removal completed, was idempotent, or only cleaned the local roster because the target was unavailable.
   - Never ask to open or launch a session.
5. Never write local Spec or repository membership metadata directly.

## Examples
- `/adk:sdd:repo --add ../ios-app`
- `/adk:sdd:repo --remove ../ios-app`
