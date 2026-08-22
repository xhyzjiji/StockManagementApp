#!/usr/bin/env bash
# filter_keyword_issues.sh
#
# KeyWord 规则扫描脚本（高敏关键词）：扫描指定文件，输出命中的敏感关键词。
#
# 设计要点：
#   1) 高敏感词不允许以明文出现在脚本与文档中，因此本脚本中的关键词、类目
#      名称、豁免路径、豁免正则等"敏感字段"全部以 base64 形式存储，运行
#      时再解码后用于匹配。
#   2) 关键词支持两种类型：
#        lit  → 字面量匹配，case-insensitive
#        re   → 正则匹配，case-insensitive；支持 {,N} 这类速记，运行时会被
#               规整为 {0,N} 以兼容 grep -E。
#   3) 每条规则可附带：
#        exempt_paths  → 路径子串/glob 命中则该规则在该文件上整体不报；
#        exempt_regex  → 命中行若同时匹配任一豁免正则（case-insensitive）
#                        则视为误报。
#   4) 规则来源：神盾导出词表（rule_content_id 即规则号）。本脚本仅承载
#      规则比对逻辑，不对外暴露规则原文，调用方如需展示类目可调用
#      `kw_get_category <rule_id>` 解码（仅在确有展示需要时调用）。
#
# 使用方式：
#   方式 A（作为库 source）：
#     source "$SKILL_ROOT/scripts/filter_keyword_issues.sh"
#     kw_scan_file "path/to/foo.go"
#
#   方式 B（独立 CLI）：
#     bash "$SKILL_ROOT/scripts/filter_keyword_issues.sh" file1 file2 ...
#     # 或从 stdin 读取每行一个文件路径：
#     printf '%s\n' file1 file2 | bash "$SKILL_ROOT/scripts/filter_keyword_issues.sh"
#
# 输出格式（TAB 分隔）：
#   file_path \t line_no \t rule_id \t pattern_type \t matched_line_text
#
#   - rule_id        :  神盾词表中的 rule_content_id
#   - pattern_type   :  lit | re
#   - matched_line_text : 命中行文本（行内 TAB 已替换为单空格，避免列错位）
#
# 退出码：
#   0 → 扫描完成（不论是否有命中）
#   2 → 参数错误

set -o pipefail

# ---------------------------------------------------------------------------
# 规则数据（base64）
# 字段含义： rule_id | pattern_type(lit|re) | base64(pattern)
# ---------------------------------------------------------------------------
KEYWORD_RULES=(
  "60244|lit|Y2FpeWluZ3dlbg=="
  "60245|lit|6YKT5bCP5bmzODk2NA=="
  "60245|lit|ZGVuZ3hpYW9waW5n"
  "60246|lit|5rGf5rO95rCR"
  "60246|lit|amlhbmd6ZW1pbg=="
  "60247|lit|5p6X6YSt5pyI5ail"
  "60248|lit|5q+b5rO95Lic"
  "60248|lit|bWFvemVkb25n"
  "60248|re|Y2hhaXJtYW4ueywyfW1hbw=="
  "60248|re|bWFvLnssMn16ZS57LDJ9ZG9uZw=="
  "60249|lit|5b2t5Li95aqb"
  "60249|lit|cGVuZ2xpeXVhbg=="
  "60250|lit|5Lmg5Lmm6K6w"
  "60250|lit|5Lmg54i354i3"
  "60250|lit|5Lmg5pak54yq"
  "60250|lit|5Lmg56WW5bit"
  "60250|lit|5Lmg5aWl5aGe5pav5bqT"
  "60250|lit|5Lmg6L+R5ZOB"
  "60250|lit|5YiB6L+R5bmz"
  "60250|lit|5YiB6YeR5bmz"
  "60250|lit|5YiB6L+R5ZOB"
  "60250|lit|5YiB6YeR5ZOB"
  "60250|lit|5Lmg5aSn5aSn"
  "60250|lit|5Lmg6Z2Z5bmz"
  "60250|lit|5Lmg6Z2Z5ZOB"
  "60250|lit|eGnov5HlubM="
  "60250|lit|eGnovrbmlqTlubM="
  "60250|lit|eGnov5Hlk4E="
  "60250|lit|eGnovrbmlqTlk4E="
  "60250|lit|eGnpnZnlk4E="
  "60250|lit|eOi/keW5sw=="
  "60250|lit|eOi+tuaWpOW5sw=="
  "60250|lit|eOi/keWTgQ=="
  "60250|lit|eOi+tuaWpOWTgQ=="
  "60250|lit|eOmdmeWTgQ=="
  "60250|lit|5YiB56aB5rOZ"
  "60250|lit|5Lmg5YyF5a2Q"
  "60250|re|WGkueywyfUppblBpbmc="
  "60250|lit|5Lmg6L+R5bmz"
  "60251|re|cGVvcGxlJ3MueywyfWxpYmVyYXRpb24ueywyfWFybXk="
  "60252|lit|UG9saXRidXJv"
  "60253|re|Y2hpbmVzZS57LDJ9Y29tbXVuaXN0LnssMn1wYXJ0eQ=="
  "60253|lit|5YWx5Lqn5YWa"
  "60254|re|Q2hpbmVzZS57LDJ9Y2Vuc29y"
  "60254|re|Q2hpbmVzZS57LDJ9Y2Vuc29yc2hpcA=="
  "60255|re|dGVhLnssMn1wYXJ0eQ=="
  "60256|lit|6buE6IOM5b+D6L+Q5Yqo"
  "60256|lit|6buD6aas55Sy"
  "60257|re|b3BlcmF0aW9uLnssMn15ZWxsb3diaXJk"
  "60258|re|YnJpbmcueywyfWJhY2sueywyfW91ci57LDJ9Z2lybHM="
  "60259|re|ODkueywyfWRlbW9jcmFjeS57LDJ9bW92ZW1lbnQ="
  "60259|re|ODkueywyfXByb3Rlc3Q="
  "60259|re|NjQueywyfXByb3Rlc3Q="
  "60259|re|anVuZS57LDJ9NC57LDJ9aW5jaWRlbnQ="
  "60259|re|anVuZS57LDJ9Zm9ydGgueywyfWluY2lkZW50"
  "60259|re|cmVkcmVzcy57LDJ9SnVuZS57LDJ9NA=="
  "60259|re|anVuZS57LDJ9NC57LDJ9Y3JhY2tkb3du"
  "60260|lit|6IyJ6I6J6Iqx6Z2p5ZG9"
  "60261|lit|5Zub5LqU6YGL5YuV"
  "60262|lit|6aaZ5riv5pq05YuV"
  "60263|re|ZmVkZXJhbC57LDJ9c3RhdGUueywyfW9mLnssMn1uZXcueywyfWNoaW5h"
  "60264|lit|6aKc6Imy6Z2p5ZG9"
  "60264|re|Y29sb3IueywyfXJldm9sdXRpb24="
  "60265|re|VW1icmVsbGEueywyfVJldm9sdXRpb24="
  "60265|lit|6Zuo5YKY6Z2p5ZG9"
  "60266|re|c291bmQueywyfW9mLnssMn1ob3BlLnssMn1yYWRpbw=="
  "60267|re|ZGEueywyfWppLnssMn15dWFu"
  "60268|re|bmV3LnssMn10YW5nLnssMn1keW5hc3R5"
  "60269|lit|6Zu25YWr5a6q56ug"
  "60269|lit|bGluZ2JheGlhbnpoYW5n"
  "60270|lit|5LqU5aSn6Ki05rGC"
  "60271|lit|5byV5rih5rOV5qGI"
  "60271|re|RnVnaXRpdmUueywyfU9mZmVuZGVycy57LDJ9YW5kLnssMn1NdXR1YWwueywyfUxlZ2FsLnssMn1Bc3Npc3RhbmNlLnssMn1pbi57LDJ9Q3JpbWluYWwueywyfU1hdHRlcnMueywyfUxlZ2lzbGF0aW9u"
  "60271|lit|6YCD54qv5qKd5L6L"
  "60271|lit|6YCD54qv5p2h5L6L"
  "60271|lit|6YCB5Lit5qKd5L6L"
  "60271|lit|6YCD54qv5Y+K5YiR5LqL5LqL5a6c55u45LqS5rOV5b6L5Y2U5Yqp5rOV5L6L"
  "60272|lit|6JeP54us"
  "60272|re|RnJlZS57LDJ9VGliZXQ="
  "60273|lit|55aG54us"
  "60274|lit|5Y+w5rm+54us56uL"
  "60275|lit|5riv542o"
  "60275|lit|5riv54us"
  "60275|lit|5YWJ5b6p6aaZ5riv"
  "60275|lit|5pmC5Luj6Z2p5ZG9"
  "60275|lit|5bmr5riv5Ye66IGy"
  "60276|re|RmFsdW4ueywyfUdvbmc="
  "60278|lit|R2Vub2NpZGU="
  "60278|lit|eWFua2Vlcw=="
  "60278|re|Y2hpbmcueywyfWNob25n"
  "60278|re|d2hpdGUueywyfXRyYXNo"
  "60278|lit|UmVkbmVja3M="
  "60278|lit|cmVkc2tpbg=="
  "60278|lit|cGFraXM="
  "60278|re|ZnJlc2gueywyfW9mZi57LDJ9Ym9hdA=="
  "60278|lit|Y2hpbmFtYW4="
  "60278|lit|Y2hpbms="
  "60278|lit|Y2hpbmt5"
  "60278|lit|bmVncm8="
  "60278|lit|bmliYmE="
  "60278|lit|bmlnZ2Vy"
  "60279|re|YXR0YWNrLnssMn1oZWxpY29wdGVy"
  "60280|lit|ZmFnZ290"
  "60281|lit|TWVtb2pp"
  "60281|lit|QW5pbW9qaQ=="
)

# ---------------------------------------------------------------------------
# 类目标签（base64） —— 仅供调用方按需解码展示，默认不输出明文。
# 字段含义： rule_id | base64(category_label)
# ---------------------------------------------------------------------------
KEYWORD_RULE_CATEGORIES=(
  "60244|6JSh6Iux5paH"
  "60245|6YKT5bCP5bmz"
  "60246|5rGf5rO95rCR"
  "60247|5p6X6YOR5pyI5ail"
  "60248|5q+b5rO95Lic"
  "60249|5b2t5Li95aqb"
  "60250|5Lmg6L+R5bmz"
  "60251|5Lq65rCR6Kej5pS+5Yab"
  "60252|5Lit5YWx5Lit5aSu5pS/5rK75bGA"
  "60253|5Lit5Zu95YWx5Lqn5YWa"
  "60254|5Lit5Zu95a6h5p+l5Yi25bqm"
  "60255|6Iy25YWa6L+Q5Yqo"
  "60256|6buE6IOM5b+D6L+Q5Yqo"
  "60257|6buE6ZuA6KGM5Yqo"
  "60258|5bCG5oiR5Lus55qE5aWz5a2p5bim5Zue5p2l6L+Q5Yqo"
  "60259|5YWt5Zub5LqL5Lu2"
  "60260|6IyJ6I6J6Iqx6Z2p5ZG9"
  "60261|5Zub5LqU6L+Q5Yqo"
  "60262|6aaZ5riv5pq05Yqo"
  "60263|5paw5Lit5Zu96IGU6YKm"
  "60264|6aKc6Imy6Z2p5ZG9"
  "60265|6Zuo5Lye6Z2p5ZG9"
  "60266|5biM5pyb5LmL5aOw"
  "60267|5aSn57qq5YWD"
  "60268|5paw5ZSQ5Lq655S16KeG5Y+w"
  "60269|6Zu25YWr5a6q56ug"
  "60270|5LqU5aSn6K+J5rGC"
  "60271|6YCD54qv5Y+K5YiR5LqL5LqL5a6c55u45LqS5rOV5b6L5Y2P5Yqp5rOV5L6L"
  "60272|6KW/6JeP54us56uL"
  "60273|5paw55aG54us56uL"
  "60274|5Y+w5rm+54us56uL"
  "60275|6aaZ5riv54us56uL"
  "60276|5rOV6L2u5Yqf"
  "60278|56eN5peP5q2n6KeG"
  "60279|5oCn5Yir5q2n6KeG"
  "60280|5oCn5ZCR5q2n6KeG"
  "60281|56ue5ZOB5ZWG5ZOB5ZCN"
)

# ---------------------------------------------------------------------------
# 路径级豁免（命中即跳过该规则在该文件上的所有匹配）。
# 字段含义： rule_id | base64(path_substr_1),base64(path_substr_2),...
# 路径匹配采用"子串包含"或 bash glob（包含 * 时按 glob 匹配）。
# ---------------------------------------------------------------------------
KEYWORD_RULE_EXEMPT_PATHS=(
  "60278|Y2h1bms="
)

# ---------------------------------------------------------------------------
# 行级豁免（命中行若同时匹配任一豁免正则，则视为误报丢弃）。
# 字段含义： rule_id | base64(re_1),base64(re_2),...
# 豁免正则采用 case-insensitive 匹配，{,N} 在运行时规整为 {0,N}。
# ---------------------------------------------------------------------------
KEYWORD_RULE_EXEMPT_REGEXES=(
  "60278|cGFraXN0YW4=,cXVhZHJvLW5lZ3Jv,Q2hpbmtSdWxl,Y2hpbmtz,Q0hJTktPVVNQQU4=,Q0hJTktFRA==,TmV3LnssMn1Zb3JrLnssMn1ZYW5rZWVz,UkVEU0tJTlM="
)

# ---------------------------------------------------------------------------
# KeyWord.md 文档级豁免（明文关键词的特定路径豁免）：
#   说明：以下条目不属于"高敏新增词表"，仅用于文档化已有 KeyWord.md 内的
#   明文关键词在特定文件上的允许出现规则；为避免在脚本中扩散更多明文，
#   这些条目同样以 base64 存储 keyword 与 path glob。
#
# 字段含义： base64(keyword) | base64(path_glob_1),base64(path_glob_2),...
# 当前条目：
#   - douyin / 抖音 在 go.mod、go.sum 中允许出现。
# ---------------------------------------------------------------------------
KEYWORD_DOC_EXEMPT_PATHS=(
  "ZG91eWlu|Ki9nby5tb2Q=,Ki9nby5zdW0=,Z28ubW9k,Z28uc3Vt"
  "5oqW6Z+z|Ki9nby5tb2Q=,Ki9nby5zdW0=,Z28ubW9k,Z28uc3Vt"
)

# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

# base64 -d 在 GNU/BSD 上均支持
_kw_b64decode() {
  printf '%s' "$1" | base64 -d 2>/dev/null
}

# 将 {,N} 速记规整为 {0,N}，提升 grep -E / BRE/ERE 兼容性
_kw_normalize_regex() {
  printf '%s' "$1" | sed -e 's/{,/{0,/g'
}

# 小写化（兼容 bash 3.2 / macOS 默认 shell）
_kw_to_lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

# 通过 rule_id 取出（解码后的）类目标签（仅在调用方需要展示时使用）
kw_get_category() {
  local rid="$1" entry
  for entry in "${KEYWORD_RULE_CATEGORIES[@]}"; do
    if [[ "${entry%%|*}" == "$rid" ]]; then
      _kw_b64decode "${entry#*|}"
      return 0
    fi
  done
  return 1
}

# 将 b64 csv 流解码为每行一个的明文 stream
_kw_iter_b64csv() {
  local b64csv="$1"
  [[ -z "$b64csv" ]] && return 0
  local IFS=','
  local b
  for b in $b64csv; do
    [[ -z "$b" ]] && continue
    _kw_b64decode "$b"
    printf '\n'
  done
}

# 取某 rule 的豁免路径（每行一条）
_kw_iter_exempt_paths() {
  local rid="$1" entry
  for entry in "${KEYWORD_RULE_EXEMPT_PATHS[@]}"; do
    if [[ "${entry%%|*}" == "$rid" ]]; then
      _kw_iter_b64csv "${entry#*|}"
      return 0
    fi
  done
}

# 取某 rule 的豁免正则（每行一条）
_kw_iter_exempt_regexes() {
  local rid="$1" entry
  for entry in "${KEYWORD_RULE_EXEMPT_REGEXES[@]}"; do
    if [[ "${entry%%|*}" == "$rid" ]]; then
      _kw_iter_b64csv "${entry#*|}"
      return 0
    fi
  done
}

# 路径子串/glob 命中检测：命中返回 0
_kw_path_hits_pattern() {
  local file_path="$1" pat="$2"
  [[ -z "$pat" ]] && return 1
  if [[ "$pat" == *"*"* || "$pat" == *"?"* || "$pat" == *"["* ]]; then
    # shellcheck disable=SC2053
    [[ "$file_path" == $pat ]]
    return $?
  fi
  [[ "$file_path" == *"$pat"* ]]
}

# 路径级豁免（针对单条 rule_id）：命中返回 0
kw_path_exempt_for_rule() {
  local rid="$1" file_path="$2" pat
  while IFS= read -r pat; do
    [[ -z "$pat" ]] && continue
    if _kw_path_hits_pattern "$file_path" "$pat"; then
      return 0
    fi
  done < <(_kw_iter_exempt_paths "$rid")
  return 1
}

# 行级豁免（针对单条 rule_id）：命中返回 0
kw_line_exempt_for_rule() {
  local rid="$1" line="$2" pat npat
  while IFS= read -r pat; do
    [[ -z "$pat" ]] && continue
    npat="$(_kw_normalize_regex "$pat")"
    if printf '%s' "$line" | grep -E -i -q -- "$npat" 2>/dev/null; then
      return 0
    fi
  done < <(_kw_iter_exempt_regexes "$rid")
  return 1
}

# KeyWord.md 文档级关键词的路径豁免检查：
#   入参：明文 keyword（任意大小写），file_path
#   命中返回 0（应豁免）
kw_doc_exempt_for_keyword() {
  local kw="$1" file_path="$2" entry b64kw rest plain pat kw_lower plain_lower
  kw_lower="$(_kw_to_lower "$kw")"
  for entry in "${KEYWORD_DOC_EXEMPT_PATHS[@]}"; do
    b64kw="${entry%%|*}"
    rest="${entry#*|}"
    plain="$(_kw_b64decode "$b64kw")"
    [[ -z "$plain" ]] && continue
    plain_lower="$(_kw_to_lower "$plain")"
    if [[ "$plain_lower" == "$kw_lower" ]]; then
      while IFS= read -r pat; do
        [[ -z "$pat" ]] && continue
        if _kw_path_hits_pattern "$file_path" "$pat"; then
          return 0
        fi
      done < <(_kw_iter_b64csv "$rest")
    fi
  done
  return 1
}

# 扫描单个文件，输出 TAB 分隔的命中信息
# 输出列： file_path \t line_no \t rule_id \t pattern_type \t matched_line_text
kw_scan_file() {
  local file_path="$1"
  [[ -z "$file_path" ]] && return 0
  if [[ ! -r "$file_path" || ! -f "$file_path" ]]; then
    return 0
  fi

  local entry rid rest ptype b64pat pattern npat
  local raw lineno line_text sanitized
  for entry in "${KEYWORD_RULES[@]}"; do
    rid="${entry%%|*}"
    rest="${entry#*|}"
    ptype="${rest%%|*}"
    b64pat="${rest#*|}"
    pattern="$(_kw_b64decode "$b64pat")"
    [[ -z "$pattern" ]] && continue

    if kw_path_exempt_for_rule "$rid" "$file_path"; then
      continue
    fi

    case "$ptype" in
      lit)
        while IFS= read -r raw; do
          [[ -z "$raw" ]] && continue
          lineno="${raw%%:*}"
          line_text="${raw#*:}"
          if kw_line_exempt_for_rule "$rid" "$line_text"; then
            continue
          fi
          sanitized="${line_text//$'\t'/ }"
          printf '%s\t%s\t%s\t%s\t%s\n' "$file_path" "$lineno" "$rid" "lit" "$sanitized"
        done < <(grep -n -i -I -F -- "$pattern" "$file_path" 2>/dev/null)
        ;;
      re)
        npat="$(_kw_normalize_regex "$pattern")"
        while IFS= read -r raw; do
          [[ -z "$raw" ]] && continue
          lineno="${raw%%:*}"
          line_text="${raw#*:}"
          if kw_line_exempt_for_rule "$rid" "$line_text"; then
            continue
          fi
          sanitized="${line_text//$'\t'/ }"
          printf '%s\t%s\t%s\t%s\t%s\n' "$file_path" "$lineno" "$rid" "re" "$sanitized"
        done < <(grep -n -i -I -E -- "$npat" "$file_path" 2>/dev/null)
        ;;
      *)
        ;;
    esac
  done
}

# 批量扫描多个文件（参数列表）
kw_scan_files() {
  local f
  for f in "$@"; do
    kw_scan_file "$f"
  done
}

# ---------------------------------------------------------------------------
# CLI 模式：仅在直接执行（非 source）时生效
#   - 有参数：依次扫描每个文件
#   - 无参数：从 stdin 读取文件路径（每行一个）
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  if [[ $# -ge 1 ]]; then
    kw_scan_files "$@"
  else
    while IFS= read -r f || [[ -n "$f" ]]; do
      [[ -z "$f" ]] && continue
      kw_scan_file "$f"
    done
  fi
fi
