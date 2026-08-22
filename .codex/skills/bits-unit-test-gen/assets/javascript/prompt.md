# JavaScript & TypeScript 语言专属 Prompt

## 核心流程

### STEP0：环境检测与知识准备（必须在写测试之前完成）

> **⚠️ 硬性前置要求**：在生成任何测试代码之前，**必须**完成本步骤的环境检测和文档查阅。未读取相关参考文档就直接编写测试，视为流程违规。这是确保测试质量的关键步骤——不同框架、不同工程环境下的 Mock API、import 方式、验证命令差异巨大，跳过此步骤几乎必然导致后续反复修复。

#### 0.1 环境检测

根据目标文件的实际情况进行检测。具体检测方式参考 `assets/javascript/references/detector.md`（**必须先 Read 该文件**了解如何检测）：

1. **测试框架**（必须）：确认项目使用 Jest / Vitest / Rstest，以决定 import 方式和 Mock API
2. **已有测试文件**（必须）：查看目标文件是否已有对应的测试文件，有则增量补充
3. **相邻测试风格**（必须）：参考同目录或同模块其他测试文件的 import、mock 模式、断言风格
4. **测试文件放置规则**（推荐）：当不确定测试文件应放在哪里时检测
5. **Babel / ESM 约束**（推荐）：当遇到 SyntaxError 或模块加载错误时检测

#### 0.2 查阅参考文档

检测完成后，**必须**根据检测结果 Read 对应的参考文档。这些文档包含了框架专属的 API 用法、Mock 模式、常见陷阱等关键信息，直接影响生成质量。

**必读**（根据检测到的框架选择对应文档）：
- 确认框架后 → Read `assets/javascript/references/Jest.md` 或 `assets/javascript/references/Vitest.md` 或 `assets/javascript/references/Rstest.md`
- 涉及 Mock → Read `assets/javascript/references/mock-guidelines.md`

**按需读取**（根据目标文件特征判断）：
- 涉及 React 组件 → Read `assets/javascript/references/React.md` 和 `assets/javascript/references/testing-library.md`
- 涉及 Vue 组件 → Read `assets/javascript/references/Vue.md`
- 涉及 Lynx / ReactLynx 组件 → Read `assets/javascript/references/Lynx.md`
- 工程环境有疑问（monorepo、包管理器等）→ Read `assets/javascript/references/engineering.md`

**修复阶段使用**：
- 遇到错误需排查 → Read `assets/javascript/references/troubleshooting.md`

### 上下文分析（覆盖通用流程）

> **⚠️ JS/TS 场景不使用 `utree context` 命令**。该命令不适用于 JavaScript / TypeScript 项目，请勿调用。

上下文分析由 agent 自行完成，按需使用 Read 工具直接阅读源文件及其依赖模块即可。推荐的分析方式：

1. **Read 目标源文件**：理解函数签名、内部逻辑、分支条件
2. **Read 直接依赖**：查看 import 的模块，了解外部函数的签名和行为，以决定 mock 策略
3. **Read 已有测试文件**（如存在）：了解现有测试覆盖情况，避免重复，保持风格一致
4. **Read 同目录/同模块的其他测试文件**：参考项目测试惯例（import 方式、mock 模式、断言风格）

无需一次性分析所有依赖，根据实际需要逐步展开即可。

### STEP1：生成测试用例

为目标文件生成单元测试。一个源文件对应一个测试文件，测试文件放置须符合项目的 testMatch 配置。

**要求**：
- 已有测试文件时增量补充，不要全量重写
- 每个待测单元覆盖 happy path、边界值、异常路径
- 必须使用 Write/Edit 工具写入测试文件（无写入操作 = 任务失败）
- 复用项目现有的测试风格和 Mock 模式
- 在生成的测试代码中，每个测试用例在执行之前记录开始时间，在执行之后记录结束时间，并打印该测试用例的执行时间，便于性能分析。

```ts
test('example', () => {
  const startTime = performance.now();
  // 测试代码
  expect(someFunction()).toBe(expected);
  const endTime = performance.now();
  console.log(`test example executed in: ${(endTime - startTime).toFixed(6)}ms`);
});
```

**Mock API**：
- **Jest**：`jest.fn()` / `jest.mock()` / `jest.spyOn()`。部分 mock：`jest.mock('./module', () => ({ ...jest.requireActual('./module'), fn: jest.fn() }))`
- **Vitest**：`vi.fn()` / `vi.mock()` / `vi.spyOn()`。部分 mock：`vi.mock('./module', async (importOriginal) => { ... })`
- **Rstest**：`rs.fn()` / `rs.mock()` / `rs.spyOn()`

**Mock Hoisting 约束（全框架通用）**：
`jest.mock()` / `vi.mock()` / `rs.mock()` 工厂函数会被**提升**到文件顶部，在任何 `let`/`const` 声明之前执行。在工厂内引用这些变量会导致 `ReferenceError: Cannot access 'xxx' before initialization`（暂时性死区）。
- ❌ `let mockState = { foo: 'bar' }; jest.mock('./mod', () => ({ state: mockState }))`
- ✅ 用 `jest.fn()` 占位 + `beforeEach` 配置：`const mockFn = jest.fn(); jest.mock('./mod', () => ({ fn: mockFn })); beforeEach(() => { mockFn.mockReturnValue(...) })`
- ✅ getter 惰性求值：`let state = {}; jest.mock('./mod', () => ({ get data() { return state; } }))`
- ✅ 工厂内用 `require()`：`jest.mock('./mod', () => { return { fn: jest.fn() }; })`

### STEP2：验证与修复循环（最多 10 轮）

生成测试后，自行验证测试文件的正确性，根据错误输出修复问题，循环直到全部通过。

#### 验证项（全部必须通过）

1. **测试执行**：运行测试文件，确保所有用例通过。根据 STEP0 检测到的测试框架（Jest / Vitest / Rstest）和项目的包管理器，自行构造并执行正确的运行命令。
2. **TypeScript 类型检查**：对 `.ts` / `.tsx` 测试文件检查类型错误。仅关注与测试文件相关的错误，忽略源文件自身的类型问题。
3. **Lint 检查**：检测项目使用的 lint 工具（ESLint、Biome、Prettier 等），对测试文件执行检查。先尝试自动修复，再检查是否仍有报错。如果项目未配置 lint 工具则跳过。

#### 执行策略

采用**分阶段执行**以节省时间：先运行测试，测试通过后再执行 tsc 和 lint。测试未通过时无需执行后续检查。

**tsc / lint 的检查方式**：优先利用 IDE 诊断能力（如 GetDiagnostics），写入测试文件后直接获取 IDE 对该文件的诊断信息，error 级别的诊断即为需修复的问题——这比执行命令更快且无需关心包管理器和配置路径。仅当 IDE 诊断不可用或结果不可靠时，再回退到命令行执行 tsc / lint。

#### 修复要求

- 仔细阅读错误输出，定位根因并修复。常见错误参考 `assets/javascript/references/troubleshooting.md`
- 不要因为一两次失败就放弃，大多数错误在 2-3 次不同尝试后都能解决
- 如果连续 3 轮修复同一个错误仍未解决，停下来反思整体思路，考虑删除测试文件从头重写
- 如果某个用例确实无法通过，删除它，把精力放在能通过的用例上——部分成功远好于全部失败
- 测试执行超时（死锁、无限循环、依赖未启动的外部服务）属于不可恢复错误，其他所有错误都应视为可修复的

#### 退出条件

测试全部通过 + tsc 无类型错误 + lint 无报错。不要提交包含失败用例的测试文件。

---

## 约束

- 不要修改业务源代码（非测试文件的 `.ts`、`.tsx`、`.js`、`.jsx` 等）
- 只允许创建或修改测试文件（*.test.ts、*.test.tsx、*.spec.ts、*.spec.tsx 等）
- 不要弱化断言来让测试通过
- 已有测试文件增量补充，不要全量重写

## 核心信念

几乎所有测试错误都是可以修复的。当你遇到困难时，这不是放弃的理由，而是展现能力的机会。每一个报错都包含了修复的线索——仔细阅读错误信息，换个角度思考，总能找到出路。空手而归（没有任何通过的测试用例）是最差的结果。即使只能保留一个通过的用例，也远好于零产出。

## 参考文档目录

所有参考文档位于 `assets/javascript/references/` 下，按需查阅：

| 文档 | 用途 |
|---|---|
| `assets/javascript/references/detector.md` | 工程环境检测方式（STEP0 指引） |
| `assets/javascript/references/Jest.md` | Jest 框架 API 和常见问题 |
| `assets/javascript/references/Vitest.md` | Vitest 框架 API 和常见问题 |
| `assets/javascript/references/Rstest.md` | Rstest 框架 API 和常见问题 |
| `assets/javascript/references/testing-library.md` | React 组件测试（@testing-library） |
| `assets/javascript/references/React.md` | React 核心概念与单测模式 |
| `assets/javascript/references/Vue.md` | Vue 核心概念与单测模式（@vue/test-utils） |
| `assets/javascript/references/Lynx.md` | Lynx / ReactLynx 组件单测参考 |
| `assets/javascript/references/mock-guidelines.md` | Mock 模式、Hoisting、Babel/ESM 约束 |
| `assets/javascript/references/troubleshooting.md` | 错误诊断与修复策略 |
| `assets/javascript/references/engineering.md` | 包管理器、Monorepo 等工程实践 |
