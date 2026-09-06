---
name: tt-nova-remove
description: "One-click remove all TT Nova skills (API, UI, DataGen, Common 及其全部子 skill) via AgentBuddy CLI. Use when the user wants to remove tt-nova skills, uninstall tt-nova, or mentions \"remove tt-nova\", \"delete tt-nova\", \"uninstall tt-nova\", \"tt-nova remove\", \"卸载 tt-nova\", \"删除 tt-nova\""
---

# TT Nova Skills Remove

一键移除所有 TT Nova skill 集合（API、UI、DataGen、Common）及其全部子 skill。

## 前置步骤：Skill 自动更新

**每次调用本 Skill 时，先执行自更新，确保使用最新版本。**

```bash
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-common -a <agent> -y
```

其中 `<agent>` 根据当前运行环境自动替换为对应的 agent 名称：`cursor`、`claude-code`、`trae` 等。

- 更新成功 → 继续后续执行流程。
- 更新失败 → 向用户报告错误，但不阻塞，继续后续流程。

---

## 移除范围

4 个顶层 skill，其中 `tt-nova-datagen-biz-skill-manage` 已合并回 `tt-nova-datagen`，随 DataGen 一并移除：

| # | 主 Skill | 包含的子 Skill | 说明 |
|---|---------|---------------|------|
| 1 | `tt-nova-api` | case-newbuilder, case-rebuilder, case-tofaas, biz-tools, knowledge-creator | API 测试全链路 |
| 2 | `tt-nova-ui`      | ui-xmind-case-gen, ui-md-case-gen, ui-md-case-upload, ui-xmind-case-upload, ui-xmind-case-specify, ui-debug-task-exec | UI自动化测试   |
| 3 | `tt-nova-datagen` | datagen-execute, datagen-pipe, datagen-biz-skill-manage | 数据生成与业务造数 skill 管理 |
| 4 | `tt-nova-common` | tt-nova-update, tt-nova-remove, tt-nova-api-mock | 公共工具（含自身） |

---

## Agent 检测

自动检测当前 agent 类型：
- 系统提示包含 "You operate in Cursor" → `cursor`
- Claude Code 环境 → `claude-code`
- Trae 环境 → `trae`
- 用户显式指定时以用户为准

---

## 执行

按顺序移除 4 个顶层 skill。所有命令**顺序执行**，单个失败不阻塞后续。

```bash
# ========== 移除顶层 skill ==========

echo "=== [1/4] Removing tt-nova-api (includes all API sub-skills) ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill remove --skill tt-nova-api -y

echo "=== [2/4] Removing tt-nova-ui (includes all UI sub-skills) ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill remove --skill tt-nova-ui -y

echo "=== [3/4] Removing tt-nova-datagen (includes DataGen execute, pipe, and biz-skill-manage skills) ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill remove --skill tt-nova-datagen -y

echo "=== [4/4] Removing tt-nova-common (includes update + remove + api-mock) ==="
npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill remove --skill tt-nova-common -y

echo "========== All TT Nova skills removed! =========="
```

---

## 执行后验证

移除完成后，运行以下命令确认无残留：

```bash
ls ~/.cursor/skills/ 2>/dev/null | grep -i tt-nova || echo "No tt-nova skills remaining."
```

如有残留文件，手动删除对应目录即可。

---

## Notes

- Requires Node.js / npm available in PATH.
- Commands need network access to `bnpm.byted.org` — request `full_network` permission when running via Shell tool.
- `tt-nova-datagen-biz-skill-manage` 是 `tt-nova-datagen` 的子 skill，随 DataGen 一并移除。
- `tt-nova-common` 最后移除（包含自身 self-cleanup）。
- 移除后如需重新安装，执行：`npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill <skill-name> -a <agent> -y`
