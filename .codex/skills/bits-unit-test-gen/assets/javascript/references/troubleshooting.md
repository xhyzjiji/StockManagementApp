# 错误诊断与修复策略

本文档汇总测试验证过程中常见的错误模式及对应修复方案。当测试运行、tsc 类型检查或 lint 检查输出错误时，可按照以下分类定位问题根因并修复。

## 模块解析错误

### `[HINT:MODULE_RESOLUTION]`
**现象**：`Cannot find module 'xxx' from 'source.ts'`（错误来自源文件而非测试文件）

**根因**：源文件依赖路径别名（如 `@/utils`），但 Jest/Vitest 的 moduleNameMapper 中未配置对应映射。

**修复**：
```ts
// 对所有不可解析的源文件 import 使用 virtual mock
jest.mock('@/utils/helper', () => ({}), { virtual: true });
```

## 测试路径问题

### `[HINT:PATH_IGNORED]`
**现象**：`No tests found` + 输出中提到 `testPathIgnorePatterns`

**根因**：测试文件路径被 `testPathIgnorePatterns` 排除。

**修复**：删除测试文件，在不被排除的路径下重新创建，然后用新路径继续验证。

### `[HINT:PATH_MISMATCH]`
**现象**：`No tests found` + 输出中提到 `testRegex` / `testMatch`

**根因**：测试文件路径不匹配 jest 配置中的 testRegex/testMatch 模式。

**修复**：读取 jest 配置获取正确的 testRegex/testMatch 模式，删除测试文件并在匹配路径下重新创建。

### `[HINT:NO_TESTS_FOUND]`
**现象**：`No tests found`（无更具体的信息）

**修复**：检查框架配置中的 testMatch/testRegex/include 模式，将测试文件移到匹配路径。

## Babel 相关错误

### `[HINT:BABEL]`
**现象**：jest.mock 工厂中出现 `SyntaxError: Unexpected token, expected ","` 或 `Missing semicolon`

**根因**：Babel 无法解析 TypeScript 类型注解。jest.mock 工厂函数被 Babel 单独提升解析，不经过 TS 转译。

**修复**：
- 从 jest.mock() 工厂中移除所有类型注解
- 使用 `(x) =>` 而非 `(x: string) =>`
- 移除 `as` 断言和 `: Type` 标注

### `[HINT:BABEL]` (import type)
**现象**：`SyntaxError` at `import type` 语句

**修复**：将所有 `import type { X }` 替换为 `import { X }`，移除内联 `type` 关键字。

### `[HINT:BABEL]` (JSX confusion)
**现象**：`Unexpected token. Did you mean {'>'}`

**根因**：Babel 将 TypeScript 泛型调用 `func<T>()` 误解析为 JSX 标签。

**修复**：避免泛型调用语法，使用 `(create as any)()` 代替 `create<MyType>()`。

### `[HINT:BABEL]` (experimental syntax)
**现象**：`Support for the experimental syntax 'xxx' isn't currently enabled`

**修复**：对于 JSX，使用 `.tsx` 扩展名；将 JSX 从 jest.mock 工厂中移出（使用 `require('react').createElement` 替代）。

### `[HINT:BABEL_SOURCE_SYNTAX]`
**现象**：源文件（非测试文件）出现 Babel 语法错误

**修复**：`jest.mock()` 整个模块或使用 `jest.createMockFromModule()`。

### `[HINT:BABEL_IMPORT]`
**现象**：源文件使用 ES module import 导致 `Cannot use import statement outside a module`

**修复**：
```ts
jest.mock('./source-file', () => ({ /* mock exports */ }));
```

### `[HINT:BABEL_TSC_CONFLICT]`
**现象**：tsc 报告 `TS7006`/`TS7031`/`TS7005` 等 implicit-any 错误，但项目使用 Babel 转换

**根因**：修复 tsc 需要加类型注解 → Babel 不支持类型注解 → 形成恶性循环。

**冲突错误码**：TS7006、TS7031、TS7005、TS7019、TS7034、TS2683

**修复**：在报错行上方添加 `// @ts-expect-error` 或 `// @ts-ignore`，不要添加类型注解。

## 环境问题

### `[HINT:JSDOM_ENV]`
**现象**：setupTests 中出现 `ReferenceError: window is not defined` 或 `document is not defined`

**修复**：在测试文件顶部添加 `/** @jest-environment jsdom */`。

### `[HINT:READONLY_GLOBAL]`
**现象**：`Cannot assign to read only property` on `object '[object Window]'`

**根因**：jsdom 中 `window.performance` 等属性是只读的。

**修复**：
```ts
Object.defineProperty(window, 'xxx', { value: mock, writable: true });
// 或
jest.spyOn(window, 'xxx', 'get').mockReturnValue(mock);
```

## Mock 问题

### `[HINT:MOCK_HOISTING]`
**现象**：`ReferenceError: Cannot access 'mockXxx' before initialization`

**根因**：jest.mock() 工厂被提升到文件顶部，在 let/const 声明之前执行（暂时性死区）。

**修复**：
```ts
// ❌ 错误：在工厂外声明变量
let mockFn = jest.fn();
jest.mock('./mod', () => ({ fn: mockFn })); // ReferenceError!

// ✅ 正确：在工厂内定义，通过 requireMock 获取引用
jest.mock('./mod', () => ({ fn: jest.fn() }));
const { fn: mockFn } = jest.requireMock('./mod');
```

### `[HINT:I18N_MOCK]`
**现象**：i18n 函数 `is not a function`

**修复**：为 i18n 模块添加 jest.mock，使用 Proxy-based stub。

## TypeScript 编译问题

### `[HINT:TS_DIAGNOSTICS]`
**现象**：`Test suite failed to run` + 源文件（非测试文件）报告 TS 编译错误

**说明**：可尝试禁用 ts-jest diagnostics（在 jest 配置中设置 `diagnostics: false`）后重试。此类错误通常来自源文件本身的类型问题，应关注测试逻辑错误而非源文件类型错误。

## 不可恢复错误

### 测试超时（不可恢复）
**现象**：测试命令超时退出或长时间无响应

**根因**：测试死锁、无限循环或依赖外部未启动的服务。

**建议**：
1. 验证测试不依赖真实网络连接或服务
2. Mock 所有异步操作（WebSocket、HTTP、timers）并使用 `jest.useFakeTimers()` + 适当 cleanup
3. 确保所有 Promise 在测试内 resolve/reject
4. 检查是否缺少 `jest.fn()` 导致回调阻塞执行
