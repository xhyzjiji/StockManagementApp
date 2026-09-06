---
name: adk-sdt-clarify
description: "Use when the user wants to clarify mobile SDT test cases, verify their logical correctness against spec and code, or adjust generated cases in test/case.md. Do not use for ordinary coding requests."
---

# ADK Mobile SDT Clarify

This skill is a Mobile SDT stage skill for clarifying test cases in `FEATURE_DIR/test/case.md` — 对齐 spec、对齐代码实现、
修正有争议的用例。It operates as a brainstorm-style multi-round dialogue, providing recommended modification options for
each review point.

## Manual Trigger Constraints

- Use this skill only when the user explicitly wants to clarify/review/adjust test cases (e.g. via `/adk-sdt-clarify`).
- This is a formal review flow of the SDT test phase, not a general "add more explanation" action.

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

If `$ARGUMENTS` contains a link, read its content first (lark/feishu docs via the available lark-docs MCP tool when
present). If `$ARGUMENTS` explicitly provides `FEATURE_DIR`, treat it as the highest-priority target feature input.

## Context

1. Language Setting — read `preferred_language` from `.ttadk/config.json`; if missing, read `lang` from
   `.adk-mobile/config.toml` (default 'en'). Use it for ALL outputs.

## Runtime Assets

Set `SDT_ASSET_ROOT` to the host-resolved `resources` directory of the installed `adk-sdt` skill (fallback:
`.claude/skills/adk-sdt/resources`, then `.cursor/skills/adk-sdt/resources`).

## Telemetry

After resolving `SDT_ASSET_ROOT`, follow `SDT_ASSET_ROOT/templates/sdt-telemetry.md` with `SKILL_NAME = adk-sdt-clarify`.

## Outline

### Step 1: Pre-check

1. Resolve `EXPLICIT_FEATURE_DIR` from `$ARGUMENTS` or session `ACTIVE_FEATURE_DIR`.
2. Run `node "$SDT_ASSET_ROOT/scripts/check-prerequisites.js" --json --require-sdt-tests --include-sdt-tests` from repo
   root, appending `--feature-dir "<EXPLICIT_FEATURE_DIR>"` when present. Abort with the script error if it fails.
3. Set `CASE_FILE = FEATURE_DIR/test/case.md`, `TASK_FILE = FEATURE_DIR/test/task.md`.

### Step 2: Load Context

1. **REQUIRED**: Read `CASE_FILE` and `FEATURE_DIR/spec.md` (or `requirements.md`).
2. **Explore codebase**: use Grep/Glob to locate the implementations the cases assert on (页面入口、AB key 注册点、
   埋点 event、UI 文案), and identify discrepancies between case assumptions and code reality.

### Step 3: Parse User Feedback

**If `$ARGUMENTS` is not empty**: extract TC-IDs and feedback content; locate the referenced case rows; proceed with only
those (plus directly dependent rows).

**If `$ARGUMENTS` is empty**: full-scan mode — analyze all case rows for issues.

### Step 4: Analyze and Propose

For each reviewed case, check at minimum:

1. **Spec alignment**: the case验证意图 matches an acceptance criterion; no invented behavior.
2. **Code alignment**: AB key 名与取值、埋点 event 名、页面链、UI 文案与代码一致（以代码为准指出出入）。
3. **Template contract**: 每个 `## TC-XXX` 区块字段齐全（标题引用块/Priority/Platform/Pkg/Path/Precondition/Steps/Assert）；
   **构建命令未定时，这里是选定它的地方（Android；iOS 没有 `task` 这一键，跳过）**：
   ff 列出的候选（多 flavor 工程常有几十个）要让用户选一个，
   写进 task.md Input 表的 `task`（执行参数只住在那里）；选定后**从它的 flavor 反查 applicationId**
   回填 task.md 的 `bundle_id` 与各条用例的 `Pkg`。`task` 空着进 implement 的后果是它停在「没有构建命令」上，
   而那时用户已经不在这一步了。
   **`Pkg` 要对账，不只是「非空」**：它必须是这一跑实际会装的那个包。字段齐全但值指向另一个 app 时，
   用例会在错误的应用上跑完一整轮，而报告里每一条都「执行了」。Android 侧拿选定的构建命令去构建脚本里
   查那个 flavor 自己的 `applicationId`，与 `Pkg` 对一遍；对不上就作为一条出入列给用户，别自己改了不说。
   Precondition 标签 ∈ {mock, assume, page(+route)} 且只含事实（操作必须在 Steps）；一步一操作（等待/观察是 Assert 不是
   Step）；Assert 带类别前缀（text/state/visual/tracker/network）且类别选择合理（能 text/state 不 visual，能
   tracker/network 不猜 text）；TC-ID 唯一。**并检查：任一用例若只剩 `visual` 断言即判为缺陷** —— 执行侧
   `assert.visual` 是 MockJudge 恒 PASS，这种用例产出的是无法与真通过区分的假绿；改法是把判据并入 `intent`
   定位描述，`visual` 退化为附加证据。
4. **Executability**: page chain 可达（有 route hint 或 deeplink）；mock 项具体可注入。
5. **Index-table sync**: 「用例表（执行索引）」与 TC 区块一一对应且内容一致——这是执行框架的解析输入，任何区块修改
   必须同步该表对应行。

For each issue, present: current row → problem → 2~3 modification options with a recommended one, via the
host-compatible structured question tool (or apply directly when the user's feedback already makes the correction
unambiguous).

### Step 5: Apply Edits

1. Edit `CASE_FILE` in place. **Never break the parsing contract**: section headings、「用例表（执行索引）」表头列名、
   `TC-NNN` id 形态必须保持；修改 TC 区块后**必须同步更新索引表对应行**，并逐项复查 用例ID / 执行步骤 / 预期结果 非空。
2. Execution parameters (run_mode / execution_mode / …) live ONLY in `TASK_FILE`'s Input table — apply any parameter
   change there directly. `case.md` carries no execution config; if a legacy file still has a `## Harness Config`
   section, delete it while you are editing (task.md is authoritative).
3. If cases were added/removed, keep TC-ID numbering unique (never renumber existing ids that a report already
   references).
4. **Collect the clarify approval (optional for `adk-sdt-implement`, but binding once recorded — sha-bound;
   editing `case.md` afterwards blocks implement until re-approved)**: ONLY
   after every reviewed point is resolved (no open product decision pending — see Error Handling) and the index table
   re-validated. Two channels; pick by availability:

   **Channel A — Lark case doc (preferred; SDD-FF-style lightweight approval, no dashboard)**: probe lark-cli
   availability first (`bytedcli lark auth status` succeeds, or a bare `lark-cli` exists). When available:

   1. Upload the reviewed `case.md` as a Feishu doc the user can read comfortably:
      `bytedcli lark docs create --title "SDT Cases — <NNN-name>" --content @<FEATURE_DIR>/test/case.md
      --doc-format markdown --as user --parent-position my_library -j` — capture `url` from the JSON.
      **Same feature re-clarify updates the SAME doc** instead of minting a new one: persist the url in
      `FEATURE_DIR/test/lark-case-doc.json` (`{"docUrl": "..."}`); when it already exists, run
      `bytedcli lark docs update --doc "<docUrl>" --command overwrite --content @<case.md> --doc-format markdown
      --as user` and reuse the url.
   2. Hand the user the link in ONE line and ask for their decision in-conversation (approve / needs revision).
      If they say they left comments in the doc instead, fetch it
      (`bytedcli lark docs fetch --doc "<docUrl>" --doc-format markdown --as user`), diff against the local
      `case.md`, treat doc-side edits and comments as Step 2 review feedback, apply locally, re-upload (overwrite),
      and re-ask. `case.md` in the repo stays the single source of truth — the doc is a review surface, never the
      storage.
   3. Approval given → record the event (Channel A stamp):
      `node "$SDT_ASSET_ROOT/scripts/sdt-events.js" record --feature-dir "<FEATURE_DIR>" --event clarify_approved
      --extra '{"channel":"lark","docUrl":"<docUrl>"}'`
   4. Needs revision → do NOT record; apply the feedback (back to Step 2 review loop), then re-collect.

   **Channel B — terminal (fallback)**: lark-cli unavailable → confirm with the user in-conversation as before, then
   record with `--extra '{"channel":"terminal"}'`. SDT keeps zero hard external dependency — Channel B must always
   work.

   Recording persists a `clarify_approved` event bound to the current `case.md` sha in `FEATURE_DIR/test/events.jsonl`;
   Reviewing is optional — implement runs without any approval. But an approval, once recorded, binds: any later edit to `case.md` invalidates it (sha mismatch →
   clarify must run again). Do NOT record while an open decision remains unresolved, never record before the user has
   EXPLICITLY approved (a delivered Lark link is not an approval), and NEVER record outside this clarify flow — it is
   the only legitimate writer of the approval.

### Step 6: Summary

Display: reviewed TC-IDs, applied changes, open questions (decisions the user still owes), the approval state
(`clarify_approved` recorded — binding on the current `case.md` sha; or withheld + why), and next step:

**Execute Tests**: run the `adk-sdt-implement` skill when the cases are confirmed.

## Error Handling

| Scenario | Handling |
|----------|----------|
| `test/case.md` missing | Prompt to run the `adk-sdt-ff` skill first |
| `test/task.md` missing | Prompt to run the `adk-sdt-ff` skill first |
| Feedback references unknown TC-ID | List available TC-IDs and ask user to pick |
| Correction requires a product decision | Stop and return the open decision to the user — do not guess |
