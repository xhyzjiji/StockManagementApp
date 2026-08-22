# React 单测参考指南

## 概述

React 是用于构建用户界面的 JavaScript 库，采用组件化 + 声明式范式。测试 React 代码的核心挑战在于：Hooks 的状态管理与副作用、组件渲染与交互、Context 传递、异步操作。本文档聚焦于生成单元测试时需要了解的 React 核心概念和模式。

> **测试 React 组件时，还需配合 `assets/javascript/references/testing-library.md` 一起使用。**

## Hooks 测试要点

### 状态类 Hooks

| Hook | 用途 | 测试关注点 |
|---|---|---|
| `useState` | 组件内部状态 | 验证初始值、状态更新后的 UI 变化 |
| `useReducer` | 复杂状态逻辑 | 验证 dispatch 不同 action 后的状态变化 |

**测试模式**：状态变更必须用 `act()` 包裹，触发事件（`fireEvent` / `userEvent`）来间接验证状态变化在 UI 上的体现。

```tsx
import { render, screen, fireEvent } from '@testing-library/react';

test('counter increments', () => {
  render(<Counter />);
  fireEvent.click(screen.getByRole('button', { name: /increment/i }));
  expect(screen.getByText('1')).toBeInTheDocument();
});
```

### 副作用类 Hooks

| Hook | 用途 | 测试关注点 |
|---|---|---|
| `useEffect` | 副作用（数据获取、订阅、DOM 操作） | 验证副作用执行和清理函数调用 |
| `useLayoutEffect` | 同步副作用（DOM 测量） | 与 `useEffect` 测试方式类似 |

**测试模式**：
- 数据获取：mock API 调用，验证加载态 → 成功态/错误态的转换
- 订阅/事件监听：验证 mount 时订阅、unmount 时取消订阅
- 定时器：使用 `jest.useFakeTimers()` / `vi.useFakeTimers()` 控制时间

```tsx
test('fetches data on mount', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue({
    json: () => Promise.resolve({ name: 'Alice' }),
  } as Response);

  render(<UserProfile userId="1" />);

  await waitFor(() => {
    expect(screen.getByText('Alice')).toBeInTheDocument();
  });
});

test('cleans up subscription on unmount', () => {
  const unsubscribe = jest.fn();
  jest.spyOn(eventBus, 'subscribe').mockReturnValue(unsubscribe);

  const { unmount } = render(<Subscriber />);
  unmount();

  expect(unsubscribe).toHaveBeenCalled();
});
```

### 缓存类 Hooks

| Hook | 用途 | 测试关注点 |
|---|---|---|
| `useMemo` | 缓存计算结果 | 通常不需专门测试，验证组件行为即可 |
| `useCallback` | 缓存函数引用 | 通常不需专门测试，验证回调行为即可 |

**单测建议**：不要测试 `useMemo` / `useCallback` 的缓存行为本身（这是 React 内部实现），只测试它们包裹的逻辑产出的结果是否正确。

### Ref 类 Hooks

| Hook | 用途 | 测试关注点 |
|---|---|---|
| `useRef` | 持有可变引用（DOM 节点或任意值） | DOM ref 通常不需测试；值 ref 验证引用保持 |
| `useImperativeHandle` | 暴露自定义 ref 方法 | 验证暴露的方法是否可调用且行为正确 |

```tsx
test('exposes focus method via ref', () => {
  const ref = React.createRef<{ focus: () => void }>();
  render(<CustomInput ref={ref} />);

  act(() => {
    ref.current?.focus();
  });

  expect(document.activeElement).toBe(screen.getByRole('textbox'));
});
```

### Context 相关

| API | 用途 | 测试关注点 |
|---|---|---|
| `createContext` | 创建 Context | — |
| `useContext` | 消费 Context 值 | 验证不同 Context 值下组件的行为 |

**测试模式**：通过 `render` 的 `wrapper` 选项提供 Provider，控制 Context 值。

```tsx
const ThemeContext = React.createContext('light');

test('renders dark theme', () => {
  render(<ThemedButton />, {
    wrapper: ({ children }) => (
      <ThemeContext.Provider value="dark">{children}</ThemeContext.Provider>
    ),
  });
  expect(screen.getByRole('button')).toHaveClass('dark');
});
```

### 异步/并发 Hooks

| Hook | 用途 | 测试关注点 |
|---|---|---|
| `useTransition` | 标记低优先级状态更新 | 验证 `isPending` 状态和过渡完成后的 UI |
| `useDeferredValue` | 延迟更新值 | 验证最终 UI 正确性 |
| `useSyncExternalStore` | 订阅外部 store | 验证 store 变化时组件更新 |

## 组件模式与测试

### 函数组件

React 组件是返回 JSX 的函数。测试时直接 `render(<Component />)` 并验证输出。

### Props 测试

```tsx
test('renders with different props', () => {
  const { rerender } = render(<Greeting name="Alice" />);
  expect(screen.getByText('Hello, Alice')).toBeInTheDocument();

  rerender(<Greeting name="Bob" />);
  expect(screen.getByText('Hello, Bob')).toBeInTheDocument();
});
```

### 条件渲染

```tsx
test('shows error when isError is true', () => {
  render(<Status isError={true} message="Failed" />);
  expect(screen.getByText('Failed')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toBeInTheDocument();
});

test('shows nothing when isError is false', () => {
  render(<Status isError={false} message="Failed" />);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
```

### 列表渲染

```tsx
test('renders list items', () => {
  const items = [{ id: '1', name: 'A' }, { id: '2', name: 'B' }];
  render(<ItemList items={items} />);
  expect(screen.getAllByRole('listitem')).toHaveLength(2);
});
```

### 表单与受控组件

```tsx
import userEvent from '@testing-library/user-event';

test('updates input value', async () => {
  const user = userEvent.setup();
  render(<SearchForm onSubmit={jest.fn()} />);

  await user.type(screen.getByRole('textbox'), 'hello');
  expect(screen.getByRole('textbox')).toHaveValue('hello');
});
```

### 回调 Props

```tsx
test('calls onSubmit with form data', async () => {
  const handleSubmit = jest.fn();
  const user = userEvent.setup();

  render(<LoginForm onSubmit={handleSubmit} />);

  await user.type(screen.getByLabelText('Email'), 'a@b.com');
  await user.click(screen.getByRole('button', { name: /submit/i }));

  expect(handleSubmit).toHaveBeenCalledWith({ email: 'a@b.com' });
});
```

## 高阶模式

### `memo` 包裹的组件

`React.memo` 会跳过 props 未变化时的重渲染。测试时无需关注 memo 优化行为，只需验证组件功能正确。

### `forwardRef` 组件

测试通过 ref 暴露的 DOM 节点或自定义方法。

### `lazy` + `Suspense`

```tsx
test('shows fallback while loading', async () => {
  render(
    <Suspense fallback={<div>Loading...</div>}>
      <LazyComponent />
    </Suspense>
  );

  expect(screen.getByText('Loading...')).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
  });
});
```

### Error Boundary

测试 Error Boundary 时需要模拟子组件抛出错误：

```tsx
test('catches rendering error', () => {
  const spy = jest.spyOn(console, 'error').mockImplementation(() => {});

  const ThrowError = () => { throw new Error('boom'); };

  render(
    <ErrorBoundary fallback={<div>Something went wrong</div>}>
      <ThrowError />
    </ErrorBoundary>
  );

  expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  spy.mockRestore();
});
```

### Portal（`createPortal`）

Portal 将子组件渲染到 DOM 中的不同位置。测试时 Portal 内容仍可通过 `screen` 查询到，无需特殊处理。

## 自定义 Hook 测试

使用 `renderHook` 独立测试自定义 Hook：

```tsx
import { renderHook, act } from '@testing-library/react';

test('useToggle switches value', () => {
  const { result } = renderHook(() => useToggle(false));

  expect(result.current[0]).toBe(false);

  act(() => {
    result.current[1](); // toggle
  });

  expect(result.current[0]).toBe(true);
});
```

**依赖 Context 的 Hook**：通过 `wrapper` 注入 Provider。

```tsx
const { result } = renderHook(() => useTheme(), {
  wrapper: ({ children }) => (
    <ThemeProvider value="dark">{children}</ThemeProvider>
  ),
});
```

## 常见 Mock 场景

| Mock 目标 | 方法 |
|---|---|
| API 请求（`fetch` / `axios`） | `jest.spyOn(global, 'fetch')` 或 MSW |
| 路由（`react-router`） | mock `useNavigate`、`useParams`、`useLocation`，或用 `MemoryRouter` 包裹 |
| 定时器（`setTimeout` 等） | `jest.useFakeTimers()` / `vi.useFakeTimers()` |
| `window` 属性 | `Object.defineProperty(window, 'prop', { value: ... })` |
| 子组件 | `jest.mock('./ChildComponent', () => ({ ChildComponent: () => <div data-testid="child" /> }))` |
| 第三方库 | `jest.mock('library-name')` |
| `IntersectionObserver` | 全局 mock 构造函数 |
| `matchMedia` | `Object.defineProperty(window, 'matchMedia', ...)` |
| `ResizeObserver` | 全局 mock 构造函数 |

### 路由 Mock 示例

```tsx
import { MemoryRouter, Route, Routes } from 'react-router-dom';

test('renders page with route params', () => {
  render(
    <MemoryRouter initialEntries={['/users/123']}>
      <Routes>
        <Route path="/users/:id" element={<UserPage />} />
      </Routes>
    </MemoryRouter>
  );

  expect(screen.getByText('User 123')).toBeInTheDocument();
});
```

### 状态管理库 Mock

- **MobX**：直接创建 store 实例，通过 Provider 注入
- **Redux**：使用 `configureStore` 创建测试 store，用 `<Provider>` 包裹
- **Zustand**：mock store 模块或使用 `create` 创建测试 store

## 关键导入来源

```ts
// React 核心
import React, { useState, useEffect, useRef, useCallback, useMemo, useContext,
  useReducer, useImperativeHandle, useMemo, createContext, forwardRef, memo,
  Suspense, lazy, Fragment } from 'react';

// React DOM
import ReactDOM from 'react-dom';
import { createPortal } from 'react-dom';
import { createRoot } from 'react-dom/client';

// 测试相关（详见 testing-library.md）
import { render, screen, fireEvent, waitFor, renderHook, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
```
