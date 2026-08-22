---
name: "security-scanner"
description: "代码安全扫描。基于内置安全审查提示词，对项目代码进行高置信安全漏洞分析，覆盖注入、越权、敏感数据泄露、代码执行等常见安全风险；默认分析当前分支增量代码，仅当用户明确要求全量扫描时才扫描全量代码，并输出标准化安全报告（风险等级、漏洞清单、修复建议）。当用户要求安全扫描、安全审查、漏洞检测等场景时触发。"
---

# 安全扫描（Security Scanner）

本 Skill 基于内置安全审查提示词，对项目代码执行安全漏洞扫描与分析，输出标准化安全报告。

---

## 执行原则

*   **增量优先**：默认分析当前分支相对基准分支的增量代码；仅当用户明确指定"全量扫描"、"扫描全仓库"等意图时才进行全量扫描。
*   **最小交互**：仅在无法自动判断时才与用户交互确认。
*   **高置信输出**：仅报告置信度较高、具备真实利用路径的 High / Medium 安全问题。
*   **结果标准化**：将安全审查输出统一转换为结构化报告。

---

## 触发场景

| 触发示例 | 说明 |
|---------|------|
| "做一下安全扫描"、"帮我扫描安全问题" | 对项目执行安全审查 |
| "检查下有没有安全漏洞"、"security review" | 同上 |
| "代码安全检查"、"安全审计" | 同上 |

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
    *   默认模式：`scope="incremental"`，分析当前分支相对基准分支的增量代码。
    *   全量扫描：仅当用户明确指定"全量扫描"、"扫描全仓库"、"检查全部代码"等意图时，设置 `scope="all"`。
    *   若用户未指定扫描范围，不要追问，直接按增量扫描执行。

5.  **开始计时**：记录扫描开始时间
    ```bash
    START_TIME=$(date +%s.%N)
    ```

### 1. 准备扫描上下文

不再检测、安装或调用 Claude Code。直接在当前 Agent 会话中使用文件搜索、代码阅读、Git 差异读取和 Subagent 能力完成安全审查。

*   **增量扫描**：读取当前分支相对基准分支的变更文件、提交记录和完整 diff，重点审查本次 PR 新增或修改的安全影响。
*   **全量扫描**：仅在用户明确要求时执行；使用同一套安全准则，但扫描范围扩展到仓库全部非测试、非文档代码。
*   **禁止新增外部扫描器依赖**：不要通过 `claude`、`/security-review` 或其他外部 CLI 安全扫描器完成本步骤。

---

### 2. 执行安全扫描

在当前 Agent 会话中按扫描模式执行以下流程：

1.  **增量扫描（默认）**：使用下面的"增量安全扫描提示词"创建第一个漏洞识别 sub-task。该 sub-task 需要使用仓库探索工具理解上下文，并分析当前分支增量代码的安全影响。
2.  **全量扫描（仅用户明确指定）**：使用同一提示词的安全准则与误报过滤规则，但将目标从"changes on this branch / PR diff"改为"entire repository"，并扫描仓库全部非测试、非文档代码。
3.  对第一个 sub-task 识别出的每个漏洞，分别创建独立的误报过滤 sub-task；这些 sub-task 应并行启动，并在提示中包含"FALSE POSITIVE FILTERING"部分的全部指令。
4.  过滤掉误报过滤 sub-task 返回置信度小于 8 的漏洞，仅保留 High / Medium 且置信度大于等于 8 的结果。
5.  将最终 markdown 报告内容写入 `pns_skills_result/security_result.txt`，供后续解析与回传步骤使用。

```bash
mkdir -p pns_skills_result
```

#### 增量安全扫描提示词

````text
You are a senior security engineer conducting a focused security review of the changes on this branch.

GIT STATUS:

```
!`git status`
```

FILES MODIFIED:

```
!`git diff --name-only origin/HEAD...`
```

COMMITS:

```
!`git log --no-decorate origin/HEAD...`
```

DIFF CONTENT:

```
!`git diff --merge-base origin/HEAD`
```

Review the complete diff above. This contains all code changes in the PR.


OBJECTIVE:
Perform a security-focused code review to identify HIGH-CONFIDENCE security vulnerabilities that could have real exploitation potential. This is not a general code review - focus ONLY on security implications newly added by this PR. Do not comment on existing security concerns.

CRITICAL INSTRUCTIONS:
1. MINIMIZE FALSE POSITIVES: Only flag issues where you're >80% confident of actual exploitability
2. AVOID NOISE: Skip theoretical issues, style concerns, or low-impact findings
3. FOCUS ON IMPACT: Prioritize vulnerabilities that could lead to unauthorized access, data breaches, or system compromise
4. EXCLUSIONS: Do NOT report the following issue types:
   - Denial of Service (DOS) vulnerabilities, even if they allow service disruption
   - Secrets or sensitive data stored on disk (these are handled by other processes)
   - Rate limiting or resource exhaustion issues

SECURITY CATEGORIES TO EXAMINE:

**Input Validation Vulnerabilities:**
- SQL injection via unsanitized user input
- Command injection in system calls or subprocesses
- XXE injection in XML parsing
- Template injection in templating engines
- NoSQL injection in database queries
- Path traversal in file operations

**Authentication & Authorization Issues:**
- Authentication bypass logic
- Privilege escalation paths
- Session management flaws
- JWT token vulnerabilities
- Authorization logic bypasses

**Crypto & Secrets Management:**
- Hardcoded API keys, passwords, or tokens
- Weak cryptographic algorithms or implementations
- Improper key storage or management
- Cryptographic randomness issues
- Certificate validation bypasses

**Injection & Code Execution:**
- Remote code execution via deseralization
- Pickle injection in Python
- YAML deserialization vulnerabilities
- Eval injection in dynamic code execution
- XSS vulnerabilities in web applications (reflected, stored, DOM-based)

**Data Exposure:**
- Sensitive data logging or storage
- PII handling violations
- API endpoint data leakage
- Debug information exposure

Additional notes:
- Even if something is only exploitable from the local network, it can still be a HIGH severity issue

ANALYSIS METHODOLOGY:

Phase 1 - Repository Context Research (Use file search tools):
- Identify existing security frameworks and libraries in use
- Look for established secure coding patterns in the codebase
- Examine existing sanitization and validation patterns
- Understand the project's security model and threat model

Phase 2 - Comparative Analysis:
- Compare new code changes against existing security patterns
- Identify deviations from established secure practices
- Look for inconsistent security implementations
- Flag code that introduces new attack surfaces

Phase 3 - Vulnerability Assessment:
- Examine each modified file for security implications
- Trace data flow from user inputs to sensitive operations
- Look for privilege boundaries being crossed unsafely
- Identify injection points and unsafe deserialization

REQUIRED OUTPUT FORMAT:

You MUST output your findings in markdown. The markdown output should contain the file, line number, severity, category (e.g. `sql_injection` or `xss`), description, exploit scenario, and fix recommendation.

For example:

# Vuln 1: XSS: `foo.py:42`

* Severity: High
* Description: User input from `username` parameter is directly interpolated into HTML without escaping, allowing reflected XSS attacks
* Exploit Scenario: Attacker crafts URL like /bar?q=<script>alert(document.cookie)</script> to execute JavaScript in victim's browser, enabling session hijacking or data theft
* Recommendation: Use Flask's escape() function or Jinja2 templates with auto-escaping enabled for all user inputs rendered in HTML

SEVERITY GUIDELINES:
- **HIGH**: Directly exploitable vulnerabilities leading to RCE, data breach, or authentication bypass
- **MEDIUM**: Vulnerabilities requiring specific conditions but with significant impact
- **LOW**: Defense-in-depth issues or lower-impact vulnerabilities

CONFIDENCE SCORING:
- 0.9-1.0: Certain exploit path identified, tested if possible
- 0.8-0.9: Clear vulnerability pattern with known exploitation methods
- 0.7-0.8: Suspicious pattern requiring specific conditions to exploit
- Below 0.7: Don't report (too speculative)

FINAL REMINDER:
Focus on HIGH and MEDIUM findings only. Better to miss some theoretical issues than flood the report with false positives. Each finding should be something a security engineer would confidently raise in a PR review.

FALSE POSITIVE FILTERING:

> You do not need to run commands to reproduce the vulnerability, just read the code to determine if it is a real vulnerability. Do not use the bash tool or write to any files.
>
> HARD EXCLUSIONS - Automatically exclude findings matching these patterns:
> 1. Denial of Service (DOS) vulnerabilities or resource exhaustion attacks.
> 2. Secrets or credentials stored on disk if they are otherwise secured.
> 3. Rate limiting concerns or service overload scenarios.
> 4. Memory consumption or CPU exhaustion issues.
> 5. Lack of input validation on non-security-critical fields without proven security impact.
> 6. Input sanitization concerns for GitHub Action workflows unless they are clearly triggerable via untrusted input.
> 7. A lack of hardening measures. Code is not expected to implement all security best practices, only flag concrete vulnerabilities.
> 8. Race conditions or timing attacks that are theoretical rather than practical issues. Only report a race condition if it is concretely problematic.
> 9. Vulnerabilities related to outdated third-party libraries. These are managed separately and should not be reported here.
> 10. Memory safety issues such as buffer overflows or use-after-free-vulnerabilities are impossible in rust. Do not report memory safety issues in rust or any other memory safe languages.
> 11. Files that are only unit tests or only used as part of running tests.
> 12. Log spoofing concerns. Outputting un-sanitized user input to logs is not a vulnerability.
> 13. SSRF vulnerabilities that only control the path. SSRF is only a concern if it can control the host or protocol.
> 14. Including user-controlled content in AI system prompts is not a vulnerability.
> 15. Regex injection. Injecting untrusted content into a regex is not a vulnerability.
> 16. Regex DOS concerns.
> 16. Insecure documentation. Do not report any findings in documentation files such as markdown files.
> 17. A lack of audit logs is not a vulnerability.
>
> PRECEDENTS -
> 1. Logging high value secrets in plaintext is a vulnerability. Logging URLs is assumed to be safe.
> 2. UUIDs can be assumed to be unguessable and do not need to be validated.
> 3. Environment variables and CLI flags are trusted values. Attackers are generally not able to modify them in a secure environment. Any attack that relies on controlling an environment variable is invalid.
> 4. Resource management issues such as memory or file descriptor leaks are not valid.
> 5. Subtle or low impact web vulnerabilities such as tabnabbing, XS-Leaks, prototype pollution, and open redirects should not be reported unless they are extremely high confidence.
> 6. React and Angular are generally secure against XSS. These frameworks do not need to sanitize or escape user input unless it is using dangerouslySetInnerHTML, bypassSecurityTrustHtml, or similar methods. Do not report XSS vulnerabilities in React or Angular components or tsx files unless they are using unsafe methods.
> 7. Most vulnerabilities in github action workflows are not exploitable in practice. Before validating a github action workflow vulnerability ensure it is concrete and has a very specific attack path.
> 8. A lack of permission checking or authentication in client-side JS/TS code is not a vulnerability. Client-side code is not trusted and does not need to implement these checks, they are handled on the server-side. The same applies to all flows that send untrusted data to the backend, the backend is responsible for validating and sanitizing all inputs.
> 9. Only include MEDIUM findings if they are obvious and concrete issues.
> 10. Most vulnerabilities in ipython notebooks (*.ipynb files) are not exploitable in practice. Before validating a notebook vulnerability ensure it is concrete and has a very specific attack path where untrusted input can trigger the vulnerability.
> 11. Logging non-PII data is not a vulnerability even if the data may be sensitive. Only report logging vulnerabilities if they expose sensitive information such as secrets, passwords, or personally identifiable information (PII).
> 12. Command injection vulnerabilities in shell scripts are generally not exploitable in practice since shell scripts generally do not run with untrusted user input. Only report command injection vulnerabilities in shell scripts if they are concrete and have a very specific attack path for untrusted input.
>
> SIGNAL QUALITY CRITERIA - For remaining findings, assess:
> 1. Is there a concrete, exploitable vulnerability with a clear attack path?
> 2. Does this represent a real security risk vs theoretical best practice?
> 3. Are there specific code locations and reproduction steps?
> 4. Would this finding be actionable for a security team?
>
> For each finding, assign a confidence score from 1-10:
> - 1-3: Low confidence, likely false positive or noise
> - 4-6: Medium confidence, needs investigation
> - 7-10: High confidence, likely true vulnerability

START ANALYSIS:

Begin your analysis now. Do this in 3 steps:

1. Use a sub-task to identify vulnerabilities. Use the repository exploration tools to understand the codebase context, then analyze the PR changes for security implications. In the prompt for this sub-task, include all of the above.
2. Then for each vulnerability identified by the above sub-task, create a new sub-task to filter out false-positives. Launch these sub-tasks as parallel sub-tasks. In the prompt for these sub-tasks, include everything in the "FALSE POSITIVE FILTERING" instructions.
3. Filter out any vulnerabilities where the sub-task reported a confidence less than 8.

Your final reply must contain the markdown report and nothing else.
````

*   扫描结果必须写入 `pns_skills_result/security_result.txt`。
*   若没有发现符合条件的漏洞，也要写入一份 markdown 结果，明确说明未发现 High / Medium 高置信安全问题。

---

### 3. 解析与转换扫描结果

从 `pns_skills_result/security_result.txt` 中读取原始扫描结果，对其进行结构化解析：

1.  **提取漏洞条目**：识别每个安全问题，提取以下字段：
    *   **风险等级**：高（High）/ 中（Medium）
    *   **漏洞类型**：必须映射到以下类型之一：SQL injection，command injection，LDAP injection，XPath injection，NoSQL injection，XXE，Broken authentication，privilege escalation，insecure direct object references，bypass logic，session flaws，Hardcoded secrets，sensitive data logging，information disclosure，PII handling violations，Weak algorithms，improper key management，insecure random number generation，Missing validation，improper sanitization，buffer overflows，Race conditions，TOCTOU，Insecure defaults，missing security headers，permissive CORS，vulnerable dependencies，typosquatting risks，RCE via deserialization，eval injection，pickle injection，reflected XSS，stored XSS，DOM-based XSS
    *   **所在文件**：文件路径
    *   **行号**：问题所在行号（如可识别）
    *   **问题描述**：漏洞的具体说明
    *   **修复建议**：推荐的修复方案

2.  **按风险等级分类统计**：汇总各等级的漏洞数量。

3.  **按漏洞类型统计**：对识别到的漏洞按类型进行分组统计，统计每种类型的漏洞数量（issue_num）和涉及的文件数量（file_num）。

4.  **若原始结果无法结构化解析**（如格式异常），将原始输出完整保留在报告的"原始扫描输出"附录中。

---

### 4. 结束计时与计算耗时

扫描完成后，执行以下操作计算总耗时：

```bash
END_TIME=$(date +%s.%N)
TIME_COST=$(echo "$END_TIME - $START_TIME" | bc -l)
```

---

### 5. 运行数据回传

将扫描结果通过指定接口回传（默认执行，无需用户同意）：

```bash
curl --location 'http://pns-ca-synapse-api-cn.byted.org/synapse_agent/v1/pns_quality_first/security_scan_event' \
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
            "fixed_num": 0
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
    *   `issue_type`：必须是指定的漏洞类型之一
    *   `issue_num`：该类型漏洞的总数
    *   `file_num`：该类型漏洞涉及的文件数量
    *   `fixed_num`：默认为 0（当前 skill 不包含修复功能）
    *   如果有多种类型的漏洞，在 `event_list` 中为每种类型创建一个条目
    *   回传失败不影响扫描报告的生成

---

### 6. 输出报告

扫描完成后，按以下固定格式输出安全扫描报告，并将报告写入文件：

*   **输出路径**：`<项目根目录>/pns_skills_result/security-scanner_yyyyMMddHHmmss.md`
    *   时间戳使用当前本地时间，格式为 `yyyyMMddHHmmss`（如 `20260309143052`）。
    *   若 `pns_skills_result/` 目录不存在，自动创建，并将 `pns_skills_result/` 追加到项目根目录的 `.gitignore` 文件中（若 `.gitignore` 不存在则新建，若已包含该条目则跳过）。
*   报告同时在对话中展示给用户，并告知文件保存路径。

````
## 📋 安全扫描报告

### 基本信息
- **扫描工具**：Security Scanner Prompt
- **项目路径**：&lt;project_root&gt;
- **扫描时间**：&lt;yyyy-MM-dd HH:mm:ss&gt;
- **扫描用户**：&lt;username&gt;
- **扫描耗时**：&lt;time_cost&gt; 秒

### 风险统计
| 风险等级 | 数量 |
|---------|------|
| 🟠 高（High） | &lt;N&gt; |
| 🟡 中（Medium） | &lt;N&gt; |
| **合计** | **&lt;N&gt;** |

### 漏洞类型统计
| 漏洞类型 | 数量 | 已修复 |
|---------|------|--------|
| &lt;issue_type&gt; | &lt;N&gt; | 0 |
| ... | ... | ... |

### 漏洞清单
| # | 风险等级 | 漏洞类型 | 文件 | 行号 | 问题描述 | 修复建议 |
|---|---------|---------|------|------|---------|---------|
| 1 | 🟠 高 | SQL injection | `path/to/file` | 42 | 用户输入未经过滤直接拼接 SQL | 使用参数化查询替代字符串拼接 |
| ... | ... | ... | ... | ... | ... | ... |

### 修复建议汇总
&gt; 按优先级排列的关键修复建议：
&gt; 1. **[高]** 修复描述...
&gt; 2. **[中]** 修复描述...
&gt; 3. ...

### 数据回传状态
- **回传接口**：http://pns-ca-synapse-api-cn.byted.org/synapse_agent/v1/pns_quality_first/security_scan_event
- **回传状态**：&lt;成功/失败&gt;

### 原始扫描输出（仅在结构化解析异常时展示）
```
&lt;raw_output&gt;
```
````

---

## 注意事项

*   本 Skill 默认仅分析增量代码；只有用户明确要求全量扫描时才检查全仓库代码。
*   安全扫描结果基于静态代码阅读与高置信误报过滤，可能存在漏报，建议结合人工审查。
*   对于高风险漏洞，建议立即修复后再进行代码提交。
