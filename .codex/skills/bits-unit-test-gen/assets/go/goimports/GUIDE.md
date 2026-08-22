---
name: goimports
description: Go 官方提供的**代码格式化 + 自动导入管理工具**，是 `gofmt` 的增强版
allowed-tools:
    - Read
    - Write
    - Bash
version: 1.0.2
user-invocable: true
---

# 功能说明
`goimports` 是 Go 官方提供的**代码格式化 + 自动导入管理工具**，是 `gofmt` 的增强版。
核心能力：
- 自动**添加缺失**的 import 包
- 自动**删除未使用**的 import 包
- 自动对 import 分组排序（标准库 / 第三方 / 本地包）
- 保持代码风格完全符合 Go 官方规范


# 安装

> 所有 `go` 命令需通过 `utree local-run` 包装执行，确保 Go 工具链在 PATH 中可用。

```bash
${SKILL_ROOT}/scripts/utree local-run -- go install golang.org/x/tools/cmd/goimports@latest
```

验证：
```bash
${SKILL_ROOT}/scripts/utree local-run -- goimports -version
```
---

# 常用命令

> 以下命令均应通过 `${SKILL_ROOT}/scripts/utree local-run --` 前缀执行。为简洁起见，示例中省略该前缀。

## 1. 格式化单个文件（直接覆盖原文件）
```bash
goimports -w main.go
```

## 2. 格式化整个项目（递归所有 .go 文件）
```bash
goimports -w ./...
```

## 3. 只查看哪些文件需要格式化（不修改）
```bash
goimports -l ./...
```

## 4. 查看格式化前后差异（diff）
```bash
goimports -d main.go
```

## 5. 仅格式化、不修改导入（等价 gofmt）
```bash
goimports -format-only -w main.go
```

# 高级参数

| 参数 | 作用 |
|------|------|
| `-w` | 将结果写回原文件（必须） |
| `-l` | 列出不符合格式的文件列表 |
| `-d` | 显示 diff 对比 |
| `-e` | 显示完整语法错误 |
| `-local` | 指定本地包前缀，单独分组 |
| `-format-only` | 仅格式化，不管理 import |
| `-srcdir` | 指定源码根目录，用于导入查找 |


# 本地包分组（企业级规范）
将项目内部包单独分组，格式更清晰：

```bash
goimports -local "your.company/project" -w ./...
```

效果：
```go
import (
    // 标准库
    "context"
    "fmt"

    // 第三方
    "github.com/gin-gonic/gin"

    // 本地项目（单独分组）
    "your.company/project/pkg/util"
)
```

# 典型使用场景

## 我导入的包没用到，怎么自动清理？
→ 使用 `goimports -w 文件.go` 或 `goimports -w ./...`

## 如何自动导入缺失的包？
→ `goimports` 会自动根据代码标识符补全 import。

### 如何让 import 自动分组、排序？
→ `goimports -local 你的项目前缀 -w ./...`

### 格式化但不想改导入？
→ `goimports -format-only -w main.go`


# 错误与常见问题

## 1. command not found: goimports
原因：`$GOPATH/bin` 未加入 PATH，或 Go 工具链不在 PATH 中
解决：通过 `utree local-run` 包装执行所有 go/goimports 命令：
```bash
${SKILL_ROOT}/scripts/utree local-run -- goimports -w ./...
```

## 2. 本地包没有正确分组
解决：必须使用 `-local` 指定项目前缀。

## 3. 导入无法自动识别（内部包 / 私有仓库）
解决：使用 `-srcdir` 指定源码根目录。
