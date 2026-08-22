# Domain（域名合规）

## 1. 执行标准

- **核心原则**：原则上，不可在代码中访问注册地为中国大陆及港澳台地区的域名。
- **审查范围**：进入 TTP（Texas Trusted Platform）的代码即被视为受外部审查范围，审查基于源代码，不区分代码逻辑是否在 TTP 环境“真实使用”。

## 2. 处理方法

### 2.1 域名归属地查询

使用 **GPCP 域名判定工具** 判断域名注册地。若命中 `CN`、`HK`、`TW`、`MO`，则必须替换为海外域名或进行合规改造。

### 2.2 服务端处理建议

1.  **TCC 配置（推荐）**：将不同环境的域名分别配置在对应环境的 **TCC (Toutiao Configuration Center)** 上。参考2.4 TCC 改造详细指南
    *   **注意**：TTP 编译环境禁止访问 TCC，因此不支持在编译期拉取配置。此场景需采用下述“分环境配置文件”方案。
2.  **分环境配置文件**：创建独立的配置文件（如 `CN_conf.yaml`, `SG_conf.yaml`），在代码中按环境导入。
    *   **合规案例**：
        *   创建 `conf/` 目录，内部按地区/环境建立独立的 `.yaml` 或 `.go` 常量文件。
        *   确保用于 TTP 机房的配置文件中不包含任何中国大陆及港澳台的域名。
    *   **错误案例**：
        *   在业务代码中硬编码域名。
        *   在单一配置文件中混合存放所有环境的域名，通过代码逻辑判断环境并选择。

### 2.3 前端/客户端处理建议

-   **前端**：
    *   可通过域名判断登录环境，但不能通过环境判断使用哪个域名。即，以域名作为输入，环境作为输出是合规的。
    *   对于不在 TTP 渲染的页面或功能，可通过分环境建立独立页面/组件（如 `CNFooBarPage.tsx`）来隔离。
-   **客户端**：
    *   **代码隔离**：拆分仓库或分支，为 TikTok 单独打包海外版组件。
    *   **Setting 平台**：通过 Setting 配置中心下发，区分海内外域名的打包和使用。

### 2.4 TCC 改造详细指南

#### 2.4.1 TCC 封装检查

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
- 若存在已有的 TCC Service 类，优先在该类中新增 `@DynamicConfig` 字段或方法来承载域名配置；选择与命中文件最相关的 TCC Service（同模块/同包路径优先）。**同时从已有的 `@DynamicConfig(name = "...", ...)` 注解中提取 `name` 属性值，即为 TCC namespace**。
- 若不存在，按下方「Java/Kotlin 最小封装示例」新增 Spring Service 类（含接口与实现），PSM 值根据项目配置确定。**此时 namespace 为新建类中 `@DynamicConfig` 注解的 `name` 值（即 PSM 常量对应的值）**。
- 命中文件中通过 `@Autowired` 或构造函数注入 TCC Service 接口。
- **[必须记录]** 将解析到的 namespace 值记录下来（如 `tiktok.pns.ca_synapse`）。

#### 2.4.2 Golang（`.go`）TCC 改造规则

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
- **配置结构**：依据域名场景语义新建 config struct，并在该 struct 内新增字段；禁止在已有 struct 上追加字段。
- **方法约束**：参考仓库已封装的 TCC 配置获取方式，新增符合域名语义的方法（如 `GetServiceDomain(ctx context.Context)`）；当 TCC 读取配置失败时，严禁使用默认值进行降级处理，必须将错误直接向上返回，确保异常能够被上层调用方感知并处理。
- **示例**：
    - `Input`: `match_content: ["example.douyin.com"]`
    - 原始：`domain := "example.douyin.com"` → 替换后：`domain, err := tcccfg.GetString(ctx, "service.domain.url")`

#### 2.4.3 Java/Kotlin（`.java`、`.kt`）TCC 改造规则

- **封装复用**：
    - 检测仓库是否已引入 TCC SDK 依赖 `com.bytedance.data.tcc.client` 及 Spring 注解 `com.bytedance.data.tcc.client.spring.DynamicConfig`。
    - 若存在已有的 TCC Service 类（通常使用 `@DynamicConfig` 注解），优先在该类中新增字段或方法来承载域名配置。
    - 若仓库中存在多个 TCC Service，选择与命中文件最相关的（同模块/同包路径优先）。
- **最小封装**：若仓库未接入 TCC，新增独立 Spring Service 类（含接口与实现），通过 `@DynamicConfig` 注解注入域名配置。
    - PSM 值需根据项目配置（如 `application.yml` / `application.properties` 中的 PSM 定义，或仓库中已有的 PSM 常量）确定。
    - **两种注入模式**：
      - **字段注入**：适用于简单字符串值，使用 `@DynamicConfig(name = PSM, key = "configKey")` 直接注解到字段上，框架自动更新字段值。
      - **方法监听注入**：适用于需要解析为复杂类型（JSON → Map / List / POJO）的配置，使用 `@DynamicConfig(name = PSM, key = "configKey")` 注解到方法 `public void methodName(String text, String ori)` 上，在回调中执行反序列化。
    - **最小封装示例**：
      ```java
      // === 接口定义 ===
      package com.example.service.tcc;

      public interface DomainTccService {
          /**
           * 获取域名配置值
           * @param key 配置键名（保留以便后续扩展多域名场景）
           * @return 配置值字符串；若未配置则返回 null
           */
          String getDomainConfig(String key);
      }

      // === 实现类 ===
      package com.example.service.tcc.impl;

      import com.bytedance.data.tcc.client.spring.DynamicConfig;
      import com.example.service.tcc.DomainTccService;
      import org.slf4j.Logger;
      import org.slf4j.LoggerFactory;
      import org.springframework.stereotype.Service;

      import java.util.Map;
      import java.util.concurrent.ConcurrentHashMap;

      @Service
      public class DomainTccServiceImpl implements DomainTccService {

          private static final Logger LOGGER = LoggerFactory.getLogger(DomainTccServiceImpl.class);

          // PSM 值需根据项目实际配置替换
          private static final String PSM = "aa.bb.cc";

          // 方式一：字段注入（简单字符串值）
          @DynamicConfig(name = PSM, key = "service.domain.url")
          private String serviceDomainUrl;

          // 方式二：方法监听注入（适用于多域名场景，动态更新 Map）
          private final Map<String, String> domainMap = new ConcurrentHashMap<>();

          @DynamicConfig(name = PSM, key = "service.domain.map")
          public void onDomainConfigUpdate(String text, String ori) {
              LOGGER.info("domain config updated, ORI: {} AFTER: {}", ori, text);
              // 解析 JSON 并更新 domainMap
              // domainMap = JSON.parseObject(text, new TypeReference<Map<String, String>>() {});
          }

          @Override
          public String getDomainConfig(String key) {
              return domainMap.getOrDefault(key, null);
          }
      }
      ```
- **配置结构**：依据域名场景语义，在 TCC Service 实现类中新增 `@DynamicConfig` 字段或方法；禁止在已有的非域名相关字段上修改用途。
- **方法约束**：新增符合域名语义的 getter 方法（如 `getServiceDomainUrl()`）暴露到接口中；调用方通过 Spring 依赖注入获取 Service 实例后调用 getter 读取配置值。当配置值为 `null` 或空时，严禁使用默认值进行降级处理，必须抛出异常或将 `null` 向上返回，确保上层调用方感知。
- **Spring 装配**：确保实现类所在包在 Spring 组件扫描路径内（`@ComponentScan` / `@SpringBootApplication` 覆盖范围）；命中文件中通过 `@Autowired` 或构造函数注入 TCC Service 接口。
- **示例**：
    - `Input`: `match_content: ["example.douyin.com"]`
    - 原始：`String domain = "example.douyin.com";`
    - 替换后：`String domain = domainTccService.getServiceDomainUrl();`
    - **禁止**：`String domain = "***";`（严禁替换为占位符）

## 3. 误报过滤（自动白名单）

> **[关键指令 — 强制执行]**：Domain 规则识别出疑似问题后，**必须**先经过本节定义的自动白名单过滤，命中规则的问题需从最终报告中剔除，仅保留未命中的问题进入"问题清单 / 修复 / 人工确认"流程。

### 3.1 过滤规则

满足任一条件，问题即视为误报并被过滤：

1. **文件路径白名单**：问题所在文件路径命中预设 glob 模式（例如 `*.md`、`*/test/*`、`*.lock`、`*/quiche/quic/*` 等 57 项）。
2. **域名白名单**：检出的域名命中预设 glob 模式（例如 `*.bytedance.net`/`*byted.org` 系列基础设施、`*github.com`、`*apache.org`、`*tiktokd.org`、`stripe.com` 等数百项内部与公开基础设施域名）。

完整的两份白名单作为脚本的**唯一可信源**维护，路径见下文。修改白名单时，请直接编辑该脚本中的 `DOMAIN_FILTER_FILE_PATH_PATTERNS` 与 `DOMAIN_FILTER_DOMAIN_PATTERNS` 数组，**不要**在 Markdown 中另行复制。

### 3.2 过滤脚本

-   **脚本路径（相对 Skill 根目录）**：`scripts/filter_domain_issues.sh`
-   **匹配语义**：使用 Bash 内置的 `[[ $value == $pattern ]]` 进行 glob 匹配，`*` 可匹配包括 `/` 在内的任意字符串，与白名单中的写法保持一致。
-   **导出函数**：
    *   `should_filter_file_path <file_path>` —— 命中文件白名单返回 `0`，否则返回 `1`。
    *   `should_filter_domain <domain>` —— 命中域名白名单返回 `0`，否则返回 `1`。
    *   `should_filter_domain_issue <file_path> <domain>` —— 任一命中即返回 `0`（应过滤），否则返回 `1`（保留）。
-   **路径解析约定**：示例中 `scripts/filter_domain_issues.sh` 是**相对本 Skill 根目录**的路径；调用方（Agent / 扫描器）应在运行时把它解析为本 Skill 在当前环境的实际绝对路径，**不要**把开发仓库内的相对路径（如 `plugins/.../code-compliance-checker/`）硬编码进调用脚本。
-   **两种使用方式**：
    *   **方式 A：source 后逐条调用函数（推荐用于扫描器内部循环）**
        ```bash
        # SKILL_ROOT 由调用方解析为本 Skill 的实际目录
        source "$SKILL_ROOT/scripts/filter_domain_issues.sh"

        # 假设 $file_path / $domain 已从 Domain 规则的单条命中中解析
        if should_filter_domain_issue "$file_path" "$domain"; then
          # 命中白名单，丢弃本条问题
          continue
        fi
        # 未命中，进入后续报告 / 修复流程
        ```
    *   **方式 B：CLI 流式过滤（适合在 shell 管道里成批处理）**
        ```bash
        # raw_issues.tsv 每行格式：<file_path>\t<domain>[\t<extra context...>]
        cat raw_issues.tsv \
          | bash "$SKILL_ROOT/scripts/filter_domain_issues.sh" \
          > filtered_issues.tsv
        ```

### 3.3 在扫描流程中的位置

执行顺序固定为：**Domain 规则原始命中 → 自动白名单过滤（本节） → 输出到合规报告 / 进入修复流程**。

-   过滤发生在「按规则类别统计」之前，被过滤的问题**不计入** `issue_num`、`file_num`，也不在 `运行数据回传` 的 `event_list` 中体现。
-   `issue_type` 仍保留为 `Domain`，仅是被过滤后该类别的 `issue_num` 可能为 0。
-   若用户后续要求"恢复某条被过滤的问题"，应建议其通过修改 `filter_domain_issues.sh` 的白名单数组而非在报告中手工添加。

## 4. 常见问题与误报处理

-   **配置文件中的域名**：
    *   `conf` 目录中的域名同样会被扫描。必须确保海外环境的配置文件在检测范围内且内容合规。
    *   其他地区的配置文件（如中国大陆专用）可评估后不强制纳入扫描，但需保证清晰的路径或文件名标识（如 `config_cn.json`），以便于解释和自动误报识别。
-   **测试与 Mock 域名**：
    *   建议将测试或 Mock 域名统一存放在有明显标识的配置文件中，以降低审查时的解释成本。
    *   如果 Mock 文件确认不会在 TTP 环境中使用，可联系合规运营同学进行处理。
-   **新增白名单的处理路径**：
    *   若发现稳定的、可重复出现的误报模式（如某类 BU 内部域名、某类工具产物路径），应在 `scripts/filter_domain_issues.sh` 中追加对应 glob 模式，并附 PR 说明来源，以便后续审计。
    *   不要在业务代码或报告中硬编码"忽略该问题"，统一通过本脚本的白名单收敛。

## 5. 细则与示例

### 合规案例 (服务端)

**✅ Case 1: 按环境拆分配置文件**

```
/conf
├── boe.yaml
├── prod.yaml
└── ttp.yaml
```

**✅ Case 2: 在文件名中明确标识地区**

```
/config
├── config_cn.go
└── config_row.go
```

### 不合规案例 (服务端)

**❌ Bad Case: 在代码中硬编码**

```go
func getDomain() string {
    if getEnv() == "TTP" {
        return "example.tiktok.com"
    }
    return "example.douyin.com" // 不合规
}
```

---
