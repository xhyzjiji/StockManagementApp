# Jest 框架知识

## 概述

Jest 是 Meta 开源的 JavaScript 测试框架，内置断言库、Mock 系统、覆盖率收集和快照测试。使用全局对象 `jest` 进行 mock 操作，无需显式导入 `describe`/`it`/`expect` 等 API（默认注入全局作用域）。TypeScript 项目通常需要搭配 `ts-jest` 或 `@swc/jest` 进行转换。

## 常见问题

### 与 Vitest / Rstest 的差异

1. **导入方式不同**：Jest 默认将 API 注入全局，无需显式导入；Vitest / Rstest 需要从包中导入
```ts
// Jest — 全局可用，无需 import
describe('test', () => {
  it('works', () => {
    expect(1 + 1).toBe(2);
  });
});

// Vitest
import { describe, it, expect } from 'vitest';

// Rstest
import { describe, it, expect } from '@rstest/core';
```

2. **Mock 函数**：使用 `jest` 全局对象而非 `vi`
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
jest.setTimeout(10_000)

// Vitest
vi.setConfig({ testTimeout: 10_000 })
```

5. **部分 Mock 获取原始模块**：
```ts
// Jest — 使用 jest.requireActual
jest.mock('./utils', () => ({
  ...jest.requireActual('./utils'),
  format: jest.fn(),
}));

// Vitest — 使用 importOriginal 或 vi.importActual
vi.mock('./utils', async (importOriginal) => ({
  ...(await importOriginal()),
  format: vi.fn(),
}));
```

6. **模块系统**：Jest 默认运行在 CommonJS 环境中，ESM 支持为实验性；Vitest 原生支持 ESM。

### 模块 Mock

#### `jest.mock` — 提升式模块 Mock

`jest.mock` 会被**提升到文件顶部**执行，无论写在代码的哪个位置。factory 函数在模块加载前执行。

```ts
jest.mock('./api', () => ({
  fetchUser: jest.fn().mockResolvedValue({ id: 1, name: 'test' }),
}));

import { fetchUser } from './api';

test('fetchUser returns mock data', async () => {
  const user = await fetchUser();
  expect(user).toEqual({ id: 1, name: 'test' });
});
```

#### `jest.requireActual` — 部分 Mock

在 `jest.mock` factory 中使用 `jest.requireActual` 获取原始模块，只覆盖需要 mock 的部分：

```ts
jest.mock('./utils', () => {
  const original = jest.requireActual('./utils');
  return {
    ...original,
    formatDate: jest.fn().mockReturnValue('2024-01-01'),
  };
});
```

#### 自动 Mock

仅传路径不提供 factory 时，Jest 会自动将所有导出替换为 `jest.fn()`：
```ts
jest.mock('./example');

import { getData } from './example';

test('auto mocked', () => {
  (getData as jest.Mock).mockReturnValue(42);
  expect(getData()).toBe(42);
});
```

也可使用 `__mocks__` 目录放置手动 mock 文件，Jest 会自动查找。

#### `jest.doMock` — 非提升式 Mock

不会被提升，可以在条件逻辑中使用，但只对后续的 `require()` 生效：
```ts
beforeEach(() => {
  jest.resetModules();
});

test('dynamic mock', () => {
  jest.doMock('./config', () => ({ env: 'test' }));
  const config = require('./config');
  expect(config.env).toBe('test');
});
```

#### Mock 默认导出注意事项

mock 含默认导出的 ES Module 时，需要提供 `__esModule: true` 和 `default` key：
```ts
jest.mock('./module', () => ({
  __esModule: true,
  default: jest.fn(() => 'mocked default'),
  namedExport: jest.fn(),
}));
```

#### ⚠️ 同文件函数 Mock 限制

无法 mock 模块内部函数之间的互相调用。如 `foobar()` 内部调用 `foo()`，mock `foo` 不会影响 `foobar` 内部的 `foo` 调用——因为内部引用的是原始绑定。

### Mock 函数与对象

#### `jest.fn` — 创建 Mock 函数
```ts
const getApples = jest.fn(() => 0);
getApples.mockReturnValueOnce(5);
expect(getApples()).toBe(5);
expect(getApples()).toBe(0);
```

#### `jest.spyOn` — 监视对象方法
```ts
const spy = jest.spyOn(cart, 'getApples').mockImplementation(() => 10);
expect(cart.getApples()).toBe(10);
expect(spy).toHaveBeenCalled();
spy.mockRestore();
```

注意 `jest.spyOn` 仅追踪**调用后**的方法调用。模块顶层代码中的调用无法被追踪。

#### 链式 Mock 设置
```ts
const mockFn = jest.fn()
  .mockReturnValueOnce(1)
  .mockReturnValueOnce(2)
  .mockReturnValue(0);

expect(mockFn()).toBe(1);
expect(mockFn()).toBe(2);
expect(mockFn()).toBe(0);
```

### Mock 清理

三个清理函数的区别：

| 方法 | 作用 |
|---|---|
| `jest.clearAllMocks()` | 清除调用记录（`.mock.calls`、`.mock.results`），**不影响**实现 |
| `jest.resetAllMocks()` | 清除调用记录 **+** 重置实现（回到 `jest.fn()` 状态） |
| `jest.restoreAllMocks()` | 恢复 `jest.spyOn` 的原始实现 |

推荐在 `afterEach` 中清理：
```ts
afterEach(() => {
  jest.restoreAllMocks();
});
```

也可在 `jest.config` 中配置自动清理：
```ts
module.exports = {
  clearMocks: true,
  resetMocks: true,
  restoreMocks: true,
};
```

### 定时器

#### `jest.useFakeTimers` — 接管定时器

使用假定时器接管 `setTimeout`、`setInterval`、`Date` 等：
```ts
beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

test('delays execution', () => {
  const callback = jest.fn();
  setTimeout(callback, 1000);

  jest.advanceTimersByTime(1000);
  expect(callback).toHaveBeenCalledTimes(1);
});
```

#### `jest.setSystemTime` — 固定当前时间
```ts
beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2024-06-15T12:00:00Z'));
});

afterEach(() => {
  jest.useRealTimers();
});

test('returns fixed date', () => {
  expect(new Date().toISOString()).toBe('2024-06-15T12:00:00.000Z');
});
```

#### 其他定时器方法
```ts
jest.runAllTimers();
jest.runOnlyPendingTimers();
jest.advanceTimersByTime(5000);
jest.advanceTimersToNextTimer();
```

⚠️ `jest.runAllTimers()` 在存在递归定时器时可能导致无限循环，此时应使用 `jest.advanceTimersByTime()` 或 `jest.runOnlyPendingTimers()`。

### 参数化测试 `test.each`

#### 数组格式
```ts
test.each([
  [1, 1, 2],
  [1, 2, 3],
  [2, 1, 3],
])('add(%i, %i) = %i', (a, b, expected) => {
  const startTime = performance.now();
  expect(a + b).toBe(expected);
  const endTime = performance.now();
  console.log(`test add [${a}, ${b}] executed in: ${(endTime - startTime).toFixed(6)}ms`);
});
```

#### 对象数组格式
```ts
test.each([
  { a: 1, b: 1, expected: 2 },
  { a: 1, b: 2, expected: 3 },
  { a: 2, b: 1, expected: 3 },
])('add($a, $b) = $expected', ({ a, b, expected }) => {
  expect(a + b).toBe(expected);
});
```

#### 模板字面量格式
```ts
test.each`
  a    | b    | expected
  ${1} | ${1} | ${2}
  ${1} | ${2} | ${3}
  ${2} | ${1} | ${3}
`('add($a, $b) = $expected', ({ a, b, expected }) => {
  expect(a + b).toBe(expected);
});
```

`describe.each` 同样支持参数化：
```ts
describe.each([
  { name: 'positive', value: 1 },
  { name: 'negative', value: -1 },
])('$name numbers', ({ value }) => {
  test('is not zero', () => {
    expect(value).not.toBe(0);
  });
});
```

### 快照测试

```ts
test('renders correctly', () => {
  const tree = renderer.create(<Button label="Click" />).toJSON();
  expect(tree).toMatchSnapshot();
});
```

内联快照（自动写入源文件）：
```ts
test('inline snapshot', () => {
  expect({ name: 'test', age: 25 }).toMatchInlineSnapshot();
});
```

更新快照命令：`jest --updateSnapshot` 或 `jest -u`。

与 Vitest 的差异：
- 快照文件头部注释不同（`Jest Snapshot v1` vs `Vitest Snapshot v1`）
- Jest 的 `printBasicPrototype` 默认为 `true`（输出包含 `Object`/`Array` 前缀）

### 异步测试

#### async / await 模式
```ts
test('fetches data', async () => {
  const data = await fetchData();
  expect(data).toEqual({ id: 1 });
});
```

#### Promise 断言
```ts
test('resolves value', async () => {
  await expect(fetchData()).resolves.toEqual({ id: 1 });
});

test('rejects with error', async () => {
  await expect(failingFn()).rejects.toThrow('Network error');
});
```

#### 回调模式（使用 `done`）
```ts
test('callback style', (done) => {
  fetchWithCallback((err, data) => {
    try {
      expect(err).toBeNull();
      expect(data).toBe('ok');
      done();
    } catch (error) {
      done(error);
    }
  });
});
```

⚠️ 使用 `done` 回调时，必须在 `catch` 中调用 `done(error)`，否则测试会超时而不是报告实际错误。

⚠️ 不要在同一个测试中同时使用 `done` 和 `async`，Jest 会抛出错误。

### 常见错误排查

| 错误信息 | 原因与修复 |
|---|---|
| `No tests found` | `testMatch` / `testRegex` 配置与文件路径不匹配。检查 `jest.config` 中的匹配规则和 `roots` 配置。 |
| `Cannot find module './path'` | 路径拼写错误，或 `moduleNameMapper` / `moduleDirectories` 未正确配置。tsconfig `paths` 需要在 `moduleNameMapper` 中映射。 |
| `SyntaxError: Unexpected token` | Jest 默认不转换 `node_modules`。需要在 `transformIgnorePatterns` 中排除相关包，或配置 `transform` 处理 ESM 包。 |
| `document is not defined` | 需要 DOM 环境。在 `jest.config` 中设置 `testEnvironment: 'jsdom'`，或在文件头部添加 `/** @jest-environment jsdom */`。 |
| Mock 不生效 | ① `jest.mock` 路径与 import 路径不一致；② 默认导出缺少 `__esModule: true`；③ `jest.mock` 未提升（动态路径无法提升）。 |
| `Exceeded timeout of 5000 ms` | 异步操作未完成。① 确认 `await` 未遗漏；② `done` 回调未调用；③ 使用 `jest.setTimeout()` 增加超时时间。 |
| `jest.mock` factory 中引用外部变量报错 | factory 在提升后无法访问外部作用域变量。将变量名加 `mock` 前缀（如 `mockFn`），Jest 会允许以 `mock` 开头的变量通过。 |
| `ReferenceError: jest is not defined` | 在 ESM 模式下 `jest` 全局不可用。需要使用 `import { jest } from '@jest/globals'` 或切换回 CJS 模式。 |
| `TypeError: xxx is not a function` | 自动 mock 将所有导出替换为 `jest.fn()`，调用前需要 `mockReturnValue` / `mockImplementation` 设置返回值。 |

### 配置文件

Jest 使用 `jest.config.ts`（或 `jest.config.js`，或 `package.json` 中的 `jest` 字段）：

```ts
import type { Config } from 'jest';

const config: Config = {
  testEnvironment: 'node',
  roots: ['<rootDir>/src'],
  testMatch: ['**/__tests__/**/*.[jt]s?(x)', '**/?(*.)+(spec|test).[jt]s?(x)'],
  transform: {
    '^.+\\.tsx?$': 'ts-jest',
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  setupFilesAfterSetup: ['./jest.setup.ts'],
  collectCoverage: true,
  coverageDirectory: 'coverage',
};

export default config;
```

#### 路径别名

tsconfig 中的 `paths` 需要手动映射到 `moduleNameMapper`：
```ts
moduleNameMapper: {
  '^@/(.*)$': '<rootDir>/src/$1',
  '^@components/(.*)$': '<rootDir>/src/components/$1',
}
```

也可使用 `ts-jest` 的 `pathsToModuleNameMapper` 工具自动转换：
```ts
import { pathsToModuleNameMapper } from 'ts-jest';
import { compilerOptions } from './tsconfig.json';

const config: Config = {
  moduleNameMapper: pathsToModuleNameMapper(compilerOptions.paths, {
    prefix: '<rootDir>/',
  }),
};
```

### 环境配置

- 默认环境为 `node`，测试 DOM 相关代码需要 `testEnvironment: 'jsdom'`
- 可在文件级别通过 Docblock 注释设置环境：
```ts
/**
 * @jest-environment jsdom
 */
```

- 使用 `jsdom` 环境需要安装 `jest-environment-jsdom`（Jest 28+ 不再内置）

### 环境变量 Mock

```ts
const originalEnv = process.env;

beforeEach(() => {
  jest.resetModules();
  process.env = { ...originalEnv };
});

afterEach(() => {
  process.env = originalEnv;
});

test('reads NODE_ENV', () => {
  process.env.NODE_ENV = 'production';
  const result = getEnv();
  expect(result).toBe('production');
});
```

## 依赖安装

如果项目缺少以下依赖，可以使用项目的包管理器安装：
- `jest`
- TypeScript 项目额外需要：`ts-jest`（或 `@swc/jest`）、`@types/jest`
- 如果需要 DOM 环境（Jest 28+）：`jest-environment-jsdom`
- 如果需要 React 组件测试：`@testing-library/react`、`@testing-library/jest-dom`、`@testing-library/user-event`
- 如果 tsconfig 使用了 paths：可通过 `moduleNameMapper` 手动配置（无额外依赖），或使用 `ts-jest` 的 `pathsToModuleNameMapper`
