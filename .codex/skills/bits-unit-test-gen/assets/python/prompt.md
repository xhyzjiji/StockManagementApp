# Python 语言专属 Prompt

## 函数提取方式

| 工具/手段   | 说明                           |
| ----------- | ------------------------------ |
| `grep`      | 快速定位 `def` / `class` 声明 |
| `ast` 模块  | 精确解析函数和类结构           |
| `inspect`   | 运行时获取函数签名和源码       |
| `pydoc`     | 查看模块/函数文档              |

## 筛选规则（Python 特有）

**跳过：**

- `if __name__ == "__main__"` 入口块
- 自动生成的代码文件（Proto 生成文件、`*_pb2.py`、`*_pb2_grpc.py` 等）
- 包含 `# Code generated` 或 `@generated` 注释的文件
- 少于 3 行的简单 property getter/setter
- 覆盖率超过 90% 的函数
- 纯类型定义文件（仅包含 `TypedDict`、`dataclass` 等声明，无业务逻辑）

## 测试文件命名约定

| 项目     | 约定                                                     |
| -------- | -------------------------------------------------------- |
| 测试文件 | `test_*.py` 或 `*_test.py`                               |
| 位置     | 与源文件同目录（跟随已有约定）                           |
| 测试类名 | `Test{ClassName}`（如 `UserService` → `TestUserService`）|
| 测试函数 | `test_<func>_<scenario>`                                 |

---

## Python 单测规范

### 测试函数/方法签名

- 测试函数必须以 `test_` 开头，pytest 才能自动发现
- 测试类必须以 `Test` 开头，且不能有 `__init__` 方法
- 测试函数参数中可声明 fixture 名称，pytest 自动注入
- 推荐使用函数式测试风格；当多个测试共享 setup 逻辑时才使用测试类

### 测试隔离原则

- 每个测试函数必须独立，不依赖其他测试的执行顺序或副作用
- 禁止在测试函数间通过模块级变量传递状态
- 需要共享 setup 逻辑时，使用 fixture（`@pytest.fixture`）而非模块级变量
- Mock / patch 必须在测试函数作用域内设置和清理，不允许泄漏到其他用例
- 使用 `with` 语句或装饰器形式的 `patch`，确保自动还原

### 断言规范

- 优先使用 pytest 原生 `assert` 语句（pytest 会自动提供详细的失败信息）
- 浮点数比较使用 `pytest.approx(expected, abs=delta)` 或 `assert abs(actual - expected) < delta`
- 集合包含关系使用 `assert item in collection` 或 `assert set_a <= set_b`
- 异常断言使用 `with pytest.raises(ExceptionType) as exc_info:` + 验证消息
- 优先使用精确值比较（`assert result == expected`），但在验证复杂对象非空后再做属性断言的场景中，`assert result is not None` 是合理的前置断言
- 禁止使用 `assertTrue` / `assertEqual` 等 `unittest` 风格断言（除非项目已有约定）

### 异常测试要求

- 可能抛出异常的函数必须覆盖异常路径
- 使用 `pytest.raises` 断言异常类型，并验证异常消息：
  ```python
  with pytest.raises(ValueError, match="不能为空"):
      service.process(None)
  ```
- 需要精确匹配异常消息时，使用 `exc_info.value` 访问异常对象：
  ```python
  with pytest.raises(ValueError) as exc_info:
      service.process(None)
  assert "不能为空" in str(exc_info.value)
  ```

### None/空值处理

- 可选参数需覆盖 `None` 输入场景
- `str` 参数需覆盖空字符串 `""` 和 `None` 两种场景
- `list`/`dict`/`set` 参数需覆盖 `None` 和空集合 `[]`/`{}`/`set()` 两种场景
- `Optional[T]` 返回值需覆盖 `None` 场景
- 数值参数需覆盖 `0`、负数、边界值（如 `sys.maxsize`、`float('inf')`）场景

### 类型安全

- 对于使用 type hints 的函数，测试应覆盖类型不匹配的边界情况（若函数未做类型检查）
- 返回 `TypedDict` / `dataclass` 的函数，需逐字段断言而非整体比较（除非已实现 `__eq__`）

---

## 验证方式

### 测试执行时间记录

在生成的测试代码中，每个测试用例在执行之前记录开始时间，在执行之后记录结束时间，并打印该测试用例的执行时间，便于性能分析。

```python
import time

def test_example():
    start_time = time.time()
    # 测试代码
    assert some_function() == expected
    end_time = time.time()
    print(f"test_example executed in: {end_time - start_time:.6f}s")
```

### local-run

```bash
./scripts/utree local-run -- -m pytest <file> -v
```

### 编译检查

```bash
python -m py_compile <file>
```

### 运行测试

```bash
pytest <file> -v
```

### 覆盖率检查

```bash
pytest <file> -v --cov=<module> --cov-report=term-missing
```

---

## 特殊修复规则

**失败分诊：**

> 缺陷判定的完整规则参见 `references/test-fixer/AGENT.md` 的"失败分诊流程"章节，此处仅列出 Python 特有的补充。

**Python 特有的缺陷信号（必须结合上下文判断，不可直接判定为缺陷）：**
- `TypeError: 'NoneType' object is not subscriptable/iterable/callable` → 可能是空值防护缺失，**但仅当 None 产生于函数内部逻辑时才算缺陷**；测试主动传 None 参数触发的不算
- `AttributeError: 'NoneType' object has no attribute 'xxx'` → 可能是 None 检查遗漏，**同上，需排除测试主动传 None 的情况**
- `IndexError: list index out of range` → 可能是边界检查缺失，**但仅当空列表来自正常业务场景时才算缺陷**
- `KeyError` → 可能是字典键存在性检查缺失，**需确认键值是否来自正常业务输入**
- `ZeroDivisionError` → 可能是除零防护缺失，**大概率是真正缺陷**
- `RecursionError: maximum recursion depth exceeded` → 可能是递归终止条件缺陷，**大概率是真正缺陷**
- 断言失败且 expected 值符合函数的正确语义 → 逻辑缺陷，**大概率是真正缺陷**

- 若 `import` 报 `ModuleNotFoundError`，检查是否缺少依赖或 `sys.path` 配置不正确
- 若 `patch` 的目标路径错误导致 mock 不生效，确保 patch 的是**使用方**的导入路径而非定义方
- 若 fixture 报 `fixture 'xxx' not found`，检查 fixture 是否定义在正确的 `conftest.py` 中
- 若出现 `AttributeError: __enter__` 或 `__exit__`，检查 `patch` 是否误用了非 context manager 形式
- 若异步函数测试报 `RuntimeWarning: coroutine was never awaited`，安装 `pytest-asyncio` 并使用 `@pytest.mark.asyncio` 装饰器

---

## 格式化

```bash
black <file>
```

或 `autopep8 -i <file>`（跟随项目配置）。

若项目使用 `ruff`：

```bash
ruff format <file>
```

---

## 代码风格

风格按优先级确定：用户指令 > AGENTS.md > 同目录已有测试 > 下方默认值。

| 项目           | 约定                                                       |
| -------------- | ---------------------------------------------------------- |
| 场景名/注释语言 | 中文                                                       |
| 命名           | `test_<func>_<scenario>` 或 `Test<Class>`                  |
| 文件           | `test_<module>.py`，与源文件同目录（跟随已有约定）         |
| 断言           | `pytest` + 内置 `assert`（或跟随已有测试）                 |
| Mock           | `unittest.mock.patch` / `pytest-mock`（或跟随已有测试）    |
| 用例组织       | 参数化用 `@pytest.mark.parametrize`                        |
| import 顺序    | 标准库 → 第三方库 → 项目内部模块，各组之间空行分隔        |

---

## Mock 用法

### 基本结构（unittest.mock）

使用 `patch` 装饰器或上下文管理器 mock 外部依赖：

```python
from unittest.mock import patch, MagicMock

def test_get_user_info_正常获取():
    # 1. setup mock
    # 2. 调用被测函数
    # 3. 断言结果
    pass
```

### patch 装饰器形式

```python
@patch("module_under_test.query_user_from_db")
def test_get_user_info_正常获取(mock_query):
    mock_query.return_value = User(id=1001, name="张三")

    result = get_user_info(1001)

    assert result.name == "张三"
    assert result.id == 1001
    mock_query.assert_called_once_with(1001)
```

### patch 上下文管理器形式

```python
def test_get_user_info_数据库查询失败():
    with patch("module_under_test.query_user_from_db") as mock_query:
        mock_query.side_effect = ConnectionError("connection refused")

        with pytest.raises(ServiceError, match="查询失败"):
            get_user_info(1001)

        mock_query.assert_called_once_with(1001)
```

### pytest-mock 形式（mocker fixture）

```python
def test_get_user_info_正常获取(mocker):
    mock_query = mocker.patch("module_under_test.query_user_from_db")
    mock_query.return_value = User(id=1001, name="张三")

    result = get_user_info(1001)

    assert result.name == "张三"
    mock_query.assert_called_once_with(1001)
```

### Mock 类方法

```python
def test_user_service_get_profile_正常获取(mocker):
    mock_dao = mocker.patch.object(UserDAO, "find_by_id")
    mock_dao.return_value = UserProfile(name="李四", email="lisi@example.com")

    svc = UserService()
    profile = svc.get_profile(1001)

    assert profile.name == "李四"
    assert profile.email == "lisi@example.com"
    mock_dao.assert_called_once_with(1001)
```

---

## 示例

### 示例 1：参数化测试（推荐模式）

被测函数：

```python
def add(a: int, b: int) -> int:
    return a + b
```

测试代码：

```python
import sys
import time
import pytest

@pytest.mark.parametrize(
    "a, b, expected",
    [
        pytest.param(1, 2, 3, id="两个正数相加"),
        pytest.param(5, -3, 2, id="正数加负数"),
        pytest.param(-1, -2, -3, id="两个负数相加"),
        pytest.param(10, 0, 10, id="加零"),
        pytest.param(0, 0, 0, id="两个零相加"),
        pytest.param(sys.maxsize, 1, sys.maxsize + 1, id="大数相加"),
    ],
)
def test_add(a, b, expected):
    start_time = time.time()
    assert add(a, b) == expected
    end_time = time.time()
    print(f"test_add [{a}, {b}] executed in: {end_time - start_time:.6f}s")
```

---

## 常见陷阱与修复

| 陷阱                                                 | 原因                                                      | 修复方式                                                            |
| ---------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------- |
| `patch` 不生效，被测函数仍调用真实实现                | patch 的路径不是使用方的导入路径                            | patch 的目标必须是 **使用方模块中的引用**，如 `module_a.func` 而非 `module_b.func` |
| `fixture 'xxx' not found`                            | fixture 未定义在正确的 `conftest.py` 或未导入              | 将 fixture 放到被测文件同级或上级目录的 `conftest.py` 中            |
| `assert` 语句被 Python 优化掉                        | 运行时使用了 `-O` 优化标志                                 | 运行测试时不使用 `-O`，pytest 默认不优化                            |
| `MagicMock` 对任意属性访问都返回新 Mock 不报错        | MagicMock 的默认行为是链式生成子 Mock                      | 使用 `spec=True` 或 `autospec=True` 限制属性访问                   |
| `patch` 装饰器叠加时参数顺序反直觉                   | 多个 `@patch` 从下到上执行，参数从左到右注入               | 注意装饰器顺序：最内层的 `@patch` 对应第一个参数                    |
| 异步测试未执行                                       | 缺少 `pytest-asyncio` 或未添加 `@pytest.mark.asyncio`     | 安装 `pytest-asyncio` 并添加装饰器                                  |
| `parametrize` 中对象参数导致测试 ID 不可读            | 默认显示对象的 `repr`                                     | 使用 `pytest.param(..., id="描述")` 指定可读 ID                    |
| 测试间相互影响                                       | 模块级变量或单例被修改后未还原                              | 在 fixture 中使用 `yield` + 清理逻辑，或使用 `monkeypatch`         |

---

## 上下文挖掘命令

```bash
grep -rn "def \|class " <file>
pip list | grep -i test
cat setup.py setup.cfg pyproject.toml 2>/dev/null
find . -name "test_*.py" -o -name "*_test.py" | head -20
grep -rn "import.*mock\|from.*mock\|@patch\|@pytest" --include="test_*.py" . | head -10
grep -rn "conftest\|fixture" --include="conftest.py" .
```
