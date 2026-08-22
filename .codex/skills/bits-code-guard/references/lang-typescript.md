# TypeScript / JavaScript 专项检测

本文档补充 TS/JS 及前端场景下较常见、但通用评审清单不易覆盖的语义缺陷。重点关注：异步、状态、接口契约、鉴权上下文。SQL 注入、硬编码凭据、null 解引用等跨语言通用问题仍以 `references/review-dimensions.md` 为准。

适用文件：`.ts` / `.tsx` / `.js` / `.jsx` / `.mjs` / `.cjs`。

## 目录

- API / Response semantics：响应语义
- UI state transition：UI 状态一致性
- Async / closure / race：异步闭包与竞态
- Mapping / DTO semantics：字段映射与可空语义
- Context / auth：鉴权与上下文

---

## API / Response semantics — 响应语义

HTTP 成功不等于业务成功。`await` / `.then` 只说明请求层完成，调用侧仍需按项目约定检查业务字段，如 `code`、`success`、`statusCode`、`errno`。

```ts
const resp = await api.submit(payload)
if (resp.code !== 0) {
    toast.error(resp.message)
    return
}
toast.success('提交成功')
navigate('/success')
```

检查要点：
- 成功路径是否显式判断业务成功，而不是只依赖 `try/catch`
- 错误分支是否 `return` / `throw`，避免继续执行跳转、清表单、关闭弹窗、成功埋点等副作用
- 使用原生 `fetch` 时是否检查 `response.ok` / `response.status`
- 请求封装或拦截器对业务失败的约定是 resolve 还是 reject，调用侧是否与该约定一致

---

## UI state transition — UI 状态一致性

请求结果应与 UI 状态一致。失败态不应触发成功副作用，`loading`、`success`、`error`、`data` 等状态应在每条路径上收敛。

```ts
setLoading(true)
try {
    const data = await api.load()
    setData(data)
    setError(null)
} catch (e) {
    setError(e)
    setData(null)
} finally {
    setLoading(false)
}
```

检查要点：
- 关闭弹窗、跳转、清表单、成功 toast 是否只在成功分支执行
- `finally` 是否只放 loading 复位、资源清理等无条件动作
- 成功分支是否清理旧 error，失败分支是否避免残留旧 data / success
- 乐观更新失败时是否回滚，并用服务端返回的真实 id / 状态校正占位数据
- 提交、支付、创建、发消息等非幂等操作是否有 loading / disabled / 防抖锁，避免重复请求

---

## Async / closure / race — 异步闭包与竞态

异步回调会捕获创建时的变量快照。React/Vue hooks、事件监听、定时器、Promise、WebSocket、轮询等场景都要确认不会读旧值、覆盖并发更新、卸载后更新状态或让过期请求覆盖新视图。

```ts
setCount(count + 1)
setTimeout(() => {
    setCount(prev => prev + 1)
}, 1000)
```

检查要点：
- 异步回调、事件订阅、定时器、`Promise.then` 中读取的 state 是否可能是发起时的旧值；需要最新值时是否使用 functional updater（如 `setX(prev => ...)`）或 ref
- 多个异步分支更新同一对象/列表时，是否避免用旧闭包里的对象直接 spread 覆盖，改用 `setX(prev => ...)`
- `useEffect` / `useCallback` 的依赖数组是否包含函数体实际读取的 state、props、context、自定义 hook 返回值；禁用依赖检查时是否有明确理由
- 定时器、订阅、事件监听、请求是否在 cleanup 中取消或解绑，避免组件卸载后仍 setState
- 搜索、分页、tab、筛选、身份切换等触发的请求是否用 `AbortController`、requestId 或发起参数校验，避免旧响应覆盖新状态

---

## Mapping / DTO semantics — 字段映射与可空语义

类型声明不能替代运行时契约。接口层级、字段名、命名风格、必填/可选/可空语义要与后端契约一致，尤其要警惕 `as`、`!`、`any` 掩盖真实数据不匹配。

```ts
const list = resp.data?.items ?? []
const pageSize = query.size ?? 10
```

检查要点：
- 响应层级是否取对，如 `resp.data.items`、`resp.list`、`resp.data.data.records`
- 字段名和风格是否匹配契约，如 `userId` / `user_id` / `userID`、`list` / `items` / `records`
- request payload 是否漏传必填字段、错传字段名，或直接 spread 表单导致多余字段穿透
- `||` 是否误用于合法 falsy 值（`0`、`''`、`false`），需要默认值时优先确认是否应使用 `??`
- 可空字段、列表字段、嵌套对象是否在使用前用 `?.`、`??` 或显式校验处理
- `!` 是否只用于已显式判空后的值；外部输入、URL query、localStorage、接口返回不应直接非空断言
- `as` / `as unknown as T` 是否伴随字段存在性校验、类型守卫、schema 校验或可信契约来源

---

## Context / auth — 鉴权与上下文

前端鉴权和上下文问题常出现在“没走统一封装”“读写 token 来源不一致”“身份切换后仍使用旧上下文”“401 回退不完整”。

```ts
const { tenantId } = useTenant()
const fetchList = useCallback(() => {
    return api.list({ tenantId })
}, [tenantId])
```

检查要点：
- 新增请求是否走统一 request 封装，或正确携带 token / cookie / `credentials`
- 多个请求实例是否都配置了相同的鉴权、错误处理和凭证刷新逻辑
- token 的读写来源是否一致；登出、切换账号时是否清理所有相关存储和用户 context
- 401 / 403 是否清理本地鉴权态并进入统一未授权处理；需要登录回跳的场景是否保留来源路径
- 刷新凭证失败是否进入统一未授权处理，避免重复刷新或死循环；并发未授权响应是否有去重策略
- `useCallback` / hook / 模块级请求函数是否捕获了旧的 user / account / tenant / locale / role；上下文切换后在途请求是否取消或在落地前校验身份仍一致
- token、手机号、身份证、邮箱、完整 payload / headers 是否被打印到 console、埋点、错误监控或前端日志
