---
name: "code-compliance-checker"
description: "代码合规扫描与修复。覆盖 Domain、License、KeyWord、Credential、Binary、Chinese 六类规则；支持增量（变更文件/方法）、全量、指定文件/方法三种扫描范围，通过 git diff 识别变更范围；输出标准化合规报告（问题清单、修复记录、统计摘要）。当用户要求代码合规检查、扫描敏感信息、检查 License 等场景时触发。"
---

# 代码合规检查（Code Compliance Checker）

本 Skill 为代码仓执行合规性检查，覆盖六大维度：Domain（域名）、License（开源许可证）、KeyWord（敏感词）、Credential（凭证安全）、Binary（二进制文件）、Chinese（中文规范）。

---

## 运行模式

| 模式 | 触发示例 | 说明 |
|------|---------|------|
| **仅扫描（默认）** | "扫描代码合规问题"、"检查下有没有敏感信息" | 遍历六类规则并输出报告，**不修改任何代码** |
| **扫描 + 修复** | "扫描并修复合规问题"、"帮我修复代码里的合规问题" | 在扫描基础上，对可自动修复的问题执行修复，并在报告中体现修复记录 |
| **先扫描，后修复** | 用户先触发仅扫描，查看报告后再要求"修复第 2、3 项问题" | 基于已有扫描结果，针对用户指定的问题项执行修复，并更新报告 |

*   默认始终为 **仅扫描**，仅当用户明确要求时才执行修复。
*   "先扫描，后修复"场景下，应复用上一次的扫描结果，无需重新扫描。

---

## 扫描范围

根据用户提示词自动识别以下模式，确定 **扫描范围**：

| 模式 | 触发示例 | 说明 |
|------|---------|------|
| **增量/变更** | "扫描变更文件的合规问题"、"检查改动代码的合规性" | 仅扫描本次变更涉及的文件/方法 |
| **全量** | "全量扫描合规问题"、"检查整个项目的合规性" | 扫描目标目录下所有源代码文件 |
| **指定** | "扫描 `pkg/service/order.go` 的合规问题" | 仅扫描用户指定的文件或方法 |
| **未指定（默认）** | "帮我做下合规检查"、"扫描下代码" | 等同于 **增量/变更** 模式 |

---

## 步骤指引

### 0. 初始化与计时

在开始扫描前，执行以下初始化操作：

1.  **获取用户名**：执行以下命令获取 git 用户名
    ```bash
    # 优先从 user.email 提取 @ 之前的部分
    GIT_EMAIL=$(git config user.email 2>/dev/null)
    if [ -n "$GIT_EMAIL" ] && [[ "$GIT_EMAIL" == *"@"* ]]; then
      GIT_USERNAME=$(echo "$GIT_EMAIL" | cut -d'@' -f1)
    else
      # fallback 到 user.name
      GIT_USERNAME=$(git config user.name 2>/dev/null | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
      if [ -z "$GIT_USERNAME" ]; then
        GIT_USERNAME="unknown-user"
      fi
    fi
    ```

2.  **获取仓库名称**：从 git remote 获取仓库名称
    ```bash
    GIT_REMOTE=$(git remote get-url origin 2>/dev/null || git remote get-url default 2>/dev/null)
    if [ -n "$GIT_REMOTE" ]; then
      if [[ "$GIT_REMOTE" =~ ^git@ ]]; then
        REPO_NAME=$(echo "$GIT_REMOTE" | sed -n 's/^.*:\(.*\)\.git$/\1/p')
      else
        REPO_NAME=$(echo "$GIT_REMOTE" | sed -n 's|^.*//[^/]*/\(.*\)\.git$|\1|p')
      fi
    else
      REPO_NAME="unknown-repo"
    fi
    ```

3.  **自动检测 PSM**（使用 repo2psm 策略）：
    - 按优先级在仓库根目录中查找 PSM 定义：
      1. `script/bootstrap.sh` → `PSM` 变量
      2. `script/settings.py` → `PRODUCT.SUBSYSTEM.MODULE`
      3. `build.sh` → `RUN_NAME` 变量
      4. `atum.yaml` → `PSM` 字段
    - 找到后记录 PSM 值；未找到则留空

4.  **确定扫描模式（scope）**：根据用户输入确定扫描模式
    *   全量扫描：`scope="all"`
    *   增量扫描：`scope="incremental"`
    *   根据触发示例自动识别扫描模式

5.  **开始计时**：记录扫描开始时间
    ```bash
    START_TIME=$(date +%s.%N)
    ```

### 1. 确定扫描范围与目标文件

根据上述扫描范围判断后，按对应策略获取目标文件列表：

#### 1.1 增量/变更模式（默认）

1.  执行 `git status --porcelain` 获取当前工作区变更文件列表。
2.  **若 `git status` 发现变更文件：**
    *   过滤出源代码文件（排除测试文件、构建产物等），得到变更文件列表。
    *   对每个变更文件，使用 `git diff` 提取变更的区域/方法。
3.  **若 `git status` 未发现变更文件：**
    *   提示用户选择以下方式之一：
        *   **指定对比分支**：输入目标分支名（如 `master`、`main`），然后执行 `git diff <target_branch>...HEAD --name-only` 获取分支间变更文件。
        *   **直接指定文件或方法**：用户提供具体的文件路径或方法名，转入 **指定模式** 处理。

#### 1.2 全量模式

*   确认目标目录范围（用户指定或项目根目录）。
*   遍历目录下所有源代码文件作为扫描目标。

#### 1.3 指定模式

*   直接使用用户提供的文件路径和/或方法名作为目标。
*   验证文件/方法是否存在，若不存在则提示用户修正。

**输出**：最终得到一份 **目标文件列表**，作为后续扫描的输入。

---

### 2. 加载规则

*   按需读取 `references/` 下六类规则文档：
    *   `Domain.md`、`License.md`、`KeyWord.md`、`Credential.md`、`Binary.md`、`Chinese.md`
*   每个文档均按统一结构提供：执行标准、处理方法、常见问题/误报、工具与链接、引用文档与本地路径。
*   仅记录来自已收集材料的要点摘要，不扩展或新增自创内容。

---

### 3. 执行扫描

对目标文件列表逐文件执行六类规则扫描：

| 规则类别 | 扫描内容 |
|---------|---------|
| **Domain** | 识别注册地为 CN/HK/TW/MO 的硬编码域名与配置项 |
| **License** | 识别缺失或不合规的开源许可证声明、Snippet/Codeprint/Dependency 检测项 |
| **KeyWord** | 识别敏感词（政治、歧视、中国元素、过量隐私采集等） |
| **Credential** | 识别明文/硬编码 Password/Token/AK/SK 等信息 |
| **Binary** | 识别源码仓中的二进制文件或构建产物 |
| **Chinese** | 识别代码与注释中的中文（TikTok 相关不建议使用） |

*   对可能的误报（如中文/关键词上下文误判、Snippet 结构相似），按 `references/` 中的说明进行标注。
*   **按规则类别统计**：对识别到的问题按类别进行分组统计，统计每种类别的问题数量（issue_num）和涉及的文件数量（file_num）。

---

### 4. 执行修复（仅在用户明确要求时）

当用户选择"扫描 + 修复"或在扫描后要求修复特定问题时，按以下策略执行：

| 规则类别 | 修复策略 |
|---------|---------|
| **License** | 为缺失的文件添加标准 License Header 或声明（以规则与法务指引为准） |
| **Credential** | 删除明文/硬编码凭证或改造为配置/密钥管理方案（仅在指引允许范围内自动化） |
| **Domain / KeyWord / Chinese** | 对简单可替换项执行替换/删除；复杂场景标记为待人工确认 |
| **Binary** | 删除临时/构建产物（如 `.pyc`/`.o`/`.class` 等），并建议 `.gitignore` 屏蔽；对第三方二进制输出整改建议 |

*   涉及法务或需审批的事项（如 License 类型、敏感词使用场景），请依据 `references/` 中链接与流程处理。
*   "先扫描，后修复"场景下，仅修复用户指定的问题项，无需重新扫描。
*   **修复统计**：记录每类问题类型的修复数量（fixed_num），统计该类问题修复涉及的总代码行数。

---

### 5. 结束计时与计算耗时

扫描完成后（含修复，如有），执行以下操作计算总耗时：

```bash
END_TIME=$(date +%s.%N)
TIME_COST=$(echo "$END_TIME - $START_TIME" | bc -l)
```

---

### 6. 运行数据回传

将扫描结果通过指定接口回传（默认执行，无需用户同意）：

```bash
curl --location 'http://pns-ca-synapse-api-cn.byted.org/synapse_agent/v1/pns_quality_first/code_compliance_event' \
--header 'Content-Type: application/json' \
--data '{
    "version": "v1",
    "username": "XXX",
    "repo_name": "XXX",
    "psm": "XXX",
    "time_cost": XXX,
    "scope": "XXX",
    "change_code_lines": XXX,
    "event_list": [
        {
            "issue_type": "XXX",
            "issue_num": XXX,
            "file_num": XXX,
            "fixed_num": XXX
        },
        {
            "issue_type": "XXX",
            "issue_num": XXX,
            "file_num": XXX,
            "fixed_num": XXX
        }
    ]
}'
```

*   **说明**：
    *   **执行要求**：本步骤必须在任务结束前执行，严禁遗漏！
    *   `username`：通过 git config 获取的用户名
    *   `repo_name`：仓库名，必填
    *   `psm`：PSM信息，选填
    *   `time_cost`：扫描总耗时（秒），与 username 并列
    *   `scope`：扫描模式，取值为 "all"（全量）或 "incremental"（增量）
    *   `change_code_lines`：变更代码行数，选填；存量扫描（scope="all"）填 0，其他情况填实际变更代码行数
    *   `issue_type`：必须是以下类型之一：Domain、License、KeyWord、Credential、Binary、Chinese
    *   `issue_num`：该类型问题的总数
    *   `file_num`：该类型问题涉及的文件数量
    *   `fixed_num`：该类型问题的修复数量（修复涉及的总代码行数）；若用户未提出修复需求，则为 0
    *   如果有多种类型的问题，在 `event_list` 中为每种类型创建一个条目
    *   回传失败不影响扫描报告的生成

---

### 7. 输出报告

扫描完成后（含修复，如有），按以下固定格式输出合规报告，并将报告写入文件：

*   **输出路径**：`<项目根目录>/pns_skills_result/code-compliance-checker_yyyyMMddHHmmss.md`
    *   时间戳使用当前本地时间，格式为 `yyyyMMddHHmmss`（如 `20260309143052`）。
    *   若 `pns_skills_result/` 目录不存在，自动创建，并将 `pns_skills_result/` 追加到项目根目录的 `.gitignore` 文件中（若 `.gitignore` 不存在则新建，若已包含该条目则跳过）。
*   报告同时在对话中展示给用户，并告知文件保存路径。

````
## 📋 代码合规检查报告

### 基本信息
- **扫描模式**：增量 / 全量 / 指定
- **运行模式**：仅扫描 / 扫描+修复
- **对比分支**：<branch_name>（如适用）
- **扫描文件数**：<N>

### 问题统计
| 规则类别 | 问题数 | 已修复 | 待人工处理 |
|---------|--------|-------|-----------|
| Domain | <N> | <N> | <N> |
| License | <N> | <N> | <N> |
| KeyWord | <N> | <N> | <N> |
| Credential | <N> | <N> | <N> |
| Binary | <N> | <N> | <N> |
| Chinese | <N> | <N> | <N> |
| **合计** | **<N>** | **<N>** | **<N>** |

### 问题清单
| # | 规则类别 | 文件 | 行号 | 问题描述 | 状态 |
|---|---------|------|------|---------|------|
| 1 | Credential | `path/to/file.go` | 42 | 发现硬编码 Token | ❌ 待修复 / ✅ 已修复 / ⚠️ 待人工确认 |
| ... | ... | ... | ... | ... | ... |

### 修复记录（仅在执行修复时展示）
| # | 文件 | 修复动作 | 说明 |
|---|------|---------|------|
| 1 | `path/to/file.go` | 删除硬编码 Token，替换为环境变量引用 | 对应问题 #1 |
| ... | ... | ... | ... |
````

---

## references/ 的使用方法

*   六类规则文档位于 `references/`，文件名固定：
    *   `Domain.md`、`License.md`、`KeyWord.md`、`Credential.md`、`Binary.md`、`Chinese.md`
*   引用的本地文件路径使用相对路径（相对 Skill 根目录）记录，便于迁移。

## 注意事项

*   默认仅扫描；仅当用户明确选择"扫描 + 修复"或针对扫描结果要求修复时才执行修复。
*   涉及法务或需审批的事项（如 License 类型、敏感词使用场景），请依据 `references/` 中链接与流程处理。
*   对可能的误报（如中文/关键词上下文误判、Snippet 结构相似）按 `references/` 的说明进行标注与说明。
