# 工程环境检测方式

在生成测试之前，按需检测项目的工程环境。不需要检测所有项目，根据目标文件的实际情况选择性检测即可。

---

## 测试框架识别（必须）

从目标文件目录逐级向上查找，确认项目使用 Jest / Vitest / Rstest。

**推荐检测方式**：
1. **查找配置文件**：检查目标文件到项目根路径上是否存在框架配置文件
   - Jest：`jest.config.{ts,js,mjs,cjs,json}`
   - Vitest：`vitest.config.{ts,js,mts,mjs}`
   - Rstest：`rstest.config.{ts,js,mjs,mts,cjs,cts}`
2. **查看 package.json 依赖**：检查 devDependencies 中的框架包名
   - `vitest` → Vitest
   - `@rstest/core` → Rstest
   - `jest` / `@types/jest` → Jest
3. **兜底**：默认 Jest

> 在 monorepo 场景下，配置文件优先于 package.json 依赖，因为根 package.json 可能同时包含多个框架。

## 已有测试文件查找（推荐）

检查目标文件是否已有对应的测试文件，有则增量补充而非全量新建。

**推荐检测方式**：
- 在目标文件同目录或 `__tests__/` 子目录中查找同名的 `.test.{ts,tsx}` 或 `.spec.{ts,tsx}` 文件
- 例如 `src/utils.ts` → 查找 `src/utils.test.ts`、`src/__tests__/utils.test.ts`

## 相邻测试风格参考（推荐）

参考同目录已有测试文件的 import 方式、mock 模式、describe/it 组织风格，保持一致。

**推荐检测方式**：
- 在目标文件同目录用 Glob 搜索 `*.test.*` / `*.spec.*`
- 读取 1-2 个相邻测试文件的头部 import 和 mock 声明部分

## 测试文件放置规则（按需）

当不确定测试文件应放在哪里时检测。

**推荐检测方式**：
- 从框架配置文件中查找 `testMatch`、`testPathIgnorePatterns`、`testRegex`（Jest）或 `include`（Vitest）
- 参考项目中已有测试文件的放置模式（Glob 搜索 `**/*.test.*`）
- 如果源文件所在目录被排除，将测试文件放到 `__tests__/` 或 `src/__tests__/` 下

## Babel Transform 约束（按需）

当 jest.mock 工厂中出现 SyntaxError 时检测。仅对 Jest 框架生效。

**推荐检测方式**：
- 读取 jest 配置文件，检查 `transform` 字段
- 包含 `ts-jest` 或 `@swc/jest` → 支持 TS 语法
- 包含 `babel-jest` 或无 transform → Babel 转译，jest.mock 工厂中禁止 TS 语法

**影响**：使用 Babel 时：
- `import type { X }` 改为 `import { X }`
- jest.mock 工厂内禁止类型注解和 `as` 断言
- tsc 报 implicit-any 时用 `// @ts-expect-error` 消除

## ES Module 约束（按需）

当遇到 `require is not defined` 或模块加载错误时检测。

**推荐检测方式**：
- 检查 package.json 中是否有 `"type": "module"`

**影响**：ESM 模式下：
- `require()` 不可用，改用 `jest.unstable_mockModule()` 或顶层 `import`

## tsconfig 路径别名（按需）

当源文件中有非相对路径 import（如 `@/utils`）时检测。

**推荐检测方式**：
- 从目标文件目录向上查找 `tsconfig.json`、`tsconfig.base.json`
- 提取 `compilerOptions.baseUrl` 和 `compilerOptions.paths`

## 导出符号分析（按需）

当需要理解源文件中有哪些可测单元时。

**推荐检测方式**：
- 读取源文件内容，关注 `export` 开头的声明
- 注意**分离式默认导出**模式：组件先声明后 `export default Comp`，测试时用默认导入

## 仓库指南（按需）

当项目可能有特殊测试约定时。

**推荐检测方式**：
- 查找项目根目录或子包根目录下的 `AGENTS.md`
- 提取与 test / mock / lint / style 相关的段落
