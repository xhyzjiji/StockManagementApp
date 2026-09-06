# Mock 工具集

## 概述

Mock 工具集提供独立调用的单个 Mock 操作工具，用户可按需调用特定功能。

**协议支持**：RPC + HTTP

**流量牵引模式**：流量标识 + 泳道标识

---

## 调用指南

### 环境标识 + RPC 协议

确保请求调用链在当前泳道，且调用方开启 Mesh RPC 出流量代理即可。若未进入泳道，可选择以下方式之一：

**方式 1：请求链路入口 HTTP 服务时带上 header**
- `x-tt-env: {当前泳道名}`

**方式 2：修改任一上游的代码，显式注入 Env 标记并透传给下游（以 Golang 为例）**
```go
ctx = kitexutil.NewCtxWithEnv(ctx, "{当前泳道名}")
```

### 环境标识 + HTTP 协议

**方式 1：使用真实业务域名**
- 在 "分流配置" 模块配置真实域名的分流配置（仅支持 boe 和 i18n-tt）
- 业务调用时，HTTP 请求需带上 header：
  - `x-tt-env: {当前泳道名}`
  - `x-use-boe: 1`

**方式 2：使用 Mock 提供的域名调用**
- 直接调用 Mock 平台提供的 Mock URL

### 流量标识 + RPC 协议

确保请求调用链携带流量标识，且调用方开启 Mesh RPC 出流量代理即可。可选择以下方式之一注入标识：

**方式 1：请求入口 HTTP 服务时带上以下 2 个 header**
- `Rpc-Persist-Dyecp-Fd-Mock: {当前 dyeing value}`
- `Rpc-Persist-Mock-Tag: {当前分组 name}`

**方式 2：修改任一上游的代码，显式注入流量标记，并透传给下游（以 Golang 为例）**
```go
ctx = metainfo.WithPersistentValue(ctx, "DYECP_FD_MOCK", "{当前 dyeing value}")
ctx = metainfo.WithPersistentValue(ctx, "MOCK_TAG", "{当前分组 name}")
```

**方式 3：通过接口测试工具调用**
请带上如下 RPC Header（选择 persistent type）：
- `DYECP_FD_MOCK: {当前 dyeing value}`
- `MOCK_TAG: {当前分组 name}`

**方式 4：接口测试工具 RPC Body 注入**
通过接口测试工具调用 RPC 接口时，也可以在请求 Body 的 `Base.Extra.user_extra` 字段中携带 Mock 标识：
```json
{
  "ItemIds": [
    7278951327475158316
  ],
  "Base": {
    "Extra": {
      "env": "prod",
      "user_extra": "{\"RPC_PERSIST_DYECP_FD_MOCK\":\"{当前 dyeing value}\",\"RPC_PERSIST_MOCK_TAG\":\"{当前分组 name}\"}"
    }
  }
}
```
**说明**：
- 在 `Base.Extra.user_extra` 中放置一个 JSON 字符串
- 字符串中包含两个 key：
  - `RPC_PERSIST_DYECP_FD_MOCK`：值为 `{当前 dyeing value}`
  - `RPC_PERSIST_MOCK_TAG`：值为 `{当前分组 name}`
- 注意 JSON 字符串中的双引号需要转义（用 `"` 表示）

### 流量标识 + HTTP 协议

只能使用 Mock 域名调用。

---

## 工具列表

### 1. 命名空间管理

#### 1.1 创建命名空间

**命令**：`create-namespace`

**功能**：创建 Mock 命名空间

```bash
bam-cli api-mock \
  --act create-namespace \
  --vregion <VREGION> \
  --input '{
    "namespace_name": "<namespace_name>",
    "flow_mode": "<flow_mode>",
    "name": "<name>"
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace_name` | 是 | 命名空间中文名称 |
| `flow_mode` | 否 | 流量模式 |
| `name` | 否 | 命名空间名称 |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "id": "123456",
    "name": "ai_agent_mock_xxx"
  }
}
```

#### 1.2 删除命名空间

**命令**：`delete-namespace`

**功能**：删除 Mock 命名空间

```bash
bam-cli api-mock \
  --act delete-namespace \
  --vregion <VREGION> \
  --input '{
    "id": "<namespace_id>"
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 命名空间 ID |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

#### 1.3 获取命名空间列表

**命令**：`get-namespaces`

**功能**：获取 Mock 命名空间列表

```bash
bam-cli api-mock \
  --act get-namespaces \
  --vregion <VREGION> \
  --input '{
    "chinese_name": "<chinese_name>",
    "keyword": "<keyword>",
    "namespace": "<namespace>",
    "psm": "<psm>",
    "page": <page>,
    "page_size": <page_size>
  }'
```

| 参数 | 必填 | 说明 | 默认值 |
|------|------|------|--------|
| `chinese_name` | 否 | 按中文名精确搜索 | "" |
| `keyword` | 否 | 搜索关键词 | "" |
| `namespace` | 否 | 命名空间名称 | "" |
| `psm` | 否 | 服务 PSM | "" |
| `page` | 否 | 页码 | 1 |
| `page_size` | 否 | 每页大小 | 10 |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "items": [
      {
        "id": "c7cbddf3-1058-4fff-be93-32d9f400c4dc",
        "name": "ai_agent_test_namespace_1",
        "chinese_name": "ai_agent_test_namespace",
        "description": "",
        "subscription": true,
        "is_boe_env": false,
        "is_ppe_env": true,
        "scope": "public",
        "create_user": "biannayun",
        "feature_id": 0,
        "source": "new_mock",
        "flow_mode": "tag",
        "is_default_namespace": false
      }
    ],
    "page": 1,
    "page_size": 10,
    "total": 35
  }
}
```

### 2. 规则管理

#### 2.1 创建规则

**命令**：`create-rule`

**功能**：创建 Mock 规则

```bash
bam-cli api-mock \
  --act create-rule \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>",
    "endpoint_id": <endpoint_id>,
    "method": "<method>",
    "protocol": "<protocol>",
    "name": "<name>",
    "mock_data": "<mock_data>",
    "mode": "<mode>",
    "sub_mode": "<sub_mode>",
    "delay": <delay>,
    "description": "<description>",
    "encoding": "<encoding>",
    "filter_type": "<filter_type>",
    "callee_psm": "<callee_psm>",
    "caller_psm": "<caller_psm>",
    "global_vars": [],
    "header_filter": []
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 是 | 命名空间名称 |
| `endpoint_id` | 是 | 端点 ID |
| `method` | 是 | 方法名 |
| `protocol` | 是 | 协议 |
| `name` | 是 | 规则名称 |
| `mock_data` | 否 | Mock 数据 |
| `mode` | 否 | 模式 |
| `sub_mode` | 否 | 子模式 |
| `delay` | 否 | 延迟时间 |
| `description` | 否 | 描述 |
| `encoding` | 否 | 编码 |
| `filter_type` | 否 | 过滤类型 |
| `callee_psm` | 否 | 被调用方 PSM |
| `caller_psm` | 否 | 调用方 PSM |
| `global_vars` | 否 | 全局变量 |
| `header_filter` | 否 | 头部过滤器 |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "id": 123456,
    "sub_id": "sub_123456"
  }
}
```

#### 2.2 更新规则

**命令**：`update-rule`

**功能**：更新 Mock 规则

```bash
bam-cli api-mock \
  --act update-rule \
  --vregion <VREGION> \
  --input '{
    "id": <rule_id>,
    "namespace": "<namespace>",
    "name": "<name>",
    "mock_data": "<mock_data>",
    "mode": "<mode>",
    "sub_mode": "<sub_mode>",
    "delay": <delay>,
    "description": "<description>",
    "encoding": "<encoding>",
    "filter_type": "<filter_type>",
    "callee_psm": "<callee_psm>",
    "caller_psm": "<caller_psm>",
    "global_vars": [],
    "header_filter": []
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 规则 ID |
| `namespace` | 是 | 命名空间名称 |
| `name` | 否 | 规则名称 |
| `mock_data` | 否 | Mock 数据 |
| `mode` | 否 | 模式 |
| `sub_mode` | 否 | 子模式 |
| `delay` | 否 | 延迟时间 |
| `description` | 否 | 描述 |
| `encoding` | 否 | 编码 |
| `filter_type` | 否 | 过滤类型 |
| `callee_psm` | 否 | 被调用方 PSM |
| `caller_psm` | 否 | 调用方 PSM |
| `global_vars` | 否 | 全局变量 |
| `header_filter` | 否 | 头部过滤器 |

**返回示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": null
}
```

#### 2.3 获取规则详情

**命令**：`get-rule-by-id`

**功能**：获取 Mock 规则详情

```bash
bam-cli api-mock \
  --act get-rule-by-id \
  --vregion <VREGION> \
  --input '{
    "id": <rule_id>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 规则 ID |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "id": 6111099,
    "name": "测试规则",
    "description": "测试规则描述",
    "caller_psm": "*",
    "caller_cluster": "",
    "callee_psm": "bytedance.bits.workitem",
    "callee_cluster": "",
    "method": "QueryPageViewWithIdentity",
    "namespace": "ppe_test_keel_1",
    "mode": "json",
    "sub_mode": "default_json",
    "delay": 1,
    "mock_data": "{\"code\":0,\"data\":{}}",
    "status": 1,
    "protocol": "thrift"
  }
}
```

#### 2.4 查询规则列表

**命令**：`query-rules`

**功能**：查询 Mock 规则列表

```bash
bam-cli api-mock \
  --act query-rules \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>",
    "psm": "<psm>",
    "method": "<method>",
    "page": <page>,
    "page_size": <page_size>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 是 | 命名空间名称 |
| `psm` | 是 | 服务 PSM |
| `method` | 否 | 方法名 |
| `page` | 否 | 页码 |
| `page_size` | 否 | 每页大小 |

**返回示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 123456,
        "name": "测试规则",
        "description": "测试规则描述",
        "caller_psm": "*",
        "callee_psm": "env.t.rpc",
        "method": "GetItem",
        "namespace": "ai_agent_skill_xxx",
        "mode": "json",
        "status": 1,
        "protocol": "thrift"
      }
    ],
    "page": 1,
    "page_size": 100,
    "total": 1
  }
}
```

#### 2.5 启用规则

**命令**：`enable-rule`

**功能**：启用 Mock 规则

```bash
bam-cli api-mock \
  --act enable-rule \
  --vregion <VREGION> \
  --input '{
    "id": <rule_id>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 规则 ID |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

#### 2.6 禁用规则

**命令**：`disable-rule`

**功能**：禁用 Mock 规则

```bash
bam-cli api-mock \
  --act disable-rule \
  --vregion <VREGION> \
  --input '{
    "id": <rule_id>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 规则 ID |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

#### 2.7 删除规则

**命令**：`delete-rule-by-id`

**功能**：删除 Mock 规则

```bash
bam-cli api-mock \
  --act delete-rule-by-id \
  --vregion <VREGION> \
  --input '{
    "id": <rule_id>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 规则 ID |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

### 3. 服务管理

#### 3.1 列出服务

**命令**：`list-service`

**功能**：列出 Mock 服务

```bash
bam-cli api-mock \
  --act list-service \
  --vregion <VREGION> \
  --input '{
    "is_default_namespace": <is_default_namespace>,
    "is_subscribed": <is_subscribed>,
    "keyword": "<keyword>",
    "namespace": "<namespace>",
    "page": <page>,
    "page_size": <page_size>,
    "protocol": "<protocol>",
    "psm": "<psm>"
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `is_default_namespace` | 否 | 是否默认命名空间 |
| `is_subscribed` | 否 | 是否订阅 |
| `keyword` | 否 | 关键词 |
| `namespace` | 否 | 命名空间 |
| `page` | 否 | 页码 |
| `page_size` | 否 | 每页大小 |
| `protocol` | 否 | 协议 |
| `psm` | 否 | PSM |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "items": [
      {
        "service_id": 123456,
        "psm": "env.t.rpc",
        "idl_version": "master",
        "idl_source": "git",
        "comment": "Test service",
        "namespace_chinese_name": "测试命名空间",
        "service_creator": "user",
        "namespace_name": "ai_agent_mock_xxx",
        "namespace_id": "123456",
        "flow_mode": "normal",
        "subscription": true,
        "idl_version_type": "branch",
        "protocol": "thrift",
        "scope": "public",
        "is_default_namespace": false,
        "templated": false,
        "template_group_id": 0,
        "template_apply_timestamp": ""
      }
    ],
    "page": 1,
    "page_size": 10,
    "total": 1
  }
}
```

#### 3.2 创建服务关系

**命令**：`create-service-relation`

**功能**：创建服务关系

```bash
bam-cli api-mock \
  --act create-service-relation \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>",
    "psm": "<psm>",
    "idl_version": "<idl_version>",
    "idl_source": "<idl_source>"
  }'
```

#### 3.3 更新服务

**命令**：`update-service`

**功能**：更新服务

```bash
bam-cli api-mock \
  --act update-service \
  --vregion <VREGION> \
  --input '{
    "id": "<namespace_id>",
    "downstream": "<service_psm>",
    "idl_version": "<idl_version>",
    "comment": "<comment>",
    "protocol": "<protocol>"
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 命名空间 ID |
| `downstream` | 是 | 服务 PSM |
| `idl_version` | 否 | IDL 版本 |
| `comment` | 否 | 描述信息 |
| `protocol` | 否 | 服务协议 |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

#### 3.4 删除服务

**命令**：`delete-service`

**功能**：删除服务

```bash
bam-cli api-mock \
  --act delete-service \
  --vregion <VREGION> \
  --input '{
    "id": "<namespace_id>",
    "downstream": "<service_psm>"
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 命名空间 ID |
| `downstream` | 是 | 服务 PSM |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

### 4. 染色管理

#### 4.1 创建/更新染色规则

**命令**：`put-flow-dyeing`

**功能**：创建或更新流量染色规则

```bash
bam-cli api-mock \
  --act put-flow-dyeing \
  --vregion <VREGION> \
  --input '{
    "callee": "<callee>",
    "callee_cluster": "<callee_cluster>",
    "caller": "<caller>",
    "caller_cluster": "<caller_cluster>",
    "method": "<method>",
    "dyeing": "<dyeing>",
    "dyeing_type": "<dyeing_type>",
    "expired_at": "<expired_at>",
    "is_valid": <is_valid>,
    "status": <status>,
    "type": "<type>",
    "is_rhino_around_mock": <is_rhino_around_mock>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `callee` | 是 | 被调用方 PSM |
| `callee_cluster` | 是 | 被调用方集群 |
| `caller` | 是 | 调用方 PSM |
| `caller_cluster` | 是 | 调用方集群 |
| `method` | 是 | 方法名 |
| `dyeing` | 是 | 染色标识，格式为 `ENV:boe_xxx`/`ENV:ppe_xxx` 或 `MOCK:new_mock_xx` |
| `dyeing_type` | 否 | 染色类型 |
| `expired_at` | 否 | 过期时间 |
| `is_valid` | 否 | 是否有效 |
| `status` | 否 | 状态 |
| `type` | 否 | 类型 |
| `is_rhino_around_mock` | 否 | 是否为 Rhino 环绕 Mock |

> ⚠️ **风险说明**：创建分流规则会将满足六元组 (caller, caller_cluster) -> (callee, callee_cluster, method, dyeing) 的流量牵引到 Mock 服务上，请谨慎操作。
> 
> 💡 **建议约束**：
> - 六元组尽量详细，少用 `*`
> 
> 🔒 **强制约束**：
> - `callee`、`dyeing` 禁止为空或者 `*`

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "id": 123456,
    "key": "dyeing_key_123"
  }
}
```

#### 4.2 删除染色规则

**命令**：`delete-flow-dyeing`

**功能**：删除流量染色规则

```bash
bam-cli api-mock \
  --act delete-flow-dyeing \
  --vregion <VREGION> \
  --input '{
    "id": <dyeing_id>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 染色规则 ID |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

#### 4.3 列出染色规则

**命令**：`list-flow-dyeing`

**功能**：列出流量染色规则

```bash
bam-cli api-mock \
  --act list-flow-dyeing \
  --vregion <VREGION> \
  --input '{
    "namespace": "<namespace>",
    "callee": "<callee>",
    "kind": "<kind>",
    "page": <page>,
    "page_size": <page_size>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 是 | 命名空间名称 |
| `callee` | 否 | 被调用方 PSM |
| `kind` | 否 | http 或 rpc |
| `page` | 否 | 页码 |
| `page_size` | 否 | 每页大小 |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": {
    "items": [
      {
        "namespace": "ppe_test_keel_1",
        "id": 439923,
        "caller": "*",
        "caller_cluster": "*",
        "callee": "bytedance.bits.workitem",
        "callee_cluster": "open_api_lark(Singapore-Central)",
        "method": "QueryPageViewWithIdentity",
        "dyeing": "ENV:ppe_test_keel_1",
        "is_valid": true,
        "expired_at": "2036-04-12T11:56:02+08:00",
        "type": "",
        "status": true
      }
    ],
    "page": 0,
    "page_size": 0,
    "total": 1
  }
}
```

#### 4.4 更新染色规则开关

**命令**：`update-flow-dyeing-switch`

**功能**：更新流量染色规则开关状态

```bash
bam-cli api-mock \
  --act update-flow-dyeing-switch \
  --vregion <VREGION> \
  --input '{
    "id": <dyeing_id>,
    "enable": <true|false>
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 染色规则 ID |
| `enable` | 是 | `true` 开启，`false` 关闭 |

**返回示例**：
```json
{
  "code": 0,
  "message": "",
  "data": null
}
```

### 5. 快速 Mock 操作

#### 5.1 创建 Mock 服务

**命令**：`create-mock-service`

**功能**：创建 Mock 服务，系统会自动创建 Mock 空间并配置分流

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

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 否 | Mock 空间名，不提供则自动生成 |
| `method` | 是 | 接口方法名 |
| `mock_data` | 是 | Mock 返回数据，必须为 JSON 格式字符串 |
| `idl_version` | 否 | IDL 版本，如 `master` |
| `idl_source` | 否 | IDL 来源 |
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

> **重要**：提取返回内容中的 `data.namespace` 作为后续请求中的 `<namespace>`。

#### 5.2 修改 Mock 数据

**命令**：`update-mock-data`

**功能**：修改指定接口的 Mock 返回数据

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

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 是 | Mock 空间名 |
| `psm` | 是 | 服务 PSM |
| `method` | 是 | 接口方法名 |
| `mock_data` | 是 | 新的 Mock 返回数据，JSON 格式 |

**返回示例**：
```json
{
  "code": 0,
  "message": "suc",
  "data": "ok"
}
```

#### 5.3 查看 Mock 数据

**命令**：`query-mock-detail`

**功能**：查询当前接口的 Mock 配置和数据

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

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 是 | Mock 空间名 |
| `psm` | 否 | 服务 PSM |
| `method` | 否 | 接口方法名 |

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

#### 5.4 开启/关闭 Mock 开关

**命令**：`update-mock-switch`

**功能**：启用或禁用 Mock 功能

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

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 是 | Mock 空间名 |
| `psm` | 否 | 服务 PSM |
| `method` | 否 | 接口方法名 |
| `enable` | 是 | `true` 启用，`false` 禁用 |

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

#### 5.5 删除 Mock

**命令**：`delete-mock`

**功能**：删除 Mock 配置，支持多种删除粒度

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

| 参数 | 必填 | 说明 |
|------|------|------|
| `namespace` | 是 | Mock 空间名 |
| `psm` | 否 | 服务 PSM |
| `method` | 否 | 接口方法名 |

---

## 错误处理

| 情况 | 处理方式 |
|------|----------|
| Mock 服务创建失败 | 检查 PSM、method 是否正确，确认 namespace 是否有效 |
| Mock 数据格式错误 | 提示用户 Mock data 必须为有效的 JSON 格式 |
| 接口未找到 | 检查 namespace、psm、method 是否匹配 |
| 权限不足 | 提示用户确认是否具有该 namespace 的操作权限 |
| 删除失败 | 确认 namespace 是否存在，或是否有正在运行的 Mock 任务 |
| 染色规则创建失败 | 检查染色标识格式是否正确（`ENV:boe_xxx`/`ENV:ppe_xxx` 或 `MOCK:new_mock_xx`） |
| 规则创建失败 | 检查必填参数是否完整（namespace、endpoint_id、method、protocol、name） |

---

## 命令速查

### 命名空间管理

| 操作 | 命令 | 说明 |
|------|------|------|
| 创建命名空间 | `create-namespace` | 创建 Mock 命名空间 |
| 获取命名空间列表 | `get-namespaces` | 获取 Mock 命名空间列表 |
| 删除命名空间 | `delete-namespace` | 删除 Mock 命名空间 |

### 规则管理

| 操作 | 命令 | 说明 |
|------|------|------|
| 创建规则 | `create-rule` | 创建 Mock 规则 |
| 更新规则 | `update-rule` | 更新 Mock 规则 |
| 获取规则详情 | `get-rule-by-id` | 获取 Mock 规则详情 |
| 查询规则列表 | `query-rules` | 查询 Mock 规则列表 |
| 启用规则 | `enable-rule` | 启用 Mock 规则 |
| 禁用规则 | `disable-rule` | 禁用 Mock 规则 |
| 删除规则 | `delete-rule-by-id` | 删除 Mock 规则 |

### 服务管理

| 操作 | 命令 | 说明 |
|------|------|------|
| 列出服务 | `list-service` | 列出 Mock 服务 |
| 创建服务关系 | `create-service-relation` | 创建服务关系 |
| 更新服务 | `update-service` | 更新服务 |
| 删除服务 | `delete-service` | 删除服务 |

### 染色管理

| 操作 | 命令 | 说明 |
|------|------|------|
| 创建/更新染色规则 | `put-flow-dyeing` | 创建或更新流量染色规则 |
| 删除染色规则 | `delete-flow-dyeing` | 删除流量染色规则 |
| 列出染色规则 | `list-flow-dyeing` | 列出流量染色规则 |
| 更新染色规则开关 | `update-flow-dyeing-switch` | 更新流量染色规则开关状态 |

### 快速 Mock

| 操作 | 命令 | 说明 |
|------|------|------|
| 创建 Mock 服务 | `create-mock-service` | 创建 Mock 服务（自动分流） |
| 修改 Mock 数据 | `update-mock-data` | 修改 Mock 返回数据 |
| 查看 Mock 数据 | `query-mock-detail` | 查询 Mock 配置和数据 |
| 开启/关闭 Mock | `update-mock-switch` | 启用或禁用 Mock |
| 删除 Mock | `delete-mock` | 删除 Mock 配置 |