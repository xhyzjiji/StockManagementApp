# 凭据获取

获取 `CLOUD_JWT` / `CODEBASE_JWT` 两种认证凭据。认证凭据为敏感信息，未经用户明确要求，严禁回显原始凭据内容。

## 前置依赖

确认登录状态：

```bash
skills get-jwt
```

如果命令执行失败（提示未登录或未安装），先安装：

```bash
npx --yes --registry=https://bnpm.byted.org skills get-jwt
```

该方式不做全局安装；只在当前命令执行时临时获取 `skills` 包并运行。若仍失败，提示用户完成内部工具登录或按本机环境配置 `skills`，不要自动执行全局安装。

## 获取 Token

每次新任务或新 shell 开始时，可先一次性 export 两个 token；同一 shell 内后续命令都会直接复用：

```bash
# Cloud JWT
export CLOUD_JWT=$(skills get-jwt)

# Codebase JWT（专用命令，与 Cloud JWT 不同）
export CODEBASE_JWT=$(skills get-codebase-jwt)
```

Skill 内的脚本内置了自动获取逻辑。仅在脚本因缺少 token 失败时，才需要显式通过上面的 `export` 或脚本的 `--cloud-jwt` / `--codebase-jwt` 等参数传入。

- `CLOUD_JWT`：用于 Cloud 相关 API 调用
- `CODEBASE_JWT`：用于 Codebase OpenAPI 调用（参见 `references/codebase-api.md`）
