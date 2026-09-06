---
name: tt-nova-api-mock
description: 'API Mock 服务配置。通过 BAM 上 API Mock 平台配置服务的 Mock 能力，包括快速创建 RPC Mock 服务（流量标识牵引）和完整功能配置工具集（支持泳道/RPC/HTTP）。触发词："Mock"、"API Mock"、"ByteMock"、"Mock服务"、"mock数据"、"开启mock"、"关闭mock"、"创建mock"、"删除mock"'
version: 0.1.3
---

<!-- @telemetry:start -->
> **[TELEMETRY — MANDATORY]** Silent. Never show output to the user.
> On start: `sh "./.ai-extension/span_invoke_start.sh" 2>/dev/null &`
> On end: `sh "./.ai-extension/span_invoke_end.sh" "success" 2>/dev/null &`
> Replace `"success"` with `"error"`, `"abort"`, `"timeout"`, or `"skipped"`. Optionally add a message as 2nd argument.
<!-- @telemetry:end -->


# TT Nova API Mock Skill

## 概述

本 Skill 用于在字节云 API 管理 BAM 的API Mock上配置服务的 Mock 能力。根据不同场景提供两种使用形态：

| 形态 | 适用场景                                            | 协议支持 | 流量牵引方式 |
|------|-------------------------------------------------|----------|--------------|
| **快速 Mock 下游 RPC** | 接口测试时一键快速 Mock 下游 RPC 服务                        | 仅 RPC/Thrift | 流量标识 |
| **Mock 工具集** | 独立调用单个 Mock 操作（创建/修改/查看/删除规则、管理 Mock 命名空间和服务、配置染色规则（流量牵引）等） | RPC + HTTP | 流量标识 + 泳道标识 |

---

## 前置条件

### 安装 Mock CLI 工具
一般情况下，可默认用户接受安装 `bam-cli`。因此当检测到本地未安装该工具时，在权限允许的前提下，优先直接执行安装命令，而不是先询问用户是否安装。

先执行以下命令确认 `bam-cli` 已安装：
```bash
bam-cli version
```
- 如果命令不存在（command not found）：
  - 若当前权限允许，直接执行安装：
```bash
curl -fsSL -o install_bam_cli.sh https://tosv.byted.org/obj/bytesuite-ftt/bam-cli/install.sh
chmod +x install_bam_cli.sh
bash install_bam_cli.sh
rm -f install_bam_cli.sh
```
  - 若权限不足、安装被拒绝或安装失败，再告知用户并给出上述安装命令

### 环境参数确认

以下参数在所有模式下均需确认：

| 参数 | 确认策略 |
|------|----------|
| VRegion | 必须确认。用户未提供时默认 `i18n-tt` |
| JWT | 根据 VRegion 自动获取（见下方） |

#### VRegion 映射表
| VREGION | ZONE | VDC | JWT-VRegion | Alias |
|---|---|---|---|---|
| i18n-tt | SGALI | sg1 *(default)*, sgdt, my, my2, my3 | i18n | Singapore-Central, sg, i18n |
| i18n-tt | MVAALI | maliva *(default)*, useast3, useastdt, useast4 | i18n | US-East, va, us |
| i18n-bd | Asia-SouthEastBD | mya *(default)*, myb, myc, bddedt, bdsgdt | i18n-bd | I18N-BD |
| boe | BOE | boe | boe | BOE |
| boei18n | BOEI18N | boei18n | boei18n | US-BOE, BOEI18N |

#### 获取 JWT
根据确认的 VRegion 查映射表得到 JWT-VRegion，然后执行：
```bash
npm_config_registry=https://bnpm.byted.org/ npx -y agentbuddy get-jwt --region <JWT-VRegion>
```
- 安全提示：JWT 为敏感信息，除非明确要求，勿直接回显 Token。

---

## Step 0：意图路由

根据用户输入判断执行模式：

| 输入信号                                  | 模式 |
|---------------------------------------|------|
| "快速Mock"、"一键Mock"、"接口测试中Mock下游"       | 快速 Mock 下游 RPC |
| "创建mock服务"、"配置mock"、明确指定 PSM + method | 快速 Mock 下游 RPC |
| "创建规则"、"更新规则"、"删除规则"、"查询规则" | Mock 工具集 |
| "启用规则"、"禁用规则"、"获取规则" | Mock 工具集 |
| "创建命名空间"、"删除命名空间"、"查询命名空间" | Mock 工具集 |
| "列出服务"、"创建服务"、"更新服务"、"删除服务" | Mock 工具集 |
| "创建染色"、"删除染色"、"查询染色"、"更新染色开关" | Mock 工具集 |
| "配置染色规则"、"流量牵引" | Mock 工具集 |
| 单独操作：查看/修改/删除/开启/关闭 mock              | Mock 工具集 |
| "泳道"、"lane"、"HTTP mock"               | Mock 工具集 |
| "管理mock"、"查看mock列表"、"配置染色规则"          | Mock 工具集 |
| "mock空间"、"mock服务分组"、"mock期望"          | Mock 工具集 |
| 无法判断                                  | 询问用户选择 |

---

## 形态一：快速 Mock 下游 RPC

### 快速 Mock 特点
- 系统自动完成全套创建（Mock 空间、Mock 服务、接口分流）
- 用户只需提供 PSM、Method、Mock 数据
- 适用场景：接口测试时一键快速 Mock 下游 RPC 服务

### 快速 Mock 能力矩阵

| 能力 | 命令 | 说明 |
|------|------|------|
| 创建 Mock 服务 | `create-mock-service` | 创建 Mock 服务 |
| 修改 Mock 数据 | `update-mock-data` | 修改 Mock 返回数据 |
| 查看 Mock 数据 | `query-mock-detail` | 查询 Mock 配置 |
| 开启/关闭 Mock | `update-mock-switch` | 启用或禁用 Mock |
| 删除 Mock | `delete-mock` | 删除 Mock 配置 |

👉 [进入快速 Mock 下游 RPC](./references/quick-rpc.md)

---

## 形态二：Mock 工具集

### 工具集特点
- 提供独立调用的单个 Mock 操作工具
- 用户可按需调用特定功能
- 用户可灵活编排使用步骤
- 支持泳道标识 + 流量标识
- 支持 RPC + HTTP 协议

### 工具集能力矩阵

| 能力     | 命令 | 说明 |
|--------|------|------|
| 期望规则管理 | `create-rule`/`update-rule`/`get-rule-by-id`/`query-rules`/`enable-rule`/`disable-rule`/`delete-rule-by-id` | Mock 规则 CRUD |
| 命名空间管理 | `create-namespace`/`delete-namespace`/`get-namespaces` | 命名空间管理 |
| 服务管理   | `list-service`/`create-service-relation`/`update-service`/`delete-service` | 服务管理 |
| 染色管理   | `put-flow-dyeing`/`delete-flow-dyeing`/`list-flow-dyeing`/`update-flow-dyeing-switch` | 流量牵引配置 |

👉 [Mock 工具集](./references/tools.md)

---

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| 区域不可用 | 返回明确的错误提示，并建议用户选择可用区域 |
| Mock 服务创建失败 | 检查 PSM、method 是否正确，确认 namespace 是否有效 |
| Mock 数据格式错误 | 提示用户 Mock data 必须为有效的 JSON 格式 |
| 未认证 (401) | 执行 `bytedcli --site <site> auth login` 登录 |
| 站点认证隔离 | `i18n-tt`（TikTok SSO）与 `prod/i18n-bd/boei18n`（ByteDance SSO）隔离，需分别登录 |
| 权限不足 | 提示用户确认是否具有该 namespace 的操作权限 |
| 染色规则未生效 | 确认染色标识 `ENV:<lane>` 或 `MOCK:new_mock_xx` 是否正确传递到请求中 |
| 染色规则创建失败 | 检查染色标识格式是否正确（`ENV:boe_xxx`/`ENV:ppe_xxx` 或 `MOCK:new_mock_xx`） |
| 规则创建失败 | 检查必填参数是否完整（namespace、endpoint_id、method、protocol、name） |
