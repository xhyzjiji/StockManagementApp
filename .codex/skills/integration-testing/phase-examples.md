# 各阶段产出文件与状态更新示例

每个阶段完成时需要：(1) 写入产出文件 (2) 更新 status.json。以下是各阶段的完整示例。

---

## Phase 0: pre_check

### 产出文件 `pre-check/task_config.json`

```json
{
  "psm": "tiktok.pns.dp_api",
  "branch": "feat/add-budget-query",
  "env_type": "ppe",
  "region": "i18n",
  "space_id": 94017024770,
  "control_planes": ["CONTROL_PLANE_I18N"],
  "test_vregion": "Singapore-Central",
  "test_vdc": "sg1",
  "affected_interfaces": [
    {
      "method": "GetBudgetInfo",
      "type": "rpc",
      "schema": {
        "request": {"budget_id": "int64", "user_id": "int64"},
        "response": {"budget": "Budget", "status": "int32"}
      },
      "description": "查询预算信息"
    },
    {
      "method": "UpdateBudgetStatus",
      "type": "rpc",
      "schema": {
        "request": {"budget_id": "int64", "status": "int32"},
        "response": {"success": "bool"}
      },
      "description": "更新预算状态"
    }
  ],
  "test_context_docs": [
    "specs/budget-query/spec.md",
    "specs/budget-query/plan.md"
  ],
  "changed_files": [
    "biz/service/budget_query.go",
    "biz/handler/budget_handler.go"
  ]
}
```

### status.json 更新

```json
{
  "current_phase": "test_design",
  "phases": {
    "pre_check": {
      "status": "completed",
      "started_at": "2026-04-16T14:31:00+08:00",
      "completed_at": "2026-04-16T14:35:00+08:00",
      "summary": "检测到 PSM tiktok.pns.dp_api，分支 feat/add-budget-query，受影响接口 2 个（GetBudgetInfo, UpdateBudgetStatus），环境 PPE/Singapore-Central → pre-check/task_config.json"
    }
  },
  "context": {
    "username": "alice",
    "scope": "incremental",
    "file_num": 2
  }
}
```

---

## Phase 1: test_design

### 产出文件 `test-design/test_plan.md`

```markdown
## 测试方案

### 测试环境
- **Env Type**: ppe
- **VRegion**: Singapore-Central
- **VDC**: sg1

### 测试用例 (5 个)

| # | 用例名称 | 接口 | 类型 | 优先级 | 请求摘要 | 预期结果 |
|---|---------|------|------|--------|---------|---------|
| 1 | 正常查询预算 | GetBudgetInfo | 读/RPC | P0 | budget_id=1001 | 返回预算详情 |
| 2 | 查询不存在的预算 | GetBudgetInfo | 读/RPC | P1 | budget_id=0 | 返回空或错误码 |
| 3 | 空参数查询 | GetBudgetInfo | 读/RPC | P1 | budget_id=null | 返回参数错误 |
| 4 | 正常更新状态 | UpdateBudgetStatus | ⚠️ 写/RPC | P0 | budget_id=1001, status=2 | 更新成功 |
| 5 | 非法状态值 | UpdateBudgetStatus | ⚠️ 写/RPC | P1 | budget_id=1001, status=-1 | 返回参数错误 |

### 待验证 Metrics (2 个)

| # | 指标名 | 类型 | 预期标签 | 预期变化 |
|---|--------|------|---------|---------|
| 1 | budget_query_qps | Counter | method=GetBudgetInfo | +N |
| 2 | budget_query_latency | Timer | method=GetBudgetInfo | 有值 |

### 测试数据来源
- 基于 spec.md 中定义的预算查询业务规则
- 基于 GetBudgetInfo/UpdateBudgetStatus 接口 Schema
```

### 产出文件 `test-design/test_cases.json`

```json
{
  "test_cases": [
    {
      "id": "TC001",
      "name": "正常查询预算",
      "interface": "GetBudgetInfo",
      "type": "rpc",
      "priority": "P0",
      "is_write": false,
      "request": {"budget_id": 1001, "user_id": 12345},
      "expected": {"status_code": 0, "has_budget": true}
    },
    {
      "id": "TC002",
      "name": "查询不存在的预算",
      "interface": "GetBudgetInfo",
      "type": "rpc",
      "priority": "P1",
      "is_write": false,
      "request": {"budget_id": 0, "user_id": 12345},
      "expected": {"status_code": 404}
    },
    {
      "id": "TC003",
      "name": "空参数查询",
      "interface": "GetBudgetInfo",
      "type": "rpc",
      "priority": "P1",
      "is_write": false,
      "request": {},
      "expected": {"status_code": 400}
    },
    {
      "id": "TC004",
      "name": "正常更新状态",
      "interface": "UpdateBudgetStatus",
      "type": "rpc",
      "priority": "P0",
      "is_write": true,
      "request": {"budget_id": 1001, "status": 2},
      "expected": {"success": true}
    },
    {
      "id": "TC005",
      "name": "非法状态值",
      "interface": "UpdateBudgetStatus",
      "type": "rpc",
      "priority": "P1",
      "is_write": true,
      "request": {"budget_id": 1001, "status": -1},
      "expected": {"status_code": 400}
    }
  ],
  "metrics_to_verify": [
    {
      "name": "budget_query_qps",
      "type": "Counter",
      "expected_tags": {"method": "GetBudgetInfo"},
      "expected_change": "+N (请求数)"
    },
    {
      "name": "budget_query_latency",
      "type": "Timer",
      "expected_tags": {"method": "GetBudgetInfo"},
      "expected_change": "有值"
    }
  ],
  "design_sources": ["specs/budget-query/spec.md", "bam-api schema", "code analysis"]
}
```

### status.json 更新

```json
{
  "current_phase": "code_submit",
  "phases": {
    "test_design": {
      "status": "completed",
      "started_at": "2026-04-16T14:35:00+08:00",
      "completed_at": "2026-04-16T14:42:00+08:00",
      "summary": "设计 5 个测试用例（P0: 2, P1: 3），识别 2 个 Metrics 指标 → test-design/test_plan.md + test-design/test_cases.json"
    }
  },
  "context": {
    "test_cases": ["...同上 test_cases 数组..."],
    "metrics_to_verify": ["...同上 metrics_to_verify 数组..."],
    "gen_case_start_time": "2026-04-16T14:35:00+08:00",
    "gen_case_end_time": "2026-04-16T14:42:00+08:00",
    "gen_case_cost": 420.0
  }
}
```

---

## Phase 2: code_submit

### 产出文件 `code-submit/submit_info.json`

```json
{
  "branch": "feat/add-budget-query",
  "commit_hash": "a1b2c3d4e5f6",
  "commit_message": "feat: add budget query and status update",
  "push_success": true,
  "changed_files": [
    "biz/service/budget_query.go",
    "biz/handler/budget_handler.go"
  ],
  "pushed_at": "2026-04-16T14:43:00+08:00"
}
```

### status.json 更新

```json
{
  "current_phase": "deploy",
  "phases": {
    "code_submit": {
      "status": "completed",
      "started_at": "2026-04-16T14:42:00+08:00",
      "completed_at": "2026-04-16T14:43:00+08:00",
      "summary": "代码已提交并推送到 feat/add-budget-query (a1b2c3d) → code-submit/submit_info.json"
    }
  },
  "context": {
    "commit_hash": "a1b2c3d4e5f6"
  }
}
```

---

## Phase 3: deploy

### 产出文件 `deploy/deploy_info.json`

```json
{
  "dev_task_id": 2147530,
  "bits_link": "https://bits.bytedance.net/devops/94017024770/detail/2147530",
  "pipeline_success": true,
  "pipeline_run_id": "run_12345",
  "pipeline_status": "succeeded",
  "test_env": "ppe_i18n_env_feature_2147530",
  "test_env_type": "ppe",
  "lane_info": {
    "lane_id": "feature_2147530",
    "lane_type": "ppe_i18n_env_"
  },
  "stages": ["DevDevelopStageSelfTestTask"],
  "deployed_at": "2026-04-16T14:55:00+08:00"
}
```

### status.json 更新

```json
{
  "current_phase": "test_execution",
  "phases": {
    "deploy": {
      "status": "completed",
      "started_at": "2026-04-16T14:43:00+08:00",
      "completed_at": "2026-04-16T14:55:00+08:00",
      "summary": "BITS 任务 2147530 创建成功，流水线通过，泳道 ppe_i18n_env_feature_2147530 就绪 → deploy/deploy_info.json"
    }
  },
  "context": {
    "dev_task_id": 2147530,
    "bits_link": "https://bits.bytedance.net/devops/94017024770/detail/2147530",
    "test_env": "ppe_i18n_env_feature_2147530"
  }
}
```

### 失败时回退

```json
{
  "current_phase": "deploy",
  "phases": {
    "deploy": {
      "status": "failed",
      "summary": "流水线失败: Job 'build' failed — compile error in budget_query.go:45"
    }
  }
}
```

---

## Phase 4: test_execution

### 产出文件 `testing/test_result.json`

```json
{
  "executed_cases": [
    {
      "id": "TC001",
      "name": "正常查询预算",
      "interface": "GetBudgetInfo",
      "vregion": "Singapore-Central",
      "env": "ppe_i18n_env_feature_2147530",
      "request": {"budget_id": 1001, "user_id": 12345},
      "response": {"budget": {"id": 1001, "amount": 5000}, "status": 0},
      "response_code": 0,
      "result": "pass",
      "executed_at": "2026-04-16T14:56:00+08:00"
    },
    {
      "id": "TC002",
      "name": "查询不存在的预算",
      "interface": "GetBudgetInfo",
      "vregion": "Singapore-Central",
      "env": "ppe_i18n_env_feature_2147530",
      "request": {"budget_id": 0, "user_id": 12345},
      "response": {"status": 404, "message": "not found"},
      "response_code": 404,
      "result": "pass",
      "executed_at": "2026-04-16T14:56:05+08:00"
    }
  ],
  "summary": {
    "total": 5,
    "pass": 4,
    "fail": 1,
    "pass_rate": "80%"
  },
  "test_start_time": "2026-04-16T14:55:30+08:00",
  "test_end_time": "2026-04-16T14:57:00+08:00"
}
```

### status.json 更新

```json
{
  "current_phase": "log_verify",
  "phases": {
    "test_execution": {
      "status": "completed",
      "started_at": "2026-04-16T14:55:30+08:00",
      "completed_at": "2026-04-16T14:57:00+08:00",
      "summary": "执行 5 个用例，通过 4 个，失败 1 个（TC005 非法状态值返回 500 而非 400）→ testing/test_result.json"
    }
  },
  "context": {
    "test_start_time": "2026-04-16T14:55:30+08:00",
    "test_end_time": "2026-04-16T14:57:00+08:00",
    "exec_cost": 90.0
  }
}
```

### 回退到 deploy（用户选择修复代码）

```json
{
  "current_phase": "deploy",
  "phases": {
    "test_execution": {
      "status": "failed",
      "summary": "3/5 用例失败，用户选择回退修复代码"
    },
    "deploy": {
      "status": "in_progress"
    }
  }
}
```

---

## Phase 5: log_verify

### 产出文件 `logs/verify_result.json`

```json
{
  "trace_verification": {
    "checked": true,
    "trace_ids": ["trace_abc123"],
    "spans_complete": true,
    "call_chain": "dp_api → budget_service → mysql",
    "latency_summary": "total=25ms, budget_service=15ms, mysql=8ms"
  },
  "error_log_verification": {
    "checked": true,
    "time_range": {
      "start": "2026-04-16T14:55:00+08:00",
      "end": "2026-04-16T14:58:00+08:00"
    },
    "error_count": 1,
    "panic_count": 0,
    "errors": [
      {
        "level": "ERROR",
        "message": "invalid status value: -1",
        "timestamp": "2026-04-16T14:56:30+08:00",
        "related_test_case": "TC005"
      }
    ]
  },
  "conclusion": "pass_with_notes",
  "notes": "TC005 触发的 ERROR 日志为预期行为（非法参数），非系统异常"
}
```

### 产出文件 `logs/logs_summary.md`

```markdown
## 日志检查结果

### Trace Log
- 查询 trace_id: trace_abc123
- 链路完整性: ✅ 正常
- 调用链: dp_api → budget_service → mysql
- 总耗时: 25ms (budget_service=15ms, mysql=8ms)

### Error Log
- 查询时间范围: 14:55:00 ~ 14:58:00
- ERROR 日志数: 1
- PANIC 日志数: 0
- 异常摘要: TC005 触发的 "invalid status value: -1" 为预期行为

### 结论: ✅ 通过（附注：1 条 ERROR 为预期行为）
```

### status.json 更新

```json
{
  "current_phase": "tracking_verify",
  "phases": {
    "log_verify": {
      "status": "completed",
      "started_at": "2026-04-16T14:57:00+08:00",
      "completed_at": "2026-04-16T14:59:00+08:00",
      "summary": "Trace 链路完整，1 条 ERROR 为预期行为，无 PANIC → logs/verify_result.json + logs/logs_summary.md"
    }
  }
}
```

---

## Phase 6: tracking_verify

### 产出文件 `tracking/verify_result.json`

```json
{
  "verified_metrics": [
    {
      "name": "budget_query_qps",
      "type": "Counter",
      "query_vregion": "Singapore-PPE",
      "query_time_range": {
        "start": "2026-04-16T14:50:00+08:00",
        "end": "2026-04-16T15:02:00+08:00"
      },
      "expected_change": "+N",
      "actual_value": 3,
      "result": "pass"
    },
    {
      "name": "budget_query_latency",
      "type": "Timer",
      "query_vregion": "Singapore-PPE",
      "query_time_range": {
        "start": "2026-04-16T14:50:00+08:00",
        "end": "2026-04-16T15:02:00+08:00"
      },
      "expected_change": "有值",
      "actual_value": "avg=18ms, p99=35ms",
      "result": "pass"
    }
  ],
  "summary": {
    "total": 2,
    "pass": 2,
    "fail": 0
  },
  "conclusion": "pass"
}
```

### status.json 更新

```json
{
  "current_phase": "report",
  "phases": {
    "tracking_verify": {
      "status": "completed",
      "started_at": "2026-04-16T14:59:00+08:00",
      "completed_at": "2026-04-16T15:01:00+08:00",
      "summary": "2 个 Metrics 指标全部验证通过 → tracking/verify_result.json"
    }
  }
}
```

### 跳过时的 status.json

```json
{
  "current_phase": "report",
  "phases": {
    "tracking_verify": {
      "status": "skipped",
      "summary": "无 Metrics 指标需要验证，跳过埋点检查"
    }
  }
}
```

---

## Phase 7: report

### 产出文件 `summary/report.md`

（完整报告内容见 SKILL.md 中的报告模板，此处不重复）

### 运行数据回传 curl 示例

```bash
curl --location 'http://pns-ca-synapse-api-cn.byted.org/synapse_agent/v1/pns_quality_first/integration_test_event' \
--header 'Content-Type: application/json' \
--data '{
    "version": "v1",
    "username": "alice",
    "scope": "incremental",
    "file_num": 2,
    "case_num": 5,
    "case_success_rate": 0.8,
    "code_cover_rate": 0,
    "gen_case_cost": 420.0,
    "exec_cost": 90.0
}'
```

### status.json 更新

```json
{
  "current_phase": "report",
  "phases": {
    "report": {
      "status": "completed",
      "started_at": "2026-04-16T15:01:00+08:00",
      "completed_at": "2026-04-16T15:03:00+08:00",
      "summary": "集成测试报告已生成 → summary/report.md；运行数据已回传"
    }
  },
  "history": [
    {
      "phase": "report",
      "action": "report_event",
      "detail": "回传成功 case_num=5, pass_rate=0.8, gen_case_cost=420.0s, exec_cost=90.0s",
      "timestamp": "2026-04-16T15:02:30+08:00"
    }
  ]
}
```
