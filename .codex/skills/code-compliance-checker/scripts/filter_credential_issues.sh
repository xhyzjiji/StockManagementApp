#!/usr/bin/env bash
# filter_credential_issues.sh
#
# Credential 规则扫描结果过滤脚本（白名单/已知误报自动剔除）。
#
# 说明：
#   - 当 Credential 规则识别到一条疑似问题后，将 file_path 传入本脚本，
#     若命中以下白名单则视为误报，应从最终报告中过滤掉：
#       1) file_path 匹配 CREDENTIAL_FILTER_FILE_PATH_PATTERNS 任一模式。
#   - 与 Domain 不同，Credential 不维护 "凭证值白名单"——明文凭证一旦真实存在
#     即应整改，不允许通过具体值豁免；豁免维度仅限于 "显然不会进入生产链路"
#     的文档/脚本/构建配置/调试与示例目录。
#   - 匹配采用 bash `[[ $value == $pattern ]]` 的内置 glob 风格，`*` 可匹配
#     包括 `/` 在内的任意字符串。模式与 SKILL 规则文档（Credential.md）保持一致。
#
# 路径解析约定：
#   下文示例中的 `scripts/filter_credential_issues.sh` 是相对本 Skill 根目录的路径。
#   $SKILL_ROOT 由调用方（Agent / 扫描器）在运行时解析为本 Skill 的实际绝对路径，
#   不要把开发仓库内的相对路径（如 plugins/.../code-compliance-checker/）硬编码进调用脚本。
#
# 使用方式：
#   方式 A（推荐，作为库 source 后调用函数）：
#     source "$SKILL_ROOT/scripts/filter_credential_issues.sh"
#     if should_filter_credential_issue "$file_path"; then
#       continue   # 命中白名单，丢弃本条问题
#     fi
#
#   方式 B（独立 CLI，使用 TAB 分隔的 stdin → stdout 流式过滤）：
#     printf '%s\n' "$file_path" | \
#       bash "$SKILL_ROOT/scripts/filter_credential_issues.sh"
#     # 命中白名单的行被丢弃；其他原样输出到 stdout（可保留额外尾列）。
#
# 退出码（函数）：
#   0 → 命中白名单，应过滤（drop）
#   1 → 未命中，保留（keep）

# ---------------------------------------------------------------------------
# 白名单：问题所在文件路径（命中则过滤）
# ---------------------------------------------------------------------------
CREDENTIAL_FILTER_FILE_PATH_PATTERNS=(
  "*.md"
  "*.sh"
  "*gradle*"
  "*.pbxproj"
  "*.podspec"
  "*.doxyfile"
  "*.makefile"
  "*.markdown"
  "*.changelog"
  "*.configure"
  "*/zk_rules/*"
  "*/debug/*"
  "*/debugger/*"
  "*/example/*"
  "*/examples/*"
  "*/test/*"
  "*/tests/*"
  "*/testing/*"
  "*/sample/*"
  "*/samples/*"
  "*/demo/*"
  "*/demos/*"
)

# ---------------------------------------------------------------------------
# 函数：判断 file_path 是否命中文件白名单
# ---------------------------------------------------------------------------
should_filter_file_path() {
  local file_path="$1"
  local pattern
  [[ -z "$file_path" ]] && return 1
  for pattern in "${CREDENTIAL_FILTER_FILE_PATH_PATTERNS[@]}"; do
    # shellcheck disable=SC2053
    if [[ "$file_path" == $pattern ]]; then
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# 函数：综合判断一条 (file_path) 问题是否应被过滤
#   命中文件白名单 → 0（过滤）
# ---------------------------------------------------------------------------
should_filter_credential_issue() {
  local file_path="$1"
  if should_filter_file_path "$file_path"; then
    return 0
  fi
  return 1
}

# ---------------------------------------------------------------------------
# 独立 CLI 模式：仅在脚本被直接执行（非 source）时生效
# 输入：每行 TAB 分隔，第 1 列 file_path，第 2+ 列为附加上下文
# 输出：未命中白名单的行原样输出
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  while IFS=$'\t' read -r file_path rest || [[ -n "$file_path$rest" ]]; do
    [[ -z "$file_path" ]] && continue
    if should_filter_credential_issue "$file_path"; then
      continue
    fi
    if [[ -n "$rest" ]]; then
      printf '%s\t%s\n' "$file_path" "$rest"
    else
      printf '%s\n' "$file_path"
    fi
  done
fi
