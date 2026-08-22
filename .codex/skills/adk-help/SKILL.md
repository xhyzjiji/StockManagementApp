---
name: adk-help
description: "Answer questions about TTADK Mobile SDD workflow, detect spec state via adk-mobile MCP, and recommend next steps. Use when the user asks about mobile SDD commands, MCP tools, or workflow guidance."
---

# ADK Help

Codex entrypoint for `/adk:help`. Follow this workflow when the user invokes the matching slash command or explicitly requests this mobile SDD action.

## User Input

```text
$ARGUMENTS
```
You **MUST** consider the user input before proceeding (if not empty).

If the given `$ARGUMENTS` contains a link, you need to read the content of the link (use lark-docs mcp if it's a lark doc) and replace the link with content.

## Context

**Read context before Executing**:

1. Language Setting
   - Read `preferred_language` from `.ttadk/config.json` (default: 'en' if missing). **IMPORTANT** **Use the configured language for ALL outputs: 'en' → English, 'zh' → 中文. This applies to: interactive prompts, status messages, explanations, and recommendations.**

## Goal

Serve as the TTADK Mobile intelligent assistant: answer user questions about SDD workflow, adk-mobile MCP tools, commands, knowledge base skills, dashboard, D2C integration, and best practices; optionally detect the current spec state when needed; and recommend appropriate next actions.

## Execution Steps

### 1. Analyze User Intent

Before gathering any context, classify the user's question:

| Category | Examples | Requires SDD State? |
|----------|---------|---------------------|
| **Knowledge Query** | "SDD 工作流是什么？", "`/adk:sdd:new` 怎么用？", "有哪些命令？", "Spec 模版怎么写？" | No |
| **State Analysis** | "我当前进度如何？", "下一步该做什么？", "帮我看看 spec 状态" | Yes |
| **KB Skills** | "怎么生成文档？", "kb-init-docs 怎么用？", "怎么跑 benchmark？" | No |
| **Troubleshooting** | "MCP 连不上怎么办？", "spec 报错了", "模型跑偏了" | Maybe |
| **Configuration** | "审批模式怎么切换？", "config.toml 怎么配？", "D2C 怎么开？" | No |

Use this classification to decide which steps to execute. **Skip unnecessary steps**.

### 2. Load Knowledge Base

Use the `adk-mobile-knowledge` skill to answer user questions:

1. Read the skill via `.ttadk/plugins/ttadk/mobile-core/skills/adk-mobile-knowledge/SKILL.md`
2. The SKILL.md contains an overview of SDD workflow, command quick reference, MCP tools, Spec template, config, and an **index to detailed sub-files**
3. Based on the user's question, follow the index in SKILL.md to read the relevant sub-files on demand:
   - **sdd-workflow.md**: SDD phases, approval flow, D2C integration, interrupt/resume, business customization
   - **commands-reference.md**: SDD commands, basic commands, KB skills, Spec template, config.toml, MCP/Preset config
   - **troubleshooting.md**: FAQ, MCP issues, interrupt recovery, D2C, iOS-specific issues

Do NOT read all sub-files blindly — only load what is needed based on the user's question topic.

### 3. Detect Current SDD State (Only When Needed)

**Skip this step** if the user is only asking knowledge-based questions.

**Execute this step** when the user's question involves their current project state, progress, or next steps.

1. **Call `spec-list`** to get all specs:
   - Tool name pattern: `mcp__*__spec-list`
   - Parse the returned multi-repository requirements and standalone Specs.

2. If specs exist, **call `spec-list` with `specName`** for the relevant group's member detail, then call `spec-status` for the relevant local Spec:
   - Tool name pattern: `mcp__*__spec-status`
   - Do not read another repository or infer member status.

3. Build a **state summary**:

```
SDD_STATE = {
  specs_count: N,
  active_spec: "...",
  current_phase: "requirements" | "design" | "tasks" | "implementation",
  phase_status: "pending" | "approved" | "in_progress",
  task_progress: "X/Y" (if in tasks/implementation phase),
  repository_count: N,
  repository_sync: [{ repository: "...", status: "in-sync" | "ahead" | "behind" }]
}
```

If no specs found → user has not started any SDD workflow yet.

### 4. Compose Response

Structure your response based on the user's intent:

**A. Current State Summary** (only when SDD state was detected in Step 3):

```
📍 Current Spec: [spec-name]
📋 Phase: [current phase] ([status])
📊 Tasks: [X/Y completed] (if applicable)
```

**B. Answer the Question**:

- If the user asked a specific question, answer it using the knowledge base and project context.
- Be concise and actionable. Prefer bullet points over long paragraphs.
- Reference commands with `/adk:sdd:command-name` format.
- Reference skills by name when relevant to the question.
- **Include documentation links**: If your answer references information from the knowledge base that has associated documentation links, include those links in your answer.
- If the knowledge base lacks information, acknowledge it and suggest using `lark-docs` MCP for Lark documents.

**C. Next Step Recommendation** (when SDD state was detected or user seems unsure):

| Current State | Recommended Next Step |
|---------------|----------------------|
| No specs | Run `/adk:sdd:new <goal>` for full SDD, `/adk:sdd:ff <goal>` for small fixes (≤10 files), or `/adk:sdd:spec <url>` to generate from PRD |
| Need another repository | Creation commands accept at most one `--add-repo`; add later members one at a time with `/adk:sdd:repo --add <repo>`. Repeated calls support same-platform and 3+ member groups |
| Remove a repository | Run `/adk:sdd:repo --remove <repo>`; the current repository cannot remove itself |
| Spec sync is `behind` | Start the next phase with `/adk:sdd:continue <local-spec>`; the phase guide offers Apply / Later / View |
| requirements phase | Review & Approve — design phase will follow automatically |
| design phase | Review & Approve — task breakdown follows automatically |
| tasks phase | Review & Approve — implementation follows automatically |
| implementation | Complete tasks, then `/adk:sdd:save` to persist spec, then `/adk:commit` |
| All done | `/adk:sdd:save` to persist, `/adk:commit` to push |

Use `/adk:sdd:list` for server-reported per-repository progress and `/adk:sdd:list <exact-spec>` for detail. It is the only status command.

For knowledge base tasks:
- New module? → Use `kb-init-docs` skill to generate docs
- Outdated docs? → Use `kb-update-docs` skill
- Check doc quality? → Use `kb-docs-validator` skill
- Measure doc usefulness? → Use `kb-docs-benchmark` skill

For interrupt/recovery:
- Model stuck? → Interrupt and say "continue"
- Model degraded? → `/clear` + `/adk:sdd:continue <spec-name>`

**D. Further Help** (always include at the end):

> 如果以上内容未能解决你的问题，你可以：
> - 📖 查阅 [TTADK Mobile 内测指引](https://bytedance.larkoffice.com/wiki/T8ACwQ7a7ifjf9kGq6jccvmenTc) 获取完整使用文档
> - 💬 加入 [Mobile AI SDE 内测反馈群](https://applink.larkoffice.com/client/chat/chatter/add_by_link?link_token=126v6b2c-d839-4a49-9c12-1e17e3oe09t2) 向团队成员提问

Adapt the language based on `preferred_language` setting (English or Chinese).

## Behavior Rules

- **Read-only**: This command MUST NOT modify any files. It is purely informational.
- **Lazy loading**: Only gather information (SDD state, knowledge sub-files) when the user's question requires it. Do not run all steps unconditionally.
- **Graceful degradation**: If MCP tools are unavailable, still answer knowledge-based questions using the ttadk-knowledge skill.
- **No hallucination**: If you don't know the answer, say so. Do not invent command options or workflow steps that don't exist.
- **Concise**: Keep responses focused and actionable.
- **Contextual**: Adapt the level of detail to the user's apparent expertise.
- **Link-rich**: When knowledge sources contain documentation links, always surface them in the response.
- **Fallback search**: When local knowledge is insufficient, suggest using `lark-docs` MCP for Lark documents.

