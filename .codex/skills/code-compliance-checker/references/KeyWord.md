# KeyWord（敏感词）

## 1. 执行标准

-   **核心原则**：政治敏感、歧视偏见、中国元素（如 `douyin`）以及易引发隐私担忧的关键词，原则上不允许出现在面向海外用户的产品代码或注释中。
-   **处理建议**：若关键词在神盾扫描的 Policy 中建议为 `DELETE`，则必须移除。
-   **适用范围**：无论是业务逻辑代码，还是测试、Demo、注释，均适用此规则。


## 2. 扫描细则：高敏关键词清单

以下清单列举了高风险的敏感词，其中政治/特殊人群/特殊事件/歧视偏见部分需要通过`scripts/filter_keyword_issues.sh`扫描与过滤，**扫描时会包含其各种大小写变体**。

| 类别 | 关键词 |
| :--- | :--- |
| **中国元素/国内产品** | `douyin`, `抖音` （注：在 `go.mod`、`go.sum` 中允许出现） |
| **设备标识符/隐私信息** | `imei`, `caid`, `oaid` |
| **地理位置** | `GIS`, `Longitude`, `latitude`, `Altitude`, `Gps` |
| **竞品商标** | 友商表情/AR 头像类等商品名（具体词项由 `scripts/filter_keyword_issues.sh` 内置覆盖，**不在本文档以明文展开**） |
| **政治/特殊人群/特殊事件/歧视偏见** | 由 `scripts/filter_keyword_issues.sh` 内置规则覆盖（含 base64 编码的字面量与正则；详情见第 3 节，**不在本文档以明文展开**） |

---


## 3. 高敏关键词扫描脚本（base64 规则集）

> **[关键指令 — 强制执行]**：政治敏感、特殊人群/特殊事件、歧视偏见等高敏关键词，**必须**通过 `scripts/filter_keyword_issues.sh` 进行扫描；这些关键词不在本 Markdown 中以明文展开，避免在 Skill 仓库中扩散敏感字符串。

### 3.1 脚本概述

-   **脚本路径（相对 Skill 根目录）**：`scripts/filter_keyword_issues.sh`
-   **数据来源**：神盾"源码中禁止出现类"词表导出（rule_content_id 为脚本内规则号）。
-   **存储形式**：所有关键词、正则、类目标签、豁免路径、豁免正则均以 **base64** 形式存储在脚本数组中，运行时解码后比对；脚本源代码内不存在敏感词明文。
-   **匹配类型**：
    -   `lit`：字面量子串匹配，case-insensitive。
    -   `re`：正则匹配，case-insensitive；脚本内置将 `{,N}` 速记规整为 `{0,N}`，以兼容 `grep -E`。
-   **维度化豁免**（按规则号配置）：
    -   `KEYWORD_RULE_EXEMPT_PATHS`：路径子串/glob 命中即跳过该规则在该文件上的所有匹配。
    -   `KEYWORD_RULE_EXEMPT_REGEXES`：命中行若同时匹配任一豁免正则（case-insensitive），视为误报丢弃。
-   **文档级豁免**（针对 `KeyWord.md` 中明文列出的关键词）：
    -   `KEYWORD_DOC_EXEMPT_PATHS`：以 base64 形式记录某关键词在特定路径下允许出现的规则。
    -   当前条目：`douyin`、`抖音` 在 `go.mod`、`go.sum` 中允许出现。

### 3.2 使用方式

-   **路径解析约定**：示例中 `scripts/filter_keyword_issues.sh` 是**相对本 Skill 根目录**的路径；调用方应在运行时把它解析为本 Skill 在当前环境的实际绝对路径，**不要**把开发仓库内的相对路径硬编码进调用脚本。
-   **方式 A：CLI 模式**
    ```bash
    # 扫描指定文件
    bash "$SKILL_ROOT/scripts/filter_keyword_issues.sh" path/to/foo.go path/to/bar.py

    # 或从 stdin 读取文件路径（每行一个），适合配合 git diff 做增量扫描
    git diff --name-only HEAD | bash "$SKILL_ROOT/scripts/filter_keyword_issues.sh"
    ```
-   **方式 B：作为库 source 后调用函数**
    ```bash
    source "$SKILL_ROOT/scripts/filter_keyword_issues.sh"

    # 扫描单个文件
    kw_scan_file "path/to/foo.go"

    # 扫描多个文件
    kw_scan_files "path/to/foo.go" "path/to/bar.py"

    # 检查 KeyWord.md 文档级关键词在某路径上是否被豁免
    if kw_doc_exempt_for_keyword "douyin" "go.mod"; then
      echo "exempt"
    fi

    # 按 rule_id 取类目标签（base64 解码后返回明文，仅在确有展示需要时调用）
    kw_get_category 60252
    ```

### 3.3 输出格式

-   每条命中输出一行 TAB 分隔的字段：
    ```
    file_path \t line_no \t rule_id \t pattern_type \t matched_line_text
    ```
-   `pattern_type` 为 `lit` 或 `re`；`rule_id` 为神盾 `rule_content_id`；`matched_line_text` 中的 TAB 已被规范化为单空格，避免列错位。
-   命中行属于代码原文，仍可能含敏感词（这是扫描的本意）；脚本本身仍不含明文。

### 3.4 误报与豁免（既定规则）

满足以下任一条件，命中应被剔除，**不计入** `issue_num` / `file_num`：

1.  **维度化路径豁免**：文件路径命中规则的 `KEYWORD_RULE_EXEMPT_PATHS`（例如 60278 号规则在路径包含 `chunk` 的文件下豁免）。
2.  **维度化行豁免**：命中行同时匹配规则的 `KEYWORD_RULE_EXEMPT_REGEXES`（例如 `pakis` 命中行若同时含 `pakistan`，视为误报）。
3.  **文档级关键词豁免**：`KeyWord.md` 中明文列出的关键词在指定路径下出现：
    -   `douyin`、`抖音` 在 `go.mod`、`go.sum` 中允许出现。
-   **白名单维护入口**：直接编辑 `scripts/filter_keyword_issues.sh` 中的对应数组，**不要**在 Markdown 中另行复制。新增白名单需附 PR 说明来源以便审计。

### 3.5 在扫描流程中的位置

执行顺序固定为：**KeyWord 规则原始命中（脚本内已应用维度化豁免） → 文档级豁免过滤 → 输出到合规报告 / 进入修复流程**。

-   过滤发生在「按规则类别统计」之前，被过滤的问题不计入回传 `event_list`。
-   `issue_type` 仍保留为 `KeyWord`，仅是被过滤后该类别的 `issue_num` 可能为 0。

## 4. 处理方法

-   **非注释代码**：建议直接删除或替换，或根据神盾工单中的具体 Policy 建议进行操作。
-   **注释/测试/Demo 代码**：
    -   **疑似国内逻辑**：如 “抖音”、“douyin”，必须替换或删除。
    -   **竞品商标**：如友商表情/AR 头像类等商品名（具体词项见扫描脚本规则集，**不在本文档以明文展开**），必须替换或删除。
    -   **政治/歧视词汇**：必须删除。
    -   **疑似过度收集隐私**：如 “imei”、“gender”、“longitude”，必须替换或删除。
-   **审批路径**：如确有必要使用某些关键词，需在神盾工单中详细阐述使用场景，或通过 Oncall 通道联系运营同学报备审批。

## 5. 常见问题与误报处理

-   **大小写问题**：扫描不区分大小写，但在审批或说明时，请关注具体的拼写和语义上下文，以判断是否为误报。
-   **上下文误判**：部分关键词可能因其在特定上下文中的含义而被误报（例如，一个变量名恰好与敏感词相同但意义完全不同）。此类情况需通过场景说明进行澄清，或在 `scripts/filter_keyword_issues.sh` 的对应规则下追加豁免正则。
-   **新增白名单的处理路径**：若发现稳定的、可重复出现的误报模式，应在 `scripts/filter_keyword_issues.sh` 中向对应规则的 `KEYWORD_RULE_EXEMPT_PATHS` 或 `KEYWORD_RULE_EXEMPT_REGEXES` 追加 base64 条目，**不要**在业务代码或报告中硬编码"忽略该问题"。


