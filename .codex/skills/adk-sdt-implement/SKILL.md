---
name: adk-sdt-implement
description: "Use when the user wants to execute mobile SDT tests: run test/task.md via the platform verification workflow (both ends resolve to `harness-workflow` — same name, two independent implementations) against test/case.md and produce test/report.md. Do not use for ordinary coding requests."
---

# ADK Mobile SDT Implement

This skill is a Mobile SDT stage skill: a **re-entrant test execution dispatcher**. It resolves the platform verification
workflow（用户不可见的 skill 选择），drives it to completion with `test/case.md` as the spec input, and produces
`FEATURE_DIR/test/report.md`.

关键性质：

- **唯一平台分叉点**在 T001 的 `VERIFY_WORKFLOW` 解析。两端都解析到名为 `harness-workflow` 的技能（或其插件命名空间
  别名 `infra-ios:` / `infra-android:`）——**同名，但是两套独立实现**。本 skill 其余逻辑平台无关，禁止平台特判：
  差异由被解析出的那个技能在自己的 `SKILL.md` 里消化，本 skill 只负责把 task Input 作为**执行配置**交过去。
- **中间失败不外抛**：build 失败修复、lint 修复由验证工作流自身完成。本 skill 不把中间失败上抛给用户确认，
  也不通过 `/adk:sdd:clarify` 走外部澄清。**用例 FAIL 之后会不会自动改代码重验，取决于那一端** ——
  有的端在本轮内修，有的端只在显式重开一轮时才重验。`max_fix_rounds` 照交，实际怎么用以它 SKILL.md /
  它打印的 note 为准；**不要假定失败一定会被修绿**，预算耗尽仍不绿是正常终态。
- **本地/远端只有一个开关**：`execution_mode`（local | remote-agent），加 iOS 构建位置 `build_mode`（local | airbuild，
  Android 无此分档——它只走远端构建）。默认值由 ff 查 profiles 的 `DEFAULT_EXECUTION_MODE` 填，
  **派出去必须有人明说**：用户一句「用远端 agent 模式跑」就够，也可以给 `EXECUTION=remote`。
  别自己把一次跑升级成远端——那要占一个容器、十几分钟、还要那一侧的工具链先就位；
  而本机跑不通是当场响的，什么都没花。
- **`remote-agent` 会多一个人工确认点**：容器里改的代码要以 patch 回到用户的工作区，由用户裁决 apply / push /
  reject。这是代码落地，不是「中间失败上抛」——必须呈给用户，不得代为决定。

## Manual Trigger Constraints

- Use this skill only when the user explicitly wants to execute SDT tests per `test/task.md` + `test/case.md`
  (e.g. via `/adk-sdt-implement`), rerun/retest them, or resume an interrupted run.

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

- `FEATURE_DIR=<path>` → highest-priority target feature.
- `EXECUTION=remote` / `execution_mode=remote-agent`，**或者用户用话说要远端**（「用远端 agent 模式跑」/「派到容器上跑」）→ set task Input `execution_mode = remote-agent`。没人提就用 profiles 的默认，别自己升级。
- `TASK=<构建命令>` / `task=<构建命令>` → set task Input `task`（**Android 专属**），压过 task.md 里已有的值。
  换了它就不能沿用旧的 `bundle_id` —— 两者必须同源，见下一条。
- `BUNDLE_ID=<包名>` / `bundle_id=<包名>` → set task Input `bundle_id`。**Android：它必须与 `task` 编出来的
  那个包一致** —— 装包时会拿 APK 的真实包名与它对账，不一致就停跑，而那句报错不会告诉你「是你俩不是一套」。
  iOS 是 `Info.plist` 的 override，通常不给。
- `BUILD=airbuild` / `build_mode=airbuild` → set task Input `build_mode = airbuild` (iOS only).
- `ARTIFACT=<path>` / `artifact_path=<path>` → BYO 产物；set `artifact_path` and force `run_mode = verify`,
  **并把这个路径原样交给验证工作流**。
  **这一档不做新鲜度判断，也不要回头问用户。** 路径是用户当面给的，那就是意图 —— 验一个线上包、
  一个同事给的包、一个特意留着的旧版本都是正当的，「比代码旧」不是错。拿它去改走 `full`、
  或者问一句「要不要重编」，都是替用户重做一次他已经做过的决定，而代价是这条路的全部价值 ——
  省掉那十几分钟远端编译。照实记进报告就够了：验的是哪个包、来源是 `external`。
- `RUN_MODE=verify` / `run_mode=verify`(**没有 `ARTIFACT` 时**) → **只跑 E2E**：跳过 build + lint,
  复用工作区里已有的构建产物。
  **这一档才有新鲜度前置(硬)**：产物来源不明,必须与当前代码一致,否则装上旧包让 E2E 验错版本——
  一份关于错误二进制的绿比没有报告更糟。产物从哪来各端不同（iOS 的 install stage 自动发现
  DerivedData / bazel-bin；Android 认的是同一轮 run 里 build 留下的产物指针，跨轮不成立），
  所以**除非你能指出产物在哪、且它比最后一次代码改动新，否则不要单用 `verify`**：
  - 有现成的包 → 用上面那条 `ARTIFACT=<path>`，路径明确，不依赖任何自动发现；
  - 说不准 → 用 `RUN_MODE=full`，让它自己编一次。
  Android 的 `summary.json` 有 `under_test.source`（`built` / `external` / `preinstalled`）能事后自证这一轮
  验的是哪个包——`preinstalled` 意味着谁都没给产物、用的是设备上原本装着的那个，报告里必须写出来。
- `UNIT_TEST=true` / `with_unit_test=true` → set task Input `with_unit_test = true`（T002 组装参数时追加
  `--with-unit-test`；需要 run_mode 含 build）。**不是每一端、每个版本的验证工作流都认这个入参**：iOS 旧版
  的参数解析末尾是 `*) shift`（静默忽略未知参数），单测**不会跑也不会报错**；Android 认得这个键但不执行，
  只记进 `ignored_config`。两种情况用户都会以为第三环开了。T002 必须先做能力探测（见该任务的 Constraints）。
- rerun/retest/复测 intent → Rerun-after-fix mode (see Step 2.5).

## Context

1. Language Setting — read `preferred_language` from `.ttadk/config.json`; if missing, read `lang` from
   `.adk-mobile/config.toml` (default 'en'). Use it for ALL outputs.

## Runtime Assets

Set `SDT_ASSET_ROOT` to the host-resolved `resources` directory of the installed `adk-sdt` skill (fallback:
`.claude/skills/adk-sdt/resources`, then `.cursor/skills/adk-sdt/resources`). **It is a literal path you carry in
context, not a shell variable** — every Bash call runs in a fresh shell, so `$SDT_ASSET_ROOT` expands to empty there
and the command silently becomes `node /scripts/...`. Write the resolved path out in full in every command.

## Skills (host compatibility)

Resolve skills by logical skill name through the current host's skill mechanism; a plugin-namespaced variant counts as
resolved. If a skill is exposed as files, read the host-resolved `SKILL.md` and execute its documented protocol.

## Telemetry

After resolving `SDT_ASSET_ROOT`, follow `SDT_ASSET_ROOT/templates/sdt-telemetry.md` with
`SKILL_NAME = adk-sdt-implement`.

## Outline

### Step 0: Git Status Check

1. Run `git status --porcelain` from repo root.
2. If non-empty, display the changed files and warn: 测试将基于当前工作区（含未提交修改）构建执行；验证工作流的
   自动修复还会继续在工作区上追加修改（build / lint / 用例失败时它会改代码重验）。Ask (structured question):
   Continue / Stop. This is the ONLY interactive confirmation before execution starts.

### Step 1: Pre-check

1. Resolve `EXPLICIT_FEATURE_DIR` from `$ARGUMENTS` or session `ACTIVE_FEATURE_DIR`.
2. Run `node "<SDT_ASSET_ROOT>/scripts/check-prerequisites.js" --json --require-sdt-tests --require-clarify
   --include-sdt-tests` from repo root, appending `--feature-dir "<EXPLICIT_FEATURE_DIR>"` when present. Abort with the
   script error if it fails. **Clarify gate — optional, but binding once used**: clarify is NOT a prerequisite.
   ff-generated cases execute directly (the script reports `CLARIFY: not_run`; proceed, and mention in the kickoff
   summary that `adk-sdt-clarify` is available if the user wants to review/adjust cases first). What still STOPS
   the run: `case.md` missing (run `adk-sdt-ff`), or a recorded approval whose sha no longer matches `case.md`
   ("was edited after … approval" — the approval is a contract; instruct the user to re-run `adk-sdt-clarify`).
   Never hand-record or otherwise forge the `clarify_approved` event — clarify is its only legitimate writer.
3. Set `CASE_FILE`, `TASK_FILE`, `REPORT_FILE` from the output (`test/case.md` / `test/task.md` / `test/report.md`).
4. Read `CASE_FILE` and `TASK_FILE`. Parse from them: `PLATFORM`, case count/priority distribution, and the task Input
   table. Apply `$ARGUMENTS` overrides to Input rows (write them back to `TASK_FILE` before execution).
6. Read `SDT_ASSET_ROOT/templates/sdt-skill-profiles.json`; resolve the platform mapping as `SKILLS`
   (domain → profile → platform, same rules as `adk-sdt-ff`).

### Step 2.5: Re-entry / Rerun State Normalization

This command is **re-entrant**.

**`[x]` alone never authorises a skip.** A tick records that *some* round ran that task — not that *this*
invocation did. The two coincide whenever a round converges normally, so the difference stays invisible until
a round dies partway: T002 ticked with a verdict nobody can use, T003 still `[ ]`. That wreckage is
**character-for-character identical** to a healthy interrupted resume, and reading it as one makes the previous
round's verdict this round's answer — no command runs, no error fires, and the report says what the last
round said. Guard against it with the identity rule below, not with the tick.

判据按下列顺序检查，**第一个命中的即生效，不再往下看**：

1. **Fresh run** — 一个 `[x]` 都没有，且 `REPORT_FILE` 不存在 → 正常执行 T001 → T002 → T003。

2. **上一轮以未决 / 阻断收尾** — T002 是 `[x]`，但它的执行结果记录里的终态属于未决档
   （两端各自的未决词汇以该端报告的终态定义为准，本 skill 不复刻一份 —— 抄一份就会漂）
   → **按第 3 档 Rerun 处置**，不是 interrupted resume。
   理由：那一轮已经产出结论了，只是结论不可用。它与“跑到一半停下”在标记上同形，而处置相反。
   追一轮未决的正确动作是重跑取证（补证据 / 加预算 / clean re-run），而跳过 T002 恰恰令它永远重复同一个未决。

3. **Rerun after fix** — 全部 `[x]`，或 `REPORT_FILE` 存在，或 `$ARGUMENTS` 有 rerun 意图 →
   **do not regenerate cases**; keep `CASE_FILE` untouched; reset T002/T003 to `[ ]`; keep T001 completed only if the
   previously resolved skill still resolves on this host. 若上轮产物仍可安装复用且用户明确只想复跑 E2E，可把 Input
   `run_mode` 改为 `verify`（快路径）；独立使用时默认仍走 `full` 以保证测试针对最新代码。

4. **Interrupted resume** — 部分 `[x]` 部分 `[ ]`，**且能证明那些 `[x]` 属于本轮** →
   skip completed tasks, continue from the first pending one。
   证明的方式看那一端的状态模型，**不要只认记录里那一行**：
   - 记录里有仍然活着的执行身份（见下一小节）→ 成立。
   - 记录里没有身份，但**那一端的状态模型本身就排除了「读到别轮」**（状态在仓内单份、起新一轮必须
     先归档，所以留下的那份只可能是这一轮）→ 同样成立。
   - 那一端一轮一目录、旧轮原地还在，而记录里又没有身份 → **不成立**，落第 5 档。

5. **以上都不命中** → 按第 3 档 Rerun 处置。**默认重跑，不默认跳过** —— 多跑一轮的代价是时间，
   跳错一轮的代价是一份读起来完全正常、内容属于别的轮次的报告。

- Write normalized statuses back to `TASK_FILE` before execution, and display a short re-entry summary
  — 写明命中的是哪一档与判据（命中第 4 档时把那个执行身份一并贴出来）。

#### T002 完成时把这一轮的执行身份记下来

写进它的执行结果记录（模板里的「执行身份」行）。上面第 4 档优先凭它判定，不凭 `[x]`；
**在一轮一目录、旧轮原地还在的那一端，它是唯一能分辨「本轮跑过」与「某轮跑过」的东西**——
漏填的表现不是报错，而是下一次调用把上一轮的结论当成它自己的。

**身份取什么、「还活着」怎么判，由被解析出的那个验证工作流的 `SKILL.md` 说了算**，两端不同且各自拥有自己的状态模型：

| 端 | 执行身份 | 「还活着」的判据 |
| :--- | :--- | :--- |
| Android | 起跑命令返回的 `run.id`（状态在仓外，一轮一目录） | 那一轮尚未收尾（它的终态字段为空） |
| iOS | 本机跑：`.harness/context.json` 的 `created_at`（状态在仓内，单份，靠 archive 隔轮）。**远端派发：本机不初始化 `.harness/`**，取那次派发返回的任务 id | 本机跑：该文件仍在且 `created_at` 与记录一致；远端：那个任务 id 仍指向同一次派发 |

身份**取不到、对不上、或那一轮已经收尾** → 不满足第 4 档，落到第 5 档按 Rerun 处置。


### Step 3: Execute Tasks (T001 → T002 → T003, sequential)

Execute strictly per `TASK_FILE` — its task rows are the source of truth. For each task: complete → verify → immediately
update `[ ]` → `[x]` in `TASK_FILE` → move on. Never batch status updates. Halt on a failed task per its 失败处理 row.

- **T001 — Resolve the platform verification workflow (the ONLY platform fork)**: resolve
  `SKILLS.VERIFY_WORKFLOW` by name via the host skill mechanism, then each entry of `SKILLS.VERIFY_WORKFLOW_ALIASES`.
  On success, record the resolved name into `TASK_FILE` (Resolved Skills). (`case.md` carries no execution config;
  a legacy `## Harness Config` section in an old case.md is ignored — `task.md` is authoritative.)
  On empty/unresolvable, **STOP** with the extension guidance from the task's 失败处理 row (Android 接入见
  `adk-sdt/README.md` § Android 扩展指引). Never substitute a guessed skill; never fall back to hand-rolled atomic
  build/lint/E2E steps.
- **T002 — Drive the verification workflow (build + lint + E2E)**: invoke the resolved skill and follow **its own
  SKILL.md execution protocol** end-to-end.
  - **Hand the task Input over as an execution CONFIG; do NOT compose its command line.** The two ends have
    different CLI shapes (iOS: `--run-mode` / `--build-mode` / `--concurrency` driven by
    `next → --verify <stage> → --final`; Android: `--preset` / `--site` driven by
    `start → submit --stage --nonce --json → next → final`, **and its parser hard-stops on unknown flags**).
    Composing one end's flags for the other fails outright at best and silently verifies the wrong thing at worst.
    **You will be reading that end's SKILL.md, and it contains native-flag examples — those are written for a human
    driving it directly, not for you.** Copying them means you did the translation: keys this end does not support
    get dropped by YOU on the way, and whatever record that end keeps of ignored keys (if it keeps one) comes
    back empty — nobody can tell what the run ignored. Hand over the keys and let it translate.
    **Composing it also loses *values*, not just keys**: a value with spaces (a build command, say) gets split
    by the shell, that end records the first token as the whole value, and the round still goes green — only
    against a package the case was not written for.
    Give it **every non-empty row of `TASK_FILE`'s Input table** plus "drive yourself to a terminal state per your own SKILL.md protocol and
    produce the report artifacts". **Work from that table, never from a key list copied to here**: a key you
    leave out simply does not take effect that round, and the report comes back looking normal.
    **Do not expect unsupported keys to echo back.** One end records what it ignored; the other keeps nothing
    and swallows unknown flags silently — so after handing over, **read back the configuration that end
    actually adopted** (its state / verdict file) instead of waiting for an error that will not come.
  - **Pass `remote_agent_provider` / `remote_model` through whenever the Input has them non-empty.** Dropping
    `remote_agent_provider` is not a no-op: the run falls back to the container platform's own gateway, which can
    reroute a long session to a model whose function-calling rejects the agent's tool schema — after that every
    tool call fails and the round dies, with nothing in the report pointing at the model. Empty value = the Input
    genuinely did not pin one; omit it and let the workflow use its default. Never invent one.
    **One exception, checked before handing over:** `execution_mode = remote-agent` and a `remote_*` row is blank
    while the platform's profile default (`SDT_ASSET_ROOT/templates/sdt-skill-profiles.json` →
    `DEFAULT_AGENT_PROVIDER` / `DEFAULT_MODEL`) is non-empty — ff should have filled it; fill it from profiles now,
    write it back into `task.md`'s Input row, and say so in the output. That is not inventing a value, it is the
    documented default. `remote_model` may be a family name (`gpt`): hand it over verbatim — whether that end
    accepts a family name is its SKILL.md's call; never expand it yourself.
  - **Spec transport (only when `execution_mode = remote-agent`)**: the case file has to exist on the machine
    that runs the pipeline. **Who puts it there is a property of the resolved workflow, not of the platform** —
    deciding it by platform gets it wrong on any repo that does not match the assumption.
    - **Default: hand `CASE_FILE` over as it sits and stage nothing.** A staged copy splits the approved
      artifact from the one actually executed, while `clarify_approved` binds to `CASE_FILE` — and the two
      files look identical. `infra-android:harness-workflow` pushes the case file into the container itself,
      so ignore rules do not decide whether it arrives.
    - **Stage a copy only for a workflow that relies on the working tree being synced.** Such a sync carries
      only what the repo does not ignore, so run `git check-ignore -q <CASE_FILE>`: if it IS ignored, the file
      never arrives and `--spec` resolves to nothing over there. **That failure is silent** — the run completes,
      comes back `unknown`, and its report suggests passing `--spec`, which the caller did. Then copy the file
      **verbatim** to any non-ignored path in the repo, point the task Input's `spec` at THAT, never edit
      the copy, and record the staged path in `TASK_FILE`. `CASE_FILE` stays the reviewed artifact.
    **Write it relative to the repo root — never absolute.** That value is handed to a workflow that runs the
    pipeline on another machine, where the repo lives under a different absolute path; workflows pass it through
    verbatim, so an absolute local path resolves to nothing over there. The symptom is not an error:
    the run completes and reports **zero cases executed** (`selection: 0 of 0`, `verdict: unknown`), while the
    advice it prints tells you to pass `--spec` — which you did.   - **Fresh start vs continue — declare it, never let it be inferred.**

    | 你在做什么 | 交给验证工作流的是 |
    |---|---|
    | **这次调用是一次新的验证**（默认） | **起新一轮** —— 怎么声明由该端 SKILL.md 说了算，去读它的 fresh-start / stale-state 那一节，**不要按另一端的做法推**（Android 有一个专门的起跑动词 `start`；其余端各有各的，且未必是无条件动作） |
    | 驱动它往前走（推进 / 交产物） | 裸的推进命令，**不带任何起跑参数** |
    | 用户说 rerun / 改完代码重验 | 它自己的**重验**入口（Android `loop --reason source_change`），不是新起也不是裸推进 |
    | 用户说「继续」上次中断的那一轮 | 裸的推进命令 |

    **默认是「新起」，不是「续跑」。** 每一次 `adk-sdt-implement` 都是一次独立的验证意图 ——
    上一轮跑的是什么用例、什么产物、多久以前，与这一次没有关系，哪怕它们在同一个仓库下。
    只有上面后三行那些**明确的**理由才续。

    这一层的区分只有你做得了：验证工作流看到的是一条条命令，分不出「同一个任务的下一步」
    和「另一个任务的第一步」——**它猜错时不会报错，只会把上一轮的配置继续用下去**。

    **起新一轮被这一端拒绝时，原样转达，不要自己绕过** —— 但**不要等一个不会来的拒绝**：会不会拦、
    拦在什么条件上，以那一端自己的 `SKILL.md` 为准。**Android 那一端的起跑不做在途检查**，还会自己
    收掉上一轮没人认领的云端派发；那里没有「被拒绝」这个分支可等，也没有出路清单要转达。

  - **Stale-state guard**, per the resolved workflow's own state model:
    - iOS (state in-repo at `.harness/`): if `.harness/context.json` exists with a DIFFERENT `run_mode` than this
      run needs (e.g. a `build`-mode pipeline left by the SDD Compile & Lint step), archive it first
      (`bash "$ORCH" --archive`) — resuming a foreign-mode pipeline would skip the verify stage entirely.
    - Android (state OUTSIDE the repo, one directory per round under
      `~/.android-harness-workflow/<repo-name>-<repo-hash>/runs/<run-id>/`): there is no `.harness/context.json`
      to archive. Its start verb always opens a fresh round; its advance verb only advances and **hard-stops on any
      start-time argument** (nothing is swallowed). **Nothing will stop you either.** A prior round — unfinished,
      mid-dispatch, whatever state it is in — does not refuse a fresh start, and there is no flag to force past one.
      Rounds are fully independent; the only way to end up reading a previous round is to advance it instead of
      starting a new one (see "Fresh start vs continue" above).
  - **Check what the workflow says it is running, before trusting anything it reports.** Android's
    responses carry a `run` block (`id` / `started_at` / `age_minutes` / `round`). **`id` is the
    only thing that identifies a round — nothing else in that block does.**

    Do this: **write down the `run.id` that the fresh-start command returns, then pass
    `--run-id <that id>` on every command afterwards and check the `run.id` that comes back is
    still it.** **同一个 id 还要写进 T002 执行结果记录的「执行身份」行** —— 它在本轮之外还有一个用途：
    下一次调用的 Step 2.5 凭它分辨这条记录属于哪一轮。只在本轮内核对的话，这条链子的起点落在 T002 内部，
    而 T002 被跳过时起跑压根没发生，它一次也不会被执行（见 Step 2.5）。 A mismatch means the run you are reading is not the one you started, and everything
    downstream — stage states, verdict, the report you were about to write — describes that other
    run. Say so and stop; do not "work with what came back".

    **Do not treat any other field in that block as an alarm.** A round is identified by its `id` and by
    nothing else; runs carry no state and no dependency between them.
  - Pass the spec **as-is** — do not pre-edit or hand-normalize it: the workflow's deterministic parser consumes
    the「用例表（执行索引）」, and its own authoring/normalize stage reads the TC blocks for semantics.
  - **【iOS】参数是否生效以 `context.json` 为准，不要看 `AGENT_RUNTIME_EXPORT`**：后者反映的是当次 shell 调用的进程变量
    默认值（不重复传参时会显示 `CONCURRENCY=3`、`SPEC_FILE=''` 之类），与 pipeline 持久化配置无关。实测中差点
    据此判定"参数没生效"而 archive 重来——**核对配置只读 `.harness/context.json`，绝不因这个输出做破坏性操作**。（`AGENT_RUNTIME_EXPORT`、仓内 `.harness/context.json`、`archive` 这三样都只有 iOS 有；Android 的状态在仓外，核对配置读它 `status` 打出来的那份。）
  - **E2E 的 stage 依赖（`run_mode=verify` 时尤其要看）**：验证工作流内部的 DAG 是
    `verify(E2E) ← install ← {build 产物, device_setup}`、`verify ← classify ← gen_case`。`verify` 模式下
    `skip_build=true`，build 不跑，install 靠自动发现工作区产物——**所以 E2E 能否开始，取决于前置 build 节点
    是否已完成且产物是最新的**（SDD 大循环场景由小循环的 Build & Lint 保证）。产物不存在就用 `full`，或用
    `artifact_path` 显式指定。
  Constraints:
  - **`with_unit_test=true` 时先探测宿主能力**：`grep -q -- '--with-unit-test' <resolved workflow>/SKILL.md`。
    探测不到 → **显式告知用户本轮不跑单测、说明是哪一端不认这个入参**，然后不带该参数继续；
    绝不静默传参——iOS 旧版会把未知参数直接吞掉，Android 认得但只记账不执行，两种情况用户都会以为跑了单测。
  - The workflow owns intermediate repair for build and lint. **Whether a FAILED CASE also gets repaired in-round
    is that end's call** — do not assume `max_fix_rounds` buys you case-level retries on every end; read what it
    reports (some ends only re-verify through an explicit new round). Do not surface intermediate failures for user confirmation; do not route through
    `/adk:sdd:clarify`. Never assume a failure will fix itself into green: a run that exhausts the budget still
    red is a normal terminal state. **A case repaired into green needs a human look** — an assertion rewritten
    or an expectation loosened also produces green, and green is exactly what the run was asked for.
  - **The ONE interaction this task does surface: code landing under `execution_mode = remote-agent`.** The
    container edits code to fix build/lint, and those edits come home as a patch for a human decision
    (apply / push / reject — iOS at settle, Android at its `land` node). This is not "an intermediate failure
    escalated"; it is code landing in the user's tree, and it MUST be shown: present the diff, take the user's
    decision, hand it back to the workflow. Never decide on their behalf. Expect this as the **third** human
    touchpoint of an SDT run (after Step 0's git-status confirm, before Step 4's report review).
  - Do not manually split cases or bypass the workflow's internal parallelism.
  - Record into `TASK_FILE` 执行结果记录: terminal state, total/passed/failed/skipped, fix rounds, artifacts dir
    (absolute path — iOS `.harness/`; Android the state dir the workflow prints, which lives outside the repo),
    and — when it ran remotely — the landing decision.
- **T003 — Generate the report**: read the workflow's report artifacts. **Where they are depends on the resolved
  workflow** — take the paths it gives you, do not guess. **But do not assume the final command prints them**:
  on iOS the terminal command reports only the pipeline status, and the artifacts (`Validation.md` /
  `Validation.html` / `cases_index.json` / worker results) sit under its in-repo `.harness/` — the paths appear in
  the report stage's own output, not at the end. Android prints its state dir and indexes everything in
  `manifest.json`. Look in that end's own output for its artifact locations before concluding it produced none:
  - **Find out which artifact that workflow calls its verdict, and read the terminal states from THAT one.**
    The ends differ on where it lives: Android emits a standalone schema'd `summary.json`; iOS carries the
    terminal state in its own state file. A human-readable report sitting next to it may be a lossy projection —
    never let it override the verdict artifact. (Android renders that projection only on request:
    `final --emit-validation`.)
  - **A rendered per-step report with screenshots usually already exists — link it, do not re-describe it.**
    **Ask the workflow where its artifact index is, then look the report up there** — do not assume a field name.
    On Android that index is `manifest.json` (`summary.json`'s `pointers.manifest` points at it; entries carry a
    `role` and a path relative to `path_base`); the per-run `pointers` block does NOT carry it in dispatch form.
    iOS renders its own under `.harness/`. **Never conclude "this end has none" without looking up the index.**

  When `SKILLS.REPORT_GENERATE` is empty, fill `SDT_ASSET_ROOT/templates/sdt-report-template.md` inline; otherwise
  invoke that skill with the same inputs. Write `REPORT_FILE`. Rules:
  - TC-IDs与 `CASE_FILE` 严格一致。
  - **「用例审核」照 Step 1 那次 pre-check 输出的 `CLARIFY` 填**：`approved` → 已批准；`not_run` → 未审核。（没有「批准已失效」这一档 —— 那种情况 pre-check 已经 STOP 了，走不到这里。）
    审核是可选的，漏填这一行就没有任何地方分得出它和一次审核过的跑。
  - **每条用例的原始终态原样进报告，状态列写成 `<图标> <原始终态>`。** 图标是给人扫的，原始终态才是判据。
    **不要把终态压成 PASS / FAIL / SKIP 三档** —— 验证工作流给几档就写几档，档数以那一端自己的终态定义
    为准，不要从图标表反推。图标怎么对应分组、哪些档是「未决」「环境阻塞」而不是缺陷，照报告模板
    （`sdt-report-template.md` 结果详情下方的说明）填，不要在这里另记一份。
  - **Carry over the workflow's own honesty signals when it emits them** — do not flatten them into a pass rate.
    Android's `summary.json` has several with no iOS counterpart, and dropping any of them turns a partial or
    unproven run into a clean-looking one:
    `verdict.selection` (ran M of N — a green group over 2 of 10 cases is not a green run),
    `under_test` (which package was actually verified: `built` / `external` / `preinstalled`, plus the version the
    device reported), `next.owner` (take its value as-is; the enum belongs to the workflow), `execution.lint.mode`
    (only `ran` means it was actually checked; the three `skipped_*` mean it was not),
    `verdict.cases[].evidence_conflict` + `health` (same array as the per-case terminal states) (a verdict the harness downgraded because the platform recorded
    an ANR/crash in that window), and `provenance` (present only when the conclusion came from another machine —
    for `remote-agent` runs it always is; the report must say so).
  - **每个非绿用例都要归类**，五档：`case_defect` | `code_defect` | `env_blocker` | `undecided` | `human_abort`。
    前三档给证据路径 + 修复建议。**`undecided` 不是缺陷** —— 它的出口是补证据 / 加预算 / 干净重跑，
    不要把它塞进 `code_defect`（那会让人去查一个可能不存在的 bug），也不要走 SDD 反哺；
    `human_abort` 同理，出口是问那个中止的人。Cases
    repaired inside the workflow's own fix loop进「修复记录」并可发 `fix_confirm` telemetry event（见 sdt-telemetry.md）。
  - No `{{...}}` placeholder remains.

### Step 4: Completion validation

- Re-read `TASK_FILE`; no pending `[ ]` remains (or execution halted at a documented blocker with its `next_action`
  recorded).
- Record the stage event (audit trail):
  `node "<SDT_ASSET_ROOT>/scripts/sdt-events.js" record --feature-dir "<FEATURE_DIR>" --event implement_completed
  --extra '{"result":"<passed|failed|blocked>"}'`
- **Collect the user's review of `test/report.md`（与 case.md 同一套审批基建）**。SDT 每个产出都要人确认后才往下走，
  报告是最后一个：

  **通道 A — 飞书文档（lark-cli 可用时优先；与 clarify 的 case 审批同一套轻量通道）**：
  1. 把 `test/report.md` 上传成飞书文档：`bytedcli lark docs create --title "SDT Report — <NNN-name>"
     --content @<FEATURE_DIR>/test/report.md --doc-format markdown --as user --parent-position my_library -j`，
     取 JSON 里的 `url`。同 feature 重跑用 `docs update --command overwrite` 覆盖同一篇（url 持久化在
     `FEATURE_DIR/test/lark-report-doc.json`）。
  2. 一行给出链接 + 报告摘要（各优先级通过率），请用户在对话内确认。用户在文档里留了评论就拉回
     （`bytedcli lark docs fetch --doc "<url>"`）按反馈处理。

  **通道 B — 终端回落**：lark-cli 不可用时，在对话内展示报告摘要 + 路径并请用户确认——SDT 保持零外部硬依赖。

  处置：`approved` → 记录
  `sdt-events.js record --event report_reviewed --extra '{"verdict":"approved","channel":"lark|terminal"}'`
  （lark 通道附 `"docUrl"`）后继续；`needs_revision` / `rejected` → 按用户反馈处理（用例问题走
  `adk-sdt-clarify` 修订后 rerun；产品代码问题按 README 的 FAIL 归因路由交回 SDD），**不要**记录
  `report_reviewed`，也不要在未确认时宣告验证完成。
- Display the execution summary (per-priority pass rates + report path).

### Step 5: Lark Export (optional)

Only when the user explicitly asks (or `$ARGUMENTS` contains `EXPORT_LARK=true`) and a lark-docs MCP import tool is
available: import `REPORT_FILE` to Lark with a concise title and return the URL. Never a default step.

## Output

Return the human-readable execution summary:

```text
## SDT Execution Complete

- Platform / workflow: <platform> / <resolved VERIFY_WORKFLOW>
- Result: PASS x / FAIL y / SKIP z (wave fix rounds: n)
- Report: FEATURE_DIR/test/report.md
- Artifacts: <artifacts dir>
```

## Error Handling

| Scenario | Handling |
|----------|----------|
| `test/case.md` / `test/task.md` missing | Prompt to run the `adk-sdt-ff` skill first |
| `clarify_approved` missing (never clarified) | Proceed — clarify is optional; note in the kickoff summary that `adk-sdt-clarify` is available for case review/repair |
| `clarify_approved` stale (`case.md` edited after an approval) | STOP — the approval is sha-bound; run the `adk-sdt-clarify` skill to re-approve. Never bypass or hand-record the event |
| `VERIFY_WORKFLOW` empty / unresolvable | STOP with platform extension guidance (`adk-sdt/README.md`); never improvise |
| Resolved workflow rejects a flag / says a key is unsupported | It is telling you the config did not translate. Report which key was dropped and continue only if that key was optional. **Never re-send it as a raw CLI flag** — one end hard-stops on unknown flags, the other silently swallows them |
| `execution_mode = remote-agent` and the `spec` file is gitignored | Only matters for a workflow that relies on the synced working tree — then the spec never arrives; stage a verbatim copy under a non-ignored path and point `spec_file` at it (T002). A workflow that delivers the file itself (`infra-android:harness-workflow`) is unaffected; staging a copy there only splits the approved artifact from the executed one |
| Workflow cannot start (env/deps) | Stop at T002 with the workflow's own diagnostic and a precise `next_action` |
| Terminal state has FAIL after fix budget | Normal completion — report with unfixed failures归因; suggest next step |
| `artifact_path` set but `run_mode != verify` | Fix Input to `run_mode = verify` and note it |
| Workflow skill执行超时/中断 | Keep task states; rerun this skill — Step 2.5 resumes from the pending task |

## Next Step Guidance

After execution, review `FEATURE_DIR/test/report.md`:

- **FAIL with `code_defect`**（预算耗尽仍未修复的）: fix via the SDD workflow — e.g. `/adk:sdd:ff <bug 描述 + 报告路径>`
  单启一个轻量 bugfix 流程（或直接修复）——then rerun `adk-sdt-implement`（Rerun-after-fix 会复用 case.md）。
- **FAIL with `case_defect`**: run the `adk-sdt-clarify` skill with `TC-xxx <问题描述>` to correct the case, then rerun implement.
- **`env_blocker`**: resolve the environment/credential issue per the report, then rerun implement.
