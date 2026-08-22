# 可用 Skill 速查与选择指南

> **重要**：在调用任何 Skill 前，**必须先阅读对应的 Skill** 获取完整的参数说明、输入输出格式和使用示例。
> **Workflow Session 约束**：本文件中的所有 `gdpa-cli run` 示例在实际执行时都应显式追加同一个 `--session-id <sid>`。

## Skill 速查表

| 阶段 | Skill | 说明 | 典型场景 |
|------|-------|------|---------|
| pre_check | `repo2psm` | PSM 自动检测 | 从仓库配置文件提取服务 PSM |
| pre_check | `repotalk` | 代码仓库智能查询 | 语义搜索变更涉及的接口和业务逻辑 |
| pre_check | `bam-api` | 查询 API 接口定义 | 获取接口 Schema（方法名、请求/响应结构） |
| test_design | `repotalk` | 代码仓库智能查询 | 深入分析代码分支路径、错误处理逻辑 |
| test_design | `bam-api` | 查询 API 接口定义 | 获取完整接口定义用于构造测试数据 |
| deploy | `env` | Env Platform 环境管理 | 创建 PPE/BOE 环境、部署服务、查询部署状态 |
| test_execution | `neptune-acl` | Neptune ACL 鉴权查询 | 检查 BAM 调用方 `explorer.api.executor` 是否被授权访问被测服务 |
| test_execution | `bam-query` | BAM 接口测试 | 发送 RPC/HTTP 测试请求 |
| log_verify | `argos-query` | Argos 日志查询 | 按 PSM/关键字/时间范围搜索业务日志和错误日志 |
| tracking_verify | `metrics` | Metrics 监控数据 | 查询 QPS/延迟/错误率等指标 |

## Skill 选择决策指南

```
需要分析代码变更检测受影响接口？
  └─ repotalk (search_nodes) → 语义搜索变更相关代码

需要获取接口的请求/响应 Schema？
  ├─ 知道 PSM → bam-api (get_api_service_list → get_api_definition_info)
  └─ 不知道 PSM → bam-api (get_api_definition_info_without_psm)

需要创建 PPE/BOE 环境并部署服务？
  └─ env (dsl_create → dsl_status 轮询；已有环境用 dsl_deploy)

需要查询已有 PPE/BOE 环境？
  └─ env (detail → 判断环境是否存在；instance_meta → 查看服务状态)

需要检查 BAM 是否有权限调用被测服务？
  └─ neptune-acl (check_authen → check_acl_enabled → check_acl_authorized caller=explorer.api.executor)

需要测试接口（发送 RPC/HTTP 请求）？
  └─ bam-query（vregion 用标准值如 Singapore-Central，env 用完整泳道名）

需要查询业务日志或错误日志？
  └─ argos-query（search: 按关键字搜索；error_overview: 错误聚合统计）

需要验证 Metrics 埋点？
  └─ metrics（按 PSM + 指标名查询，PPE 用 Singapore-PPE 等 PPE VRegion）
```

## 关键阶段 Skill 调用示例

### pre_check 阶段

**repotalk — 语义搜索变更涉及的接口**

```bash
gdpa-cli run repotalk --session-id <sid> --input '{"action": "search_nodes", "question": "GetBudgetInfo handler implementation", "repo_names": "tiktok/pns_dp_api"}'
```

**bam-api — 获取接口定义**

```bash
# 获取服务的接口列表
gdpa-cli run bam-api --session-id <sid> --input '{"action": "get_api_service_list", "psm": "tiktok.pns.dp_api"}'

# 获取具体接口定义（含请求/响应 Schema）
gdpa-cli run bam-api --session-id <sid> --input '{"action": "get_api_definition_info", "psm": "tiktok.pns.dp_api", "method": "GetBudgetInfo"}'
```

### deploy 阶段

**env — 查询环境是否存在**

```bash
gdpa-cli run env --session-id <sid> --input '{"action": "detail", "name": "ppe_privacy_query_test", "vregion": "Singapore-Central"}'
```

**env — 创建新 PPE 环境并部署（环境不存在时）**

```bash
gdpa-cli run env --session-id <sid> --input '{"action": "dsl_create", "name": "ppe_privacy_query_test", "psm": "tiktok.pns.dp_api", "branch": "test/privacy-query-integration", "vregion": "Singapore-Central"}'
```

**env — 升级已有环境中的服务（环境已存在时）**

```bash
gdpa-cli run env --session-id <sid> --input '{"action": "dsl_deploy", "name": "ppe_privacy_query_test", "psm": "tiktok.pns.dp_api", "branch": "test/privacy-query-integration", "vregion": "Singapore-Central"}'
```

**env — 查询部署状态**

```bash
gdpa-cli run env --session-id <sid> --input '{"action": "dsl_status", "deployment_id": "2045028287951577088", "name": "ppe_privacy_query_test", "vregion": "Singapore-Central"}'
```

**env — 查看服务实例详情**

```bash
gdpa-cli run env --session-id <sid> --input '{"action": "instance_meta", "name": "ppe_privacy_query_test", "service_types": "tce", "services": "tiktok.pns.dp_api", "vregion": "Singapore-Central"}'
```

**env — 测试完成后清理环境（可选）**

```bash
gdpa-cli run env --session-id <sid> --input '{"action": "delete_env", "name": "ppe_privacy_query_test", "vregion": "Singapore-Central"}'
```

### test_execution 阶段

**neptune-acl — ACL 鉴权预检查（在 bam-query 之前执行）**

```bash
# 1. 检查服务鉴定是否开启
gdpa-cli run neptune-acl --session-id <sid> --input '{"action":"check_authen","callee":"tiktok.pns.dp_api","vregion":"Singapore-Central"}'

# 2. 检查严格授权是否开启（仅当 authen_enabled=true 时）
gdpa-cli run neptune-acl --session-id <sid> --input '{"action":"check_acl_enabled","callee":"tiktok.pns.dp_api","vregion":"Singapore-Central"}'

# 3. 检查 BAM 调用方是否已授权（仅当 acl_enabled=true 时）
gdpa-cli run neptune-acl --session-id <sid> --input '{"action":"check_acl_authorized","callee":"tiktok.pns.dp_api","caller":"explorer.api.executor","vregion":"Singapore-Central"}'
```

> BAM 固定使用 `explorer.api.executor` 作为调用方，不可更改。如果被测服务开启严格授权且未授权该 PSM，需要用户在 Neptune 平台手动添加授权。

**bam-query — 接口测试**

> **重要**：`vregion` 必须使用标准值，`env` 使用完整泳道名。所有参数从 `status.json` 的 `context` 读取。

```bash
# RPC 接口测试
gdpa-cli run bam-query --session-id <sid> --input '{"action": "rpc", "psm": "tiktok.pns.dp_api", "func_name": "GetBudgetInfo", "request": "{\"budget_id\": 1001, \"user_id\": 12345}", "vregion": "Singapore-Central", "env": "ppe_i18n_env_feature_2147530", "vdc": "sg1"}'
```

| 参数 | 来源 | 示例值 |
|------|------|--------|
| `vregion` | `context.test_vregion` | `Singapore-Central`（不是 `sg`） |
| `vdc` | `context.test_vdc` | `sg1`（不是 `sg`） |
| `env` | `context.test_env` | `ppe_i18n_env_feature_2147530`（不是 `ppe`） |

### log_verify 阶段

**argos-query — 业务日志查询**

```bash
# 搜索业务关键字（如 handler 方法名）
gdpa-cli run argos-query --session-id <sid> --input '{"action": "search", "psm": "tiktok.pns.dp_api", "keyword": "PrivacyQuery", "start_time": "2026-04-17T07:25:00+08:00", "end_time": "2026-04-17T07:35:00+08:00", "vregion": "Singapore-Central"}'
```

**argos-query — 错误日志查询**

```bash
# 搜索 ERROR 级别日志
gdpa-cli run argos-query --session-id <sid> --input '{"action": "search", "psm": "tiktok.pns.dp_api", "keyword": "error", "start_time": "2026-04-17T07:25:00+08:00", "end_time": "2026-04-17T07:35:00+08:00", "vregion": "Singapore-Central"}'

# 搜索 PANIC 级别日志
gdpa-cli run argos-query --session-id <sid> --input '{"action": "search", "psm": "tiktok.pns.dp_api", "keyword": "panic", "start_time": "2026-04-17T07:25:00+08:00", "end_time": "2026-04-17T07:35:00+08:00", "vregion": "Singapore-Central"}'

# 错误聚合统计
gdpa-cli run argos-query --session-id <sid> --input '{"action": "error_overview", "psm": "tiktok.pns.dp_api", "start_time": "2026-04-17T07:25:00+08:00", "end_time": "2026-04-17T07:35:00+08:00", "vregion": "Singapore-Central"}'
```

> **注意**：
> - Argos 日志可能有 1-5 分钟延迟，首次无结果应等待 60 秒后重试
> - PPE 日志合并到在线存储，VRegion 使用**在线 VRegion**（如 `Singapore-Central`），不要用 PPE VRegion
> - 错误日志需区分"预期内错误"（异常用例触发）和"非预期错误"（正向用例触发）

### tracking_verify 阶段

**metrics — 指标查询**

```bash
# 查询 QPS 指标
gdpa-cli run metrics --session-id <sid> --input '{"action": "query", "psm": "tiktok.pns.dp_api", "metric": "budget_query_qps", "vregion": "Singapore-PPE", "start_time": "2026-04-16T14:50:00+08:00", "end_time": "2026-04-16T15:02:00+08:00"}'
```

| 环境 | Metrics VRegion | 说明 |
|------|----------------|------|
| PPE (sg1) | `Singapore-PPE` | PPE 环境使用 PPE VRegion |
| PPE (useast5) | `US-TTP-PPE` | |
| BOE | `China-BOE` | BOE 环境 |
| 线上 (sg1) | `Singapore-Central` | 线上环境（通常不在此 workflow 中使用） |

> PPE Metrics VRegion 映射详见 `integration-testing-knowledge` Skill 的 "Query Metrics" 部分。
