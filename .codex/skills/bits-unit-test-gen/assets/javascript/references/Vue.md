# Vue 单测参考指南

## 概述

Vue 是渐进式 JavaScript 框架，支持 Options API 和 Composition API 两种编程范式。测试 Vue 代码的核心挑战在于：响应式系统、组件生命周期、模板指令、组件通信（props/emits/provide-inject）、异步更新机制。本文档聚焦于生成单元测试时需要了解的 Vue 核心概念和模式。

> **测试库**：Vue 组件测试主要使用 `@vue/test-utils`（官方测试工具库），配合 Jest 或 Vitest。

## 两种 API 风格

### Composition API（推荐，Vue 3 主流）

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';

const count = ref(0);
const doubled = computed(() => count.value * 2);
const increment = () => count.value++;

onMounted(() => {
  console.log('mounted');
});
</script>
```

### Options API（Vue 2 风格，Vue 3 兼容）

```vue
<script>
export default {
  data() {
    return { count: 0 };
  },
  computed: {
    doubled() { return this.count * 2; }
  },
  methods: {
    increment() { this.count++; }
  },
  mounted() {
    console.log('mounted');
  }
};
</script>
```

**单测注意**：两种风格的测试方式基本一致（都通过 `mount` / `shallowMount` 渲染），但 Composition API 的 Composables 可以独立测试。

## 响应式系统

### 核心 API

| API | 用途 | 测试关注点 |
|---|---|---|
| `ref(value)` | 创建基本类型响应式引用 | 验证 `.value` 变化后 UI 更新 |
| `reactive(obj)` | 创建对象响应式代理 | 验证属性变化后 UI 更新 |
| `computed(() => ...)` | 派生计算属性 | 验证依赖变化时计算结果正确 |
| `watch(source, cb)` | 监听响应式数据变化 | 验证回调在数据变化时触发 |
| `watchEffect(cb)` | 自动追踪依赖并执行 | 验证副作用执行 |

### 响应式工具

| API | 用途 |
|---|---|
| `toRef(obj, key)` | 将 reactive 对象的属性转为 ref |
| `toRefs(obj)` | 将 reactive 对象所有属性转为 ref |
| `unref(val)` | 如果是 ref 返回 `.value`，否则返回自身 |
| `isRef(val)` / `isReactive(val)` | 类型判断 |
| `shallowRef` / `shallowReactive` | 浅层响应式 |
| `triggerRef(ref)` | 手动触发 shallowRef 更新 |
| `nextTick()` | 等待 DOM 更新完成 |

**单测关键**：Vue 的 DOM 更新是异步的，状态变更后需要 `await nextTick()` 或 `await wrapper.vm.$nextTick()` 才能验证 DOM 变化。

## 组件测试（@vue/test-utils）

### 挂载组件

```ts
import { mount, shallowMount } from '@vue/test-utils';
import MyComponent from './MyComponent.vue';

// 完整挂载（渲染子组件）
const wrapper = mount(MyComponent, {
  props: { title: 'Hello' },
});

// 浅挂载（子组件用 stub 替代，推荐用于隔离测试）
const wrapper = shallowMount(MyComponent, {
  props: { title: 'Hello' },
});
```

### 挂载选项

```ts
mount(MyComponent, {
  props: { name: 'Alice' },          // 传入 props
  slots: {                            // 插槽内容
    default: '<span>Default</span>',
    header: '<h1>Header</h1>',
  },
  global: {
    plugins: [pinia, router],         // 全局插件
    provide: { key: 'value' },        // provide/inject
    stubs: {                          // 替换子组件
      ChildComponent: true,           // 用 stub 替代
      RouterLink: RouterLinkStub,     // 用自定义 stub
    },
    mocks: {                          // mock 全局属性（Options API 的 this.$xxx）
      $route: { params: { id: '1' } },
      $t: (key: string) => key,       // i18n mock
    },
    components: { MyGlobal },         // 注册全局组件
    directives: { focus: vFocus },    // 注册全局指令
  },
  attachTo: document.body,            // 挂载到真实 DOM（需要时）
});
```

### 查找元素与组件

```ts
// 查找 DOM 元素
wrapper.find('button');               // CSS 选择器
wrapper.find('[data-testid="btn"]');  // data-testid
wrapper.findAll('li');                // 查找所有匹配元素

// 查找子组件
wrapper.findComponent(ChildComponent);
wrapper.findComponent({ name: 'ChildComponent' });
wrapper.findAllComponents(ListItem);

// 判断存在性
wrapper.find('.error').exists();      // 返回 boolean
```

### 交互操作

```ts
// 点击
await wrapper.find('button').trigger('click');

// 输入
await wrapper.find('input').setValue('hello');

// 键盘事件
await wrapper.find('input').trigger('keydown.enter');

// 自定义事件
await wrapper.find('.item').trigger('mouseenter');
```

**重要**：所有交互操作后需要 `await` 等待异步更新完成。

### 断言

```ts
// 文本内容
expect(wrapper.text()).toContain('Hello');

// HTML 内容
expect(wrapper.html()).toContain('<span>Hello</span>');

// 元素属性
expect(wrapper.find('input').element.value).toBe('hello');
expect(wrapper.find('button').attributes('disabled')).toBeDefined();

// CSS 类
expect(wrapper.find('.btn').classes()).toContain('active');

// 可见性
expect(wrapper.find('.modal').isVisible()).toBe(true);

// 组件是否存在
expect(wrapper.findComponent(Child).exists()).toBe(true);

// emitted 事件
expect(wrapper.emitted()).toHaveProperty('submit');
expect(wrapper.emitted('submit')![0]).toEqual([{ name: 'Alice' }]);

// 快照
expect(wrapper.html()).toMatchSnapshot();
```

## Props 测试

```ts
test('renders title from props', () => {
  const wrapper = mount(Header, {
    props: { title: 'Hello', showIcon: true },
  });
  expect(wrapper.text()).toContain('Hello');
  expect(wrapper.find('.icon').exists()).toBe(true);
});

test('updates when props change', async () => {
  const wrapper = mount(Header, {
    props: { title: 'Hello' },
  });
  await wrapper.setProps({ title: 'World' });
  expect(wrapper.text()).toContain('World');
});
```

## 事件（Emits）测试

```ts
test('emits submit event with data', async () => {
  const wrapper = mount(Form);

  await wrapper.find('input').setValue('Alice');
  await wrapper.find('form').trigger('submit');

  expect(wrapper.emitted('submit')).toBeTruthy();
  expect(wrapper.emitted('submit')![0]).toEqual([{ name: 'Alice' }]);
});

test('emits update:modelValue for v-model', async () => {
  const wrapper = mount(CustomInput, {
    props: { modelValue: '' },
  });

  await wrapper.find('input').setValue('hello');

  expect(wrapper.emitted('update:modelValue')![0]).toEqual(['hello']);
});
```

## 插槽（Slots）测试

```ts
test('renders default slot content', () => {
  const wrapper = mount(Card, {
    slots: {
      default: '<p>Content</p>',
      header: '<h1>Title</h1>',
      footer: { template: '<button>OK</button>' },
    },
  });
  expect(wrapper.find('h1').text()).toBe('Title');
  expect(wrapper.find('p').text()).toBe('Content');
});

// 作用域插槽
test('renders scoped slot', () => {
  const wrapper = mount(List, {
    props: { items: ['A', 'B'] },
    slots: {
      item: `<template #item="{ item }"><span>{{ item }}</span></template>`,
    },
  });
  expect(wrapper.findAll('span')).toHaveLength(2);
});
```

## Provide / Inject 测试

```ts
test('uses injected value', () => {
  const wrapper = mount(ChildComponent, {
    global: {
      provide: {
        theme: 'dark',
        userStore: { name: 'Alice' },
      },
    },
  });
  expect(wrapper.text()).toContain('dark');
});
```

## 生命周期钩子

| Composition API | Options API | 测试关注点 |
|---|---|---|
| `onMounted` | `mounted` | 验证副作用（API 调用、事件绑定） |
| `onUnmounted` | `unmounted` / `beforeDestroy` | 验证清理逻辑（调用 `wrapper.unmount()`） |
| `onUpdated` | `updated` | 验证更新后的 DOM 状态 |
| `onBeforeMount` | `beforeMount` | 通常不需专门测试 |

```ts
test('fetches data on mount', async () => {
  const fetchSpy = vi.spyOn(api, 'getData').mockResolvedValue({ name: 'Alice' });

  const wrapper = mount(UserProfile);
  await flushPromises();

  expect(fetchSpy).toHaveBeenCalled();
  expect(wrapper.text()).toContain('Alice');
});

test('removes event listener on unmount', () => {
  const removeSpy = vi.spyOn(window, 'removeEventListener');
  const wrapper = mount(ResizeTracker);

  wrapper.unmount();

  expect(removeSpy).toHaveBeenCalledWith('resize', expect.any(Function));
});
```

## Composables 测试（Composition API 的逻辑复用）

Composable 是 Vue 3 中的自定义 Hook，可以独立测试：

### 纯逻辑 Composable（不依赖组件）

```ts
import { useCounter } from './useCounter';

test('useCounter increments', () => {
  const { count, increment } = useCounter();

  expect(count.value).toBe(0);
  increment();
  expect(count.value).toBe(1);
});
```

### 依赖生命周期的 Composable

需要在组件上下文中测试：

```ts
import { mount } from '@vue/test-utils';
import { defineComponent } from 'vue';
import { useFetch } from './useFetch';

test('useFetch loads data', async () => {
  vi.spyOn(global, 'fetch').mockResolvedValue({
    json: () => Promise.resolve({ name: 'Alice' }),
  } as Response);

  const TestComponent = defineComponent({
    setup() {
      const { data, loading } = useFetch('/api/user');
      return { data, loading };
    },
    template: '<div>{{ loading ? "Loading" : data?.name }}</div>',
  });

  const wrapper = mount(TestComponent);
  await flushPromises();

  expect(wrapper.text()).toBe('Alice');
});
```

## 异步处理

```ts
import { flushPromises } from '@vue/test-utils';
import { nextTick } from 'vue';

// 方式1：flushPromises —— 等待所有 Promise 完成
await flushPromises();

// 方式2：nextTick —— 等待 Vue DOM 更新
await nextTick();

// 方式3：组合使用
await wrapper.find('button').trigger('click');
await flushPromises();  // 等待 API 请求
await nextTick();       // 等待 DOM 更新
```

**典型异步测试**：

```ts
test('loads and displays data', async () => {
  vi.spyOn(api, 'fetchList').mockResolvedValue([{ id: 1, name: 'A' }]);

  const wrapper = mount(DataList);

  // 初始 loading 状态
  expect(wrapper.find('.loading').exists()).toBe(true);

  await flushPromises();

  // 数据加载后
  expect(wrapper.find('.loading').exists()).toBe(false);
  expect(wrapper.findAll('.item')).toHaveLength(1);
});
```

## 路由测试

```ts
import { mount } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/users/:id', component: UserPage },
  ],
});

test('renders user page', async () => {
  router.push('/users/123');
  await router.isReady();

  const wrapper = mount(UserPage, {
    global: { plugins: [router] },
  });

  expect(wrapper.text()).toContain('User 123');
});
```

**简单 mock 方式**（不创建真实 router）：

```ts
const wrapper = mount(MyComponent, {
  global: {
    mocks: {
      $route: { params: { id: '123' }, query: { tab: 'info' } },
      $router: { push: vi.fn() },
    },
    stubs: { RouterLink: true },
  },
});
```

## 状态管理（Pinia）测试

```ts
import { mount } from '@vue/test-utils';
import { createTestingPinia } from '@pinia/testing';
import { useUserStore } from '@/stores/user';

test('displays user name from store', () => {
  const wrapper = mount(UserProfile, {
    global: {
      plugins: [
        createTestingPinia({
          initialState: {
            user: { name: 'Alice', role: 'admin' },
          },
        }),
      ],
    },
  });

  expect(wrapper.text()).toContain('Alice');
});

test('calls store action', async () => {
  const wrapper = mount(LoginForm, {
    global: {
      plugins: [createTestingPinia()],
    },
  });

  const store = useUserStore();

  await wrapper.find('button').trigger('click');

  expect(store.login).toHaveBeenCalled();
});
```

## 常见 Mock 场景

| Mock 目标 | 方法 |
|---|---|
| API 请求 | `vi.spyOn(api, 'method')` 或 `vi.mock('./api')` |
| 路由 | `global.mocks` 或创建测试 router |
| Store（Pinia） | `createTestingPinia({ initialState })` |
| Store（Vuex） | `createStore({ state })` |
| 子组件 | `global.stubs: { Child: true }` |
| 全局属性（`this.$xxx`） | `global.mocks: { $t: fn }` |
| 定时器 | `vi.useFakeTimers()` / `jest.useFakeTimers()` |
| `window` / `document` | `vi.spyOn` 或 `Object.defineProperty` |
| 第三方库 | `vi.mock('library')` / `jest.mock('library')` |
| 自定义指令 | `global.directives` 或 stub |
| `provide/inject` | `global.provide: { key: value }` |
| i18n（`$t`） | `global.mocks: { $t: (k) => k }` |

## 模板指令速查（影响测试方式）

| 指令 | 用途 | 测试影响 |
|---|---|---|
| `v-if` / `v-else` | 条件渲染（移除 DOM） | 用 `.exists()` 验证 |
| `v-show` | 条件显示（display:none） | 用 `.isVisible()` 验证 |
| `v-for` | 列表渲染 | 用 `.findAll()` 验证数量 |
| `v-model` | 双向绑定 | 用 `setValue()` 或验证 `update:modelValue` 事件 |
| `v-on` / `@` | 事件绑定 | 用 `trigger()` 触发 |
| `v-bind` / `:` | 属性绑定 | 用 `.attributes()` 或 `.classes()` 验证 |
| `v-slot` / `#` | 插槽 | 通过 `slots` 选项传入内容 |

## 关键导入来源

```ts
// Vue 核心
import { ref, reactive, computed, watch, watchEffect, nextTick,
  onMounted, onUnmounted, onUpdated, provide, inject,
  defineComponent, defineProps, defineEmits, defineExpose,
  toRef, toRefs, unref, isRef } from 'vue';

// 测试工具
import { mount, shallowMount, flushPromises, VueWrapper, DOMWrapper } from '@vue/test-utils';

// 路由
import { createRouter, createMemoryHistory, RouterLinkStub } from 'vue-router';

// Pinia 测试
import { createTestingPinia } from '@pinia/testing';
import { useXxxStore } from '@/stores/xxx';
```
