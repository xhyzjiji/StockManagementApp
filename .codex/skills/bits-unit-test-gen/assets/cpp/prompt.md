# C++ 语言专属 Prompt

## 函数提取方式

| 工具/手段   | 说明                                   |
| ----------- | -------------------------------------- |
| `grep`      | 快速定位函数声明                       |
| `ctags`     | 生成符号索引，提取函数列表             |
| `clangd`    | LSP 精确解析类和函数结构               |
| `nm`        | 查看编译产物中的符号表                 |

## 筛选规则（C++ 特有）

**跳过：**

- `main` 函数
- 自动生成的代码文件（Proto 生成文件、`*.pb.h`/`*.pb.cc` 等）
- 包含 `// Code generated` 或 `@generated` 注释的文件
- 纯模板特化（header-only 且无副作用的简单 getter/setter）
- 少于 3 行的简单 getter/setter

## 测试文件命名约定

| 项目     | 约定                                                   |
| -------- | ------------------------------------------------------ |
| 测试文件 | `*_test.cpp` 或 `*_unittest.cpp`                       |
| 位置     | 与源文件同目录或 `test/` 下（跟随已有约定）            |
| 头文件   | 测试文件直接 `#include` 被测源文件对应的头文件         |

---

## C++ 单测规范

### 测试命名规则

- 测试套件名（SuiteName）使用类名或模块名，采用 PascalCase
- 测试用例名（TestName）描述测试场景，采用 PascalCase 或下划线分隔
- `TEST(SuiteName, TestName)` 用于无 fixture 的独立测试
- `TEST_F(FixtureName, TestName)` 用于需要共享 setup/teardown 的测试
- `TEST_P(SuiteName, TestName)` 用于参数化测试

### 测试隔离原则

- 每个 `TEST` / `TEST_F` 用例必须独立，不依赖其他用例的执行顺序
- `TEST_F` 的 fixture 在每个用例执行前重新构造（`SetUp`），执行后销毁（`TearDown`）
- 禁止在测试用例间通过全局变量或静态变量传递状态
- Mock 对象的生命周期必须在单个测试用例内管理

### Fixture 使用规范

- 当多个测试需要相同的初始化逻辑时，使用 `TEST_F` + Fixture 类
- Fixture 类继承 `::testing::Test`
- `SetUp()` 中初始化资源，`TearDown()` 中释放资源
- 避免在 Fixture 构造函数中做复杂初始化，优先使用 `SetUp()`

### 断言规范

- `EXPECT_*` 系列：失败后继续执行后续断言（推荐默认使用）
- `ASSERT_*` 系列：失败后立即终止当前测试（用于后续断言依赖此结果的场景）
- 整数比较使用 `EXPECT_EQ` / `EXPECT_NE` / `EXPECT_LT` / `EXPECT_GT` / `EXPECT_LE` / `EXPECT_GE`
- 浮点数比较使用 `EXPECT_FLOAT_EQ` / `EXPECT_DOUBLE_EQ` 或 `EXPECT_NEAR(val1, val2, abs_error)`
- 字符串比较使用 `EXPECT_STREQ` / `EXPECT_STRNE`（C 风格字符串）或 `EXPECT_EQ`（`std::string`）
- 布尔值使用 `EXPECT_TRUE` / `EXPECT_FALSE`
- 优先使用精确断言（如 `EXPECT_NE(ptr, nullptr)`），但在验证复杂对象非空后再做字段断言的场景中，`EXPECT_TRUE(ptr != nullptr)` 是可接受的前置断言

### 错误处理测试要求

- 抛出异常的函数使用 `EXPECT_THROW(expr, exception_type)` 断言
- 不抛异常的正常路径使用 `EXPECT_NO_THROW(expr)`
- 返回错误码的函数必须覆盖错误码非零的路径
- 对于 `std::optional` / `std::expected` 返回值，需覆盖有值和无值两种场景

### nullptr/空值处理

- 指针参数需覆盖 `nullptr` 输入场景
- `std::string` 参数需覆盖空字符串 `""` 场景
- 容器参数需覆盖空容器场景
- `std::optional` 参数需覆盖 `std::nullopt` 场景
- 数值参数需覆盖 `0`、负数、边界值（如 `INT_MAX`、`INT_MIN`）场景

### 内存安全

- 测试中动态分配的资源必须在用例结束前释放，或使用智能指针管理
- 使用 `EXPECT_DEATH` / `EXPECT_DEBUG_DEATH` 测试致命错误（仅在需要时）
- 推荐结合 AddressSanitizer（`-fsanitize=address`）运行测试

---

## 验证方式

### 测试执行时间记录

在生成的测试代码中，每个测试用例在执行之前记录开始时间，在执行之后记录结束时间，并打印该测试用例的执行时间，便于性能分析。

```cpp
#include <chrono>
#include <iostream>

TEST(ExampleTest, TestCase) {
    auto startTime = std::chrono::high_resolution_clock::now();
    // 测试代码
    EXPECT_EQ(expected, someFunction());
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(endTime - startTime);
    std::cout << "ExampleTest.TestCase executed in: " << duration.count() << "us" << std::endl;
}
```

### local-run

```bash
./scripts/utree local-run -- ctest -R <test>
```

### 编译检查

```bash
cmake --build . --target <test>
```

### 运行测试

```bash
ctest -R <test> --output-on-failure
```

### 覆盖率检查

```bash
cmake --build . --target <test> -- CXXFLAGS="--coverage"
lcov --capture --directory . --output-file coverage.info
lcov --list coverage.info
```

---

## 特殊修复规则

- 若编译报 `undefined reference`，检查 CMakeLists.txt 中是否链接了被测目标
- 若出现 `multiple definition`，检查是否在头文件中定义了非 inline 函数
- 若 Mock 类报 `unimplemented pure virtual method`，确保所有纯虚函数都被 `MOCK_METHOD` 覆盖
- 若 `EXPECT_DEATH` 在非 debug 模式下失败，改用 `EXPECT_DEBUG_DEATH` 或跳过
- 若出现 `error: use of deleted function`，检查被测类的拷贝/移动语义

---

## 格式化

```bash
clang-format -i <file>
```

---

## 代码风格

风格按优先级确定：用户指令 > AGENTS.md > 同目录已有测试 > 下方默认值。

| 项目           | 约定                                                             |
| -------------- | ---------------------------------------------------------------- |
| 场景名/注释语言 | 中文                                                             |
| 命名           | `TEST(SuiteName, TestName)` 或 `TEST_F`                         |
| 文件           | `<module>_test.cpp`，与源文件同目录或 `test/` 下                 |
| 断言           | Google Test `EXPECT_EQ` / `ASSERT_EQ`（或跟随已有测试）         |
| Mock           | Google Mock `MOCK_METHOD`（或跟随已有测试）                      |
| 用例组织       | 相关用例放在同一 `TEST_F` fixture 下                             |
| include 顺序   | 被测头文件 → 标准库 → 第三方库 → 项目内部头文件，各组之间空行分隔 |

---

## Google Mock 用法

### 基本结构

定义 Mock 类继承接口，使用 `MOCK_METHOD` 声明 mock 方法：

```cpp
class MockUserService : public UserService {
public:
    MOCK_METHOD(User*, GetUser, (int64_t id), (override));
    MOCK_METHOD(bool, UpdateUser, (const User& user), (override));
};
```

### Mock 虚函数接口

```cpp
class MockDatabase : public Database {
public:
    MOCK_METHOD(std::optional<Record>, Find, (const std::string& key), (override));
    MOCK_METHOD(bool, Insert, (const std::string& key, const Record& record), (override));
    MOCK_METHOD(bool, Delete, (const std::string& key), (override));
};

TEST_F(OrderServiceTest, 正常创建订单) {
    MockDatabase mockDB;
    OrderService service(&mockDB);

    EXPECT_CALL(mockDB, Insert(testing::_, testing::_))
        .WillOnce(testing::Return(true));

    auto result = service.CreateOrder("user_001", 9900);

    EXPECT_TRUE(result.has_value());
    EXPECT_EQ(result->amount, 9900);
}
```

### 设置期望与返回值

```cpp
TEST_F(UserServiceTest, 正常获取用户信息) {
    MockUserDAO mockDAO;
    UserService service(&mockDAO);

    User expectedUser{1001, "张三", "zhangsan@example.com"};

    EXPECT_CALL(mockDAO, GetUser(1001))
        .Times(1)
        .WillOnce(testing::Return(&expectedUser));

    auto* user = service.FindUser(1001);

    ASSERT_NE(user, nullptr);
    EXPECT_EQ(user->name, "张三");
    EXPECT_EQ(user->email, "zhangsan@example.com");
}
```

---

## 示例

### 示例 1：参数化测试（推荐模式）

被测函数：

```cpp
int Add(int a, int b) {
    return a + b;
}
```

测试代码：

```cpp
struct AddTestParam {
    std::string name;
    int a;
    int b;
    int expected;
};

class AddTest : public ::testing::TestWithParam<AddTestParam> {};

TEST_P(AddTest, 计算结果正确) {
    const auto& param = GetParam();
    auto startTime = std::chrono::high_resolution_clock::now();
    EXPECT_EQ(Add(param.a, param.b), param.expected);
    auto endTime = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(endTime - startTime);
    std::cout << "AddTest [" << param.name << "] executed in: " << duration.count() << "us" << std::endl;
}

INSTANTIATE_TEST_SUITE_P(
    AddTestCases, AddTest,
    ::testing::Values(
        AddTestParam{"两个正数相加", 1, 2, 3},
        AddTestParam{"正数加负数", 5, -3, 2},
        AddTestParam{"两个负数相加", -1, -2, -3},
        AddTestParam{"加零", 10, 0, 10},
        AddTestParam{"两个零相加", 0, 0, 0},
        AddTestParam{"大数相加", INT_MAX - 1, 1, INT_MAX}
    ),
    [](const ::testing::TestParamInfo<AddTestParam>& info) {
        return info.param.name;
    }
);
```

---

## 常见陷阱与修复

| 陷阱                                             | 原因                                                    | 修复方式                                                           |
| ------------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------------------------ |
| `undefined reference to vtable`                  | Mock 类未实现所有纯虚函数                               | 确保所有纯虚方法都用 `MOCK_METHOD` 声明                            |
| `EXPECT_CALL` 不生效                             | Mock 对象不是通过指针/引用传入被测代码                   | 被测代码必须通过指针/引用持有 Mock 对象，不能拷贝                   |
| `Uninteresting mock function call`               | Mock 方法被调用但未设置 `EXPECT_CALL`                    | 添加 `EXPECT_CALL` 或使用 `NiceMock<T>` 抑制警告                  |
| 浮点数 `EXPECT_EQ` 失败                          | 浮点运算精度问题                                        | 使用 `EXPECT_NEAR` 或 `EXPECT_DOUBLE_EQ`                          |
| `EXPECT_DEATH` 在某些平台无法使用                | 需要 fork 支持，某些环境不可用                           | 使用 `GTEST_FLAG_SET(death_test_style, "threadsafe")` 或跳过       |
| 测试间相互影响                                   | 全局/静态变量被修改后未还原                              | 在 Fixture `TearDown` 中重置，或避免使用全局状态                   |
| 链接错误 `multiple definition`                   | 头文件中定义了非 inline 函数                             | 将函数定义移到 `.cpp` 文件，或加 `inline` 关键字                   |
| Mock 析构时报 `unresolved expectation`           | `EXPECT_CALL` 设置的期望未满足                           | 检查被测代码是否正确调用了 mock 方法，或调整 `Times` 约束          |

---

## 上下文挖掘命令

```bash
find . -name "*.h" -o -name "*.hpp" -o -name "*.cpp" | head -50
grep -rn "class.*:.*public" --include="*.h" --include="*.hpp" .
cat CMakeLists.txt
grep -rn "Mock\|Fake\|Stub" --include="*test*" .
grep -rn "TEST\|TEST_F\|TEST_P" --include="*test*" .
```
