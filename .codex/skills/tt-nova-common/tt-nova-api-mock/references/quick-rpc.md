# 快速 Mock 下游 RPC

## 概述

快速 Mock 下游 RPC 屏蔽了创建 Mock 服务分组、Mock 服务和分流信息的复杂性，系统会自动帮你全套自动创建。

**适用场景**：
- 简单的 RPC 服务 Mock
- 快速验证接口 Mock 效果
- 流量标识牵引模式
- 接口测试时一键快速 Mock 下游 RPC 服务

**协议支持**：仅 RPC/Thrift

---

## 执行流程

### Step 1：确认基础信息

询问用户以下信息：

| 参数 | 说明 | 示例 |
|------|------|------|
| `<psm>` | 被 Mock 服务的 PSM | `env.t.rpc` |
| `<method>` | 要 Mock 的接口方法名 | `Ping` |
| `<mock_data>` | 接口要返回的 Mock 数据（JSON 格式） | `{"code":0,"message":"success"}` |
| `<namespace>` | Mock 空间名（可选，不提供则自动创建） | `ai_agent_mock_xxx` |

### Step 2：创建 Mock 服务（自动分流）

执行以下命令，系统会自动创建 Mock 空间、Mock 服务并配置分流：

```bash
bam-cli api-mock \
  --act create-mock-service \
  --vregion <VREGION> \
  --psm <psm> \
  --input '{
    "namespace": "<namespace>",
    "method": "<method>",
    "mock_data": "<mock_data>",
    "idl_version": "<idl_version>",
    "idl_source": "<idl_source>",
    "mock_sub_mode": "<mock_sub_mode>"
  }'
```

**参数说明**：
| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 否 | Mock 空间名，不提供则自动生成 |
| `method` | 是 | 接口方法名 |
| `mock_data` | 是 | Mock 返回数据，必须为 JSON 格式字符串 |
| `idl_version` | 否 | IDL 版本，如 `master` |
| `idl_source` | 否 | IDL 来源，如 `i18n` |
| `mock_sub_mode` | 否 | Mock 子模式，默认为 `default_json` |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "namespace": "ai_agent_mock_xxx",
    "psm": "env.t.rpc",
    "method": "Ping"
  }
}
```

**重要**：返回数据中的 `namespace` 即为 Mock 空间名，请记住这个值，后续步骤都需要用到。

- 提取返回内容中的 `data.namespace` 如果不为空，作为后续请求中的`<namespace>`。

---

### Step 2.5：调用链携带标识（流量牵引）

Mock 配置完成后，想要让请求走到 Mock 服务，需要在调用链中携带流量标识。选择以下方式之一：

#### 方式一：HTTP 请求入口 Header 注入 或者 接口测试工具 HTTP请求的 Header 注入

在请求入口 HTTP 服务时带上以下 2 个 header：

| Header Key | Header Value |
|------------|--------------|
| `Rpc-Persist-Dyecp-Fd-Mock` | `new_mock_<namespace>` |
| `Rpc-Persist-Mock-Tag` | `<namespace>` |

示例：
```bash
curl -X POST "http://your-service/api" \
  -H "Rpc-Persist-Dyecp-Fd-Mock: new_mock_ai_agent_skill_82ulyj" \
  -H "Rpc-Persist-Mock-Tag: ai_agent_skill_82ulyj" \
  -d '{"key": "value"}'
```

#### 方式二：代码注入流量标记（Golang 示例）

修改上游代码，显式注入流量标记并透传给下游：

```go
import "github.com/bytedance/gopkg/util/metainfo"

ctx = metainfo.WithPersistentValue(ctx, "DYECP_FD_MOCK", "new_mock_<namespace>")
ctx = metainfo.WithPersistentValue(ctx, "MOCK_TAG", "<namespace>")
```

#### 方式三：接口测试工具调用

通过接口测试工具调用时，需要在 RPC Header 中携带标识：

| Header Key | Header Value |
|------------|--------------|
| `DYECP_FD_MOCK` | `new_mock_<namespace>` |
| `MOCK_TAG` | `<namespace>` |

> **注意**：Header 类型选择 `persistent`，确保标识能够透传给下游服务。

#### 方式四：接口测试工具 RPC Body 注入

通过接口测试工具调用 RPC 接口时，也可以在请求 Body 的 `Base.Extra.user_extra` 字段中携带 Mock 标识：

```json
{
  "ItemIds": [
    7278951327475158316
  ],
  "Base": {
    "Extra": {
      "env": "prod",
      "user_extra": "{\"RPC_PERSIST_DYECP_FD_MOCK\":\"new_mock_<namespace>\",\"RPC_PERSIST_MOCK_TAG\":\"<namespace>\"}"
    }
  }
}
```

**说明**：
- 在 `Base.Extra.user_extra` 中放置一个 JSON 字符串
- 字符串中包含两个 key：
  - `RPC_PERSIST_DYECP_FD_MOCK`: 值为 `new_mock_<namespace>`
  - `RPC_PERSIST_MOCK_TAG`: 值为 `<namespace>`
- 注意 JSON 字符串中的双引号需要转义（用 `\"` 表示）

---

### Step 3：修改 Mock 数据

用户可以随时修改指定接口的 Mock 数据：

```bash
bam-cli api-mock \
  --act update-mock-data \
  --vregion <VREGION> \
  --psm <psm> \
  --input '{
    "namespace": "<namespace>",
    "psm": "<psm>",
    "method": "<method>",
    "mock_data": "<mock_data>"
  }'
```

**返回示例**：
```json
{
  "code": 0,
  "message": "suc",
  "data": "ok"
}
```

---

### Step 4：查看 Mock 数据

用户可以随时查看当前接口的 Mock 配置和数据：

```bash
bam-cli api-mock \
  --act query-mock-detail \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>",
    "psm": "<psm>",
    "method": "<method>"
  }'
```

**返回示例**：
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "namespace": "ai_agent_skill_uciuo8",
        "psm": "env.t.rpc",
        "method": "Ping",
        "mock_data": "{\"code\":0,\"message\":\"success\"}",
        "protocol": "thrift",
        "status": 1,
        "idl_info": "master"
      }
    ],
    "page": 0,
    "page_size": 100,
    "total": 1
  },
  "message": ""
}
```

---

### Step 5：开启/关闭 Mock 开关

当用户暂时不需要 Mock 某个接口时，可以关闭 Mock；需要时再开启：

```bash
bam-cli api-mock \
  --act update-mock-switch \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>",
    "psm": "<psm>",
    "method": "<method>",
    "enable": <true|false>
  }'
```

**返回示例**：
```json
{
  "data": {
    "namespace": "ai_agent_skill_two7th",
    "psm": "env.t.rpc",
    "method": "Ping",
    "enable": true
  }
}
```

---

### Step 6：删除 Mock 服务

测试完成后，用户可以删除 Mock 配置：

**删除整个 Mock 空间（namespace 必填）**：
```bash
bam-cli api-mock \
  --act delete-mock \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>"
  }'
```

**删除空间下的某个具体接口（namespace 必填，psm 和 method 选填）**：
```bash
bam-cli api-mock \
  --act delete-mock \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>",
    "psm": "<psm>",
    "method": "<method>"
  }'
```

---

## 上下文信息记录

在整个 Mock 配置流程中，以下信息需要记录并在后续步骤中使用：

| 变量 | 说明 | 来源 |
|------|------|------|
| `<namespace>` | Mock 空间名 | Step 2 创建返回 |
| `<psm>` | 服务 PSM | Step 1 用户提供 |
| `<method>` | 接口方法名 | Step 1 用户提供 |

---

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| Mock 服务创建失败 | 检查 PSM、method 是否正确，确认 namespace 是否有效 |
| Mock 数据格式错误 | 提示用户 Mock data 必须为有效的 JSON 格式 |
| 接口未找到 | 检查 namespace、psm、method 是否匹配 |
| 权限不足 | 提示用户确认是否具有该 namespace 的操作权限 |
| 删除失败 | 确认 namespace 是否存在，或是否有正在运行的 Mock 任务 |

---

## 快速模式命令速查

| 操作             | 命令 |
|----------------|------|
| 创建 Mock 服务     | `create-mock-service` |
| 修改 Mock 数据     | `update-mock-data` |
| 查看 Mock 数据     | `query-mock-detail` |
| 开启/关闭 Mock     | `update-mock-switch` |
| 删除 Mock        | `delete-mock` |
