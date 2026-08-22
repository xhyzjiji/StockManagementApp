# 工程环境知识

本文档覆盖不同工程环境的执行和适配方式，帮助在各种项目结构中正确生成和运行测试。

## 包管理器识别与使用

### 识别方式

| 锁文件 | 包管理器 |
|---|---|
| `pnpm-lock.yaml` | pnpm |
| `yarn.lock` | yarn |
| `package-lock.json` | npm |
| `bun.lockb` | bun |

也可通过 `package.json` 的 `packageManager` 字段识别：
```json
{ "packageManager": "pnpm@8.0.0" }
```

### 使用原则

- 识别到项目使用的包管理器后，可用于理解项目结构、安装依赖和运行测试命令
- 如果项目缺少必要的测试依赖，可以使用对应的包管理器安装

## Monorepo 结构

### 识别标记

| 标记文件 | 工具 |
|---|---|
| `pnpm-workspace.yaml` | pnpm workspace |
| `lerna.json` | Lerna |
| `nx.json` | Nx |
| `turbo.json` | Turborepo |
| `rush.json` | Rush |
| `eden.monorepo.json` | Eden (字节内部) |

### pnpm workspace

```yaml
# pnpm-workspace.yaml
packages:
  - 'packages/*'
  - 'apps/*'
```

- 在 monorepo 中执行测试时，需要先定位到正确的子包目录

#### `--filter` 选择器

pnpm 通过 `--filter`（简写 `-F`）在 monorepo 中精确定位子包执行命令，支持多种匹配模式：

**按包名 / glob 匹配：**

```bash
pnpm --filter <package-name> test
pnpm --filter "@scope/utils" test
pnpm --filter "./packages/core" test
pnpm --filter "{packages/**}" test
```

**按 git 变更范围匹配（仅选中有变更的包）：**

```bash
pnpm --filter "...[origin/main]" test
pnpm --filter "{packages/**}[origin/main]" test
```

**按依赖关系匹配：**

```bash
pnpm --filter "...@scope/core" test
pnpm --filter "@scope/core..." test
```

- `...pkg`：选中 `pkg` 及其所有依赖方（dependents）
- `pkg...`：选中 `pkg` 及其所有依赖项（dependencies）

**组合多个 filter：**

```bash
pnpm --filter "@scope/a" --filter "@scope/b" test
```

#### `pnpm exec` 与 `pnpm dlx`

- `pnpm exec`：在当前项目的 `node_modules/.bin` 上下文中执行命令，等价于 `npx` 但限定于本地已安装的包：

```bash
pnpm exec jest --config jest.config.ts
pnpm --filter "@scope/core" exec vitest run
```

- `pnpm dlx`：临时下载并执行一个包（不写入 `node_modules`），等价于 `npx`：

```bash
pnpm dlx create-react-app my-app
```

#### CI 环境中使用 `--frozen-lockfile`

在 CI 中应始终使用 `--frozen-lockfile` 确保锁文件一致性，如果 `pnpm-lock.yaml` 与 `package.json` 不一致则会直接报错而非自动更新锁文件：

```bash
pnpm install --frozen-lockfile
```

### Yarn workspace

通过根目录 `package.json` 的 `workspaces` 字段声明子包：

```json
{
  "private": true,
  "workspaces": ["packages/*", "apps/*"]
}
```

Yarn Berry（v2+）还支持 `workspaces` 中使用 `nohoist` 等高级配置。

#### 常用命令

**在指定子包中运行脚本：**

```bash
yarn workspace @scope/core test
yarn workspace @scope/core run test -- --coverage
```

**对所有子包执行命令（Yarn Berry v2+）：**

```bash
yarn workspaces foreach run test
yarn workspaces foreach --parallel run build
yarn workspaces foreach --topological run build
```

- `--parallel`：并行执行
- `--topological`：按依赖拓扑排序执行，确保被依赖的包先执行

**Yarn Classic（v1）批量执行：**

```bash
yarn workspaces run test
```

#### `yarn dlx`

Yarn Berry 提供 `yarn dlx`（等价于 `npx`），临时下载并执行一个包：

```bash
yarn dlx create-react-app my-app
```

#### 在 Yarn monorepo 中运行测试

- 定位目标子包后，使用 `yarn workspace <pkg> test` 运行该包的测试脚本
- 如果需要执行本地安装的二进制工具，在 Yarn Berry 中可用 `yarn exec`：

```bash
yarn workspace @scope/core exec jest --config jest.config.ts
```

### Rush

- 使用 `rush test` 或在子包内直接运行测试命令

#### `rush.json` 结构

`rush.json` 是 Rush monorepo 的核心配置文件，通过 `projects` 数组声明所有子包：

```json
{
  "rushVersion": "5.100.0",
  "pnpmVersion": "8.15.0",
  "projects": [
    {
      "packageName": "@scope/core",
      "projectFolder": "packages/core",
      "reviewCategory": "libraries"
    },
    {
      "packageName": "@scope/app",
      "projectFolder": "apps/web",
      "reviewCategory": "apps"
    }
  ]
}
```

#### 常用命令

**全量构建与测试：**

```bash
rush build
rush test
```

**仅构建/测试指定包及其依赖：**

```bash
rush build --to @scope/core
rush build --from @scope/core
rush test --to @scope/app
```

- `--to pkg`：构建 `pkg` 及其所有上游依赖
- `--from pkg`：构建 `pkg` 及其所有下游依赖方

#### `rushx` 在子包内执行脚本

`rushx` 是 Rush 提供的轻量级脚本执行器，必须在子包目录内运行，等价于 `npm run`：

```bash
cd packages/core
rushx test
rushx test -- --coverage
```

- `rushx` 只执行当前目录下 `package.json` 中的 `scripts`

### Eden / EMO（字节内部）

如果存在 `eden.monorepo.json`，说明是 EMO 管理的 Eden monorepo 项目。EMO 使用 pnpm 作为底层依赖管理工具。

- 如果需要安装依赖，使用 `emo install`（EMO 底层使用 pnpm）

#### `eden.monorepo.json` 配置

核心配置文件，定义子包目录和项目元信息：

```json
{
  "config": {
    "edenMonoVersion": "3.10.0",
    "infraDir": "infra"
  },
  "packages": [
    { "path": "apps/eden", "shouldPublish": false },
    { "path": "packages/util", "shouldPublish": true }
  ]
}
```

也支持 glob 表达式注册 workspace：
```json
{
  "workspaces": ["apps/*", "packages/*"]
}
```

#### 基建目录模式

EMO 支持两种基建目录模式：

- **顶层基建模式**（默认）：基建在项目根目录，`node_modules/.bin` 在根目录
- **折叠基建模式**（`infraDir` 非空）：基建折叠到指定目录（如 `infra/`），CLI 工具在 `${infraDir}/node_modules/.bin` 下

折叠基建模式下：
- 需要使用 `emox` 调用 CLI 工具（如 `emox jest`、`emox eslint`）
- `emox` 自动定位 `${infraDir}/node_modules/.bin` 下的工具

```json
// package.json scripts 示例
{
  "scripts": {
    "test": "emox jest",
    "lint": "emox eslint .",
    "format": "emox prettier"
  }
}
```

#### `emox` 命令

`emox` 是 EMO 提供的 CLI 工具调度器，在折叠基建模式和顶层基建模式下均可使用：

```bash
emox jest --config jest.config.ts     # 执行 jest
emox vitest run src/utils.test.ts     # 执行 vitest
emox eslint . --fix                   # 执行 eslint
```

#### `emo test` 和 `emo run`

```bash
# 运行所有子包的 test 脚本
emo run test
emo test

# 在指定子包中运行 test
emo run --filter @scope/core test
emo test --filter "@scope/core"
```

#### `--filter` 选择器（基于 @pnpm/matcher）

EMO 的 filter 支持包名、glob、依赖关系和 git 变更范围：

```bash
# 指定包名
emo test --filter "@scope/project"

# glob 通配符
emo test --filter "@scope/p*"

# 包及其所有依赖（含自身）
emo test --filter "@scope/project..."

# 仅包的依赖（不含自身）
emo test --filter "@scope/project^..."

# 所有依赖该包的包（含自身）
emo test --filter "...@scope/lib"

# 按目录路径
emo test --filter ./packages/app/

# 按 git 变更范围
emo test --filter "[origin/master]"

# 排除某个包
emo test --filter=!@scope/legacy

# 组合多个 filter
emo test --filter @scope/a --filter @scope/b
```

#### `emo run-pnpm`（`emo rpm`）

直接调用项目中 `pnpmVersion` 指定的 pnpm 版本运行命令：

```bash
emo rpm list lodash -r    # 查看所有子项目中 lodash 的版本
emo rpm list react -r     # 查看所有依赖 react 的包
```

### Turborepo

通过 `turbo.json` 配置文件管理 monorepo 的任务编排和缓存策略。

#### 识别

存在 `turbo.json` 文件即说明项目使用 Turborepo。

#### `turbo.json` pipeline 配置

```json
{
  "$schema": "https://turbo.build/schema.json",
  "pipeline": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**"]
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": [],
      "inputs": ["src/**", "test/**"]
    },
    "lint": {
      "dependsOn": [],
      "outputs": []
    },
    "dev": {
      "cache": false,
      "persistent": true
    }
  }
}
```

- `dependsOn`：定义任务间的依赖关系，`^build` 表示先执行上游依赖包的 `build`
- `outputs`：声明输出产物目录，用于 Turborepo 远程/本地缓存
- `inputs`：指定影响缓存 key 的输入文件，变更后会触发重新执行
- `cache: false`：禁用缓存（如 `dev` 任务）
- `persistent: true`：标记为长时间运行任务

#### 常用命令

```bash
turbo run test
turbo run build
turbo run test --filter=@scope/core
turbo run test --filter=@scope/core...
turbo run build test lint
```

- `--filter=pkg`：仅执行指定包的任务
- `--filter=pkg...`：执行指定包及其依赖方的任务
- 多个任务名可并列执行

- Turborepo 本身不管理依赖安装，需通过底层包管理器（pnpm/yarn/npm）安装

## 测试框架配置

### Jest

配置文件优先级（从高到低）：
1. `jest.config.ts`
2. `jest.config.js`
3. `jest.config.mjs`
4. `jest.config.cjs`
5. `jest.config.json`
6. `package.json` 中的 `"jest"` 字段

关键配置项：
```js
module.exports = {
  preset: 'ts-jest',           // TypeScript 支持
  testEnvironment: 'node',     // 或 'jsdom'
  testMatch: ['**/*.test.ts'], // 测试文件匹配
  transform: {},               // 转换器配置
  moduleNameMapper: {},        // 路径别名映射
  setupFilesAfterSetup: [],    // 测试环境初始化
};
```

### Vitest

配置文件：`vitest.config.ts` 或 `vite.config.ts` 中的 `test` 字段

```ts
import { defineConfig } from 'vitest/config';
export default defineConfig({
  test: {
    environment: 'node',    // 或 'jsdom', 'happy-dom', 'edge-runtime'
    globals: true,           // 允许不显式 import describe/it/expect
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./vitest.setup.ts'],
    clearMocks: true,        // 每个测试后自动 vi.clearAllMocks()
    restoreMocks: true,      // 每个测试后自动 vi.restoreAllMocks()
  },
});
```

关键特性：
- 基于 Vite 构建，内置 TypeScript / ESM / JSX 支持，无需额外配置转换器
- 如果已有 `vite.config.ts`，可通过 `/// <reference types="vitest/config" />` 添加 `test` 字段
- 独立 `vitest.config.ts` 会**覆盖** `vite.config.ts` 的所有配置（需要时用 `mergeConfig` 合并）
- 路径别名通过 Vite 的 `resolve.alias` 配置，或使用 `vite-tsconfig-paths` 插件
- 运行命令：`npx vitest run <test-file>` 或 `npx vitest run <test-file> --config <config-path>`
- Mock API 使用 `vi` 对象（`vi.mock` / `vi.fn` / `vi.spyOn`）

Vitest 也可复用已有 Vite 配置：
```ts
import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config';

export default mergeConfig(viteConfig, defineConfig({
  test: { exclude: ['packages/template/*'] },
}));
```

### Rstest

配置文件：`rstest.config.ts`（或 `.mjs`、`.js`、`.cjs`、`.mts`、`.cts`）

```ts
import { defineConfig } from '@rstest/core';
export default defineConfig({
  testEnvironment: 'node',   // 或 'jsdom', 'happy-dom'
  globals: true,              // 允许不显式 import describe/it/expect
  include: ['src/**/*.{test,spec}.{ts,tsx}'],
  setupFiles: ['./rstest.setup.ts'],
});
```

关键特性：
- 基于 Rspack 构建，内置 SWC 转译，原生支持 TypeScript 和 ESM
- 提供 Jest 兼容 API，使用 `rs`（或 `rstest`）替代 `jest` / `vi`
- 支持 Rsbuild/Rslib/Rspack adapter 复用已有构建配置
- 路径别名通过 Rsbuild 的 `resolve.alias` 配置
- 运行命令：`npx rstest run <test-file>` 或 `npx rstest run <test-file> --config <config-path>`

## TypeScript 配置

### 路径别名

如果 `tsconfig.json` 配置了 `paths`，测试框架也需要对应映射：

```json
// tsconfig.json
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"],
      "@utils/*": ["./src/utils/*"]
    }
  }
}
```

Jest 需要在 `moduleNameMapper` 中配置：
```js
moduleNameMapper: {
  '^@/(.*)$': '<rootDir>/src/$1',
  '^@utils/(.*)$': '<rootDir>/src/utils/$1',
}
```

Vitest 通过 Vite 的 `resolve.alias` 继承路径别名。如果 `tsconfig.json` 使用了 `baseUrl`/`paths`，可通过 `vite-tsconfig-paths` 插件或手动在 `resolve.alias` 中配置（MUST NOT 使用相对路径）。

### 严格模式注意事项

如果 `tsconfig.json` 开启了 `strict: true`，需要注意：
- Mock 对象的类型可能需要显式断言
- 使用 `as jest.Mock` 或 `as unknown as Type` 处理类型不匹配
- 确保异步函数返回 `Promise<void>` 类型
