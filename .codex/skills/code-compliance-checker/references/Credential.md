# Credential（凭证安全）

## 1. 执行标准

-   **核心原则**：代码中严禁以明文或硬编码形式存放任何凭证信息，包括但不限于密码（Password）、令牌（Token）、访问密钥（AK/SK）等。
-   **适用范围**：此规则同样适用于测试代码中使用的**真实且有效**的凭证。虚假或编造的凭证（如 `password = "123456"`）虽风险较低，但仍建议移除以降低解释成本。

## 2. 处理方法

### 2.1 风险分类

在整改前，首先需要评估凭证的风险类别。以下为需要整改的凭证类型：

| 类别 | 场景描述 |
| :--- | :--- |
| **内部系统鉴权** | 访问内部系统，无论是否涉及用户数据。 |
| **外部 API** | 调用付费购买、以公司名义注册或有使用限制（如 QPS）的外部服务。 |
| **其他** | 存在泄漏风险的其他功能性鉴权。 |

**无需整改**的凭证仅限于：
-   外部 API 的凭证已在开源代码中公开。
-   完全虚假、用于占位的凭证。

### 2.2 整改方案

**首选方案是“删除”**。如果凭证并非必要，请直接从代码库中移除。

若必须使用，请选择以下方案之一进行改造：

-   **TCC (Toutiao Configuration Center)**：
    -   **特点**：推荐方案。配置中心化，支持加密和访问控制（ACL），方便环境切换。参考2.3 TCC 改造详细指南
    -   **适用场景**：服务端运行时配置。
-   **DKMS (Data Key Management Service)**：
    -   **特点**：专业的数据密钥管理服务，提供加解密能力，支持 TTP-US 环境。
    -   **适用场景**：需要对敏感数据进行加解密的场景。
-   **TBS (Tencent Block Storage) / ByteDrive**：
    -   **特点**：将凭证文件存放在块存储中，在服务部署时挂载为本地文件系统进行读取。
    -   **适用场景**：物理机部署或无法接入 TCC 的场景。
-   **Codebase CI Variables**：
    -   **特点**：用于托管 CI/CD 流程中的敏感变量，仅项目 Master 和 Owner 可访问。
    -   **适用场景**：构建或部署阶段需要使用的凭证。
-   **加密文件存储**：
    -   **特点**：使用 `Java Keystore` (PKCS12) 或类似机制，将凭证加密后存放在一个受密码保护的文件中。
    -   **适用场景**：无法依赖其他平台（如 TCC）的非 TCE 服务。

### 2.3 TCC 改造详细指南

#### 2.3.1 TCC 封装检查

根据目标文件语言选择对应策略，检测仓库现有 TCC 封装并决定复用或新建。

> **[关键指令 — TCC Namespace 记录]**：在本节确定 TCC 封装方案后，**必须立即记录**解析到的 **TCC namespace**（即 PSM 值 / `@DynamicConfig` 的 `name` 值）。此 namespace 将在后续步骤中用于构造 TCC 配置预览链接并写入 commit message，**不可遗漏**。

**Golang（`.go`）**

- 搜索仓库中是否已引用 `code.byted.org/gopkg/tccclient` 或 `code.byted.org/gopkg/tccclient/v3`。
- 若存在，分析可用方法并复用；**同时从 `tccclient.NewClientV2("...", ...)` 或 `tccclient.NewClient("...", ...)` 调用中提取第一个字符串参数，即为 TCC namespace**。
- 若不存在，按下方「Golang 最小封装示例」新增封装文件，并在入口处调用初始化方法。**此时 namespace 为新建封装中 `NewClientV2` 第一个参数的值（即 `TCC_PSM` 对应的值）**。
- 若需新增封装文件，解析仓库根 `build.sh` 的 `RUN_NAME` 并用作 `TCC_PSM` 配置值。
- 若同时存在 v2 与 v3，或仅存在 v2，优先复用 `code.byted.org/gopkg/tccclient`（v2 接口）。
- 若仅存在 v3，复用 v3 接口。
- **[必须记录]** 将解析到的 namespace 值记录下来（如 `tiktok.pns.ca_synapse`）。

**Java/Kotlin（`.java`、`.kt`）**

- 搜索仓库中是否已引入 TCC SDK 依赖 `com.bytedance.data.tcc.client` 及 Spring 注解 `@DynamicConfig`。
- 若存在已有的 TCC Service 类，优先在该类中新增 `@DynamicConfig` 字段或方法来承载凭据配置；选择与命中文件最相关的 TCC Service（同模块/同包路径优先）。**同时从已有的 `@DynamicConfig(name = "...", ...)` 注解中提取 `name` 属性值，即为 TCC namespace**。
- 若不存在，按下方「Java/Kotlin 最小封装示例」新增 Spring Service 类（含接口与实现），PSM 值根据项目配置确定。**此时 namespace 为新建类中 `@DynamicConfig` 注解的 `name` 值（即 PSM 常量对应的值）**。
- 命中文件中通过 `@Autowired` 或构造函数注入 TCC Service 接口。
- **[必须记录]** 将解析到的 namespace 值记录下来（如 `tiktok.pns.ca_synapse`）。

#### 2.3.2 Golang（`.go`）TCC 改造规则

- **封装复用**：
    - 检测仓库是否已引用 Golang 包名 `code.byted.org/gopkg/tccclient` 或 `code.byted.org/gopkg/tccclient/v3`。
    - 若同时存在或仅存在 v2，优先复用 `code.byted.org/gopkg/tccclient`（v2 接口）。
    - 若仅存在 v3，复用 v3 接口。
- **最小封装**：若仓库未接入 TCC，新增独立封装文件（如 `internal/tcc_cfg`），提供 `InitTCCClient`、`Get`/`GetString`。
    - `TCC_PSM` 值需根据仓库根的 `build.sh` 中 `RUN_NAME` 配置。
    - **最小封装示例**：
      ```go
      package tcccfg

      import (
          "context"

          "code.byted.org/gopkg/logs/v2"
          "code.byted.org/gopkg/tccclient"
      )

      const (
          TCC_PSM               = "aa.bb.cc" // 将在执行时按 build.sh 的 RUN_NAME 替换
          TCC_DEFAULT_NAMESPACE = "default"
      )

      var client *tccclient.ClientV2

      func InitTCCClient() {
          if client != nil {
              return
          }
          cfg := tccclient.NewConfigV2()
          cfg.Confspace = TCC_DEFAULT_NAMESPACE
          c, err := tccclient.NewClientV2(TCC_PSM, cfg)
          if err != nil {
              logs.Error("Init TCC client error: %v", err)
              panic(err)
          }
          client = c
      }

      func GetString(ctx context.Context, key string) (string, error) {
          v, err := client.Get(ctx, key)
          if err != nil {
              return "", err
          }
          return v, nil
      }
      ```
- **配置结构**：依据凭据场景语义新建 config struct，并在该 struct 内新增字段；禁止在已有 struct 上追加字段。
- **方法约束**：参考仓库已封装的 TCC 配置获取方式，新增符合凭据语义的方法（如 `GetProxyForwardURL(ctx context.Context)`）；当 TCC 读取配置失败时，严禁使用默认值进行降级处理，必须将错误直接向上返回，确保异常能够被上层调用方感知并处理。
- **示例**：
    - `Input`: `match_content: ["http://user:pass@proxy.example.org:8080"]`
    - 原始：`proxyURL := "http://user:pass@proxy.example.org:8080"` → 替换后：`proxyURL, err := tcccfg.GetString(ctx, "service.proxy.forward_url")`

#### 2.3.3 Java/Kotlin（`.java`、`.kt`）TCC 改造规则

- **封装复用**：
    - 检测仓库是否已引入 TCC SDK 依赖 `com.bytedance.data.tcc.client` 及 Spring 注解 `com.bytedance.data.tcc.client.spring.DynamicConfig`。
    - 若存在已有的 TCC Service 类（通常使用 `@DynamicConfig` 注解），优先在该类中新增字段或方法来承载凭据配置。
    - 若仓库中存在多个 TCC Service，选择与命中文件最相关的（同模块/同包路径优先）。
- **最小封装**：若仓库未接入 TCC，新增独立 Spring Service 类（含接口与实现），通过 `@DynamicConfig` 注解注入凭据配置。
    - PSM 值需根据项目配置（如 `application.yml` / `application.properties` 中的 PSM 定义，或仓库中已有的 PSM 常量）确定。
    - **两种注入模式**：
      - **字段注入**：适用于简单字符串值，使用 `@DynamicConfig(name = PSM, key = "configKey")` 直接注解到字段上，框架自动更新字段值。
      - **方法监听注入**：适用于需要解析为复杂类型（JSON → Map / List / POJO）的配置，使用 `@DynamicConfig(name = PSM, key = "configKey")` 注解到方法 `public void methodName(String text, String ori)` 上，在回调中执行反序列化。
    - **最小封装示例**：
      ```java
      // === 接口定义 ===
      package com.example.service.tcc;

      public interface CredentialTccService {
          /**
           * 获取凭据配置值
           * @param key 配置键名（保留以便后续扩展多凭据场景）
           * @return 配置值字符串；若未配置则返回 null
           */
          String getCredentialConfig(String key);
      }

      // === 实现类 ===
      package com.example.service.tcc.impl;

      import com.bytedance.data.tcc.client.spring.DynamicConfig;
      import com.example.service.tcc.CredentialTccService;
      import org.slf4j.Logger;
      import org.slf4j.LoggerFactory;
      import org.springframework.stereotype.Service;

      import java.util.Map;
      import java.util.concurrent.ConcurrentHashMap;

      @Service
      public class CredentialTccServiceImpl implements CredentialTccService {

          private static final Logger LOGGER = LoggerFactory.getLogger(CredentialTccServiceImpl.class);

          // PSM 值需根据项目实际配置替换
          private static final String PSM = "aa.bb.cc";

          // 方式一：字段注入（简单字符串值）
          @DynamicConfig(name = PSM, key = "credential.proxy.forward_url")
          private String proxyForwardUrl;

          // 方式二：方法监听注入（适用于多凭据场景，动态更新 Map）
          private final Map<String, String> credentialMap = new ConcurrentHashMap<>();

          @DynamicConfig(name = PSM, key = "credential.config.map")
          public void onCredentialConfigUpdate(String text, String ori) {
              LOGGER.info("credential config updated, ORI: {} AFTER: {}", ori, text);
              // 解析 JSON 并更新 credentialMap
              // credentialMap = JSON.parseObject(text, new TypeReference<Map<String, String>>() {});
          }

          @Override
          public String getCredentialConfig(String key) {
              return credentialMap.getOrDefault(key, null);
          }
      }
      ```
- **配置结构**：依据凭据场景语义，在 TCC Service 实现类中新增 `@DynamicConfig` 字段或方法；禁止在已有的非凭据相关字段上修改用途。
- **方法约束**：新增符合凭据语义的 getter 方法（如 `getProxyForwardUrl()`）暴露到接口中；调用方通过 Spring 依赖注入获取 Service 实例后调用 getter 读取配置值。当配置值为 `null` 或空时，严禁使用默认值进行降级处理，必须抛出异常或将 `null` 向上返回，确保上层调用方感知。
- **Spring 装配**：确保实现类所在包在 Spring 组件扫描路径内（`@ComponentScan` / `@SpringBootApplication` 覆盖范围）；命中文件中通过 `@Autowired` 或构造函数注入 TCC Service 接口。
- **示例**：
    - `Input`: `match_content: ["http://user:pass@proxy.example.org:8080"]`
    - 原始：`String proxyURL = "http://user:pass@proxy.example.org:8080";`
    - 替换后：`String proxyURL = credentialTccService.getProxyForwardUrl();`
    - **禁止**：`String proxyURL = "***";`（严禁替换为占位符）

## 3. 误报过滤（自动白名单）

> **[关键指令 — 强制执行]**：Credential 规则识别出疑似问题后，**必须**先经过本节定义的自动白名单过滤，命中规则的问题需从最终报告中剔除，仅保留未命中的问题进入"问题清单 / 修复 / 人工确认"流程。

### 3.1 过滤规则

满足以下条件，问题即视为误报并被过滤：

1.  **文件路径白名单**：问题所在文件路径命中预设 glob 模式。覆盖文档/脚本/构建配置类文件（`*.md`、`*.sh`、`*gradle*`、`*.pbxproj`、`*.podspec`、`*.doxyfile`、`*.makefile`、`*.markdown`、`*.changelog`、`*.configure`），以及调试/示例/测试目录（`*/zk_rules/*`、`*/debug/*`、`*/debugger/*`、`*/example/*`、`*/examples/*`、`*/test/*`、`*/tests/*`、`*/testing/*`、`*/sample/*`、`*/samples/*`、`*/demo/*`、`*/demos/*`）。

完整的白名单作为脚本的**唯一可信源**维护，路径见下文。修改白名单时，请直接编辑该脚本中的 `CREDENTIAL_FILTER_FILE_PATH_PATTERNS` 数组，**不要**在 Markdown 中另行复制。

> 设计说明：与 Domain 不同，Credential 不维护"凭证值白名单"——明文凭证一旦真实存在即应整改，不允许通过具体值豁免；豁免维度仅限于"显然不会进入生产链路"的文档/脚本/构建配置/调试与示例目录。

### 3.2 过滤脚本

-   **脚本路径（相对 Skill 根目录）**：`scripts/filter_credential_issues.sh`
-   **匹配语义**：使用 Bash 内置的 `[[ $value == $pattern ]]` 进行 glob 匹配，`*` 可匹配包括 `/` 在内的任意字符串，与白名单中的写法保持一致。
-   **导出函数**：
    *   `should_filter_file_path <file_path>` —— 命中文件白名单返回 `0`，否则返回 `1`。
    *   `should_filter_credential_issue <file_path>` —— 与 `should_filter_file_path` 等价，仅作为统一对外入口；命中即返回 `0`（应过滤），否则返回 `1`（保留）。
-   **路径解析约定**：示例中 `scripts/filter_credential_issues.sh` 是**相对本 Skill 根目录**的路径；调用方（Agent / 扫描器）应在运行时把它解析为本 Skill 在当前环境的实际绝对路径，**不要**把开发仓库内的相对路径（如 `plugins/.../code-compliance-checker/`）硬编码进调用脚本。
-   **两种使用方式**：
    *   **方式 A：source 后逐条调用函数（推荐用于扫描器内部循环）**
        ```bash
        # SKILL_ROOT 由调用方解析为本 Skill 的实际目录
        source "$SKILL_ROOT/scripts/filter_credential_issues.sh"

        # 假设 $file_path 已从 Credential 规则的单条命中中解析
        if should_filter_credential_issue "$file_path"; then
          # 命中白名单，丢弃本条问题
          continue
        fi
        # 未命中，进入后续报告 / 修复流程
        ```
    *   **方式 B：CLI 流式过滤（适合在 shell 管道里成批处理）**
        ```bash
        # raw_issues.tsv 每行格式：<file_path>[\t<extra context...>]
        cat raw_issues.tsv \
          | bash "$SKILL_ROOT/scripts/filter_credential_issues.sh" \
          > filtered_issues.tsv
        ```

### 3.3 在扫描流程中的位置

执行顺序固定为：**Credential 规则原始命中 → 自动白名单过滤（本节） → 输出到合规报告 / 进入修复流程**。

-   过滤发生在「按规则类别统计」之前，被过滤的问题**不计入** `issue_num`、`file_num`，也不在 `运行数据回传` 的 `event_list` 中体现。
-   `issue_type` 仍保留为 `Credential`，仅是被过滤后该类别的 `issue_num` 可能为 0。
-   若用户后续要求"恢复某条被过滤的问题"，应建议其通过修改 `filter_credential_issues.sh` 的白名单数组而非在报告中手工添加。

## 4. 常见问题与注意事项

-   **测试凭证**：只要测试中使用的凭证是**真实有效**的，就必须整改。无效或编造的凭证可以豁免，但建议替换为无意义字符串。
-   **客户端凭证**：客户端不应使用配置文件来托管密钥，因为配置文件最终仍会打包到 App 中，存在泄漏风险。推荐的方案是在构建时通过环境变量注入，或直接删除。
-   **TCC 平台自身的凭证**：对于 TCC 平台自身的代码库，其凭证问题可使用 DKMS 进行加密存储。

