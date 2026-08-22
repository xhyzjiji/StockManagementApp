# Java 语言专属 Prompt

## 函数提取方式

| 工具/手段   | 说明                                                   |
| ----------- | ------------------------------------------------------ |
| `grep`      | 快速定位方法签名 `public`/`protected`/`private`        |
| IDE LSP     | 精确解析类和方法结构                                   |
| `javap`     | 查看编译后的类方法签名                                 |

## 筛选规则（Java 特有）

**跳过：**

- `public static void main` 入口方法
- 自动生成的代码：`*Generated*`、Proto 生成文件
- Lombok 生成的 getter/setter/toString/equals/hashCode（`@Data`、`@Getter` 等注解标记的类）
- 少于 3 行的简单 getter/setter
- 接口中的 `default` 方法（除非包含复杂逻辑）

## 测试文件命名约定

| 项目       | 约定                                                         |
| ---------- | ------------------------------------------------------------ |
| 测试文件   | `*Test.java`                                                 |
| 位置       | `src/test/java/` 对应包路径下                                |
| 包名       | 与被测类的包名一致                                           |
| 测试类名   | `{ClassName}Test`（如 `UserService` → `UserServiceTest`）    |

---

## Java 单测规范

### 测试方法签名

- 使用 JUnit 5 的 `@Test` 注解标记测试方法
- 方法必须为 `void` 返回类型、无参数、非 `static`
- 方法名遵循 `test<Method>_<scenario>` 或 `should<Expected>_when<Condition>` 命名
- 方法访问修饰符推荐 `package-private`（即不写修饰符），无需 `public`

### 测试类结构

- 测试类不需要继承任何基类（JUnit 5）
- 使用 `@BeforeEach` / `@AfterEach` 替代 JUnit 4 的 `@Before` / `@After`
- 使用 `@BeforeAll` / `@AfterAll` 管理类级别的资源（方法必须 `static`）
- `@ExtendWith(MockitoExtension.class)` 启用 Mockito 注解支持

### 测试隔离原则

- 每个 `@Test` 方法必须独立，不依赖其他测试的执行顺序
- 禁止在测试方法间通过实例变量传递状态（除非在 `@BeforeEach` 中重新初始化）
- Mock 对象在每个测试方法执行前自动重置（Mockito 默认行为）
- 禁止使用 `@TestMethodOrder` 强制测试顺序来满足依赖关系

### 断言规范

- 优先使用 JUnit 5 的 `Assertions`：`assertEquals(expected, actual)` — 注意参数顺序：**expected 在前，actual 在后**
- 或使用 AssertJ 的流式断言：`assertThat(actual).isEqualTo(expected)`（跟随已有测试）
- 浮点数比较使用 `assertEquals(expected, actual, delta)` 或 `assertThat(actual).isCloseTo(expected, within(delta))`
- 集合断言使用 `assertThat(list).hasSize(3).contains("a", "b")`
- 异常断言使用 `assertThrows(ExceptionType.class, () -> { ... })`
- 优先使用精确值比较（`assertEquals`/`isEqualTo`），但在验证复杂对象非空后再做字段断言的场景中，`assertNotNull` 是合理的前置断言
- 对于复杂对象比较，优先使用 `assertThat(actual).usingRecursiveComparison().isEqualTo(expected)`

### 异常测试要求

- 可能抛出异常的方法必须覆盖异常路径
- 使用 `assertThrows` 断言异常类型，并验证异常消息：
  ```java
  Exception ex = assertThrows(IllegalArgumentException.class, () -> service.process(null));
  assertThat(ex.getMessage()).contains("不能为空");
  ```
- 禁止使用 JUnit 4 的 `@Test(expected = ...)` 语法

### null/空值处理

- 引用类型参数需覆盖 `null` 输入场景
- `String` 参数需覆盖空字符串 `""` 和 `null` 两种场景
- `List`/`Map`/`Set` 参数需覆盖 `null`、空集合 `Collections.emptyList()` 两种场景
- `Optional` 返回值需覆盖 `Optional.empty()` 场景
- 数值参数需覆盖 `0`、负数、边界值（如 `Integer.MAX_VALUE`）场景

### 访问控制

- 测试类与被测类在同一包路径下，可访问 `package-private` 方法
- `private` 方法不直接测试，通过调用其公开方法间接覆盖
- 禁止使用反射绕过访问控制来测试 `private` 方法（极端情况除外）

---

## 验证方式

### 测试执行时间记录

在生成的测试代码中，每个测试用例在执行之前记录开始时间，在执行之后记录结束时间，并打印该测试用例的执行时间，便于性能分析。

```java
@Test
void testExample() {
    long startTime = System.nanoTime();
    // 测试代码
    assertEquals(expected, someFunction());
    long endTime = System.nanoTime();
    double duration = (endTime - startTime) / 1_000_000.0;
    System.out.printf("testExample executed in: %.6fms%n", duration);
}
```

### local-run

```bash
./scripts/utree local-run -- mvn test -pl <module> -Dtest=<TestClass> test
```

### 编译检查

```bash
mvn compile -pl <module>
```

### 运行测试

```bash
mvn test -pl <module> -Dtest=<TestClass>
```

### 覆盖率检查

```bash
mvn test -pl <module> -Dtest=<TestClass> -Djacoco.skip=false
mvn jacoco:report -pl <module>
```

---

## 特殊修复规则

**失败分诊：**

> 缺陷判定的完整规则参见 `references/test-fixer/AGENT.md` 的"失败分诊流程"章节，此处仅列出 Java 特有的补充。

**Java 特有的缺陷信号（必须结合上下文判断，不可直接判定为缺陷）：**
- `java.lang.NullPointerException`（非 Mock 注入问题）→ 可能是空值防护缺失，**但仅当 null 产生于方法内部逻辑时才算缺陷**；测试主动传 null 参数触发的不算
- `java.lang.ArrayIndexOutOfBoundsException` → 可能是数组边界检查缺失，**但仅当输入来自正常业务场景时才算缺陷**
- `java.lang.StringIndexOutOfBoundsException` → 可能是字符串索引越界，**同上**
- `java.lang.ArithmeticException: / by zero` → 可能是除零防护缺失，**大概率是真正缺陷**
- `java.lang.ClassCastException` → 可能是类型检查缺失，**需确认正常流程中是否会出现不匹配类型**
- `java.util.ConcurrentModificationException` → 可能是并发安全问题，**大概率是真正缺陷**
- `java.lang.StackOverflowError` → 可能是递归终止条件缺陷，**大概率是真正缺陷**
- 断言失败且 expected 值符合方法的正确语义 → 逻辑缺陷，**大概率是真正缺陷**

- 若编译报 `cannot find symbol`，检查 import 语句和依赖是否在 `pom.xml` / `build.gradle` 中声明
- 若出现 `NullPointerException` 而非预期行为，检查 mock 对象是否正确注入（`@InjectMocks` + `@Mock`）
- 若 Mockito 报 `Unnecessary stubbings detected`，使用 `@MockitoSettings(strictness = Strictness.LENIENT)` 或移除未使用的 stub
- 若出现 `org.mockito.exceptions.misusing.MissingMethodInvocationException`，检查是否对 final 类/方法进行了 mock（需要 `mockito-inline`）
- 若 Spring 上下文加载失败，检查是否缺少必要的 `@MockBean` 声明

---

## 格式化

跟随项目 formatter 配置。

若项目无统一 formatter，推荐使用 Google Java Format：

```bash
google-java-format -i <file>
```

---

## 代码风格

风格按优先级确定：用户指令 > AGENTS.md > 同目录已有测试 > 下方默认值。

| 项目           | 约定                                                              |
| -------------- | ----------------------------------------------------------------- |
| 场景名/注释语言 | 中文                                                              |
| 命名           | `test<Method>_<scenario>`（JUnit 5 `@Test`）                     |
| 文件           | `<ClassName>Test.java`，位于 `src/test/java/` 对应包路径          |
| 断言           | `org.junit.jupiter.api.Assertions` 或 `AssertJ`（跟随已有测试）  |
| Mock           | `Mockito`（或跟随已有测试）                                       |
| 用例组织       | `@ParameterizedTest` + `@MethodSource` / `@CsvSource`            |
| import 顺序    | 静态导入 → 标准库 → 第三方库 → 项目内部包，各组之间空行分隔      |

---

## Mockito 用法

### 基本结构

使用 `@ExtendWith` + `@Mock` + `@InjectMocks` 组合：

```java
@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock
    private UserDAO userDAO;

    @Mock
    private CacheClient cacheClient;

    @InjectMocks
    private UserService userService;

    @Test
    void testGetUser_正常获取用户() {
        // 1. setup mock
        // 2. 调用被测方法
        // 3. 断言结果
        // 4. 验证调用（可选）
    }
}
```

### Mock 方法返回值

```java
@Test
void testGetUser_正常获取用户() {
    User expectedUser = new User(1001L, "张三", "zhangsan@example.com");
    when(userDAO.findById(1001L)).thenReturn(Optional.of(expectedUser));

    User result = userService.getUser(1001L);

    assertEquals("张三", result.getName());
    assertEquals("zhangsan@example.com", result.getEmail());
    verify(userDAO).findById(1001L);
}

@Test
void testGetUser_用户不存在抛出异常() {
    when(userDAO.findById(999L)).thenReturn(Optional.empty());

    Exception ex = assertThrows(UserNotFoundException.class,
        () -> userService.getUser(999L));

    assertThat(ex.getMessage()).contains("用户不存在");
}
```

### Mock 方法抛出异常

```java
@Test
void testGetUser_数据库查询失败() {
    when(userDAO.findById(anyLong()))
        .thenThrow(new RuntimeException("connection refused"));

    assertThrows(ServiceException.class,
        () -> userService.getUser(1001L));
}
```

### 条件 Mock（根据参数返回不同结果）

```java
@Test
void testBatchGetUsers_不同ID返回不同结果() {
    when(userDAO.findById(1L)).thenReturn(Optional.of(new User(1L, "用户A")));
    when(userDAO.findById(2L)).thenReturn(Optional.of(new User(2L, "用户B")));
    when(userDAO.findById(999L)).thenReturn(Optional.empty());

    List<User> users = userService.batchGetUsers(List.of(1L, 2L, 999L));

    assertThat(users).hasSize(2);
    assertThat(users).extracting(User::getName).containsExactly("用户A", "用户B");
}
```

### Mock void 方法

```java
@Test
void testDeleteUser_正常删除() {
    doNothing().when(userDAO).deleteById(1001L);

    userService.deleteUser(1001L);

    verify(userDAO).deleteById(1001L);
}

@Test
void testDeleteUser_删除失败抛出异常() {
    doThrow(new RuntimeException("删除失败"))
        .when(userDAO).deleteById(anyLong());

    assertThrows(ServiceException.class,
        () -> userService.deleteUser(1001L));
}
```

---

## 示例

### 示例 1：参数化测试（推荐模式）

被测方法：

```java
public int add(int a, int b) {
    return a + b;
}
```

测试代码：

```java
@ParameterizedTest(name = "{0}: add({1}, {2}) = {3}")
@MethodSource("addTestCases")
void testAdd_参数化验证(String name, int a, int b, int expected) {
    long startTime = System.nanoTime();
    assertEquals(expected, calculator.add(a, b));
    long endTime = System.nanoTime();
    double duration = (endTime - startTime) / 1_000_000.0;
    System.out.printf("testAdd [%s] executed in: %.6fms%n", name, duration);
}

static Stream<Arguments> addTestCases() {
    return Stream.of(
        Arguments.of("两个正数相加", 1, 2, 3),
        Arguments.of("正数加负数", 5, -3, 2),
        Arguments.of("两个负数相加", -1, -2, -3),
        Arguments.of("加零", 10, 0, 10),
        Arguments.of("两个零相加", 0, 0, 0),
        Arguments.of("大数相加", Integer.MAX_VALUE - 1, 1, Integer.MAX_VALUE)
    );
}
```

---

## 常见陷阱与修复

| 陷阱                                               | 原因                                                    | 修复方式                                                              |
| -------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------- |
| `Unnecessary stubbings detected`                   | 设置了 stub 但测试中未实际调用                           | 移除未使用的 stub，或使用 `@MockitoSettings(strictness = LENIENT)`    |
| `Cannot mock final class/method`                   | Mockito 默认不支持 final 类/方法                         | 添加 `mockito-inline` 依赖（Mockito 5+ 默认支持）                    |
| `@InjectMocks` 注入失败                            | 被测类构造函数参数与 `@Mock` 字段类型不匹配              | 手动构造被测对象，在构造函数中传入 mock 对象                          |
| `NullPointerException` on mock object              | mock 方法未 stub 返回值，默认返回 null                   | 为所有被调用的 mock 方法设置返回值                                    |
| `assertEquals` 对浮点数比较失败                     | 浮点精度问题                                            | 使用 `assertEquals(expected, actual, delta)` 三参数版本               |
| `assertEquals` 对自定义对象比较失败                 | 对象未重写 `equals`/`hashCode`                           | 使用 AssertJ 的 `usingRecursiveComparison()` 或逐字段断言             |
| 静态方法无法 mock                                   | Mockito 需要 `mockStatic` 且在 try-with-resources 内使用 | 使用 `try (MockedStatic<T> mocked = mockStatic(T.class)) { ... }`    |
| Spring 集成测试上下文加载缓慢                       | `@SpringBootTest` 启动完整上下文                         | 单元测试使用 `@ExtendWith(MockitoExtension.class)` 代替              |

---

## 上下文挖掘命令

```bash
grep -rn "public.*class\|public.*interface" <package_path>
cat pom.xml build.gradle 2>/dev/null
find . -name "*Test.java" | head -20
grep -rn "@Mock\|@InjectMocks\|@MockBean" --include="*Test.java" .
grep -rn "import.*assert\|import.*Mock" --include="*Test.java" . | head -10
```
