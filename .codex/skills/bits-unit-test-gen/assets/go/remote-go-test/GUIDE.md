---
name: remote go test
description: 远程环境执行Go单元测试，完美兼容本地环境限制，执行结果与CI流水线单测表现完全一致
allowed-tools:
  - Read
  - Write
  - Bash
version: 1.0.2
user-invocable: true
---

# 功能说明
提供远端容器运行环境，自动加载项目根目录 `.codebase/pipelines` 下的CI配置YAML文件完成环境初始化，确保`go test`无阻碍执行，且测试结果与后续CI流水线执行单元测试的表现完全一致。

## 支持操作
| 操作类型                | 所需参数         |
|-------------------------|------------------|
| 单个test文件测试        | 测试文件绝对路径 |
| 整个目录批量测试        | 目标目录绝对路径 |

# 快速运行指南

## 第一步：准备工具
在当前 skill 目录，如果没有找到 utd，则下载：
```bash
export UTD_COMMAND=$(if [ "$(uname -s)" = "Linux" ]; then echo "utd_linux"; else echo "utd"; fi)
curl https://tosv.byted.org/obj/smart-unit-cases/ut_skills/$UTD_COMMAND -o utd
```

## 第二步：环境变量配置（必做）
在当前skill目录下执行以下命令，配置基础运行变量：
```bash
# 配置UTD工具绝对路径（当前skill目录）
export UTD_ABS_PATH=$(pwd)
```

## 第三步：选择执行命令
### 场景 1：测试单个 test 文件
```bash
# 【需替换】测试文件的绝对路径
TEST_FILE="<如：/project/src/utils/utils_test.go>"
# 【需替换】选择CI配置文件（.codebase/pipelines下含codecov/template的yaml文件名）
CI_YAML_FILE_NAME="<如：ut_ci.yaml>"

# 自动推导变量（无需修改）
WORKING_DIR=$(dirname "$TEST_FILE")
PROJECT_DIR="<项目根目录>" # 自动定位项目根目录
RESULT_DIR="$PROJECT_DIR/utd" # 测试结果统一存储目录

# 创建结果目录（不存在则创建）
mkdir -p "$RESULT_DIR"

# 执行远程测试（核心命令，无需修改）
"$UTD_ABS_PATH/utd" remote_test \
--pipeline_file="./.codebase/pipelines/$CI_YAML_FILE_NAME" \
--result_dir="$RESULT_DIR" \
--test_kind=file \
--status_file="$RESULT_DIR/status" \
--files="$TEST_FILE" \
--working_directory="$WORKING_DIR" \
--enable_coverage \
--save_test_log_mode=1
```

### 场景 2：测试整个目录下所有 test 文件
```bash
# 【需替换】目标测试目录的绝对路径
DIRECTORY_PATH="<如：/project/src/utils>"
# 【需替换】选择CI配置文件（.codebase/pipelines下含codecov/template的yaml文件名）
CI_YAML_FILE_NAME="<如：ut_ci.yaml>"

# 自动推导变量（无需修改）
WORKING_DIR="$DIRECTORY_PATH" # 工作目录为目标目录
PROJECT_DIR="<项目根目录>" # 自动定位项目根目录
RESULT_DIR="$PROJECT_DIR/utd" # 测试结果统一存储目录

# 创建结果目录（不存在则创建）
mkdir -p "$RESULT_DIR"

# 执行远程测试（核心命令，无需修改）
"$UTD_ABS_PATH/utd" remote_test \
--pipeline_file="./.codebase/pipelines/$CI_YAML_FILE_NAME" \
--result_dir="$RESULT_DIR" \
--test_kind=directory \
--status_file="$RESULT_DIR/status" \
--directory="$DIRECTORY_PATH" \
--working_directory="$WORKING_DIR" \
--enable_coverage \
--save_test_log_mode=1
```

## 关键说明
1. CI 配置文件选择规则：必须从 .codebase/pipelines 目录下选择包含 codecov 或 template 关键字的 yaml 文件，确保环境与 CI 一致；
2. 结果存储目录：$PROJECT_DIR/utd 目录会存储所有测试结果，包括：覆盖率报告、用例执行结果、编译日志、运行日志，所有分析均在此目录进行；
3. 路径注意事项：--pipeline_file 参数必须使用相对路径（以.开头），禁止展开为绝对路径，否则会导致配置加载失败；
4. 在执行 utd 之前，务必切换到项目根目录（仓库根目录），即执行 ```cd <仓库根目录>```
