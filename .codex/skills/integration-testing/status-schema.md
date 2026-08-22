# status.json 完整结构

存放路径：`.gdpa/{session-id}/status.json`

## 字段说明

```json
{
  "session_id": "string — 会话唯一标识，必须与 workflow 中所有命令显式传递的 --session-id 保持一致（直接使用 gdpa-cli create-session 返回值）",
  "created_at": "string — 创建时间 ISO8601",
  "requirement": "string — 用户需求一句话描述",
  "current_phase": "string — 当前所在阶段（pre_check|test_design|code_submit|deploy|test_execution|log_verify|tracking_verify|report）",
  "phases": {
    "pre_check": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null — 开始时间",
      "completed_at": "string|null — 完成时间",
      "summary": "string — 该阶段执行摘要"
    },
    "test_design": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null",
      "completed_at": "string|null",
      "summary": "string"
    },
    "code_submit": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null",
      "completed_at": "string|null",
      "summary": "string"
    },
    "deploy": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null",
      "completed_at": "string|null",
      "summary": "string"
    },
    "test_execution": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null",
      "completed_at": "string|null",
      "summary": "string"
    },
    "log_verify": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null",
      "completed_at": "string|null",
      "summary": "string"
    },
    "tracking_verify": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null",
      "completed_at": "string|null",
      "summary": "string"
    },
    "report": {
      "status": "string — pending|in_progress|completed|skipped|failed",
      "started_at": "string|null",
      "completed_at": "string|null",
      "summary": "string"
    }
  },
  "context": {
    "psm": "string — 服务 PSM（来源：pre_check，使用：全部）",
    "branch": "string — Git 开发分支名（来源：pre_check，使用：code_submit, deploy）",
    "env_type": "string — 部署环境类型 boe|ppe（来源：pre_check，使用：deploy, test_execution, log_verify, tracking_verify）",
    "region": "string — 区域 i18n|cn（来源：pre_check，使用：deploy）",
    "deploy_env_name": "string — PPE/BOE 环境名（来源：deploy，使用：test_execution, log_verify, tracking_verify）",
    "deployment_id": "string|null — Env Platform 部署 ID（来源：deploy，使用：deploy 状态轮询）",
    "test_vregion": "string — 标准 VRegion，如 Singapore-Central（来源：pre_check，使用：test_execution, log_verify, tracking_verify）",
    "test_vdc": "string — VDC，如 sg1（来源：pre_check，使用：test_execution, log_verify）",
    "affected_interfaces": [
      {
        "method": "string — 接口方法名",
        "type": "string — rpc|http",
        "schema": "object|null — 请求/响应 Schema",
        "description": "string — 接口描述"
      }
    ],
    "test_context_docs": ["string — 参考文档路径列表（来源：pre_check，使用：test_design）"],
    "test_cases": [
      {
        "id": "string — 用例 ID",
        "name": "string — 用例名称",
        "interface": "string — 接口方法名",
        "type": "string — rpc|http",
        "priority": "string — P0|P1|P2",
        "is_write": "boolean — 是否写操作",
        "request": "object — 请求体",
        "expected": "object — 预期结果"
      }
    ],
    "test_data": "object|null — 构造的测试数据（来源：test_design，使用：test_execution）",
    "commit_hash": "string — Push 的 commit hash（来源：code_submit，使用：deploy, report）",
    "deploy_method": "string — 部署方式 dsl_create|dsl_deploy（来源：deploy，使用：report）",
    "test_env": "string — 完整泳道名（来源：deploy，使用：test_execution, log_verify, tracking_verify）",
    "test_start_time": "string|null — 测试开始时间 ISO8601（来源：test_execution，使用：log_verify, tracking_verify）",
    "test_end_time": "string|null — 测试结束时间 ISO8601（来源：test_execution，使用：log_verify, tracking_verify）",
    "metrics_to_verify": [
      {
        "name": "string — 指标名",
        "type": "string — Counter|Timer|Store",
        "expected_tags": "object — 预期标签",
        "expected_change": "string — 预期变化描述"
      }
    ],
    "username": "string — Git 用户名（来源：pre_check，使用：report 数据回传）",
    "scope": "string — 测试范围 all|incremental（来源：pre_check，使用：report 数据回传）",
    "file_num": "number — 测试涉及的源代码文件数量（来源：pre_check，使用：report 数据回传）",
    "gen_case_start_time": "string|null — 测试用例生成开始时间 ISO8601（来源：test_design，使用：report 数据回传）",
    "gen_case_end_time": "string|null — 测试用例生成结束时间 ISO8601（来源：test_design，使用：report 数据回传）",
    "gen_case_cost": "number|null — 测试用例生成总耗时（秒，来源：test_design，使用：report 数据回传）",
    "exec_cost": "number|null — 测试执行总耗时（秒，来源：test_execution，使用：report 数据回传）"
  },
  "history": [
    {
      "phase": "string — 所属阶段",
      "action": "string — 操作标识",
      "detail": "string — 操作详情",
      "timestamp": "string — ISO8601 时间"
    }
  ]
}
```

## 初始化模板

新会话时创建 `.gdpa/{session-id}/status.json`：

```json
{
  "session_id": "sess_20260416_143052_abcd1234",
  "created_at": "2026-04-16T14:30:52+08:00",
  "requirement": "用户的集成测试需求描述",
  "current_phase": "pre_check",
  "phases": {
    "pre_check":        { "status": "pending", "started_at": null, "completed_at": null, "summary": "" },
    "test_design":      { "status": "pending", "started_at": null, "completed_at": null, "summary": "" },
    "code_submit":      { "status": "pending", "started_at": null, "completed_at": null, "summary": "" },
    "deploy":           { "status": "pending", "started_at": null, "completed_at": null, "summary": "" },
    "test_execution":   { "status": "pending", "started_at": null, "completed_at": null, "summary": "" },
    "log_verify":       { "status": "pending", "started_at": null, "completed_at": null, "summary": "" },
    "tracking_verify":  { "status": "pending", "started_at": null, "completed_at": null, "summary": "" },
    "report":           { "status": "pending", "started_at": null, "completed_at": null, "summary": "" }
  },
  "context": {
    "psm": "",
    "branch": "",
    "env_type": "",
    "region": "i18n",
    "deploy_env_name": "",
    "deployment_id": null,
    "test_vregion": "",
    "test_vdc": "",
    "affected_interfaces": [],
    "test_context_docs": [],
    "test_cases": [],
    "test_data": null,
    "commit_hash": "",
    "deploy_method": "",
    "test_env": "",
    "test_start_time": null,
    "test_end_time": null,
    "metrics_to_verify": [],
    "username": "",
    "scope": "incremental",
    "file_num": 0,
    "gen_case_start_time": null,
    "gen_case_end_time": null,
    "gen_case_cost": null,
    "exec_cost": null
  },
  "history": []
}
```
