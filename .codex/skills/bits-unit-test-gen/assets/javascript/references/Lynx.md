# Lynx / ReactLynx 单测参考指南

## 概述

Lynx 是一个跨平台 UI 框架，使用类 React 的开发范式（ReactLynx）构建原生渲染的界面。**它不运行在浏览器环境中**，没有 DOM/BOM API。与标准 React 的核心差异体现在元素系统、事件模型、线程架构和全局 API 上。

## 内置元素（替代 HTML 标签）

Lynx **不使用任何 HTML 标签**。在 JSX 中必须使用 Lynx 内置元素：

| Lynx 元素 | Web 近似 | 说明 |
|---|---|---|
| `<view>` | `<div>`（不可滚动） | 基础容器，用于布局和包裹 |
| `<text>` | `<p>` / `<span>` | 显示文本，**所有文本必须包裹在 `<text>` 中** |
| `<image>` | `<img>` | 自闭合标签，通过 `src` 属性指定图片 |
| `<scroll-view>` | `<div style="overflow:scroll">` | 滚动容器，通过 `scroll-orientation` 控制方向 |
| `<list>` + `<list-item>` | 无（类似 `react-virtualized`） | 虚拟列表，子项需 `item-key` 属性 |
| `<x-input>` / `<x-input-ng>` | `<input>` | 输入框 |
| `<x-textarea>` / `<x-textarea-ng>` | `<textarea>` | 多行输入 |
| `<x-swiper>` | 无 | 轮播组件 |
| `<x-overlay-ng>` | 无 | 覆盖层 |
| `<x-refresh-view>` | 无 | 下拉刷新 |

**单测关键**：测试代码 / 快照中只应出现 `<view>`, `<text>` 等 Lynx 元素，不能使用 `<div>`, `<span>`, `<p>` 等 HTML 标签。

## ReactLynx Hooks

### 与 React 一致的 Hooks

来自 `@byted-lynx/react`，用法与 React 基本相同：

- `useState`, `useEffect`, `useCallback`, `useMemo`, `useRef`, `useContext`, `useReducer`, `useImperativeHandle`, `useSyncExternalStore`

**注意**：
- `useLayoutEffect` **已废弃**，是 `useEffect` 的别名（Lynx 后台线程无法提供精确布局读取时机）
- `useRef` 绑定到元素时类型为 `NodesRef`（非 DOM Element）

### Lynx 特有 Hooks

```ts
// 获取宿主平台传入的初始数据，变化时自动触发重渲染
import { useInitData } from '@byted-lynx/react';
const initData = useInitData();

// 监听 initData 变化
import { useInitDataChanged } from '@byted-lynx/react';
useInitDataChanged((data) => { /* ... */ });

// 监听 Lynx 全局事件（如曝光、全局属性变化）
import { useLynxGlobalEventListener } from '@byted-lynx/react';
useLynxGlobalEventListener('exposure', (e) => { /* ... */ });

// 创建主线程引用（双线程架构专用）
import { useMainThreadRef } from '@byted-lynx/react';
const ref = useMainThreadRef(initialValue);
```

### 跨线程执行函数

```ts
import { runOnBackground, runOnMainThread } from '@byted-lynx/react';

// 在主线程函数中调度后台线程执行
runOnBackground(() => { /* 后台线程代码 */ })();

// 在后台线程函数中调度主线程执行
runOnMainThread(() => { /* 主线程代码 */ })();
```

## 事件系统

### 事件绑定语法

Lynx 使用 `bind*` / `catch*` 前缀绑定事件，**不使用** `onClick` 等 React DOM 事件属性：

```tsx
// 后台线程事件处理（冒泡）
<view bindtap={handleTap} />

// 后台线程事件处理（阻止冒泡）
<view catchtap={handleTap} />

// 主线程事件处理（更低延迟）
<view main-thread:bindtap={handleTapInMTS} />

// 捕获阶段
<view capture-bind:tap={handleCapture} />
```

### 常见事件类型

| 事件 | 触发时机 |
|---|---|
| `tap` | 点击（对应 Web 的 click） |
| `longpress` | 长按 |
| `touchstart` / `touchmove` / `touchend` | 触摸事件 |
| `input` | 输入框内容变化 |
| `scroll` | 滚动 |
| `binduiappear` / `binduidisappear` | 元素可见性变化（Lynx 特有） |

### 事件对象差异

```ts
// Lynx 事件对象通过 detail 访问数据
function handleInput(e) {
  const value = e.detail.value; // ✅ Lynx
  // const value = e.target.value; // ❌ Web 方式
}

// 后台线程事件对象是纯 JSON（不可操作 DOM）
// 主线程事件对象可通过 e.currentTarget 操作元素
function handleTapMTS(e: MainThread.TouchEvent) {
  'main thread';
  e.currentTarget.setStyleProperty('background-color', 'red');
}
```

### 事件传播

- **冒泡**：`bind*` 前缀，事件从目标向祖先传播
- **阻止冒泡**：`catch*` 前缀，事件不再向上传播
- **捕获**：`capture-bind:*` / `capture-catch:*` 前缀

## 测试库：`@byted-lynx/react/testing-library`

API 设计类似 `@testing-library/react`，但适配 Lynx 元素树（非 DOM）。

### 核心 API

```ts
import {
  render,
  renderHook,
  cleanup,
  fireEvent,
  createEvent,
  waitFor,
  waitSchedule,
  waitForElementToBeRemoved,
  within,
  prettyDOM,
  screen,
} from '@byted-lynx/react/testing-library';
```

### 渲染组件

```tsx
import { render } from '@byted-lynx/react/testing-library';

// 基础渲染
const { container, getByText, getByTestId } = render(<MyComponent />);

// 使用 wrapper（如 Context Provider）
const WrapperComponent = ({ children }) => (
  <view data-testid="wrapper">{children}</view>
);
const { container } = render(<Comp />, { wrapper: WrapperComponent });

// 快照断言
expect(container.firstChild).toMatchInlineSnapshot(`
  <view data-testid="wrapper">
    <view data-testid="inner" style="background-color: yellow;" />
  </view>
`);
```

### 渲染 Hook

```tsx
import { renderHook } from '@byted-lynx/react/testing-library';
import { createContext, useContext } from '@byted-lynx/react';

const Context = createContext('default');
function Wrapper({ children }) {
  return <Context.Provider value="provided">{children}</Context.Provider>;
}

const { result } = renderHook(() => useContext(Context), { wrapper: Wrapper });
expect(result.current).toEqual('provided');
```

### 查询方法

与 `@testing-library/react` 一致的查询方法集：

| 类型 | 方法 | 说明 |
|---|---|---|
| `getBy*` | `getByText`, `getByTestId`, `getByRole` 等 | 找到恰好一个，否则抛错 |
| `queryBy*` | `queryByText`, `queryByTestId` 等 | 找到零或一个，不抛错 |
| `getAllBy*` | `getAllByText`, `getAllByTestId` 等 | 找到一或多个 |
| `findBy*` | `findByText`, `findByTestId` 等 | 异步查找，返回 Promise |

### 事件触发

```tsx
import { render, fireEvent } from '@byted-lynx/react/testing-library';

const { getByTestId } = render(<MyButton />);
fireEvent(getByTestId('my-button'), new Event('tap'));
```

### 异步等待

```tsx
import { waitFor, waitSchedule } from '@byted-lynx/react/testing-library';

// 等待条件满足
await waitFor(() => {
  expect(getByText('loaded')).toBeTruthy();
});

// 等待 Lynx 调度完成
await waitSchedule();
```

### 测试环境

```ts
import { LynxTestingEnv, initElementTree } from '@lynx-js/testing-environment';

// LynxTestingEnv 提供 Lynx 测试环境的初始化和管理
// initElementTree() 初始化元素树用于测试
```

## 全局对象：`lynx`（替代 `window` / `document`）

Lynx 没有 `window` 和 `document`，全局 API 通过 `lynx` 对象访问：

```ts
// DOM 查询（替代 document.getElementById / querySelector）
lynx.getElementById(id);
lynx.createSelectorQuery().select('#id').exec();

// 定时器（与 Web 一致，但来自 lynx 环境）
setTimeout(fn, ms);
setInterval(fn, ms);

// 动画
lynx.requestAnimationFrame(callback);
lynx.cancelAnimationFrame(id);
lynx.animate(element, keyframes, options);

// 网络请求（基本兼容 Web Fetch）
fetch(url, options);

// SSE（通过 lynx 对象创建）
new lynx.EventSource(url);

// Session Storage（非标准 Web Storage API）
lynx.getSessionStorageItem(key);
lynx.setSessionStorageItem(key, value);
lynx.subscribeSessionStorage(key, callback);

// 可见性检测
lynx.createIntersectionObserver(options, config);
lynx.stopExposure();
lynx.resumeExposure();

// 模块系统
lynx.requireModule(name);
lynx.requireModuleAsync(name);
```

**单测关键**：测试中需要 mock `lynx` 全局对象及其方法。

## 原生模块（NativeModules）

`NativeModules` 是全局对象，提供原生平台能力的 JS 访问入口：

```ts
declare let NativeModules: {
  NativeLocalStorageModule: {
    setStorageItem(key: string, value: string): void;
    getStorageItem(key: string, callback: (value: string) => void): void;
    clearStorage(): void;
  };
};

NativeModules.NativeLocalStorageModule.getStorageItem('key', (value) => {
  console.log(value);
});
```

**单测关键**：`NativeModules` 在测试环境中不存在，必须 mock。回调模式的方法需在测试中手动触发回调。

## InitData 机制

InitData 是宿主平台（Native App）传入 Lynx 页面的初始数据，用于 IFR（即时首帧渲染）：

```tsx
import { useInitData } from '@byted-lynx/react';

// 声明 InitData 类型
declare module '@byted-lynx/react' {
  interface InitData {
    title: string;
    items: Array<{ id: string; name: string }>;
  }
}

export function App() {
  const initData = useInitData();
  return <text>{initData.title}</text>;
}
```

**单测关键**：需要 mock `useInitData` 返回测试数据。

## 双线程架构

Lynx 采用主线程 + 后台线程的双线程模型：

- **主线程**：处理用户事件和绘制，可直接操作元素
- **后台线程**：执行 React 渲染逻辑，不能直接操作元素

### 线程标记

```ts
// 标记函数在主线程执行
function handleTap(e) {
  'main thread';
  e.currentTarget.setStyleProperty('color', 'red');
}

// 标记代码仅在后台线程编译
function bgOnlyLogic() {
  'background only';
  // ...
}
```

### 编译时宏

| 宏 | 类型 | 说明 |
|---|---|---|
| `__BACKGROUND__` | `boolean` | 是否在后台线程 |
| `__MAIN_THREAD__` | `boolean` | 是否在主线程 |
| `__RUNTIME_TYPE__` | `'background' \| 'main-thread'` | 运行时类型 |

**单测关键**：测试中需定义这些全局宏，通常设置 `__BACKGROUND__ = true`。

## 布局系统差异

| 差异点 | Lynx | Web |
|---|---|---|
| `box-sizing` 默认值 | `border-box` | `content-box` |
| margin 折叠 | **不存在** | 存在 |
| `display` 值 | `linear` / `flex` / `grid` / `relative` / `none` | `block` / `inline` / `flex` / `grid` 等 |
| CSS 继承 | **默认不继承**，需显式开启 | 部分属性默认继承 |
| 文本渲染 | 必须在 `<text>` 内 | 文本可直接放在 `<div>` 内 |
| 滚动 | 必须用 `<scroll-view>` / `<list>`，`overflow:scroll` **不支持** | 任何元素 `overflow:scroll` |

### Lynx 独有布局

- **Linear Layout**（`display: linear`）：类似 Android LinearLayout，通过 `linear-weight` 分配空间
- **Relative Layout**（`display: relative`）：类似 Android RelativeLayout，通过 `relative-id` 和 `relative-*-of` 定位

## 单测 Mock 清单

生成 Lynx 组件的单元测试时，以下对象/API 通常需要 mock：

| Mock 目标 | 说明 |
|---|---|
| `lynx` 全局对象 | `createSelectorQuery`, `getElementById`, `requireModule` 等 |
| `NativeModules` | 所有原生模块调用 |
| `useInitData` / `useInitDataChanged` | 宿主平台初始数据 |
| `useLynxGlobalEventListener` | 全局事件监听 |
| `useMainThreadRef` / `runOnMainThread` / `runOnBackground` | 跨线程函数 |
| `__BACKGROUND__` / `__MAIN_THREAD__` | 编译时宏 |
| `fetch` | 网络请求 |
| `lynx.EventSource` | SSE |
| `lynx.createIntersectionObserver` | 交叉观察器 |
| 自定义原生组件标签 | 如 `<explorer-input>` 等 |

## 关键类型导入

```ts
// 核心 React API
import { useState, useEffect, useRef, useCallback, useMemo, useContext, createContext, forwardRef, memo, Fragment, Suspense, root } from '@byted-lynx/react';

// Lynx 特有 Hooks
import { useInitData, useInitDataChanged, useLynxGlobalEventListener, useMainThreadRef, runOnBackground, runOnMainThread } from '@byted-lynx/react';

// InitData 相关组件
import { InitDataProvider, InitDataConsumer, withInitDataInState } from '@byted-lynx/react';

// 类型定义
import type { TouchEvent, NodesRef, SelectorQuery } from '@byted-lynx/type-lynx';
import type { MainThread } from '@byted-lynx/type-lynx';

// 测试库
import { render, renderHook, cleanup, fireEvent, waitFor, waitSchedule, screen, within } from '@byted-lynx/react/testing-library';
```
