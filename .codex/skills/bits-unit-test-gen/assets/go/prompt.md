# Go 语言专属 Prompt

## 筛选规则（Go 特有）

**跳过：**

- `init` 函数、`main` 函数、覆盖率超过 90% 的函数
- 自动生成的代码目录/文件：`kitex_gen`、`hertz_gen`、Proto 生成文件
- 包含 `// Code generated` 注释的文件
- 少于 3 行的简单 getter/setter

## 测试文件命名约定

| 项目     | 约定                                               |
| -------- | -------------------------------------------------- |
| 测试文件 | `*_test.go`                                        |
| 位置     | 与源文件同目录、同包                               |
| 包名选择 | 优先与已有测试一致；无已有测试则用源文件同包名     |
| 黑盒测试 | 若已有测试使用 `_test` 后缀包名，则跟随（如 `package foo_test`） |

---

## 前置检测（必须在写测试之前完成）

> **⚠️ 硬性前置要求**：在生成任何测试代码之前，**必须**完成本步骤的环境检测和项目学习。未完成前置检测就直接编写测试，视为流程违规。不同项目的 Go 版本、Mock 框架、测试风格差异巨大，跳过此步骤几乎必然导致后续反复修复。

### 1. 环境检测

1. **检查 Go 版本**（必须）：`head -1 go.mod` 确认 Go 版本
   - Go < 1.22：循环变量需在 `t.Run` 前 `tt := tt` 重新赋值
   - Go ≥ 1.22：循环变量在每次迭代中会被重新创建，不需要额外赋值
2. **检查测试依赖**（必须）：`grep -E "testify|mockey|gomock|goconvey|gomonkey" go.mod` 确认已有的 Mock/断言框架
   - 有 `mockey` → 使用 mockey + PatchConvey 模式
   - 有 `gomock` → 使用 gomock + mockgen 模式
   - 有 `gomonkey` → 使用 gomonkey 模式
   - 都没有 → 默认使用 mockey（参见代码风格表中的约定）
3. **检查多 module 项目**（推荐）：`find . -name "go.mod" -maxdepth 3` 确认是否为多 module 项目
   - 多 module 项目中，`go test` 需要在目标 module 所在目录执行

### 2. 学习项目测试模式

在目标函数所在目录（及相邻目录）中学习已有测试的风格：

1. **扫描已有测试文件**（必须）：在目标函数同目录下读取 1-2 个已有 `*_test.go` 文件，学习以下维度：
   - **Mock 策略**：项目用 mockey、gomock、gomonkey，还是 interface 注入？
   - **断言风格**：testify/assert、testify/require、还是标准库的 `if got != want`？
   - **命名约定**：测试函数名/场景名的实际命名规律
   - **用例组织**：是 table-driven、独立 `t.Run`，还是 `Convey` 嵌套？
2. **发现 Test Helper / Factory**（推荐）：搜索项目中可复用的测试资产
   ```bash
   grep -rn "func.*Test\|func setup\|func new.*Test\|testHelper\|testdata\|testutil" --include="*_test.go" <target_dir>
   ```
   - 若存在 `testutil`、`testhelper`、`fixture` 等包，优先复用
3. **读取项目约定**（推荐）：检查 `PROJECT_ROOT` 下的 `AGENTS.md`、`CLAUDE.md`
   - 提取其中与单测相关的要求（命名规范、Mock 框架、目录结构等）

### 3. 上下文分析

对每个目标函数，获取足够的上下文信息：

1. **Layer 1（必做）**：Read 被测函数源码，理解函数签名、参数/返回值类型定义
2. **Layer 2（推荐）**：使用 `utree context` 获取依赖链，或直接 Read 依赖模块的接口定义
   ```bash
   ${SKILL_ROOT}/scripts/utree context --file <file> --line <line> --output ${TMP_ROOT}/<file>_<line>.json
   ```
   - 若 `utree context` 失败（非零退出码或输出为空），降级为手动 Read 直接依赖的源文件
3. **Layer 3（按需）**：当 Layer 2 信息不足以确定 mock 策略时，Read 间接依赖或类型定义文件

---

## Go 单测规范

### 测试函数签名

- 测试函数必须以 `Test` 开头，签名为 `func TestXxx(t *testing.T)`
- `Xxx` 首字母必须大写，否则 `go test` 不识别
- 基准测试使用 `func BenchmarkXxx(b *testing.B)`
- 示例函数使用 `func ExampleXxx()`

### 包级别约束

- 测试文件的 `package` 声明必须与同目录源文件一致（白盒测试），或使用 `包名_test`（黑盒测试）
- 同一目录下不能同时存在两个不同的非 `_test` 包名
- `_test.go` 文件中可以访问同包未导出的函数/变量（白盒模式）

### 测试隔离原则

- 每个 `t.Run` 子测试必须独立，不依赖其他子测试的执行顺序或副作用
- 禁止在子测试间通过包级变量传递状态
- 需要共享 setup 逻辑时，使用 `TestMain` 或在每个子测试内部独立初始化
- Mock 必须在子测试作用域内设置和清理，不允许泄漏到其他用例

### 错误处理测试要求

- 返回 `error` 的函数，必须覆盖 error 非 nil 的路径
- 使用 `assert.NoError` / `assert.Error` 明确断言错误状态
- 对于特定错误类型，使用 `assert.ErrorIs` 或 `assert.ErrorAs` 精确匹配
- 禁止忽略 error 返回值（即 `_ = SomeFunc()` 后不断言）

### nil/零值处理

- 指针类型参数需覆盖 `nil` 输入场景
- slice/map 参数需覆盖 `nil` 和空（`[]T{}`/`map[K]V{}`）两种场景
- string 参数需覆盖空字符串 `""` 场景
- 数值参数需覆盖 `0`、负数、边界值（如 `math.MaxInt64`）场景

### 并发安全

- 使用 `t.Parallel()` 时，循环变量必须在子测试闭包内重新赋值（Go < 1.22）
- 并发测试中禁止使用 `t.Fatal` / `t.FailNow`（仅允许在主 goroutine 中调用）
- 涉及共享资源的测试，需验证并发安全性（如使用 `sync.WaitGroup` + 多 goroutine 并发调用）

### 断言规范

- 优先使用 `assert.Equal(t, expected, actual)` — 注意参数顺序：**expected 在前，actual 在后**
- 浮点数比较使用 `assert.InDelta(t, expected, actual, delta)`
- 判断包含关系使用 `assert.Contains`
- 多个断言需要全部执行时使用 `assert`；遇到第一个失败即终止时使用 `require`
- 优先使用精确值比较（`assert.Equal`），但在验证复杂对象非空后再做字段断言的场景中，`assert.NotNil` 是合理的前置断言

---

## 验证方式

### 测试执行时间记录

在生成的测试代码中，每个测试用例在执行之前记录开始时间，在执行之后记录结束时间，并打印该测试用例的执行时间，便于性能分析。

```go
import "time"

func TestExample(t *testing.T) {
    startTime := time.Now()
    // 测试代码
    assert.Equal(t, expected, someFunction())
    endTime := time.Now()
    duration := endTime.Sub(startTime)
    t.Logf("TestExample executed in: %v", duration)
}
```

> **⚠️ 所有 `go` 命令必须通过 `utree local-run` 包装执行**，以确保 Go 工具链在 PATH 中可用。直接裸跑 `go test` / `go build` 等命令可能因环境 PATH 不包含 Go 安装路径而失败。

### local-run（默认方式）

```bash
${SKILL_ROOT}/scripts/utree local-run -- go test -v -gcflags="all=-l -N" ./path/to/pkg/...
```

### remote-run（Go 独有）

当本地环境无法满足执行条件时（如缺少依赖服务、环境配置与 CI 不一致），可使用远程执行：

```bash
${SKILL_ROOT}/scripts/utree remote-run
```

详细用法参见 `assets/go/remote-go-test/GUIDE.md`。

### 编译检查

```bash
${SKILL_ROOT}/scripts/utree local-run -- go build ./...
```

### 运行测试

```bash
${SKILL_ROOT}/scripts/utree local-run -- go test -v -gcflags="all=-l -N" ./path/to/pkg/...
```

### 覆盖率检查

```bash
${SKILL_ROOT}/scripts/utree local-run -- go test -v -gcflags="all=-l -N" -coverprofile=${TMP_ROOT}/coverage.out ./path/to/pkg/...
${SKILL_ROOT}/scripts/utree local-run -- go tool cover -func=${TMP_ROOT}/coverage.out
```

---

## Go 特有的缺陷信号

> 缺陷判定的完整规则参见 `references/test-fixer/AGENT.md`，此处仅列出 Go 特有的补充信号（必须结合上下文判断，不可直接判定为缺陷）：

- `panic: runtime error: index out of range` → 可能是切片越界缺陷，**但仅当输入来自正常业务场景时才算缺陷**；测试主动传空切片触发的不算
- `panic: runtime error: invalid memory address or nil pointer dereference` → 可能是空指针缺陷，**但仅当 nil 产生于函数内部逻辑时才算缺陷**；测试主动传 nil 参数触发的不算
- `panic: interface conversion` → 可能是类型断言缺陷，**需确认正常流程中是否会出现不匹配类型**
- `concurrent map read and map write` → 并发安全缺陷，**大概率是真正缺陷**
- 断言失败且 expected 值符合函数的正确语义 → 逻辑缺陷，**大概率是真正缺陷**

---

## 特殊修复规则

- 若依赖包的 init 失败，添加 `import _ "code.byted.org/test_infra/init_tracer"`
- 若 `go build` 报 `undefined` 错误，检查是否遗漏了必要的 import
- 若测试中出现 `interface conversion` panic，检查 mock 返回值的类型是否匹配接口定义
- 若出现 `concurrent map read and map write`，需在被测代码或测试中加锁，或换用 `sync.Map`
- 若出现 `go.sum` 缺失依赖，执行 `${SKILL_ROOT}/scripts/utree local-run -- go mod tidy`

---

## 格式化
- 代码格式化方式优先级：用户指令 > AGENTS.md 。如果没有代码格式化的方式要求，默认使用 goimports 进行代码格式化。
- goimports 详细用法参见 `assets/go/goimports/GUIDE.md`。

---

## 代码风格

风格按优先级确定：用户指令 > AGENTS.md > 同目录已有测试 > 下方默认值。

| 项目           | 约定                                                         |
| -------------- | ------------------------------------------------------------ |
| 场景名/注释语言 | 中文                                                         |
| 命名           | `Test{Struct}{Method}_BitsUT` 或 `Test{Func}_BitsUT`        |
| 文件           | 与源文件同目录的 `*_test.go`，优先追加到已有测试文件         |
| 包名           | 与已有测试一致；无已有测试则用源文件同包名                   |
| 断言           | `github.com/stretchr/testify/assert`（或跟随已有测试）       |
| Mock           | `github.com/bytedance/mockey`（或跟随已有测试）              |
| 用例组织       | `t.Run` 展开子场景                                           |
| 编译标志       | `-gcflags="all=-l -N"`（禁用内联，mockey 要求）              |
| import 分组    | 标准库 → 第三方库 → 内部包，各组之间空行分隔                |

---

## mockey 用法

### 基本结构

在 `t.Run` 内嵌套 `mockey.PatchConvey` 管理 mock 生命周期：

```go
func TestFoo_BitsUT(t *testing.T) {
    t.Run("场景描述", func(t *testing.T) {
        mockey.PatchConvey("", t, func() {
            // 1. setup mock
            // 2. 调用被测函数
            // 3. 断言结果
        })
    })
}
```

### Mock 普通函数

```go
func TestGetUserInfo_BitsUT(t *testing.T) {
    t.Run("正常获取用户信息", func(t *testing.T) {
        mockey.PatchConvey("", t, func() {
            mockey.Mock(QueryUserFromDB).Return(&User{
                ID:   1001,
                Name: "张三",
            }, nil).Build()

            user, err := GetUserInfo(1001)

            assert.NoError(t, err)
            assert.Equal(t, "张三", user.Name)
            assert.Equal(t, int64(1001), user.ID)
        })
    })

    t.Run("数据库查询失败返回错误", func(t *testing.T) {
        mockey.PatchConvey("", t, func() {
            mockey.Mock(QueryUserFromDB).Return(nil, fmt.Errorf("connection refused")).Build()

            user, err := GetUserInfo(1001)

            assert.Error(t, err)
            assert.Nil(t, user)
            assert.Contains(t, err.Error(), "connection refused")
        })
    })
}
```

### Mock 结构体方法

```go
func TestUserServiceGetProfile_BitsUT(t *testing.T) {
    t.Run("正常获取用户资料", func(t *testing.T) {
        mockey.PatchConvey("", t, func() {
            mockey.Mock((*UserDAO).FindByID).Return(&UserProfile{
                Name:  "李四",
                Email: "lisi@example.com",
            }, nil).Build()

            svc := &UserService{}
            profile, err := svc.GetProfile(1001)

            assert.NoError(t, err)
            assert.Equal(t, "李四", profile.Name)
            assert.Equal(t, "lisi@example.com", profile.Email)
        })
    })
}
```

### 条件 Mock（根据入参返回不同结果）

```go
func TestBatchGetUsers_BitsUT(t *testing.T) {
    t.Run("不同用户ID返回不同结果", func(t *testing.T) {
        mockey.PatchConvey("", t, func() {
            mockey.Mock(QueryUserFromDB).To(func(id int64) (*User, error) {
                switch id {
                case 1:
                    return &User{ID: 1, Name: "用户A"}, nil
                case 2:
                    return &User{ID: 2, Name: "用户B"}, nil
                default:
                    return nil, fmt.Errorf("用户不存在: %d", id)
                }
            }).Build()

            users, errs := BatchGetUsers([]int64{1, 2, 999})

            assert.Equal(t, 2, len(users))
            assert.Equal(t, 1, len(errs))
            assert.Contains(t, errs[0].Error(), "用户不存在")
        })
    })
}
```

### Mock 反面示例（禁止）

- ❌ Mock 简单工具函数（如 `strings.TrimSpace`）→ ✅ 直接调用，无需 mock
- ❌ Mock 被测函数调用的同包 helper → ✅ 只 mock 外部依赖（DB/RPC），让内部逻辑自然执行
- ❌ Mock 所有依赖导致测试变成"验证调用顺序" → ✅ 只 mock 不可控的外部依赖
- ❌ Mock 返回值类型与真实签名不匹配 → ✅ Mock 返回值必须与函数签名一致

---

## 示例

### 示例 1：Table-Driven 测试（推荐模式）

被测函数：

```go
func Add(a, b int) int {
    return a + b
}
```

测试代码：

```go
func TestAdd_BitsUT(t *testing.T) {
    tests := []struct {
        name     string
        a, b     int
        expected int
    }{
        {"两个正数相加", 1, 2, 3},
        {"正数加负数", 5, -3, 2},
        {"两个负数相加", -1, -2, -3},
        {"加零", 10, 0, 10},
        {"两个零相加", 0, 0, 0},
        {"大数相加", math.MaxInt32, 1, math.MaxInt32 + 1},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            startTime := time.Now()
            got := Add(tt.a, tt.b)
            endTime := time.Now()
            duration := endTime.Sub(startTime)
            t.Logf("TestAdd [%s] executed in: %v", tt.name, duration)
            assert.Equal(t, tt.expected, got)
        })
    }
}
```

---

## 常见陷阱与修复

| 陷阱                                           | 原因                                                  | 修复方式                                                       |
| ---------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------- |
| `mockey.Mock` 不生效                           | 编译时内联优化，mock 补丁无法生效                     | 必须使用 `-gcflags="all=-l -N"` 禁用内联                      |
| `PatchConvey` 外的 mock 泄漏到其他子测试       | mock 未在 `PatchConvey` 作用域内管理                  | 所有 mock 必须放在 `PatchConvey` 回调函数内部                  |
| `assert.Equal` 对 `time.Time` 比较失败         | `time.Time` 包含 monotonic clock 信息                 | 使用 `assert.WithinDuration` 或 `time.Truncate`               |
| Table-Driven 循环变量捕获问题（Go < 1.22）     | 闭包捕获的是循环变量的引用而非值                      | 在 `t.Run` 前 `tt := tt` 重新赋值                             |
| `interface conversion: xxx is nil, not yyy`    | mock 返回了 `nil` 但调用方做了类型断言                | mock 返回值需与接口定义匹配，或返回正确的零值实例              |
| 测试间相互影响                                 | 包级变量被修改后未还原                                | 在每个子测试内独立初始化，或使用 `t.Cleanup` 还原              |
| `go test -race` 报数据竞争                     | 测试中并发访问共享变量                                | 使用 `sync.Mutex` / `atomic` 保护，或避免在并发中使用 `t.Fatal` |
| `import cycle not allowed`                     | 测试文件引入了导致循环依赖的包                        | 使用 `_test` 后缀包名进行黑盒测试，打破循环依赖               |
| `package xxx is not in std` OR `no tests to run`             | golang的多module项目                  | 对于多module的项目，需要以该module所在的目录为执行go test的执行目录（考虑cd到目录中） |

---

## 上下文挖掘命令

```bash
${SKILL_ROOT}/scripts/utree local-run -- go list ./...
${SKILL_ROOT}/scripts/utree local-run -- go doc <package>.<Function>
${SKILL_ROOT}/scripts/utree local-run -- go test -cover ./<package>/...
cat go.mod
${SKILL_ROOT}/scripts/utree local-run -- go vet ./...
grep -rn "Mock\|Fake\|Stub\|testHelper" --include="*_test.go" .
```
