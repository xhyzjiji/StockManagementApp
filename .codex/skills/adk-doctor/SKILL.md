---
name: adk-doctor
description: >-
  adk-Doctor — one-stop diagnose & fix for the CLI + MCP environment required by Mobile SDD.
  CLI covers lark-cli, bitscli (BITS / Codebase), and bytedcli (Meego only).
  MCP covers per-preset (ios / android) required server probing, connection fixes,
  and re-initialization via `ttadk mobile init` when MCP servers are missing or the project has never been initialized.
  IDE is inferred from this SKILL.md's path (Cursor / Trae / Coco / Claude).
  Triggers when the user says 环境检查 / CLI 检查 / MCP 检查 / Meego 环境检查 / ttadk 环境就绪, etc.
---

# adk-Doctor (One-stop CLI + MCP Environment Check)

> **Language rule**: reply to the user in **Chinese by default** throughout this skill. Switch to English only when the user's triggering message (or the surrounding conversation) is in English. 

> **CLI responsibilities**:
> - `lark-cli` → Feishu / Lark
> - `bitscli` → BITS MR, Codebase MR
> - `bytedcli` → Meego tickets only (no longer used for Codebase / BITS / SSO checks)

## Routing (pick scope from user input)

| User keywords | Scope |
|---------------|-------|
| `CLI 检查` / `lark-cli 检查` / `bitscli 检查` / `Meego 环境检查` | Stage A only |
| `MCP 检查` / `MCP 同步` / `MCP 修复` | Stage B only |
| `环境检查` / `环境就绪` / `adk-doctor` / other defaults | Stage A → Stage B (in order) |

Execution rule: fully complete Stage A (probe + summary + fix) before entering Stage B. Do not interleave.

---

## Before execution: build the task checklist (mandatory)

Before issuing any probe / fix action, **first call `TodoWrite`** to write the full todo list for this run in one shot and show it to the user, then start executing. Mark each item complete immediately upon finish.

Generate todos per route (fix-related items get refined after probe+summary identifies what actually needs fixing):

**Stage A only**:
1. Probe CLIs in parallel (lark-cli / bitscli / bytedcli)
2. Summarize detection results
3. Fix failing items in order (lark-cli → bitscli → bytedcli)

**Stage B only**:
1. Read preset + determine `IDE_TARGET`
2. Health-check required MCPs
3. Handle unhealthy servers: configured-but-failing → user fixes per the IDE's own error log; never-configured → re-init via `ttadk mobile init`

**Stage A → Stage B**: merge both lists into a single ordered todo.

---

## Pre-check: Node version

```bash
node -v 2>&1
```

Parse the major version number. **Require node ≥ 18.** If the version is < 18 or `node` is not found:

Tell the user:

> 当前 node 版本过低（需 ≥ 18），ttadk CLI 和 MCP 配置工具依赖 node 18+。
> 请执行 `nvm install 20 && nvm use 20` 后重新触发检查。

Then **stop** — do not proceed to Stage A or Stage B.

> **Design note**: adk-doctor is a diagnostic tool; it does **not** silently switch the user's nvm / shell environment. It only reports and exits.

---

## Stage A — CLI Environment

### A0. Parallel probe

Issue the following commands **in parallel** in the same round (multiple independent shells fired at once). **Do not wait for one result before issuing the next.**

#### lark-cli

```bash
lark-cli --version 2>&1; echo "---"; lark-cli auth status 2>&1
```

#### bitscli (BITS / Codebase)

```bash
bitscli --version 2>&1
bitscli codebase auth status 2>&1
```

#### bytedcli (Meego only)

```bash
bytedcli --version 2>&1
bytedcli --json meego workitem list --project-key __auth_check__ 2>&1
```

> bytedcli here **only checks Meego**: no SSO / Codebase JWT / BITS link checks anymore.

#### tt-nova-ui (Mobile SDT optional — `ui-md-case-gen` delegate for `adk-sdt-ff`)

```bash
command -v agentbuddy 2>&1 || ls "$HOME"/.nvm/versions/node/*/bin/agentbuddy 2>/dev/null | head -1
ls .claude/skills/tt-nova-ui/ui-md-case-gen/SKILL.md 2>&1
```

> **Optional semantics**: missing tt-nova-ui never blocks readiness — `adk-sdt-ff` lazily installs it on
> first use, and self-authors cases if that fails. Report it as ⚠️ enhancement, not ❌; fixing it here just
> front-loads the install.

### A1. Summarize status

Output the following table to the user, then proceed to fixing:

```text
## CLI Detection Result

| Tool | Check | Status |
|------|-------|--------|
| lark-cli | install | ✅ v1.x.x / ❌ not installed |
| lark-cli | config | ✅ configured / ❌ not configured |
| lark-cli | user auth | ✅ user ready / ✅ user needs_refresh (auto-refresh next call) / ❌ not logged in / ⚠️ bot only |
| bitscli | install | ✅ v1.x.x / ❌ not installed |
| bitscli | Codebase auth | ✅ logged in / ❌ not logged in / — skipped (not installed) |
| bytedcli | install | ✅ v1.x.x / ❌ not installed |
| bytedcli | Meego auth | ✅ logged in / ❌ not logged in / — skipped (not installed) |
| tt-nova-ui | SDT case-gen (optional) | ✅ installed / ⚠️ not installed (sdt:ff self-authors) |

## Items to fix (execute in order)
1. …
```

**Pass criteria**:

| Check | Pass condition |
|-------|----------------|
| lark-cli install | `--version` succeeds |
| lark-cli config | no `not configured` / config-related errors |
| lark-cli user auth | `auth status` exits 0 AND `identities.user.status ∈ {ready, needs_refresh}` — `needs_refresh` means the token expired but lark-cli will auto-refresh it on the next user API call; treat as healthy, **do NOT** trigger any fix. (**bot-only readiness does NOT count**) |
| bitscli install | `bitscli --version` succeeds |
| bitscli Codebase auth | `bitscli codebase auth status` shows authenticated (with Username) |
| bytedcli install | `bytedcli --version` succeeds |
| bytedcli Meego auth | `meego workitem list` returns `error.code` != `MEEGO_AUTH_REQUIRED` |
| tt-nova-ui (optional) | `.claude/skills/tt-nova-ui/ui-md-case-gen/SKILL.md` exists in the project — ⚠️ when missing, NEVER ❌ (does not affect readiness) |

All CLIs ✅ → skip A2, proceed to Stage B (if the route includes it). A ⚠️ on tt-nova-ui alone
does NOT block Stage B; offer its fix only when the user wants delegated case generation.

### A2. Fix in order

Only process planned items; after each fix **retest only that item**, and proceed to the next only after it passes.

**Serial order**: lark-cli → bitscli → bytedcli. The three cannot run in parallel (browser-based auth flows interfere with each other).

#### lark-cli

Agent runs directly:

> 帮我安装飞书 CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md

> **Gate**: all three lark-cli items (install / config / user auth) must be ✅ before moving on to bitscli / bytedcli fixes.

#### bitscli (BITS / Codebase)

```bash
npm install -g @byted/bits-cli --registry=https://bnpm.byted.org
bitscli update
```

Codebase auth (pick one):

```bash
bitscli codebase auth login
# Or auto-fetch JWT:
_jwt=$(npx --registry=https://bnpm.byted.org -y skills get-codebase-jwt 2>/dev/null) \
  && bitscli codebase auth login --jwt "$_jwt"
```

Retest: `bitscli codebase auth status` — output containing `Username` means pass.

#### tt-nova-ui (optional — used for delegated SDT case generation)

`tt-nova-ui` is vendored inside mobile-core and ships with the plugin — a missing copy means the
plugin install is incomplete, not that anything needs fetching:

```bash
ttadk plugin update ttadk/mobile-core
```

Retest: `[ -s .claude/skills/tt-nova-ui/ui-md-case-gen/SKILL.md ]` → pass. Skipping this fix
is always acceptable (`adk-sdt-ff` self-authors cases without it).

#### bytedcli (Meego only)

```bash
NPM_CONFIG_REGISTRY=http://bnpm.byted.org npm install -g @bytedance-dev/bytedcli@latest
export PATH="$(npm root -g)/../bin:$PATH"
bytedcli meego login
```

**Important**: `bytedcli meego login` is **interactive** — it prints the OAuth URL on stdout (alongside a QR-code image path which you should **ignore**) and then **blocks waiting for the user to authorize**. Run it with the Shell tool using a short `block_until_ms` (e.g. 5000ms) so you can read the URL out of stdout while the process keeps running in the background. Do **not** mention or show the QR-code image to the user — only the OAuth URL via `open` is needed.

Extract the OAuth URL from stdout by matching the pattern:

```
https://meego.larkoffice.com/b/auth/mcp?mode=device&user_code=XXXXX-XXXXX
```

Then open it for the user:

```bash
open "<extracted_url>"
```

Tell the user:

> Meego authorization page has opened:
> 1. Log in with your **Feishu account** (the corporate Feishu account linked to Meego)
> 2. Click **"Authorize"**
> 3. After seeing "Authorization succeeded" or the page auto-closes, reply **done**

(The backgrounded `bytedcli meego login` will finish on its own once the user authorizes; no need to kill it manually.)

After the user replies **done**, retest:

```bash
bytedcli --json meego workitem list --project-key __auth_check__ 2>&1
```

`error.code` != `MEEGO_AUTH_REQUIRED` → pass.

---

## Stage B — MCP Environment

### B-1. Read preset

```bash
cat "$(git rev-parse --show-toplevel)/.ttadk/config.json" 2>/dev/null
```

Parse `preset` (`ios` / `android`). If the file exists and contains a valid preset → proceed to B-2.

**No preset found** — further classify:

```bash
ls -d "$(git rev-parse --show-toplevel)/.ttadk" 2>/dev/null
```

| Situation | Detection | Action |
|-----------|-----------|--------|
| **Project never initialized** | `.ttadk/` directory does not exist | Ask the user via `AskQuestion` (MCQ, single-select): `该项目尚未执行 ttadk mobile init 初始化。是否现在执行？` → **yes**: jump to **B-0**; **no**: exit Stage B. |
| **Config missing / corrupt** | `.ttadk/` exists but `config.json` is absent or unparseable | Tell the user: `配置文件 .ttadk/config.json 缺失或损坏，建议重新初始化。` Then ask same question → **yes**: jump to **B-0**; **no**: exit Stage B. |

### B-0. Full init (triggered from B-1 when no valid preset)

> This section is only entered via B-1's referral. It is **not** a standalone entry point.

1. **Node version**: verify node ≥ 18 (should have been caught by Pre-check, but guard here too):
   ```bash
   node -v 2>&1
   ```
   If < 18 → tell the user to upgrade and stop.

2. **Install ttadk CLI**:
   ```bash
   npm install -g @byted/ttadk@latest --registry=https://bnpm.byted.org
   ttadk --version
   ```

3. **Clear preset cache** (prevents stale MCP versions):
   ```bash
   rm -rf "$HOME/.ttadk/store" 2>/dev/null || true
   ```

4. **Ask platform + agents**: use `AskQuestion` twice:
   - Platform → MCQ single-select (`ios` / `android`)
   - Target IDEs (agents) → MCQ **multi-select** (`cursor`, `trae`, `coco`, `claude`) — pre-select the current `IDE_TARGET` (inferred from B-2 logic, i.e. this SKILL.md's path).

5. **Run init**:
   ```bash
   cd "$(git rev-parse --show-toplevel)"
   ttadk mobile init --platform {platform} --agents {agents} --yes
   ```

6. **Return to B-1**: re-read `.ttadk/config.json`. If preset now exists → continue to B-2. If still missing → tell the user init failed, share the wiki (`https://bytedance.larkoffice.com/wiki/WyaNwSAz2iR7PDkG3ChcK6sLnOg#share-YZRZdQzOioRgFVxC517lOjnxgEb`) and exit Stage B.

### B-2. Determine IDE

Read the basename of the directory **two levels above** this SKILL.md (each IDE installs its skills under its own dedicated directory, so the physical path is the authoritative signal):

| This SKILL.md path | `IDE_TARGET` |
|--------------------|--------------|
| `<repo>/.cursor/skills/adk-doctor/SKILL.md` | `cursor` |
| `<repo>/.trae/skills/adk-doctor/SKILL.md`   | `trae` |
| `<repo>/.coco/skills/adk-doctor/SKILL.md`   | `coco` |
| `<repo>/.claude/skills/adk-doctor/SKILL.md` | `claude` |

That is: take the basename of `<skill_dir>` two levels up and strip the leading `.` — that's `IDE_TARGET`.

**Fallback**: if the basename is not one of `.cursor / .trae / .coco / .claude` (debug or non-standard install) → use the `AskQuestion` tool (MCQ, single-select) to let the user pick from `cursor / trae / coco / claude`.

### B-3. MCP list (required + optional)

| preset | required servers | optional servers |
|--------|------------------|------------------|
| `ios` | `adk-mobile`, `tiktok_d2c_mcp`, `tiktok_arch_mcp`, `UI_Wiki`, `iOS_context` | — |
| `android` | `adk-mobile`, `build-ai`, `core-ai` | `d2c4a` |

**Per-preset resolution**: look up the row for the current `preset` and read **both** the required and optional columns. iOS has no optional servers — do not check `d2c4a` (or any other Android-only server) on iOS.

**Optional servers** — health-checked in B-4 alongside required ones, but if unhealthy (any cause):

- do **NOT** enter B-5 classification, do **NOT** enter B-6 sync
- simply tell the user: `{name} is optional and currently unavailable; configure per wiki: <URL>`
- optional failures do **NOT** block the Stage B done status

Per-server wiki references:

| Optional server | Preset | Setup wiki |
|-----------------|--------|-----------|
| `d2c4a` | `android` only | `https://bytedance.larkoffice.com/wiki/U7evwxfueiONnJkWLjqcfDpanoc#share-XMoQdXaNjodpI2xYVUTlpINGgoc` |

### B-4. Health check

**Check list** = required servers ∪ optional servers, both looked up from B-3 by `preset`. On `ios`, the optional set is empty, so only required servers are checked.

For each server in the check list, just verify reachability — do NOT inspect MCP config files or invent server-specific probe tools. Pick the procedure by `IDE_TARGET`:

**Claude** (`claude`):
1. Call `ListMcpResourcesTool` with `server="adk-mobile"`. The response contains `"Available servers: ..."` — the full list of currently running MCP servers.
2. For each server in the check list, **substring-match** its name against that list (actual names may carry prefixes, e.g. `plugin:common-plugin:core-ai` matches `core-ai`).
3. In the list → **healthy**; absent → **unhealthy**.

**Cursor / Trae / Coco**:
1. For each server in the check list, call `CallMcpTool(server="<name>", toolName="_ping")`.
2. **Healthy**: normal result **or** `tool not found` error (the server is alive; `_ping` simply doesn't exist).
3. **Unhealthy**: `server not found` / connection / timeout / spawn error.

### B-5. Handle unhealthy servers

**Scope**: this step applies to **required** servers only. Unhealthy **optional** servers are handled per B-3 (just point the user to the wiki and move on).

**Classify by inspecting the IDE's MCP config file**. For `IDE_TARGET == cursor`, that means reading **both**:

- `<repo>/.cursor/mcp.json` (project-level)
- `~/.cursor/mcp.json` (user-level)

and looking up the server name under `mcpServers.<name>`. For Trae / Coco, check their equivalent MCP settings file or UI.

For each unhealthy required server, classify into one of two buckets:

| Bucket | How to tell | Action |
|--------|-------------|--------|
| **Configured but failing** | Server name IS present in the config file (e.g. `.cursor/mcp.json` contains `mcpServers.<name>`) but the probe can't reach it | The **most common cause on Cursor is the server being manually disabled by the user**. Do **not** invoke B-6 sync. Tell the user (in Chinese by default per the language rule): `<name> 已存在于 Cursor 配置 (.cursor/mcp.json)，请打开 Settings → Tools & MCP，找到 <name> 并点击 Enable / Reload。完成后回复 done。` After the user replies **done**, re-probe just that server. If after Enable + Reload the probe still fails, then ask the user to open the same Settings page, read the actual error message that Cursor shows, and share it back — diagnose from the real error, do **not** prescribe a low-level fix flowchart. |
| **Never configured** | Server name is NOT in any of the IDE's MCP config files (truly missing) | Collect into the **missing list** → go to B-6 |

> **`IDE_TARGET == claude`**: `ttadk mobile init --agents claude` can provision Claude's `.mcp.json`. For classification, inspect `<repo>/.mcp.json` (project-level). For **never-configured** servers, collect them into the missing list and enter B-6 (same as other IDEs). For **configured-but-failing** servers, tell the user: `<name> 已配置在 .mcp.json 中但连接失败，请执行 claude mcp list 检查状态，或在 Claude 设置中重启该 MCP server。完成后回复 done。` After **done**, re-probe. If still failing → ask the user to share the error from `claude mcp list` output and diagnose from the real error.

### B-6. Never-configured servers — hardstop ask to re-init (the only question point)

**Entry condition**: `IDE_TARGET ∈ {cursor, trae, coco, claude}` AND the missing list from B-5 is non-empty.

No questions are asked in any other case (CLI fixes, configured-but-failing servers).

Ask the user via the `AskQuestion` tool (MCQ, single-select):

```yaml
prompt: |
  以下 MCP server 在 {IDE_TARGET} 中未配置：
  {missing_list}

  如何处理？
options:
  - id: sync
    label: 执行 ttadk mobile init 重新初始化 MCP 配置到 {IDE_TARGET}
  - id: skip
    label: 跳过 — 我自行按文档配置
```

- `sync` → run the re-init script below
- `skip` → stop this flow, share the wiki: `https://bytedance.larkoffice.com/wiki/WyaNwSAz2iR7PDkG3ChcK6sLnOg#share-YZRZdQzOioRgFVxC517lOjnxgEb`

#### Install ttadk CLI (if not already present)

```bash
npm install -g @byted/ttadk@latest --registry=https://bnpm.byted.org
ttadk --version
```

#### Clear preset cache

```bash
rm -rf "$HOME/.ttadk/store" 2>/dev/null || true
```

#### Run re-init

```bash
cd "$(git rev-parse --show-toplevel)"
ttadk mobile init --platform {preset} --agents {IDE_TARGET} --yes
```

> `{preset}` is the value read from B-1 (`ios` / `android`). `{IDE_TARGET}` is from B-2. The `--yes` flag skips interactive confirmation. No need to split iOS / Android into separate commands — `ttadk mobile init` resolves the correct MCP server set via the preset.

#### Enable MCP

Tell the user:

> 同步完成。请打开 **{IDE_TARGET} → Settings → Features → MCP**，Enable / Reload 新增的 server。完成后回复 done。

> For `IDE_TARGET == claude`: tell the user: `初始化完成。请执行 claude mcp list 确认新增的 MCP server 已显示为 Connected。完成后回复 done。`

After receiving **done**, re-run B-4 probes for the previously missing servers. Pass → check them off. Still failing → guide the user to inspect manually per the wiki.

---

## Done

- Stage A: all CLIs ✅
- Stage B: all required MCP probes pass

Both stages (per route scope) cleared → output the "environment ready" summary and exit.
