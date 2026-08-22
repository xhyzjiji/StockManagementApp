# Vitest 框架知识

## 概述

Vitest 是一个基于 Vite 的测试框架，API 兼容 Jest，内置 TypeScript / ESM / JSX 支持，无需额外配置转换器。使用 `vi` 对象进行 mock 操作。

## 常见问题

### 与 Jest 的主要差异

1. **导入方式不同**：Vitest 需要显式从 `vitest` 导入 API
```ts
import { describe, it, expect, vi } from 'vitest';
```

2. **Mock 函数**：使用 `vi` 而非 `jest`
```ts
// Jest
jest.fn()
jest.mock('./module')
jest.spyOn(obj, 'method')

// Vitest
vi.fn()
vi.mock('./module')
vi.spyOn(obj, 'method')
```

3. **定时器**：
```ts
// Jest
jest.useFakeTimers()
jest.advanceTimersByTime(1000)
jest.setSystemTime(new Date('2024-01-01'))
jest.useRealTimers()

// Vitest
vi.useFakeTimers()
vi.advanceTimersByTime(1000)
vi.setSystemTime(new Date('2024-01-01'))
vi.useRealTimers()
```

4. **超时设置**：
```ts
// Jest
jest.setTimeout(5_000)

// Vitest
vi.setConfig({ testTimeout: 5_000 })
```

### 模块 Mock

#### `vi.mock` — 提升式模块 Mock

`vi.mock` 会被**提升到文件顶部**执行，无论写在哪里。factory 内部**不能引用外部变量**（除非用 `vi.hoisted`）。

```ts
import { vi } from 'vitest';

vi.mock('./api', () => ({
  fetchUser: vi.fn().mockResolvedValue({ id: 1, name: 'test' }),
}));
```

推荐使用动态 import 语法获得更好的类型支持：
```ts
vi.mock(import('./api'), () => ({
  fetchUser: vi.fn().mockResolvedValue({ id: 1 }),
}));
```

#### 部分 Mock — 使用 `importOriginal`

factory 接收 `importOriginal` 函数获取原始模块，实现部分 mock：
```ts
vi.mock(import('./utils'), async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...original,
    formatDate: vi.fn().mockReturnValue('2024-01-01'),
  };
});
```

Jest 的 `jest.requireActual` 在 Vitest 中对应 `vi.importActual`（或 factory 中的 `importOriginal`）：
```ts
vi.mock('./utils', async () => {
  const originalModule = await vi.importActual('./utils');
  return { ...originalModule, get: vi.fn() };
});
```

#### 自动 Mock

仅传路径不提供 factory 时，如果存在 `__mocks__` 目录下的同名文件则使用它，否则自动替换所有导出：
```ts
vi.mock('./example'); // 查找 __mocks__/example.js 或自动 mock
```

自动 mock 算法：所有方法返回 `undefined`，所有数组变为空，原始值保持不变。

#### `vi.mock` + `{ spy: true }` — Spy 模式

保留原始实现但追踪调用：
```ts
vi.mock(import('./calculator'), { spy: true });

expect(calculator(1, 2)).toBe(3);
expect(calculator).toHaveBeenCalledWith(1, 2);
```

#### `vi.doMock` — 非提升式 Mock

不会被提升，可以引用外部变量，但只对后续的动态 import 生效：
```ts
vi.doMock('./increment', () => ({ increment: () => 100 }));
const { increment } = await import('./increment');
expect(increment()).toBe(100);
```

#### `vi.hoisted` — 在 import 之前执行代码

允许在 `vi.mock` factory 中引用变量：
```ts
const mocks = vi.hoisted(() => ({
  namedExport: vi.fn(),
}));

vi.mock('./module', () => ({
  namedExport: mocks.namedExport,
}));
```

#### Mock 默认导出注意事项

mock 含默认导出的模块时，需要提供 `default` key：
```ts
vi.mock('./module', () => ({
  default: { myDefaultKey: vi.fn() },
  namedExport: vi.fn(),
}));
```

#### ⚠️ 同文件函数 Mock 限制

无法 mock 模块内部函数之间的互相调用。如 `foobar()` 内部调用 `foo()`，mock `foo` 不会影响 `foobar` 内部的 `foo` 调用——因为内部引用的是原始绑定。

### Mock 函数与对象

#### `vi.fn` — 创建 Mock 函数
```ts
const getApples = vi.fn(() => 0);
getApples.mockReturnValueOnce(5);
expect(getApples()).toBe(5);
```

#### `vi.spyOn` — 监视对象方法
```ts
const spy = vi.spyOn(cart, 'getApples').mockImplementation(() => apples);
expect(spy).toHaveBeenCalled();
```

注意 `vi.spyOn` 仅追踪**调用后**的方法调用。import 时已执行的顶层代码无法被追踪。

#### `vi.mocked` — TypeScript 类型辅助
```ts
import * as example from './example';
vi.mock('./example');
vi.mocked(example.add).mockReturnValue(10);
// 支持 partial 和 deep 选项
vi.mocked(example.getUser, { partial: true, deep: true }).mockReturnValue({
  address: { city: 'LA' },
});
```

#### `vi.mockObject` — 深度 Mock 对象

对一个已有对象进行深度 mock，将所有方法替换为 mock 函数，同时保留原始值属性。嵌套对象中的方法也会被递归 mock。

```ts
const original = {
  prop: 'foo',
  simple: () => 'real',
  nested: {
    method: () => 'real nested',
    value: 42,
  },
};

const mocked = vi.mockObject(original);
expect(mocked.simple()).toBe(undefined);
expect(mocked.nested.method()).toBe(undefined);
expect(mocked.prop).toBe('foo');
expect(mocked.nested.value).toBe(42);

mocked.simple.mockReturnValue('mocked');
mocked.nested.method.mockReturnValue('mocked nested');
expect(mocked.simple()).toBe('mocked');
expect(mocked.nested.method()).toBe('mocked nested');
```

使用 `{ spy: true }` 选项保留原始实现，同时追踪调用：
```ts
const spied = vi.mockObject(original, { spy: true });
expect(spied.simple()).toBe('real');
expect(spied.simple).toHaveBeenCalledTimes(1);
```

与 `vi.fn()` / `vi.spyOn()` 的区别：`vi.mockObject` 适合一次性将整个对象（包括深层嵌套属性）全部 mock 化，无需逐一 `spyOn` 每个方法。

#### `vi.isMockFunction` — 判断是否为 Mock
```ts
vi.isMockFunction(fn); // boolean + 类型收窄
```

### Mock 清理

三个清理函数的区别：

| 方法 | 作用 |
|---|---|
| `vi.clearAllMocks()` | 清除调用记录（`.mock.calls`、`.mock.results`），**不影响**实现 |
| `vi.resetAllMocks()` | 清除调用记录 **+** 重置实现 |
| `vi.restoreAllMocks()` | 恢复 `vi.spyOn` 的原始实现（**不影响**自动 mock 模块） |

推荐在 `afterEach` 中清理，或使用配置项自动清理：
```ts
afterEach(() => {
  vi.restoreAllMocks();
});
```

配置项等价写法（`vitest.config.ts`）：
```ts
test: {
  clearMocks: true,    // 等同于 vi.clearAllMocks()
  resetMocks: true,    // 等同于 vi.resetAllMocks()
  restoreMocks: true,  // 等同于 vi.restoreAllMocks()
}
```

### 环境变量与全局变量 Mock

```ts
// Mock 环境变量
vi.stubEnv('NODE_ENV', 'production');
// process.env.NODE_ENV === 'production'
// import.meta.env.NODE_ENV === 'production'

// Mock 全局变量
vi.stubGlobal('innerWidth', 100);
// globalThis.innerWidth === 100

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
```

### 异步等待工具

#### `vi.waitFor` — 等待回调成功执行

重复执行回调直到不再抛出错误为止。支持异步回调。可选参数 `timeout`（默认 1000ms）和 `interval`（默认 20ms）。

```ts
await vi.waitFor(() => {
  if (!server.isReady) throw new Error('Server not started');
}, { timeout: 500, interval: 20 });
```

支持异步回调与断言组合使用：
```ts
await vi.waitFor(async () => {
  const response = await fetch('/api/status');
  const data = await response.json();
  expect(data.status).toBe('ready');
});
```

注意：如果启用了 `vi.useFakeTimers`，`vi.waitFor` 会自动在每次检查中调用 `vi.advanceTimersByTime(interval)`，因此可以与 fake timers 无缝配合：
```ts
vi.useFakeTimers();

const start = Date.now();
setTimeout(() => { state.ready = true; }, 300);

await vi.waitFor(() => {
  expect(state.ready).toBe(true);
});
```

如果回调始终抛出错误直到超时，`vi.waitFor` 会抛出最后一次回调中的错误。

#### `vi.waitUntil` — 等待条件为 truthy

与 `vi.waitFor` 类似，但基于返回值判断——重复执行回调直到返回 truthy 值，并将该值作为 Promise 结果返回。适合需要获取异步产生的值的场景：

```ts
const element = await vi.waitUntil(
  () => document.querySelector('.element'),
  { timeout: 500, interval: 20 }
);
expect(element.textContent).toBe('Hello');
```

`vi.waitFor` 与 `vi.waitUntil` 的区别：
| | `vi.waitFor` | `vi.waitUntil` |
|---|---|---|
| 判定条件 | 回调不抛错即成功 | 回调返回 truthy 值即成功 |
| 返回值 | 回调的返回值（通常为 void） | 回调返回的 truthy 值（带类型推断） |
| 适用场景 | 配合 `expect` 断言 | 需要获取异步产生的值 |

#### `expect.poll` — 轮询断言（替代方案）

Vitest 还提供 `expect.poll` 作为轮询断言的语法糖，与 `vi.waitFor` 功能类似但写法更简洁：
```ts
await expect.poll(() => fetchStatus()).toBe('ready');
await expect.poll(() => document.querySelector('.el'), {
  timeout: 1000,
  interval: 50,
}).not.toBeNull();
```

注意：`expect.poll` 目前不支持与 `vi.useFakeTimers` 搭配使用。

### 配置文件

Vitest 使用 `vitest.config.ts`（或复用 `vite.config.ts` 中的 `test` 字段）：

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node', // 或 'jsdom', 'happy-dom', 'edge-runtime'
    globals: true,        // 允许不显式 import describe/it/expect
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./vitest.setup.ts'],
  },
});
```

如果已有 `vite.config.ts`，可通过 `/// <reference types="vitest/config" />` 直接在其中添加 `test` 字段：
```ts
/// <reference types="vitest/config" />
import { defineConfig } from 'vite';

export default defineConfig({
  test: { /* ... */ },
});
```

独立 `vitest.config.ts` 可通过 `mergeConfig` 复用已有 Vite 配置：
```ts
import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default mergeConfig(viteConfig, defineConfig({
  test: { exclude: ['packages/template/*'] },
}));
```

### No tests found

- 检查 `include` 配置的文件匹配模式
- 确认测试文件后缀与配置的 `include` 模式一致
- 如果使用 `globals: true`，确保 `tsconfig.json` 中包含 `"types": ["vitest/globals"]`

### 环境配置

- 测试 DOM 相关代码需要 `environment: 'jsdom'` 或 `environment: 'happy-dom'`
- 可在文件级别通过注释设置环境（支持 Docblock 和单行注释两种格式）：
```ts
// @vitest-environment jsdom
```
或
```ts
/**
 * @vitest-environment jsdom
 */
```

- Vitest 也支持 Jest 兼容的环境注释：`/** @jest-environment jsdom */`
- 使用 `jsdom` 环境时可在 `tsconfig.json` 中添加 `"types": ["vitest/jsdom"]` 以获得 `jsdom` 全局变量类型支持

### 路径别名

Vitest 使用 Vite 的 `resolve.alias` 配置。如果 `tsconfig.json` 中使用了 `baseUrl` 或 `paths`，需安装 `vite-tsconfig-paths` 插件（如项目已有该依赖），或手动在 `resolve.alias` 中配置。

```ts
import tsconfigPaths from 'vite-tsconfig-paths';
export default defineConfig({
  plugins: [tsconfigPaths()],
});
```

注意：Vitest 不支持在 `resolve.alias` 中使用相对路径，需使用绝对路径：
```ts
alias: {
  '@/': new URL('./src/', import.meta.url).pathname, // ✅
  // '@/': './src/',  // ❌ 不要使用相对路径
}
```

### 参数化测试

#### `test.each` — 数据驱动的测试用例

使用数组形式提供多组测试数据，避免重复编写类似的测试逻辑：

```ts
test.each([
  [1, 1, 2],
  [1, 2, 3],
  [2, 1, 3],
])('add(%i, %i) -> %i', (a, b, expected) => {
  const startTime = performance.now();
  expect(a + b).toBe(expected);
  const endTime = performance.now();
  console.log(`test add [${a}, ${b}] executed in: ${(endTime - startTime).toFixed(6)}ms`);
});
```

使用对象数组形式，可读性更好：
```ts
test.each([
  { a: 1, b: 1, expected: 2 },
  { a: 1, b: 2, expected: 3 },
  { a: 2, b: 1, expected: 3 },
])('add($a, $b) -> $expected', ({ a, b, expected }) => {
  expect(a + b).toBe(expected);
});
```

标签模板字面量（tagged template literal）语法：
```ts
test.each`
  a    | b    | expected
  ${1} | ${1} | ${2}
  ${1} | ${2} | ${3}
  ${2} | ${1} | ${3}
`('add($a, $b) -> $expected', ({ a, b, expected }) => {
  expect(a + b).toBe(expected);
});
```

#### `describe.each` — 数据驱动的测试套件

为每组数据生成一个独立的 `describe` 块，适合需要共享 `beforeEach`/`afterEach` 的场景：

```ts
describe.each([
  { name: 'node', env: 'node' },
  { name: 'jsdom', env: 'jsdom' },
])('environment: $name', ({ env }) => {
  it('should be defined', () => {
    expect(env).toBeDefined();
  });
});
```

#### 格式化占位符

`test.each` / `describe.each` 的测试名称支持以下 printf 风格的占位符：

| 占位符 | 说明 |
|---|---|
| `%s` | 字符串 |
| `%d` / `%i` | 数字 / 整数 |
| `%f` | 浮点数 |
| `%j` | JSON |
| `%o` | 对象 |
| `%#` | 当前测试数据的索引（从 0 开始） |
| `%%` | 转义百分号 |
| `$property` | 对象属性名（对象数组或模板字面量形式） |

#### 与 Jest 的兼容性

Vitest 的 `test.each` / `describe.each` 与 Jest 的用法**完全兼容**，包括数组形式、对象形式和标签模板字面量形式。从 Jest 迁移无需修改参数化测试代码。

### 快照测试

#### 基本用法

```ts
expect(result).toMatchSnapshot();
expect(result).toMatchInlineSnapshot();
```

可传入提示字符串区分同一测试中的多个快照：
```ts
test('multiple snapshots', () => {
  expect(header).toMatchSnapshot('header');
  expect(body).toMatchSnapshot('body');
});
```

#### `toMatchInlineSnapshot` — 内联快照

快照内容直接写入测试文件中（首次运行时自动生成），无需独立 `.snap` 文件。适合输出较短的场景：
```ts
expect({ name: 'Alice', age: 30 }).toMatchInlineSnapshot(`
  {
    "age": 30,
    "name": "Alice",
  }
`);
```

#### `toMatchFileSnapshot` — 文件快照

Vitest 独有功能（Jest 无此 API），将快照保存到指定路径的独立文件中。适合大型输出（HTML、JSON、生成代码等）：
```ts
await expect(generateHTML()).toMatchFileSnapshot('./snapshots/output.html');
await expect(JSON.stringify(data, null, 2)).toMatchFileSnapshot('./snapshots/data.json');
```

注意：`toMatchFileSnapshot` 返回 Promise，必须使用 `await`。

#### 与 Jest 的差异

1. **快照文件头部注释不同**：`Vitest Snapshot v1` vs `Jest Snapshot v1`，迁移时会导致 diff。

2. **`printBasicPrototype` 默认为 `false`**：Vitest 和 Jest 的快照均由 `pretty-format` 驱动。Vitest 将 `printBasicPrototype` 默认设为 `false`，使输出更简洁，不打印 `Array`/`Object` 等基本类型前缀：
```ts
// Jest 默认快照输出
// Array [
//   "hello",
// ]

// Vitest 默认快照输出
// [
//   "hello",
// ]
```

如果希望与 Jest 行为一致，可在配置中手动开启：
```ts
test: {
  snapshotSerializers: [],
  snapshotFormat: {
    printBasicPrototype: true,
  },
}
```

3. **`toMatchFileSnapshot` 为 Vitest 独有**：Jest 无此功能，需借助第三方库实现类似效果。

4. **`--update` 标志**：更新快照使用 `vitest --update`（或 `-u`），与 Jest 一致。Vitest 在 watch 模式下也可以按 `u` 键交互式更新。

#### 快照中处理动态值

使用 `expect.any()` 或属性匹配器处理不确定的值：
```ts
expect(user).toMatchSnapshot({
  id: expect.any(Number),
  createdAt: expect.any(String),
  name: 'Alice',
});
```

### 常见错误排查

| 错误信息 | 原因与修复 |
|---|---|
| `Cannot find module './relative-path'` | 路径拼写、`baseUrl` 未生效（需 `vite-tsconfig-paths`）、`resolve.alias` 使用了相对路径 |
| `Failed to Terminate Worker` | `fetch` + `pool: 'threads'` 冲突，切换为 `pool: 'forks'` |
| `vi is not defined` | 未 import `vi`，或未启用 `globals: true` |
| `vi.mock` factory 中引用外部变量报错 | 使用 `vi.hoisted` 定义变量或改用 `vi.doMock` |
| `document is not defined` | 需要 `jsdom` 环境 → 添加 `// @vitest-environment jsdom` 注释 |
| mock 默认导出不生效 | factory 中需要提供 `default` key |
| `Unhandled Rejection` | 异步函数未 `await`，使用 `await` 或 `expect().rejects` |

### 环境检测

```ts
if (process.env.VITEST) {
  // Vitest 环境下 process.env.VITEST 为 'true'
  // import.meta.env.VITEST 也为 'true'
}
```

## 依赖安装

如果项目缺少以下依赖，可以使用项目的包管理器安装：
- `vitest`
- 如果需要 DOM 环境：`jsdom` 或 `happy-dom`
- 如果需要 React 组件测试：`@testing-library/react`、`@testing-library/jest-dom`
- 如果 tsconfig 使用了 paths/baseUrl：`vite-tsconfig-paths`（可选，项目可能通过 `resolve.alias` 替代）
