---
name: adk-sdt-ff
description: "Use when the user wants to convert a mobile SDD spec into test cases (test/case.md + test/task.md), or explicitly enters the ff (fast forward) phase of the Mobile SDT workflow. Do not use for general implementation requests."
---

# ADK Mobile SDT FF (Fast Forward)

This skill is a Mobile SDT stage skill for generating text test cases. 输入是 SDD 工作流的产物（`spec.md`，可选
`plan.md`/`design.md`），输出两个文件：

- `FEATURE_DIR/test/case.md` — harness-consumable 测试用例文档（同时供人工 review 与平台验证工作流 `--spec` 消费）
- `FEATURE_DIR/test/task.md` — 平台无关的测试执行计划（唯一平台分叉点在 T001 解析的 `VERIFY_WORKFLOW`）

## Manual Trigger Constraints

- Use this skill only when the user explicitly mentions `sdt-ff`, `sdt:ff`, `sdt fast forward`, `生成测试用例`, or
  explicitly names this skill (e.g. via `/adk-sdt-ff`).
- If the user only says something general like "help me test this", do not switch to this skill automatically.

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

If the given `$ARGUMENTS` contains a link, read its content first. For lark/feishu doc URLs, export via the available
lark-docs MCP tool when present, otherwise ask the user to paste the content.

If `$ARGUMENTS` explicitly provides a `FEATURE_DIR` value, or clearly provides a feature-directory path, you **MUST**
treat it as the highest-priority target feature input.

## Context

**Read context before Executing**:

1. Language Setting
   - Read `preferred_language` from `.ttadk/config.json`; if missing, read `lang` from `.adk-mobile/config.toml`
     (default: 'en' if both missing). **Use the configured language for ALL outputs.**

## Skills (host compatibility)

Resolve skills by logical skill name through the current host's skill mechanism. If the host exposes a skill as an
invocable tool, invoke it by name. If the host exposes skill files instead, read the host-resolved `SKILL.md` and execute
its workflow. A plugin-namespaced variant of the same skill name counts as resolved.

If host lookup cannot resolve a skill by name, fall back to `<skillName>/SKILL.md` under the project-root
`.claude/skills`, then `.cursor/skills`. TTAT package skills nest one level deeper — for `ui-md-case-gen`
specifically, also try `tt-nova-ui/ui-md-case-gen/SKILL.md` under the same roots (agentbuddy installs the
`tt-nova-ui` package as one top-level dir with sub-skills inside; the sub-skill is not indexed as a standalone
host skill).

**A package's top-level routing table is not the capability contract — the sub-skill's own `description` is.**
Field case: `tt-nova-ui/SKILL.md` lists only the "BITS mind-map link / case ID" trigger, so the delegate looked
inapplicable for a spec-driven run; `ui-md-case-gen`'s own description declares a second input mode (PRD / 需求文档 /
feature markdown) that fits exactly. Read the sub-skill before concluding a capability does not apply.

**Resolution means a READABLE `SKILL.md` FILE, never a directory.** A half-finished / cleaned install leaves the
directory tree in place with zero files (`ui-md-case-gen/{references,scripts}/` and no `SKILL.md`), so `ls -d` on
the directory "succeeds" while the skill is unusable — verify with a file test (`[ -s <path>/SKILL.md ]`) or by
actually reading it. Field-proven trap: an agent checked the directory, announced the skill was available,
then had to retract it one turn later.

## Runtime Assets

This stage skill uses shared assets from the `adk-sdt` skill package. Set `SDT_ASSET_ROOT` to the host-resolved
`resources` directory of the installed `adk-sdt` skill (fallback: `.claude/skills/adk-sdt/resources`, then
`.cursor/skills/adk-sdt/resources`).

## Telemetry

After resolving `SDT_ASSET_ROOT`, follow `SDT_ASSET_ROOT/templates/sdt-telemetry.md` with `SKILL_NAME = adk-sdt-ff`.

## Outline

### Step 1: Pre-check

1. Inspect `$ARGUMENTS` for `EXPLICIT_FEATURE_DIR` (explicit value or clear feature path); otherwise use a valid
   `ACTIVE_FEATURE_DIR` from session context.
2. Run `node "$SDT_ASSET_ROOT/scripts/check-prerequisites.js" --paths-only --json` from repo root, appending
   `--feature-dir "<EXPLICIT_FEATURE_DIR>"` when present.
3. Parse the JSON output to get `FEATURE_DIR` and `ALL_FEATURES`. If parsing fails, abort with the script's error message.
4. If no explicit feature was given and `ALL_FEATURES` has multiple entries, ask the user to select one with the
   host-compatible structured question tool. Record the result as `ACTIVE_FEATURE_DIR`.

### Step 2: Load Requirement Documents

1. **PRIMARY**: Read `FEATURE_DIR/spec.md`. If missing, read `FEATURE_DIR/requirements.md` instead.
   - If neither exists, **STOP**: "spec.md / requirements.md not found. Run the SDD workflow first
     (`/adk:sdd:ff` or `/adk:sdd:spec`)."
2. **OPTIONAL**: Read `FEATURE_DIR/plan.md` (FF mode) or `FEATURE_DIR/design.md` (full SDD mode) for technical context —
   尤其是改动的模块、页面入口、涉及的 AB 实验与埋点。

### Step 3: Infer Target Platform

Infer exactly one platform: `ios` or `android`.

1. **Explicit scope in spec/plan**: iOS/Xcode/Swift/Objective-C/Podfile signals → `ios`;
   Android/Gradle/Kotlin/APK signals → `android`.
2. **Repository hints**: `*.xcworkspace` / `Podfile` / `Modules/*.podspec` → `ios`; `build.gradle` / `settings.gradle` /
   `app/src/main` → `android`.
3. If both are explicitly in scope, ask the user to pick exactly one for this run (never generate a mixed task).

### Step 4: Resolve Skill Profile (no user interaction)

1. Read `SDT_ASSET_ROOT/templates/sdt-skill-profiles.json`.
2. Infer `DOMAIN` from spec/repo signals; if unsure use `unknown`. Resolve `PROFILE` via `domains[DOMAIN].profile`,
   else `defaultProfile`.
3. Take the platform mapping `profiles[PROFILE][platform]` as `SKILLS`.
4. Capability rules:
   - `VERIFY_WORKFLOW`: record the configured name for injection into `task.md` (Input/Resolved Skills — the single
     home of execution wiring; `case.md` carries no execution config). FF 阶段只记录不调用；为空也不在本阶段报错
     （implement T001 负责失败处理与扩展指引）。
   - `TEXT_CASE_GENERATE`: the mobile spec2case skill (default `ui-md-case-gen`, from the `tt-nova-ui` package
     **vendored inside mobile-core** — it ships with this plugin, same delivery as adk-sdt itself; no remote install,
     no network). Optional (`TEXT_CASE_GENERATE_OPTIONAL=true`) — missing/unresolvable never errors; fall back to
     self-authoring.
   - **Resolution (do this HERE, before deciding the generation path)**:
     1. **Probe** `TEXT_CASE_GENERATE_PROBE` (repo-root-relative). It must be a **non-empty FILE**
        (`[ -s <probe> ]`); a leftover directory tree without `SKILL.md` means NOT installed.
     2. Probe passes → delegated path.
     3. Probe fails → the bundled copy did not reach this project (mobile-core installed from an old version, or a
        partial copy). Do NOT install anything from the network here (`TEXT_CASE_GENERATE_INSTALL` is empty by
        design — the capability is vendored, not fetched). Say so in one line — 内置的 `tt-nova-ui` 副本缺失，
        建议 `ttadk plugin update ttadk/mobile-core` — and continue with self-authoring. **Never block the SDT
        flow on this**; it stays an optional capability.
     - The vendored copy has the upstream daily self-update **removed** (see the 版本说明 banner in its SKILL.md),
       so it cannot wipe itself mid-session. If you ever see the delegate attempt a self-update, that is a
       non-vendored copy — re-run the probe after it returns before deciding delegate-vs-self-author.
5. Do not display skill names to normal users unless debugging is explicitly requested.

### Step 5: Generate `test/case.md`

1. If `FEATURE_DIR/test/case.md` already exists, confirm with the user: Overwrite / Append / Cancel.
2. Read the case template `SDT_ASSET_ROOT/templates/sdt-case-template.md` to obtain the required output format and the
   5 authoring principles (Goal = verification intent; mock must be concrete; page-chain notation; one action per step —
   等待/观察是断言不是动作; pick the right Assert category and never embed "确认结果" semantics in an action).
3. Generation path:
   - **Delegated (preferred, when `SKILLS.TEXT_CASE_GENERATE` resolves on this host)**: run the resolved skill per
     **Skills (host compatibility)** (invoke by name when the host supports it, **or** resolve its `SKILL.md` and follow
     it) to generate the mobile E2E test cases. Provide it:
     - The spec context from Step 2 (`spec.md` plus optional `plan.md`/`design.md`) as the requirement source
       (its "纯业务知识输入" mode — no Bits mind-map required).
     - **The case template as the output format contract**, instructing the output to match exactly: each case carries
       标题引用块 (verification intent), `Priority`, `Platform` (Android | iOS), `Pkg`（**取值规则见模板的字段说明**——
       它要与这一跑实际会装的那个包一致，别从构建脚本里挑第一个搜到的标识符）, `Path`, `Precondition`
       (`mock | / assume | / page |` with nested `route |` hints), `Steps` (one action per step, each with
       `Assert: <category> | <expectation>`), and a final `Assert` block. Assert categories must be one of
       `text | state | visual | tracker | network`. Delegation must not change this output contract — the template
     overrides the skill's native output format.
   - **Fallback (self-authoring, when unresolvable)**: derive the cases directly from spec/plan in the same format.
     Every acceptance criterion in the spec maps to ≥1 case.
4. **Emit ONLY the template's 产物骨架** (title + two-line intro + TC blocks + 用例表) to assemble the final
   `FEATURE_DIR/test/case.md`:
   - Do NOT copy the template's comment block (编写原则 / 字段说明 — authoring rules for you, not case content),
     and do NOT write a `Harness Config` section: execution parameters (run_mode / execution_mode / build_mode /
     concurrency / max_fix_rounds) live ONLY in `test/task.md`'s Input table — the single source implement T002
     reads. `$ARGUMENTS` overrides for those parameters go to `task.md`.
   - The `## TC-XXX` case blocks (from step 3).
   - **「用例表（执行索引）」**: derive one table row per TC block, following the derivation rules embedded in the
     template (前置条件/执行步骤/预期结果 压缩规则). This table is what the verification workflow's deterministic
     parser consumes — it is NOT optional.
5. **Validation gate** before finishing:
   - Every `## TC-XXX` block has all required fields; TC-IDs are unique.
   - The 用例表（执行索引） has exactly one row per TC block and the contents are consistent with the blocks;
     every row has non-empty 用例ID / 执行步骤 / 预期结果.
   - No `{{...}}` placeholder or template comment remains.
   - If validation fails, fix and re-validate; do not deliver a broken case file.

### Step 6: Generate `test/task.md`

1. If `FEATURE_DIR/test/task.md` exists, confirm Overwrite / Keep.
2. **Copy the template first, then edit in place**: `SDT_ASSET_ROOT/templates/sdt-mobile-task-template.md` →
   `FEATURE_DIR/test/task.md`. Keep the original structure and text; only fill values.
3. Fill: `{{FEATURE_NAME}}`, `{{FEATURE_DIR}}` (absolute), `{{PLATFORM}}`, `{{VERIFY_WORKFLOW_SKILL}}` from `SKILLS`,
   `{{REPORT_GENERATE_SKILL}}` (empty string allowed), and:
   - `{{SPEC_FILE}}` → **相对仓库根**的用例路径，默认 `<FEATURE_DIR 相对部分>/test/case.md`。**不要填本机绝对路径**：
     远端形态下那个值被原样透传给另一台机器，解析到一个不存在的文件，**表现是「跑完了但一条用例都没执行」而不是报错**。
   - `{{TASK}}` / `{{BUNDLE_ID}}` → 见下面「定 `task` 与 `bundle_id`」那节；**该节不适用的平台（iOS）这两位置空**
     （空行不参与交接），未定时也置空 —— 留占位符会被原样交出去。
   - `{{EXECUTION_MODE}}` / `{{AGENT_PROVIDER}}` / `{{MODEL}}` → 见下面 profiles 默认值那段。
   Honor `$ARGUMENTS` overrides for Input rows
   (`execution_mode` / `build_mode` / `run_mode` / `artifact_path` / `concurrency` / `max_fix_rounds` /
   `remote_agent_provider` / `remote_model`).
4. Verify no `{{...}}` placeholder remains.

### Step 7: Record Event & Report Generation Results

1. Record the stage event (audit trail; binds the generated `case.md` sha):
   `node "$SDT_ASSET_ROOT/scripts/sdt-events.js" record --feature-dir "<FEATURE_DIR>" --event ff_generated`
2. Report:

```text
## Generation Complete

- **Target platform**: ios | android
- **Test cases**: N (P0: a / P1: b / P2: c)
- **Case generation**: delegated to ui-md-case-gen | self-authored (ui-md-case-gen 未安装 —
  可选增强，安装见 adk-sdt/README「环境准备」或跑 adk-doctor)
- **Output**: FEATURE_DIR/test/case.md, FEATURE_DIR/test/task.md
- **Verification workflow**: <VERIFY_WORKFLOW 或 "未配置（该平台 profiles 里为空）">
- **Execution mode**: <execution_mode 的取值> (default from profiles)
- **Remote agent runtime**: <remote_agent_provider / remote_model 的取值，空的写「未指定」> (仅 execution_mode = remote-agent 时打印)
- **Pending decisions**: <这一轮**故意留空、要用户拍板**的 Input 键 + 候选清单；没有就写「无」>
  —— 典型是多 flavor 仓的构建命令。**这一行必须出现**：上游（SDD 自动衔接）按它决定是「停下问人」
  还是「继续往下走」，漏了它那一侧会以为备料齐了，然后在 implement 处撞上一个填不了的空值。
```

### 定 `task` 与 `bundle_id`（Android；iOS 跳过这一节）

这两位**同源推导，顺序不能反**：先定构建命令，再从它的 flavor 反查包名。各推各的会在装包时
对账失败，而那个失败的报错方向不指向「你俩不是一套」。

**第一步 · 读被测仓 `.idea/meta.xml`。** 取 `PersistentSyncState` 的
`lastSyncSelectedMetaTarget`，形状是 `<variant>@<module>`，两位都从它出：
`task` = `./gradlew <module>:assemble<Variant 首字母大写>`，`bundle_id` 按第三步从这个
variant 的 flavor 反查。填了要注明来源，clarify 仍可改。

四种情况不能用它，走第二步留空：文件不存在、没有这个属性、`lastSyncResult` 不是 `SUCCESS`、
`lastSyncGitCommit` 与当前 HEAD 对不上（那个目标属于另一棵树）。

**不要拿 `app/build/outputs/` 下的构建产物当来源** —— 它说的是历史上构建过什么，不是这一次
要构建什么。两者差一个 flavor 时，推出来的 `task` 与 `bundle_id` 会一路通过所有检查，
直到用例在另一个 app 上跑完一整轮。

**第二步 · 没有可用的同步目标时，列候选，不要猜。** 从被测仓的构建脚本枚举
`productFlavors` × `buildTypes`（`app/build.gradle` 之类）得到候选构建命令。
**候选多不是让你挑一个的理由** —— 挑错不报错，只会编出一个不是你要的包。

- 候选**恰好一个** → 直接填。
- 候选**多于一个** → 把候选清单写进 task.md 的备注，`task` 留空，
  并在你的输出里明说「构建命令待定，需要在 clarify 阶段选定」。**留空不是失败**，
  不要为了填满字段挑一个。

**第三步 · 从 flavor 反查包名。** 构建命令定下来之后，取它的 flavor 名，在构建脚本里找
**那个 flavor 自己的 `applicationId`**，填进 `bundle_id` 与每条用例的 `Pkg`。

**不要取构建脚本顶部那个默认 `applicationId`** —— 多 flavor 的工程里它往往不是本次构建的那个
（同一个文件里常有若干条按 flavor 覆盖的）。取错了不报错：用例会在错误的应用上跑完一整轮，
而报告里每一条都「执行了」。

`task` 未定时 `bundle_id` 也留空 —— 它依赖前者，先猜一个只会让 clarify 少一次核对的机会。

When filling `task.md`'s Input table, take `execution_mode` from the platform's
`DEFAULT_EXECUTION_MODE` in profiles unless the user asked for a specific one — in which case the
user wins. Same for `remote_agent_provider` / `remote_model` from
`DEFAULT_AGENT_PROVIDER` / `DEFAULT_MODEL`. These are per-platform DEFAULTS, not a fork: nothing downstream
reads `platform` to decide behavior.

**"The user asked for one" includes plain words — take them:**

| The user says | `execution_mode` |
|---|---|
| 「用远端 agent 模式跑」「派到容器上跑」「用云端跑」 / "run it remotely", "dispatch it" | `remote-agent` |
| 「在本机跑」「用我这台机器」 / says nothing about where | leave it at the profile default |

**Never upgrade a run to `remote-agent` on your own.** Dispatching costs a container slot, ten-odd
minutes, and a container-side toolchain that must already be in place; a local run that cannot work
fails immediately and for free. `$ARGUMENTS` may also carry `EXECUTION=remote` or
`execution_mode=remote-agent` explicitly — either outranks both the words and the default.

**An empty default means "omit this row's value", not "pass an empty string"** — the verification
workflow then uses its own default. Do NOT invent a value for an empty one, and do NOT drop a
non-empty one: `remote_agent_provider` in particular exists because the container platform's own gateway
can reroute a long session to a model whose function-calling rejects the agent's tool schema,
and when that happens every tool call afterwards fails while the report still reads normal.

**Self-check before finishing (part of the validation gate):** when `execution_mode = remote-agent`,
every `remote_*` row whose profile default (`DEFAULT_AGENT_PROVIDER` / `DEFAULT_MODEL`) is non-empty
must be non-empty in `task.md` — the user's value or the default, never blank. A blank
`remote_agent_provider` next to a non-empty `DEFAULT_AGENT_PROVIDER` is a generation bug: the round
would silently fall back to the platform gateway. `DEFAULT_MODEL` may be a family name (`gpt`); copy it
as-is — whether the verification workflow accepts a family name is its SKILL.md's call, not yours.

The **Case generation** line is mandatory — never silently self-author: the user must always
see which path produced the cases (this line is the optional-capability transparency contract).

## Error Handling

| Scenario | Handling |
|----------|----------|
| spec.md / requirements.md missing | Prompt user to run the SDD workflow first |
| No acceptance criteria extractable | Display error and ask user to补充验收标准 or provide PRD link |
| Both iOS and Android explicit | Structured question — pick exactly one platform for this run |
| `test/case.md` already exists | Structured question — Overwrite / Append / Cancel |
| `TEXT_CASE_GENERATE` unresolvable | Silent — it is optional; use self-authoring path |
| Explicit `FEATURE_DIR` invalid | Stop and ask the user to verify the provided path |

## Next Step Guidance

After executing this command:

1. **Execute**: run the `adk-sdt-implement` skill to execute tests via the platform verification workflow (both ends resolve to `harness-workflow` — same name,
   two independent implementations; 小循环修复在 workflow 内部闭环). Freshly generated cases run directly — no approval step in between.
2. **Not satisfied with the cases?** Run the `adk-sdt-clarify` skill with your feedback first — it reviews/adjusts `case.md` against
   spec and code, and records a sha-bound `clarify_approved` event. That approval is optional but binding: once it
   exists, any later edit to `case.md` makes implement refuse until clarify re-approves (route case feedback through
   clarify rather than hand-editing an approved file).
