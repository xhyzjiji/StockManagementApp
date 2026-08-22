# Rstest 框架知识

## 概述

Rstest 是基于 Rspack 的测试框架，提供 Jest 兼容的 API，内置对 TypeScript、ESM 的原生支持。Rstest 使用 `@rstest/core` 包，提供 `rs` 和 `rstest` 两个等价的工具对象。

## 常见问题

### 与 Jest/Vitest 的主要差异

1. **导入方式不同**：Rstest 需要从 `@rstest/core` 导入 API
```ts
import { describe, it, expect, test, rs, rstest } from '@rstest/core';
```

2. **Mock 函数**：使用 `rs`（或 `rstest`）而非 `jest` / `vi`
```ts
// Jest
jest.fn()
jest.mock('./module')
jest.spyOn(obj, 'method')

// Vitest
vi.fn()
vi.mock('./module')
vi.spyOn(obj, 'method')

// Rstest
rs.fn()
rs.mock('./module', () => ({ ... }))
rs.spyOn(obj, 'method')
```

3. **定时器**：
```ts
// Rstest
rs.useFakeTimers()
rs.advanceTimersByTime(1000)
rs.useRealTimers()
```

4. **模块 Mock**：

ESM 模块使用 `rs.mock()`（会被提升到文件顶部）：
```ts
import { rs } from '@rstest/core';
import { fetchUser } from './api';

rs.mock('./api', () => ({
  fetchUser: rs.fn().mockResolvedValue({ id: '1', name: 'Alice' }),
}));
```

非提升版本使用 `rs.doMock()`：
```ts
rs.doMock('./feature', () => ({
  readFeatureFlag: () => 'mocked',
}));
const { readFeatureFlag } = await import('./feature');
```

CommonJS 模块使用 `rs.mockRequire()` / `rs.doMockRequire()`。

5. **Auto-mock 模块**（替换所有函数导出为 mock 函数）：
```ts
rs.mock('./math', { mock: true });
```

6. **Spy 整个模块**（保留真实实现但可追踪调用）：
```ts
rs.mock('./calculator', { spy: true });
```

7. **部分 Mock 模块**（使用 `importActual`）：
```ts
import * as actualDateUtils from './date-utils' with { rstest: 'importActual' };
import { formatDate, parseDate } from './date-utils';

rs.mock('./date-utils', () => ({
  ...actualDateUtils,
  formatDate: rs.fn().mockReturnValue('2026-03-19'),
}));
```

注意：Rstest 的 `rs.mock()` 仅传路径时只会查找 `__mocks__` 目录，不会自动 mock。若需自动 mock，必须显式传 `{ mock: true }`。

8. **Deep-mock 对象**：
```ts
const service = rs.mockObject({
  user: { fetch: async (id: string) => ({ id, name: 'real' }) },
  version: 'v1',
});
service.user.fetch.mockResolvedValue({ id: '1', name: 'mocked' });
```

9. **超时设置**：
```ts
// Jest
jest.setTimeout(5_000)

// Rstest
rstest.setConfig({ testTimeout: 5_000 })
```

10. **Done callback 不支持**：Rstest 不支持 `done` 回调，使用 `async/await` 或返回 Promise。

### CLI 命令

Rstest 提供轻量级 CLI，包含以下子命令：

**`rstest run`**：单次运行测试，不启用 watch 模式，适用于 CI 环境：
```bash
npx rstest run
```

**`rstest watch`**：启动监听模式，当测试文件或其依赖文件发生变更时自动重新执行关联的测试：
```bash
npx rstest watch
```

watch 模式下可使用以下快捷键：
- `f` — 重跑失败的测试
- `a` — 重跑所有测试
- `u` — 更新快照
- `t` — 按测试名称正则过滤
- `p` — 按文件名正则过滤
- `q` — 退出进程

**`rstest list`**：列出所有匹配条件的测试用例，默认打印测试名称：
```bash
npx rstest list
npx rstest list --filesOnly
npx rstest list --json
npx rstest list --json=./output.json
npx rstest list --printLocation
npx rstest list -t='test a'
```

**`rstest merge-reports`**：将多个分片产生的 blob 报告合并为统一报告，配合 `--shard` 使用：
```bash
npx rstest merge-reports
npx rstest merge-reports ./custom-reports-dir
npx rstest merge-reports --cleanup
```

常用 CLI 选项（`rstest`、`rstest run`、`rstest watch` 共享）：

| 选项 | 说明 |
|------|------|
| `-c, --config <path>` | 指定配置文件路径 |
| `--globals` | 提供全局 API |
| `--reporter <name>` | 指定 reporter（可多次使用） |
| `--coverage` | 启用代码覆盖率收集 |
| `-u, --update` | 更新快照文件 |
| `-t, --testNamePattern <regex>` | 按测试名称正则匹配运行 |
| `--testEnvironment <name>` | 设置测试环境 |
| `--testTimeout <ms>` | 测试超时时间 |
| `--bail [number]` | 指定数量的测试失败后中止 |
| `--shard <index>/<count>` | 测试分片 |
| `--browser` | 在浏览器模式下运行测试 |
| `--passWithNoTests` | 没有匹配测试文件时仍通过 |
| `--no-<option>` | 布尔选项取反，如 `--no-coverage` |

### 配置文件

Rstest 使用 `rstest.config.ts`（或 `.mjs`、`.js`、`.cjs`、`.mts`、`.cts`）：

```ts
import { defineConfig } from '@rstest/core';

export default defineConfig({
  testEnvironment: 'node', // 或 'jsdom', 'happy-dom'
  globals: true,           // 允许不显式 import describe/it/expect
  include: ['src/**/*.{test,spec}.{ts,tsx}'],
  setupFiles: ['./rstest.setup.ts'],
});
```

如果项目已有 Rsbuild 配置，可通过 adapter 复用（需安装 `@rstest/adapter-rsbuild`）：
```ts
import { withRsbuildConfig } from '@rstest/adapter-rsbuild';
import { defineConfig } from '@rstest/core';

export default defineConfig({
  extends: withRsbuildConfig(),
  testEnvironment: 'happy-dom',
});
```

如果项目使用 Rslib，可通过 `@rstest/adapter-rslib` 复用构建配置：
```ts
import { withRslibConfig } from '@rstest/adapter-rslib';
import { defineConfig } from '@rstest/core';

export default defineConfig({
  extends: withRslibConfig(),
});
```

如果项目使用 Rspack，可通过 `@rstest/adapter-rspack` 复用构建配置：
```ts
import { withRspackConfig } from '@rstest/adapter-rspack';
import { defineConfig } from '@rstest/core';

export default defineConfig({
  extends: withRspackConfig(),
});
```

三个 adapter 均支持传入选项来指定配置文件路径或修改配置，例如：
```ts
withRsbuildConfig({ configPath: './rsbuild.config.ts' })
withRspackConfig({ configPath: './rspack.config.ts', configName: 'web' })
withRslibConfig({ configPath: './rslib.config.ts' })
```

### No tests found

- 检查 `include` 配置的文件匹配模式
- 确认测试文件后缀与配置的 `include` 模式一致
- 如果使用 `globals: true`，确保 `tsconfig.json` 中包含 `"types": ["@rstest/core/globals"]`

### 环境配置

- 测试 DOM 相关代码需要 `testEnvironment: 'jsdom'` 或 `testEnvironment: 'happy-dom'`
- 可在文件级别通过注释设置环境：
```ts
// @rstest-environment jsdom
```

### Mock 清理

```ts
afterEach(() => {
  rs.restoreAllMocks();  // 恢复 spyOn 的原始实现
  rs.clearAllMocks();    // 清除调用记录
});

// 或在 rstest.config.ts 中全局配置
// restoreMocks: true,
// clearMocks: true,
```

也可使用配置项：`clearMocks`、`resetMocks`、`restoreMocks`。

### 快照测试

```ts
expect(result).toMatchSnapshot();
expect(result).toMatchInlineSnapshot();
await expect(result).toMatchFileSnapshot('./basic.output.html');
```

### React 组件测试

Rstest 支持通过 `@rsbuild/plugin-react` 插件和 `@testing-library/react` 进行 React 组件测试：

```tsx
import { expect, test } from '@rstest/core';
import { render, screen, fireEvent } from '@testing-library/react';
import Counter from './Counter';

test('increments counter on click', () => {
  render(<Counter />);
  const button = screen.getByRole('button');
  expect(screen.getByText('Count: 0')).toBeInTheDocument();
  fireEvent.click(button);
  expect(screen.getByText('Count: 1')).toBeInTheDocument();
});
```

需要安装 `@testing-library/jest-dom` 并在 setup 文件中配置 matchers：
```ts
// rstest.setup.ts
import { afterEach, expect } from '@rstest/core';
import { cleanup } from '@testing-library/react';
import * as jestDomMatchers from '@testing-library/jest-dom/matchers';

expect.extend(jestDomMatchers);
afterEach(() => { cleanup(); });
```

### Markdown reporter

Markdown reporter 将测试结果以结构化 Markdown 文档输出到 stdout，专为 Agent / LLM 场景设计。在 Agent 环境中（如 Claude Code、Cursor、Codex 等），如果用户没有显式配置 reporter，Rstest 会自动检测并默认使用 `md` reporter。

```bash
npx rstest --reporter=md
```

Markdown reporter 的特点：
- 每个失败用例附带一键复现命令（文件名+测试名），方便 Agent 重跑单个失败用例
- 堆栈默认输出 `top`（稳定锚点帧）而非完整 stack
- 当失败数超过 `failures.max` 时，先打印所有失败的精简列表，再展开前 N 个的完整详情
- 智能截断输出以控制在 context 限制内，节省 token

可通过 reporter 选项进一步调整输出：
```ts
import { defineConfig } from '@rstest/core';

export default defineConfig({
  reporters: [
    [
      'md',
      {
        preset: 'normal',
        failures: { max: 50 },
        stack: 'top',
        testLists: 'auto',
        console: { maxLogsPerTestPath: 10, maxCharsPerEntry: 500 },
      },
    ],
  ],
});
```

`testLists` 选项控制测试列表的输出行为：`'auto'`（默认，仅在聚焦运行且通过时打印）或 `'always'`（始终打印）。

### In-source testing（源码内测试）

Rstest 支持将测试代码直接写在源码文件中，类似 Rust 的模块测试。适用于小型功能函数和工具函数的快速验证。

1. 在配置文件中添加 `includeSource`：
```ts
import { defineConfig } from '@rstest/core';

export default defineConfig({
  includeSource: ['src/**/*.{js,ts}'],
});
```

2. 在源码文件中使用 `import.meta.rstest` 编写测试：
```ts
export const sayHi = () => 'hi';

if (import.meta.rstest) {
  const { it, expect } = import.meta.rstest;
  it('should test source code correctly', () => {
    expect(sayHi()).toBe('hi');
  });
}
```

3. 生产构建时，在构建配置中将 `import.meta.rstest` 定义为 `false` 以消除测试代码：
```ts
import { defineConfig } from '@rsbuild/core';

export default defineConfig({
  source: {
    define: {
      'import.meta.rstest': false,
    },
  },
});
```

4. TypeScript 支持需在项目中创建类型声明文件：
```ts
/// <reference types="@rstest/core/importMeta" />
```

### Browser mode（浏览器模式）

Rstest 支持在真实浏览器中运行测试（实验性功能），使用 Playwright 作为 provider。与 `jsdom` / `happy-dom` 模拟环境不同，Browser mode 在实际浏览器中执行测试。

启用 Browser mode 需安装 `@rstest/browser` 和对应浏览器：
```bash
pnpm add @rstest/browser -D
npx playwright install chromium
```

配置示例：
```ts
import { defineConfig } from '@rstest/core';

export default defineConfig({
  browser: {
    enabled: true,
    provider: 'playwright',
    browser: 'chromium',
    headless: true,
  },
});
```

支持的浏览器：`chromium`（默认）、`firefox`、`webkit`。

React 组件在浏览器模式下使用 `@rstest/browser-react` 提供的 `render` 和 `renderHook`：
```tsx
import { render } from '@rstest/browser-react';
import { getByRole, getByText } from '@testing-library/dom';
import userEvent from '@testing-library/user-event';
import { expect, test } from '@rstest/core';

test('increments counter on click', async () => {
  const { container } = await render(<Counter />);
  const button = getByRole(container, 'button');
  await userEvent.click(button);
  expect(getByText(container, 'Count: 1')).toBeTruthy();
});
```

可在多项目配置中同时使用 Node、jsdom 和 Browser 模式：
```ts
import { defineConfig } from '@rstest/core';

export default defineConfig({
  projects: [
    {
      name: 'browser',
      include: ['src/**/*.browser.test.ts'],
      browser: { enabled: true, provider: 'playwright' },
    },
    {
      name: 'node',
      include: ['src/**/*.node.test.ts'],
      testEnvironment: 'node',
    },
  ],
});
```

### Test sharding（测试分片）

Rstest 支持测试分片，将测试文件拆分到多台 CI 机器上并行执行，显著缩短整体测试时间。

使用 `--shard` 选项运行分片：
```bash
npx rstest --shard 1/3
npx rstest --shard 2/3
npx rstest --shard 3/3
```

完整的 CI 分片合并流程：

1. 在各分片 CI 机器上使用 `blob` reporter 运行测试：
```bash
npx rstest run --shard 1/3 --reporter=blob --coverage
npx rstest run --shard 2/3 --reporter=blob --coverage
npx rstest run --shard 3/3 --reporter=blob --coverage
```

2. 收集所有 `.rstest-reports/` 目录后执行合并：
```bash
npx rstest merge-reports --cleanup
```

合并命令会：
- 汇总所有分片的测试结果
- 通过配置的 reporter 生成统一报告
- 合并覆盖率数据（如果启用了 coverage）
- `--cleanup` 选项可在合并后删除 blob 报告目录

### 环境检测

```ts
if (process.env.RSTEST) {
  // Rstest 环境下为 'true'
}
```

## 依赖安装

如果项目缺少以下依赖，可以使用项目的包管理器安装：
- `@rstest/core`
- 如果需要 DOM 环境：`jsdom` 或 `happy-dom`
- 如果测试 React 组件：`@rsbuild/plugin-react`、`@testing-library/react`、`@testing-library/jest-dom`
- 如果复用 Rsbuild 配置：`@rstest/adapter-rsbuild`
- 如果复用 Rslib 配置：`@rstest/adapter-rslib`
- 如果复用 Rspack 配置：`@rstest/adapter-rspack`
- 如果使用 Browser mode：`@rstest/browser`、`playwright`
- 如果使用 Browser mode 测试 React 组件：`@rstest/browser-react`、`@testing-library/dom`、`@testing-library/user-event`
