---
name: global-rule-creator
description: Create or refine global engineering Rule files for TikTok iOS/Android. Use when the user asks to write global rules, rule-* files, MUST/MUST NOT guidance, rule templates, or convert a Lark doc URL into global Rule content.
---

# Global Rule Creator

Use this skill to author agent-facing global Rule content. The output should be concise instructions that are safe to load in every session.

## Platform Placement

Write global rules to the platform's existing global rule location:

- iOS: `TikTok/infra/ai/claude/rules/` (`TikTok/.claude/rules/` may be a symlink to this directory).
- Android: `TikTok/.airef/rules/`.

Do not create or edit global rules outside these platform locations. If the target platform is unclear, ask the user or infer it from the repository path before editing.

Keep long reference material outside global rule directories: `TikTok/infra/ai/claude/references/` for iOS and `TikTok/.airef/references/` for Android. References are not global rules and should be read only when a Rule file explicitly points to them.

For Android, `.claude/settings.json` must load `TikTok/.airef/rules/*.md` from the `SessionStart` hook.

## Template

Use [rule.template.md](rule.template.md) as the default output shape. Match this template before adding extra sections.

The one-sentence description under `# Rule: <Topic Name>` should describe the durable topic area this Rule file owns, not enumerate only the scenarios currently present. Rule files grow over time, so keep the description broad enough for future rules in the same topic.

## Rule File Naming

For iOS, global rule files are topic files under `TikTok/infra/ai/claude/rules/`.

- New topic files must use `rule-<topic>.md`, for example `rule-network.md` or `rule-module-boundary.md`.
- Prefer updating an existing topic file when the rule clearly belongs there.
- Keep existing historical filenames unless the user explicitly asks for a rename.
- Keep long reference docs under `TikTok/infra/ai/claude/references/`.
- Do not put reference docs under `TikTok/infra/ai/claude/rules/`; everything under `rules/` is loaded as global context.
- Do not split one topic across multiple files unless the existing file is no longer reviewable.

For Android, global rule files are topic files under `TikTok/.airef/rules/`.

- New topic files must use `rule-<topic>.md`, for example `rule-meta-build.md`.
- Prefer updating an existing topic file when the rule clearly belongs there.
- Keep long reference docs under `TikTok/.airef/references/`, preserving existing reference filenames when moving files.
- Do not put reference docs under `TikTok/.airef/rules/`; everything under `rules/` is loaded as global context.

## Cursor Compatibility

Cursor rule files are maintained as symlinks under `TikTok/.cursor/rules/` and are referenced by `TikTok/.cursor/rules/project-rules.mdc`.

When adding, deleting, or renaming global rule files:

- MUST update the matching `.cursor/rules/` symlink.
- MUST update `.cursor/rules/project-rules.mdc` so it references the current rule filenames.
- MUST verify every `.cursor/rules/*.md` symlink resolves to an existing file.
- For Android, ensure `.gitignore` allows `.cursor/rules/` and `.cursor/rules/project-rules.mdc` to be tracked while keeping other generated `.cursor` content ignored.

## Owner

- When creating a new Rule file, ask the user for the `Owner` value before writing the file.
- When updating an existing Rule file, preserve the existing `Owner` unless the user explicitly changes it.
- Do not default `Owner` to the current logged-in user; the rule owner is the rule maintainer, not necessarily the person running the skill.

## Input Sources

If the user provides a Lark doc URL as rule source material, fetch the document before writing rules:

- Use the Lark document skill / `lark-cli` to read the source document.
- For large documents, inspect the outline first and read only sections relevant to the requested rule.

Convert the fetched content into global Rule content by extracting stable engineering constraints. Do not copy product background, meeting notes, broad explanations, or long procedures into the Rule file. Put focused reference material behind `MUST read <doc-name>.md`; put long operational workflows behind `MUST invoke <skill-name>`.

## Core Principles

- Global Rule is fully loaded, so every sentence must directly improve agent behavior.
- Global Rule is for cross-module, high-risk, stable, repeated engineering constraints.
- Do not put module-specific behavior, product domain explanation, or one-off workflow notes into global Rule.
- Use scenario sections with `WHEN` plus `MUST` / `MUST NOT`.
- Use `Context` only for facts required to apply the rule. Write it in simple, natural language; do not force a fixed format.
- Keep file-level ownership metadata short (`Owner`) so humans know who maintains the Rule file.
- Add lint references only when concrete and useful. Do not add `TBD` lint lines to agent-facing Rule text.

## When a Rule Belongs in Global Rule

First decide whether the proposed guidance is allowed in global Rule at all. Classification into `reliability`, `performance`, `security`, or another topic happens only after this gate passes.

Add or keep a rule globally only when it passes this specificity gate:

- It names a TikTok iOS/Android-specific API, helper, file, config, lifecycle, ownership boundary, build rule, dependency rule, or repeated local anti-pattern.
- Or it is backed by a concrete local source of truth, such as an existing repo rule, Lark design doc, lint rule, build check, owner guidance, or repeated review finding.

If a proposed rule only says what a capable coding agent should already know, delete it or do not create it. Platform-common rules such as "UI work must run on the main thread", "reuse cells", "handle errors", or "avoid heavy work on the main thread" must not be added just because they fit a topic file. Reject them directly instead of searching for helpers to justify them.

Do not upgrade a platform-common rule into global Rule content merely because a project wrapper, helper, dispatch API, or assertion exists. A helper makes the rule eligible only when the rule is specifically about using that TikTok-provided helper in a documented project workflow, lint/build check, owner guidance, or repeated local anti-pattern.

If the user asks whether a platform-common rule should be added, answer that it should not be added to global Rule unless the user provides a TikTok-specific source of truth or asks to investigate a concrete local anti-pattern.

After passing the specificity gate, the rule should satisfy most of these:

- It applies across many modules or the whole platform.
- Violating it causes security, privacy, reliability, architecture, performance, or long-term maintainability risk.
- Agents or developers have repeatedly made this mistake.
- The rule is stable and not tied to a short-lived product requirement.
- The rule can be written as a short, actionable instruction with clear exceptions.
- It has or can later have lint, build, benchmark, or review evidence.

If the rule is about a single module, put it in module docs such as `docs/rule.md`. If it explains business concepts or flows, put it in `domain.md` or `workflow.md`.

Before recommending or editing an existing Rule file, read that target file first. Do not suggest "add to rule-*.md" based only on the topic name.

## Content That Does Not Belong

Do not add or keep content that a capable coding agent should already know without TikTok iOS/Android context:

- Generic coding advice, such as "write complete code", "reuse existing code", "keep style consistent", "handle errors", or "avoid overengineering".
- Generic platform-common knowledge that is not narrowed to a TikTok iOS/Android constraint.
- Vague performance, reliability, robustness, security, or stability advice without a concrete platform boundary, API, file, owner, lifecycle, or repeated local anti-pattern.
- Pure architecture descriptions, directory inventories, dependency inventories, naming inventories, test matrices, product notes, meeting notes, or speculative guidance.

If the source material is mostly generic, do not create a global Rule file from it. Extract only stable TikTok-specific constraints, or report that no keep-worthy global Rule was found.

`Context` is not a place for broad background. Keep it to facts the agent must know before applying the following `WHEN` rules, explained briefly in plain language.

## When Guidance Should Reference a Doc

Use `MUST read <doc-name>.md` when the rule depends on a stable, focused reference document that is too detailed to inline but does not require an operational workflow. The referenced doc should be directly relevant to the trigger, reasonably short, and safe to load before acting.

Do not use doc references as a dumping ground for broad background reading. If the guidance is a step-by-step process with commands, scripts, examples, or troubleshooting branches, use a Skill instead.

## When Guidance Should Become a Skill

Global Rule should state what must happen, not teach a long operational workflow. If the proposed content includes many concrete steps, commands, scripts, examples, or troubleshooting branches, keep only the short trigger in the Rule file and move the detailed procedure into a Skill.

Use this split:

- Global Rule: a concise `WHEN` trigger plus `MUST invoke <skill-name>` for the detailed workflow.
- Skill: step-by-step instructions, command sequences, examples, references, and fallback handling.

When no suitable Skill exists, ask the user to create one with `/skill-creator` instead of expanding the global Rule body. After the Skill exists, add a short trigger in the relevant global Rule that tells the agent when to invoke it.

## Quality Checklist

- The rule follows [rule.template.md](rule.template.md).
- The rule is global, actionable, and not duplicated by an existing global rule.
- The rule passes the specificity gate and is not generic coding-agent knowledge.
- Any referenced doc is focused and necessary.
- Any long workflow is delegated to a Skill or marked as a `/skill-creator` follow-up.
