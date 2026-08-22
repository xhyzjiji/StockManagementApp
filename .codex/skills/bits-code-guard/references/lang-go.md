# Go 语言专项检测

本文档补充 Go 语言特有的缺陷模式，作为通用评审维度之外的额外检测项。

## 目录

- 变量遮蔽
- nil map 写入
- channel 误操作
- 类型断言缺少安全检查
- defer 与循环
- slice 与 append 陷阱
- range 循环变量

---

## 变量遮蔽

`:=` 在 if/for 等内层作用域中会创建同名新变量，外层变量不会被修改。

```go
var err error
if condition {
    result, err := doSomething() // 这里的 err 是新变量，外层 err 仍为 nil
    _ = result
}
// 此处 err 仍为 nil，bug 被掩盖
```

检查要点：
- 内层 `:=` 赋值的变量是否与外层同名，导致外层值未被更新
- 特别关注 `err` 变量在多层 if/for 中的遮蔽

## nil map 写入

未初始化的 map 读取返回零值不会 panic，但写入会直接 panic。

```go
var m map[string]int
_ = m["key"]     // 正常，返回 0
m["key"] = 1     // panic: assignment to entry in nil map
```

检查要点：
- 函数内声明的 map 变量是否在写入前通过 `make()` 或字面量初始化
- 结构体中的 map 字段是否在构造时初始化

## channel 误操作

向已关闭的 channel 发送数据或重复关闭 channel 都会 panic。

```go
close(ch)
ch <- val    // panic: send on closed channel
close(ch)    // panic: close of closed channel
```

检查要点：
- 关闭 channel 的职责是否明确（通常由发送方负责关闭）
- 是否存在多个 goroutine 都可能关闭同一 channel 的路径
- 关闭后是否仍有代码尝试向该 channel 发送

## 类型断言缺少安全检查

不带 comma-ok 的类型断言在类型不匹配时会 panic。

```go
val := someInterface.(ConcreteType) // 类型不匹配时 panic

// 安全写法
val, ok := someInterface.(ConcreteType)
if !ok { ... }
```

检查要点：
- 对 `interface{}` / `any` 的类型断言是否使用了 comma-ok 模式
- type switch 已经是安全的，不需要额外检查

## defer 与循环

在循环体内使用 defer 时，资源释放会延迟到函数返回而非每次迭代结束。

```go
for _, file := range files {
    f, _ := os.Open(file)
    defer f.Close() // 所有文件句柄在函数返回时才关闭，循环次数多时可能耗尽文件描述符
}
```

检查要点：
- 循环内的 defer 是否会导致资源在整个函数执行期间累积
- 是否应该将循环体提取为独立函数，或手动在迭代末尾释放

## slice 与 append 陷阱

多个 slice 共享底层数组时，append 可能意外修改其他 slice 的数据。

```go
a := []int{1, 2, 3, 4}
b := a[:2]          // b 和 a 共享底层数组
b = append(b, 99)   // a[2] 被意外修改为 99
```

检查要点：
- 对切片进行子切片操作后，是否意识到底层数组共享
- 需要独立副本时是否使用了 `copy()` 或完整切片表达式 `a[:2:2]`

## range 循环变量

Go 1.21 以前，range 循环变量在每次迭代中复用同一地址，在 goroutine 或闭包中捕获时会导致所有引用指向最后一个值。

```go
for _, item := range items {
    go func() {
        process(item) // Go < 1.22: 所有 goroutine 可能都处理最后一个 item
    }()
}
```

检查要点：
- Go 1.22+ 已修复此问题，检查项目的 Go 版本（go.mod 中的 go 指令）
- 低版本中是否在循环体内重新声明变量或将值作为参数传入闭包
