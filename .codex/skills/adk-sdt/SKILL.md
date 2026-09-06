---
name: adk-sdt
description: "Use when the user wants to run the Mobile SDT (Spec Driven Test) workflow but has not specified a stage. Routes to adk-sdt-ff, adk-sdt-clarify, or adk-sdt-implement based on feature test-file state and user intent. iOS/Android 双端通用。"
---

# ADK Mobile SDT

This skill is the Mobile SDT entrypoint and shared resource package. It routes the user to the right SDT stage without
exposing internal skill selection details.

Mobile SDT 与 SDD 平行：SDD 解决"代码如何生成"，SDT 提供测试用例生成（ff）、澄清（clarify）到执行（implement）的
完整测试工作流，测试结果反哺 SDD。执行阶段唯一的平台分叉点是 profiles 解析出的平台验证工作流：iOS 与
Android 都解析到名为 `harness-workflow` 的技能——**同名，两套独立实现**，差异由各自的 `SKILL.md` 消化
（implement 交过去的是一段执行配置，不是拼好的命令行）。见 `README.md` § Android 接入。

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding.

## Runtime Assets

Resolve the installed `adk-sdt` skill's resource directory with the host's skill mechanism, then set `SDT_ASSET_ROOT` to
its `resources` directory. Do not look for these assets in plugin source directories.

If host lookup cannot resolve `adk-sdt`, fall back to `.claude/skills/adk-sdt/resources`, then
`.cursor/skills/adk-sdt/resources` under the project root.

The stage skills must use this same asset root for scripts, profiles, and templates:

- Check script: `SDT_ASSET_ROOT/scripts/check-prerequisites.js`
- Skill profiles: `SDT_ASSET_ROOT/templates/sdt-skill-profiles.json`
- Case template: `SDT_ASSET_ROOT/templates/sdt-case-template.md`
- Task template: `SDT_ASSET_ROOT/templates/sdt-mobile-task-template.md`
- Report template: `SDT_ASSET_ROOT/templates/sdt-report-template.md`

## Telemetry

After resolving `SDT_ASSET_ROOT`, follow `SDT_ASSET_ROOT/templates/sdt-telemetry.md` with `SKILL_NAME = adk-sdt`.

## Stage Skill Resolution

Select and hand off to stage skills by skill name through the host's skill mechanism.

If host lookup cannot resolve a skill by name, fall back to reading `<skillName>/SKILL.md` under the project-root
`.claude/skills`, then `.cursor/skills`.

Stages:

- `adk-sdt-ff`: generate `test/case.md` (harness-consumable test spec) and `test/task.md`
- `adk-sdt-clarify`: review and update generated test cases
- `adk-sdt-implement`: execute `test/task.md` via the platform verification workflow and generate `test/report.md`

If a selected stage skill is not invocable as a tool, use the host-provided skill lookup/read mechanism and execute that
workflow directly.

## Routing Workflow

1. Inspect `$ARGUMENTS`:
   - If it explicitly mentions `ff`, `fast forward`, `generate case`, or `生成用例`, route to `adk-sdt-ff`.
   - If it explicitly mentions `clarify`, `review case`, `adjust case`, `澄清`, `修改用例`, or `确认用例`, route to
     `adk-sdt-clarify`.
   - If it explicitly mentions `implement`, `execute`, `run test`, `rerun`, `retest`, `执行`, `跑测试`, or `复测`, route
     to `adk-sdt-implement`.
2. If no explicit stage is found, resolve `FEATURE_DIR`:
   - Prefer `$ARGUMENTS` `FEATURE_DIR`; otherwise use a valid `ACTIVE_FEATURE_DIR` from the current session context.
   - Run `node "$SDT_ASSET_ROOT/scripts/check-prerequisites.js" --paths-only --json` from repo root, appending
     `--feature-dir "<FEATURE_DIR>"` when either value exists.
   - After resolution, record the absolute result as `ACTIVE_FEATURE_DIR` for later SDT skill calls in this session.
   - If resolution fails, or `ALL_FEATURES` contains multiple candidates and none was specified, ask the user to select
     the target feature with the host-compatible structured question tool.
3. Inspect feature test files:
   - If `FEATURE_DIR/test/case.md` is missing, route to `adk-sdt-ff`.
   - If `FEATURE_DIR/test/case.md` exists and `FEATURE_DIR/test/task.md` is missing, route to `adk-sdt-ff`.
   - If both files exist and `$ARGUMENTS` is empty, route to `adk-sdt-implement` — freshly generated cases
     execute directly. Route to `adk-sdt-clarify` only when the caller asks for review/validation or is
     unsatisfied with the cases: clarify collects an approval, and **an approval once given is sha-bound**
     (any later edit to `case.md` then STOPs implement until it is re-approved). Do not push the caller
     through that door by default.
   - If both files exist and there is clear execute/rerun intent, route to `adk-sdt-implement`.
   - If `FEATURE_DIR/test/report.md` also exists, the report contains failures, and the user wants repair + retest:
     business-code defects are repaired via the SDD workflow (a lightweight `/adk:sdd:ff` bugfix run) or直接修复后, then
     route back to `adk-sdt-implement` for the rerun. 测试执行内部的失败修复（build/lint/用例 wave fix）由验证工作流
     自身闭环，无需人工路由。
4. If state and intent remain ambiguous, ask one structured question:
   - "What would you like to do next in SDT?"
   - Options: Generate/update test cases (`adk-sdt-ff`), Clarify/review test cases (`adk-sdt-clarify`), Execute tests
     (`adk-sdt-implement`).

## Execution Rules

- Preserve `$ARGUMENTS` when handing off to the selected stage.
- Do not display internal profile or skill mapping details unless the user explicitly asks for debugging information.
- Do not copy resources into stage skill directories. Stage skills must read shared assets from `adk-sdt/resources`.
- If `adk-sdt/resources` is missing in a standalone installation, stop with an actionable message asking the user to
  install or sync the `adk-sdt` skill package (plugin `ttadk/mobile-core`).
