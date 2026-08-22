---
name: workflow-routing
description: 场景判定与工作流路由。根据用户意图和代码状态判定执行场景（修复/维护/重写/全新生成），路由到对应的精简 Agent 管线。
allowed-tools:
- Read
- Grep
- Glob
- Bash
metadata:
  version: 1.0.2
---

# 场景判定与工作流路由

本文档定义了 Orchestrator 的场景判定规则和各场景对应的 Agent 调度管线。

## Table of Contents

- [场景对照表](#场景对照表)
- [场景判定规则](#场景判定规则)
  - [优先级 1：用户 prompt 中的显式意图](#优先级-1用户-prompt-中的显式意图)
  - [优先级 2：自动判定](#优先级-2自动判定用户未明确意图时)
- [targets.json 格式](#targetsjson-格式)
- [场景 A: 修复模式](#场景-a-修复模式modefix)
- [场景 B: 维护模式](#场景-b-维护模式modemaintain)
- [场景 C: 重写模式](#场景-c-重写模式moderewrite)
- [场景 D: 全新生成模式](#场景-d-全新生成模式modenew)
- [并行优化](#并行优化可选适用于场景-bcd)

## 场景对照表

| 场景 | 触发条件 | Code Reviewer | Test Writer | Test Fixer | 规范学习 |
|------|---------|:---:|:---:|:---:|:---:|
| **A: 修复模式** | 业务代码无 diff，修复已有测试 | ❌ 跳过 | ❌ 跳过 | ✅ 完整 | ❌ 仅读已有测试 |
| **B: 维护模式** | 业务代码有 diff，已有测试能跑通 | ⚡ 轻量（仅 diff） | ⚡ 增量 | ✅ 完整 | ❌ 仅读已有测试 |
| **C: 重写模式** | 业务代码有 diff，已有测试跑不通 | ✅ 完整 | ✅ 完整 | ✅ 完整 | ⚡ 读已有测试风格后清除 |
| **D: 全新生成模式** | 无已有测试 | ✅ 完整 | ✅ 完整 | ✅ 完整 | ✅ 广泛学习 |

## 场景判定规则

确定目标函数后，**必须**判定本次执行的场景模式。按以下优先级判定：

### 优先级 1：用户 prompt 中的显式意图

| 用户 prompt 关键词 | 判定场景 |
|---|---|
| "修复测试"、"fix test"、"跑不过"、"编译失败"、"测试挂了"、"修复单测" | **修复模式（A）** |
| "补场景"、"加用例"、"增加测试"、"维护"、"保鲜"、"补充覆盖" | **维护模式（B）** |
| "重写"、"重新生成"、"删掉重写"、"废弃重来" | **重写模式（C）** |
| "写单测"、"生成单测"、"写 test"（无已有测试时） | **全新生成模式（D）** |

### 优先级 2：自动判定（用户未明确意图时）

```
目标函数是否有对应的已有测试文件？
    │
    ├── 无 → 全新生成模式（D）
    │
    └── 有 → 业务代码是否有 diff（git 变更）？
            │
            ├── 无 diff → 修复模式（A）
            │           （业务代码没变，用户调用 skill 大概率是为了修复测试问题）
            │
            └── 有 diff → 预执行已有测试（编译+运行）
                        │
                        ├── 测试通过 → 维护模式（B）
                        │             （已有测试能用，在此基础上增删场景）
                        │
                        └── 测试不通过 → 重写模式（C）
                                       （已有测试已坏，清除后重写）
```

将判定结果记录为 `MODE` 变量（`fix` / `maintain` / `rewrite` / `new`）。

## targets.json 格式

```json
{
  "lang": "go",
  "mode": "maintain",
  "targets": [
    {
      "file": "path/to/file.go",
      "function": "FunctionName",
      "line": 42,
      "receiver": "ServiceName"
    }
  ],
  "existing_test_files": ["path/to/file_test.go"]
}
```

其中 `existing_test_files` 在修复模式（A）和维护模式（B）下必填，其他模式可为空数组。

---

## 场景 A: 修复模式（`MODE=fix`）

> 目标：修复已有测试的编译/运行问题，不生成新测试。

**跳过** Code Reviewer Agent 和 Test Writer Agent。

1. **读取已有测试**：读取 `existing_test_files` 中的测试文件，理解当前测试结构和风格
2. **直接调度 Test Fixer Agent**：
    - 读取 `references/test-fixer/AGENT.md` 的内容
    - 传入 `SKILL_ROOT`、`PROJECT_ROOT`、`TMP_ROOT`、`LANG`
    - 传入已有测试文件路径作为待修复目标
    - Test Fixer Agent 执行编译检查 → 运行测试 → 修复失败用例的循环
3. **回传埋点数据**（必须执行）：
   将测试结果通过指定接口回传
4. Test Fixer Agent 完成后，输出 `${TMP_ROOT}/final_report.json`

---

## 场景 B: 维护模式（`MODE=maintain`）

> 目标：在已有测试基础上，为 diff 涉及的代码变更增删测试场景。

1. **读取已有测试**：读取 `existing_test_files` 中的测试文件，学习测试风格（Mock 策略、断言风格、命名约定、用例组织方式）。**不需要广泛学习项目测试规范**，已有测试就是最好的范本
2. **调度 Code Reviewer Agent（轻量模式）**：
    - 读取 `references/code-reviewer/AGENT.md` 的内容
    - 传入 `targets.json`（其中 `mode=maintain`）
    - **轻量模式指令**：仅审查 diff 涉及的代码变更部分，不对整个函数做全量缺陷审查。重点关注变更引入的新分支、新错误路径、被修改的逻辑
    - 输出 `${TMP_ROOT}/review_report.json`
3. **调度 Test Writer Agent（增量模式）**：
    - 读取 `references/test-writer/AGENT.md` 的内容
    - 传入 `review_report.json` 和已有测试文件
    - **增量模式指令**：在已有测试文件中增删场景，不从头生成。需要新增覆盖 diff 变更的用例，如有被删除代码对应的用例则移除
    - 输出 `${TMP_ROOT}/test_files.json`
4. **调度 Test Fixer Agent**：
    - 读取 `references/test-fixer/AGENT.md` 的内容
    - 传入 `test_files.json` 和 `review_report.json`
5. **回传埋点数据**（必须执行）：
   将测试结果通过指定接口回传
6. Test Fixer Agent 完成后，输出 `${TMP_ROOT}/final_report.json`

---

## 场景 C: 重写模式（`MODE=rewrite`）

> 目标：已有测试不可用，清除后重新生成。

1. **学习已有测试风格**：读取 `existing_test_files`，提取 Mock 策略、断言风格、命名约定等有价值的模式信息
2. **清除已有测试**：将已有测试文件内容清空（或标记为待覆盖），后续由 Test Writer 从头生成
3. **调度 Code Reviewer Agent（完整模式）**：
    - 读取 `references/code-reviewer/AGENT.md` 的内容
    - 传入 `targets.json`（其中 `mode=rewrite`）
    - 执行完整的缺陷审查流程
    - 输出 `${TMP_ROOT}/review_report.json`
4. **调度 Test Writer Agent（完整模式）**：
    - 读取 `references/test-writer/AGENT.md` 的内容
    - 传入 `review_report.json` 和第 1 步学到的风格约定
    - 从头生成完整的测试文件
    - 输出 `${TMP_ROOT}/test_files.json`
5. **调度 Test Fixer Agent**：
    - 读取 `references/test-fixer/AGENT.md` 的内容
    - 传入 `test_files.json` 和 `review_report.json`
6. **回传埋点数据**（必须执行）：
   将测试结果通过指定接口回传
7. Test Fixer Agent 完成后，输出 `${TMP_ROOT}/final_report.json`

---

## 场景 D: 全新生成模式（`MODE=new`）

> 目标：无已有测试，需要广泛学习规范后从头生成。

1. **广泛学习项目测试规范**：
    - 在目标函数所在目录及相邻目录中搜索已有的 `*_test.*` 文件
    - 学习项目的 Mock 策略、断言风格、命名约定、测试组织方式
    - 搜索项目中的 Test Helper / Factory / testutil 等可复用资产
    - 读取 AGENTS.md / CLAUDE.md 中的测试相关约定
2. **调度 Code Reviewer Agent（完整模式）**：
    - 读取 `references/code-reviewer/AGENT.md` 的内容
    - 传入 `targets.json`（其中 `mode=new`）
    - 执行完整的缺陷审查流程
    - 输出 `${TMP_ROOT}/review_report.json`
3. **调度 Test Writer Agent（完整模式）**：
    - 读取 `references/test-writer/AGENT.md` 的内容
    - 传入 `review_report.json` 和第 1 步学到的规范
    - 从头生成完整的测试文件
    - 输出 `${TMP_ROOT}/test_files.json`
4. **调度 Test Fixer Agent**：
    - 读取 `references/test-fixer/AGENT.md` 的内容
    - 传入 `test_files.json` 和 `review_report.json`
5. **回传埋点数据**（必须执行）：
   将测试结果通过指定接口回传
6. Test Fixer Agent 完成后，输出 `${TMP_ROOT}/final_report.json`

---

## 并行优化（可选，适用于场景 B/C/D）

当目标函数分布在多个独立的文件/包中时，可以对不同文件/包并行执行 Agent 管线：

```
文件 A 的函数 → [Review A] → [Write A] → [Fix A]
文件 B 的函数 → [Review B] → [Write B] → [Fix B]  (并行)
文件 C 的函数 → [Review C] → [Write C] → [Fix C]
```
