# Mock 指南

## Mock Hoisting 机制

`jest.mock()` / `vi.mock()` / `rs.mock()` 调用会被框架**自动提升（hoist）**到文件顶部执行，在所有 `import` 和 `let`/`const` 声明之前。这意味着：

- 工厂函数中**不能引用**文件顶部用 `let`/`const` 声明的变量（暂时性死区 TDZ）
- 工厂函数中**不能使用** `import` 导入的模块（因为 mock 在 import 之前执行）

### 安全模式

**模式 1：jest.fn() 占位 + beforeEach 配置**
```ts
const mockFn = jest.fn();
jest.mock('./service', () => ({
  fetchData: mockFn,
}));

beforeEach(() => {
  mockFn.mockReturnValue({ data: 'test' });
});
```

**模式 2：getter 惰性求值**
```ts
let mockState: Record<string, any> = {};
jest.mock('./store', () => ({
  get state() { return mockState; },
}));

beforeEach(() => {
  mockState = { user: { name: 'test' } };
});
```

**模式 3：工厂内 require()**
```ts
jest.mock('./utils', () => {
  const actual = require('./utils');
  return {
    ...actual,
    formatDate: jest.fn(),
  };
});
```

**模式 4：jest.requireMock() 获取引用**
```ts
jest.mock('./api', () => ({
  request: jest.fn(),
}));

// 在 mock 声明之后获取引用
const { request: mockRequest } = jest.requireMock('./api');
```

### 危险模式

```ts
// ❌ TDZ 错误：mockFn 在 jest.mock 提升后尚未初始化
const mockFn = jest.fn();
jest.mock('./mod', () => ({ fn: mockFn }));

// ❌ 引用外部 import
import { helper } from './helper';
jest.mock('./mod', () => ({ fn: helper }));

// ❌ 在工厂中使用 import 语句
jest.mock('./mod', () => {
  import { x } from './other'; // SyntaxError
  return { x };
});
```

## Babel 环境下的特殊约束

当项目使用 Babel 转译（而非 ts-jest / @swc/jest）时，jest.mock 工厂函数被 Babel parser 单独解析，**不经过 TypeScript 转译**。

### 禁止事项

1. **禁止 `import type`**：改用 `import { X }`
2. **禁止工厂内类型注解**：
   - ❌ `(x: string) => x`
   - ✅ `(x) => x`
3. **禁止 `as` 断言**：
   - ❌ `value as MyType`
   - ✅ 直接使用值，或用 `// @ts-expect-error` 消除类型警告
4. **禁止泛型调用语法**：
   - ❌ `create<MyType>()`（Babel 误解析为 JSX）
   - ✅ `(create as any)()`

### tsc 隐式 any 冲突

在 Babel 环境下，以下 tsc 错误无法通过添加类型注解修复（会导致 Babel SyntaxError）：
- TS7006：Parameter implicitly has 'any' type
- TS7031：Binding element implicitly has 'any' type
- TS7005：Variable implicitly has 'any' type

**修复方式**：在报错行上方添加 `// @ts-expect-error`，不要添加类型注解。

## ESM 环境下的特殊约束

当项目使用 ES Module（`"type": "module"`）且框架为 Jest（非 Vitest）时：

- `require()` 可能不可用
- 改用 `jest.unstable_mockModule()` 或顶层 `import`
- `jest.mock()` 工厂函数中不能使用 `import` 语句

## 部分 Mock

当只需要 mock 模块中的部分导出时：

**Jest**：
```ts
jest.mock('./module', () => ({
  ...jest.requireActual('./module'),
  targetFn: jest.fn(),
}));
```

**Vitest**：
```ts
vi.mock('./module', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    targetFn: vi.fn(),
  };
});
```

**Rstest**：
```ts
rs.mock('./module', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    targetFn: rs.fn(),
  };
});
```

## Virtual Mock

对于无法在测试运行时解析的模块路径（如路径别名缺少 moduleNameMapper 映射）：

```ts
jest.mock('@/utils/someModule', () => ({
  someExport: jest.fn(),
}), { virtual: true });
```

`{ virtual: true }` 告诉 Jest 此模块不需要在文件系统上存在。

## Timer Mock

### Jest
```ts
jest.useFakeTimers();

// 快进所有计时器
jest.runAllTimers();

// 快进指定时间
jest.advanceTimersByTime(1000);

// 恢复真实计时器
jest.useRealTimers();
```

### Vitest
```ts
vi.useFakeTimers();
vi.runAllTimers();
vi.advanceTimersByTime(1000);
vi.useRealTimers();
```

## 全局对象 Mock

### 只读属性
```ts
// ❌ 直接赋值只读属性会报 TypeError
window.performance = mockPerf;

// ✅ 使用 Object.defineProperty
Object.defineProperty(window, 'performance', {
  value: mockPerf,
  writable: true,
});

// ✅ 使用 jest.spyOn
jest.spyOn(window, 'matchMedia').mockImplementation(query => ({
  matches: false,
  media: query,
  // ...
}));
```

### 清理
在 `afterEach` 中恢复原始值或调用 `jest.restoreAllMocks()`，避免测试间状态泄漏。
