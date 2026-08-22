# @testing-library 使用指南

## 概述

@testing-library 是一组以用户视角进行 UI 测试的工具库，核心原则：测试应模拟用户实际交互方式。

## 核心包

| 包名 | 用途 |
|---|---|
| `@testing-library/react` | React 组件渲染与查询 |
| `@testing-library/dom` | 底层 DOM 查询 |
| `@testing-library/jest-dom` | 扩展 Jest 断言（`toBeInTheDocument` 等） |
| `@testing-library/user-event` | 高级用户交互模拟 |

## 基本用法

### 渲染组件

```tsx
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MyComponent } from './MyComponent';

test('renders component', () => {
  render(<MyComponent title="Hello" />);
  expect(screen.getByText('Hello')).toBeInTheDocument();
});
```

### 重新渲染（测试 Props 变化）

`render` 返回的 `rerender` 方法可以用新的 props 重新渲染组件，适用于测试组件对 props 变化的响应：

```tsx
import { render, screen } from '@testing-library/react';

test('updates title when props change', () => {
  const { rerender } = render(<MyComponent title="Hello" />);
  expect(screen.getByText('Hello')).toBeInTheDocument();

  rerender(<MyComponent title="World" />);
  expect(screen.getByText('World')).toBeInTheDocument();
  expect(screen.queryByText('Hello')).not.toBeInTheDocument();
});
```

### 卸载（测试清理逻辑）

`render` 返回的 `unmount` 方法用于手动卸载组件，适用于测试副作用清理（如事件监听器移除、定时器清理等）：

```tsx
import { render } from '@testing-library/react';

test('cleans up event listener on unmount', () => {
  const removeListener = vi.fn();
  vi.spyOn(window, 'addEventListener').mockImplementation(() => {});
  vi.spyOn(window, 'removeEventListener').mockImplementation(removeListener);

  const { unmount } = render(<WindowResizeTracker />);
  unmount();

  expect(removeListener).toHaveBeenCalled();
});
```

### 作用域查询（within）

`within` 可将查询范围限定在某个容器元素内，适用于页面中有多个相似结构的场景：

```tsx
import { render, screen, within } from '@testing-library/react';

test('finds item in specific list', () => {
  render(<Dashboard />);

  const nav = screen.getByRole('navigation');
  const navLinks = within(nav).getAllByRole('link');
  expect(navLinks).toHaveLength(3);

  const main = screen.getByRole('main');
  expect(within(main).getByText('Welcome')).toBeInTheDocument();
});
```

### 查询优先级（MUST 遵循）

按优先级从高到低使用查询方式：

1. **`getByRole`** — 最推荐，按 ARIA role 查询
2. **`getByLabelText`** — 表单元素
3. **`getByPlaceholderText`** — 输入框
4. **`getByText`** — 按文本内容查询
5. **`getByDisplayValue`** — 表单当前值
6. **`getByAltText`** — 图片 alt
7. **`getByTitle`** — title 属性
8. **`getByTestId`** — 最后手段，需要添加 `data-testid`

### 用户交互

#### fireEvent（基础）

```tsx
import { fireEvent } from '@testing-library/react';

fireEvent.click(screen.getByRole('button'));
fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hello' } });
```

#### userEvent（推荐）

```tsx
import userEvent from '@testing-library/user-event';

const user = userEvent.setup();

await user.click(screen.getByRole('button'));
await user.type(screen.getByRole('textbox'), 'hello');
await user.selectOptions(screen.getByRole('combobox'), 'option1');
```

### 异步操作

```tsx
import { waitFor, screen } from '@testing-library/react';

// 等待元素出现
await waitFor(() => {
  expect(screen.getByText('Loaded')).toBeInTheDocument();
});

// 或使用 findBy（自带等待）
const element = await screen.findByText('Loaded');
```

### 等待元素移除（waitForElementToBeRemoved）

`waitForElementToBeRemoved` 用于等待元素从 DOM 中消失，常见于 loading 状态消失、弹窗关闭等场景：

```tsx
import { render, screen, waitForElementToBeRemoved } from '@testing-library/react';

test('loading spinner disappears after data loads', async () => {
  render(<DataList />);

  expect(screen.getByText('Loading...')).toBeInTheDocument();

  await waitForElementToBeRemoved(() => screen.queryByText('Loading...'));

  expect(screen.getByText('Data loaded')).toBeInTheDocument();
});
```

> ⚠️ 注意：回调中 MUST 使用 `queryBy` 而非 `getBy`，因为元素消失后 `getBy` 会抛出异常。

## 测试 React Hooks

### renderHook 基本用法

`renderHook` 用于独立测试自定义 Hook，无需创建额外的测试组件：

```tsx
import { renderHook, act } from '@testing-library/react';
import { useCounter } from './useCounter';

test('increments counter', () => {
  const { result } = renderHook(() => useCounter(0));

  expect(result.current.count).toBe(0);

  act(() => {
    result.current.increment();
  });

  expect(result.current.count).toBe(1);
});
```

### renderHook 的 rerender

通过 `rerender` 可以用新的参数重新执行 Hook，测试 Hook 对参数变化的响应：

```tsx
import { renderHook } from '@testing-library/react';
import { useFormattedPrice } from './useFormattedPrice';

test('updates formatted price when value changes', () => {
  const { result, rerender } = renderHook(
    ({ price }) => useFormattedPrice(price),
    { initialProps: { price: 100 } }
  );

  expect(result.current).toBe('$100.00');

  rerender({ price: 200 });

  expect(result.current).toBe('$200.00');
});
```

### renderHook 与异步操作

对于包含异步逻辑的 Hook，结合 `waitFor` 等待状态更新：

```tsx
import { renderHook, waitFor } from '@testing-library/react';
import { useFetchUser } from './useFetchUser';

test('fetches user data', async () => {
  const { result } = renderHook(() => useFetchUser('123'));

  expect(result.current.loading).toBe(true);

  await waitFor(() => {
    expect(result.current.loading).toBe(false);
  });

  expect(result.current.data).toEqual({ id: '123', name: 'Alice' });
});
```

## 自定义 Wrapper（Provider 包装器）

当组件或 Hook 依赖 Context（如主题、状态管理、路由等）时，需要通过 `wrapper` 选项提供 Provider 包装：

### 组件渲染使用 wrapper

```tsx
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from './ThemeContext';
import { BrowserRouter } from 'react-router-dom';
import { ThemedNav } from './ThemedNav';

const AllProviders = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>
    <ThemeProvider value="dark">
      {children}
    </ThemeProvider>
  </BrowserRouter>
);

test('renders nav with dark theme', () => {
  render(<ThemedNav />, { wrapper: AllProviders });
  expect(screen.getByRole('navigation')).toHaveClass('dark');
});
```

### renderHook 使用 wrapper

```tsx
import { renderHook, act } from '@testing-library/react';
import { StoreProvider } from './store';
import { useCart } from './useCart';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <StoreProvider>{children}</StoreProvider>
);

test('adds item to cart', () => {
  const { result } = renderHook(() => useCart(), { wrapper });

  act(() => {
    result.current.addItem({ id: '1', name: 'Item' });
  });

  expect(result.current.items).toHaveLength(1);
});
```

### 创建可复用的自定义 render

将 Provider 包装抽象为自定义 render 函数，避免在每个测试中重复配置：

```tsx
import { render, RenderOptions } from '@testing-library/react';
import { ThemeProvider } from './ThemeContext';
import { StoreProvider } from './store';

const AllProviders = ({ children }: { children: React.ReactNode }) => (
  <StoreProvider>
    <ThemeProvider>
      {children}
    </ThemeProvider>
  </StoreProvider>
);

const customRender = (
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) => render(ui, { wrapper: AllProviders, ...options });

export { customRender as render };
```

## MSW（Mock Service Worker）集成

MSW 通过拦截网络请求实现 API Mock，比直接 mock `fetch` 或 `axios` 更贴近真实场景。

### 基本配置

```tsx
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

const server = setupServer(
  http.get('/api/users', () => {
    return HttpResponse.json([
      { id: '1', name: 'Alice' },
      { id: '2', name: 'Bob' },
    ]);
  }),

  http.post('/api/users', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: '3', ...body }, { status: 201 });
  })
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

### 在测试中使用

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UserList } from './UserList';

test('displays users from API', async () => {
  render(<UserList />);

  await waitFor(() => {
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });
});
```

### 单个测试覆盖 Handler

使用 `server.use()` 在特定测试中覆盖默认的 Handler，常用于测试错误场景：

```tsx
import { http, HttpResponse } from 'msw';

test('shows error when API fails', async () => {
  server.use(
    http.get('/api/users', () => {
      return HttpResponse.json(
        { message: 'Internal Server Error' },
        { status: 500 }
      );
    })
  );

  render(<UserList />);

  await waitFor(() => {
    expect(screen.getByText('Failed to load users')).toBeInTheDocument();
  });
});
```

## 常见错误

### "Unable to find role" 

组件可能没有正确的 ARIA role。使用 `screen.debug()` 查看渲染的 DOM 结构。

### "not wrapped in act(...)"

异步状态更新未被正确等待。使用 `waitFor` 或 `findBy` 查询。

### 测试文件使用 .ts 而非 .tsx

React 组件测试 MUST 使用 `.tsx` / `.jsx` 后缀，否则 JSX 语法无法解析。

## 依赖安装

如果项目缺少以下依赖，可以使用项目的包管理器安装：
- `@testing-library/react`、`@testing-library/dom`、`@testing-library/jest-dom`
- 可选：`@testing-library/user-event`（高级交互）
- 可选：`msw`（Mock Service Worker，API Mock）
- TypeScript 项目：`@types/react`、`@types/react-dom`
