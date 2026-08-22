---
name: adk-sdd-new
description: "Start full Mobile SDD; an optional --add-repo flag start the same requirement in other repositories."
---

# ADK SDD New

Codex entrypoint for `/adk:sdd:new`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action.

## Mission
Initialize full Mobile SDD in the current repository. One optional `--add-repo` flag also starts this requirement in one other initialized repository.

## Implementation
**CRITICAL: This uses MCP tool calls, NOT bash commands**

When invoked:
1. Accept at most one `--add-repo <repo>` occurrence anywhere in the arguments. Remove the pair from the goal and store its value as `additionalRepoPath: string`; omit the field when absent.
   - Reject a missing value and show `/adk:sdd:new --add-repo <repo> <goal>`.
   - Reject two or more `--add-repo` flags. STOP and tell the user to add further repositories one at a time with `/adk:sdd:repo --add <repo>`.
   - Do not inspect the target repository yourself; MCP validates its platform and workspace.
2. Parse the remaining goal and referenced files. The goal is required.
   - If the argument starts with an exact existing local Spec name, or its existing `spec.md` path, reuse that Spec directory. Confirm `spec-status.data.mode === 'sdd'`; read `launch-prompt.md` and optional `source-spec-decision-record.md`, then follow the Guide's additive platform-adaptation rules. Do not create a second Spec or delete source-repository content.
3. Call the available MCP tool ending in `sdd-guide` with no `phase` and with `additionalRepoPath`, omitting `additionalRepoPath` when absent. This entrypoint always uses workflow mode `sdd`; do not ask the user to choose a mode.
4. Follow the returned playbook verbatim. When `additionalRepoPath` is non-empty and it reaches the handoff after creating the local Spec, use `spec-group(action="add", specName=<generated>, repoPath=additionalRepoPath, workflowMode="sdd", launchNow=<selected timing>)` exactly as instructed. Do not call an inspect action. MCP owns validation, repository membership, local Spec preparation, and any requested launch.
5. When `launchNow` is true, MCP has already handled opening the target repository session. Do not invoke Bash or another launcher. Relay `data.launch` output, error, and full Prompt verbatim; if Agent inference fails, follow the MCP retry guidance.

## Examples
- `/adk:sdd:new Create user authentication system`
- `/adk:sdd:new @prd_file.md Implement feature per PRD`
- `/adk:sdd:new Create a shared profile flow --add-repo ../ios-app`

