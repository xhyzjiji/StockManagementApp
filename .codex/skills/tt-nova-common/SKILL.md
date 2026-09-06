---
name: tt-nova-common
description: "TT Nova 公共工具集，提供所有 TT Nova skill 集合（API、UI、DataGen、Common）的一键更新和一键移除能力，并提供 API Mock 配置能力。当用户提到 \"update tt-nova\"、\"upgrade tt-nova\"、\"更新 tt-nova\"、\"remove tt-nova\"、\"delete tt-nova\"、\"卸载 tt-nova\"、\"删除 tt-nova\"、\"Mock\"、\"API Mock\"、\"ByteMock\"、\"Mock服务\"、\"开启mock\"、\"关闭mock\"、\"创建mock\"、\"删除mock\" 时自动路由到对应子 skill。"
---

# TT Nova 公共工具集

提供所有 TT Nova skill 集合的生命周期管理能力：**一键更新**、**一键移除**，以及 Common 公共能力：**API Mock 配置**。

---

## 版本说明（vendored 内置副本，无自动更新）

本目录是随 `ttadk/mobile-core` 插件分发的**固定版本副本**（tt-nova-common 1.0.126，vendored 自
`skills.byted.org/ttat/tt_nova`）。原版的「每日自更新」前置步骤在此副本中**移除**：
- 不检查 `/tmp/.skill-tt-nova-common-updated`，不执行任何 agentbuddy/npx 更新命令，直接进入下方路由；
- 目的：版本确定、离线可用（自更新中断会留下只有目录没有 SKILL.md 的空壳，曾导致探测假阳性）。

升级方式：维护者以新版本包替换本目录后随 mobile-core 发版。临时想用官方最新版可手动执行
`npm_config_registry="https://bnpm.byted.org" npx -y agentbuddy@latest skill add skills.byted.org/ttat/tt_nova --skill tt-nova-common --agent claude-code --yes`
覆盖本地副本（下次 `ttadk plugin update` 会还原为内置版本）。

---

## 子 Skill 索引

| # | 子 Skill | 定位 | 子技能路径 |
|---|---------|------|-----------|
| 1 | **tt-nova-update** | 一键更新全部 TT Nova skill 集合 | [tt-nova-update/SKILL.md](tt-nova-update/SKILL.md) |
| 2 | **tt-nova-remove** | 一键移除全部 TT Nova skill 及自身 | [tt-nova-remove/SKILL.md](tt-nova-remove/SKILL.md) |
| 3 | **tt-nova-api-mock** | API Mock 服务配置，支持快速 RPC Mock 和 Mock 工具集 | [tt-nova-api-mock/SKILL.md](tt-nova-api-mock/SKILL.md) |

---

## 路由规则

| 用户意图 / 触发信号 | 路由目标 |
|-------------------|---------|
| "update tt-nova"、"upgrade tt-nova"、"更新 tt-nova"、"刷新 tt-nova"、"tt-nova update" | **tt-nova-update** |
| "remove tt-nova"、"delete tt-nova"、"uninstall tt-nova"、"卸载 tt-nova"、"删除 tt-nova"、"tt-nova remove" | **tt-nova-remove** |
| "Mock"、"API Mock"、"ByteMock"、"Mock服务"、"mock数据"、"开启mock"、"关闭mock"、"创建mock"、"删除mock"、"配置mock"、"快速Mock"、"一键Mock"、"泳道"、"流量牵引" | **tt-nova-api-mock** |

匹配到子 skill 后，`Read` 对应的 SKILL.md 获取完整执行指引。

---

## 子 Skill 说明

### tt-nova-update — 一键更新

通过 `npx -y agentbuddy@latest skill add` 顺序更新 4 个顶层 skill：

| # | 集合 | 安装命令中的 skill 名 |
|---|------|--------------------|
| 1 | TT Nova API | `tt-nova-api` |
| 2 | TT Nova UI | `tt-nova-ui` |
| 3 | TT Nova DataGen（含 execute、pipe、biz-skill-manage） | `tt-nova-datagen` |
| 4 | TT Nova Common | `tt-nova-common` |

### tt-nova-remove — 一键移除

通过 `npx -y agentbuddy@latest skill remove` 移除全部 4 个顶层 skill（API → UI → DataGen → Common）。`tt-nova-datagen-biz-skill-manage` 已合并回 `tt-nova-datagen`，随 DataGen 一并移除；`tt-nova-common` 最后删除（self-cleanup）。

### tt-nova-api-mock — API Mock 配置

通过 BAM API Mock 平台配置服务 Mock 能力。支持快速创建下游 RPC Mock 服务，也支持规则、命名空间、服务关系和染色规则等完整 Mock 工具集。

---

## 共享约定

- **Agent 自动检测**：系统提示包含 "You operate in Cursor" → `cursor`；Claude Code → `claude-code`；Trae → `trae`；用户显式指定时以用户为准。
- **npm registry**：统一使用 `npm_config_registry="https://bnpm.byted.org"`（字节内网源）。
- **网络权限**：Shell 执行时需要 `full_network` 权限访问 `bnpm.byted.org`。
- **容错**：单个命令失败不阻塞后续，最终汇总报告所有失败项。
