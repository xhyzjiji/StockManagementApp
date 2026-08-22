import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kb_common import DEFAULT_EXCLUDES, SOURCE_EXTS, iter_files, repo_root, resolve_repo_path

SWIFT_TYPE_DECL_RE = re.compile(
    r"^\s*(?:public|open|internal|fileprivate|private)?\s*(?:final\s+)?"
    # negative lookahead: `class func` / `class var` / `class let` etc. are type-MEMBER
    # declarations, not a type named "func"/"var". Without this, `class func foo()` is
    # mis-parsed as a class named `func` (which then dominates fan-in counts).
    r"(class|struct|enum|protocol|actor)\s+(?!(?:func|var|let|init|deinit|subscript|associatedtype|typealias)\b)([A-Za-z_]\w*)\b"
)
SWIFT_EXT_DECL_RE = re.compile(r"^\s*extension\s+([A-Za-z_]\w*)\b")
SWIFT_CONFORMANCE_RE = re.compile(r":\s*([A-Za-z_]\w*)")

OBJC_INTERFACE_RE = re.compile(r"^\s*@interface\s+([A-Za-z_]\w*)\b")
OBJC_IMPLEMENTATION_RE = re.compile(r"^\s*@implementation\s+([A-Za-z_]\w*)\b")
OBJC_PROTOCOL_RE = re.compile(r"^\s*@protocol\s+([A-Za-z_]\w*)\b")
# `@interface Foo (Cat)` / `@interface Foo ()` / `@implementation Foo (Cat)` extend an
# EXISTING class; they are not a declaration of `Foo`. Treating them as one mis-attributes a
# type to a category file (and wrongly elevates externally-defined base classes like GPBMessage
# that only appear here via local categories). The optional `<...>` clause also catches a
# category on a lightweight-generic class, e.g. `@interface NSArray<ObjectType> (MyCat)`.
OBJC_CATEGORY_RE = re.compile(r"^\s*@(?:interface|implementation)\s+[A-Za-z_]\w*\s*(?:<[^>]*>\s*)?\(")
# `@protocol Foo;` / `@protocol Foo, Bar;` is a forward declaration, not a definition. A real
# definition is `@protocol Foo <...>` or `@protocol Foo` followed by a body. Without this, a
# forward decl in a .h shadows the real definition (e.g. a Swift `protocol Foo`).
OBJC_PROTOCOL_FWD_RE = re.compile(r"^\s*@protocol\s+[A-Za-z_]\w*\s*[;,]")

KOTLIN_TYPE_DECL_RE = re.compile(
    r"^\s*(?P<prefix>(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|private|protected|internal|final|open|abstract|sealed|data|enum|annotation|value|inline|fun|inner|external|expect|actual)\s+)*)?"
    r"(?P<kw>class|interface|object)\s+(?P<name>[A-Za-z_]\w*)\b"
)

JAVA_ANNOTATION_TYPE_RE = re.compile(
    r"^\s*(?P<prefix>(?:public|protected|private)\s+)?@interface\s+(?P<name>[A-Za-z_]\w*)\b"
)
JAVA_TYPE_DECL_RE = re.compile(
    r"^\s*(?P<prefix>(?:public|protected|private|static|final|abstract|strictfp|sealed|non-sealed)\s+)*"
    r"(?P<kw>class|interface|enum|record)\s+(?P<name>[A-Za-z_]\w*)\b"
)

# Rust：struct / enum / trait / type alias / union；impl 块不产生新类型名，单独识别用于
# 复杂度归并（impl Foo / impl Trait for Foo 都归到 Foo 名下）。
# `pub(crate)` / `pub(super)` 一律算 public（对模块外可见即算 API 面）。
RUST_TYPE_DECL_RE = re.compile(
    r"^\s*(?P<prefix>(?:#\[[^\]]*\]\s*)*(?:pub(?:\([^)]*\))?\s+)?)"
    r"(?P<kw>struct|enum|trait|type|union)\s+(?P<name>[A-Za-z_]\w*)\b"
)
RUST_IMPL_RE = re.compile(
    r"^\s*(?:unsafe\s+)?impl(?:\s*<[^>]*>)?\s+(?:(?:[A-Za-z_][\w:]*)(?:\s*<[^>]*>)?\s+for\s+)?(?P<name>[A-Za-z_]\w*)\b"
)

IDENT_RE = re.compile(r"\b[A-Za-z_]\w*\b")


@dataclass(frozen=True)
class TypeDecl:
    name: str
    kind: str
    file_path: Path
    is_public: bool


def _strip_comments_and_strings(text: str) -> str:
    i = 0
    n = len(text)
    out: list[str] = []

    def push_spaces(count: int) -> None:
        if count > 0:
            out.append(" " * count)

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if ch == "/" and nxt == "/":
            j = i
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            push_spaces(i - j)
            continue

        if ch == "/" and nxt == "*":
            j = i
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            push_spaces(i - j)
            continue

        if ch == '"' and text[i : i + 3] == '"""':
            j = i
            i += 3
            while i + 2 < n and text[i : i + 3] != '"""':
                i += 1
            i = min(n, i + 3)
            push_spaces(i - j)
            continue

        if ch == '"':
            j = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            push_spaces(i - j)
            continue

        if ch == "'" and nxt:
            j = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "'":
                    i += 1
                    break
                i += 1
            push_spaces(i - j)
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _is_public_swift_decl_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("public ") or stripped.startswith("open ")


def _is_public_kotlin_decl_prefix(prefix: str) -> bool:
    toks = set(IDENT_RE.findall(prefix))
    return not ({"private", "protected", "internal"} & toks)


def _kotlin_kind(prefix: str, kw: str) -> str:
    if kw != "class":
        return kw
    toks = set(IDENT_RE.findall(prefix))
    if "enum" in toks:
        return "enum"
    if "annotation" in toks:
        return "annotation"
    return "class"


def _is_public_java_decl_prefix(prefix: str) -> bool:
    toks = set(IDENT_RE.findall(prefix))
    return "public" in toks


def _is_public_rust_decl_prefix(prefix: str) -> bool:
    # Rust 默认私有；带 pub（含 pub(crate)/pub(super)）才是对外可见。
    return bool(re.search(r"\bpub\b", prefix or ""))


def _rust_kind(kw: str) -> str:
    return {"struct": "rust_struct", "enum": "rust_enum", "trait": "rust_trait",
            "type": "rust_type_alias", "union": "rust_union"}.get(kw, "rust_type")


def _collect_type_decls(module_root: Path, excludes: set[str]) -> tuple[dict[str, TypeDecl], dict[Path, set[str]]]:
    decls: dict[str, TypeDecl] = {}
    file_to_decls: dict[Path, set[str]] = {}

    for p in iter_files(module_root, SOURCE_EXTS, excludes):
        suffix = p.suffix.lower()
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        decl_names: set[str] = set()
        for line in raw.splitlines():
            if suffix == ".swift":
                m = SWIFT_TYPE_DECL_RE.match(line)
                if m:
                    kind, name = m.group(1), m.group(2)
                    if name not in decls:
                        decls[name] = TypeDecl(
                            name=name, kind=kind, file_path=p, is_public=_is_public_swift_decl_line(line)
                        )
                    decl_names.add(name)
                    continue

            if suffix == ".kt":
                m4 = KOTLIN_TYPE_DECL_RE.match(line)
                if m4:
                    name = m4.group("name")
                    prefix = m4.group("prefix") or ""
                    kind = _kotlin_kind(prefix, m4.group("kw"))
                    if name not in decls:
                        decls[name] = TypeDecl(
                            name=name,
                            kind=kind,
                            file_path=p,
                            is_public=_is_public_kotlin_decl_prefix(prefix),
                        )
                    decl_names.add(name)
                    continue

            if suffix == ".rs":
                m6 = RUST_TYPE_DECL_RE.match(line)
                if m6:
                    name = m6.group("name")
                    if name not in decls:
                        decls[name] = TypeDecl(
                            name=name,
                            kind=_rust_kind(m6.group("kw")),
                            file_path=p,
                            is_public=_is_public_rust_decl_prefix(m6.group("prefix")),
                        )
                    decl_names.add(name)
                    continue
                # impl 块：类型名已在别处声明（同文件或同模块），只记引用、不新建声明
                m7 = RUST_IMPL_RE.match(line)
                if m7:
                    decl_names.add(m7.group("name"))
                    continue

            if suffix == ".java":
                m5 = JAVA_ANNOTATION_TYPE_RE.match(line)
                if m5:
                    name = m5.group("name")
                    prefix = m5.group("prefix") or ""
                    if name not in decls:
                        decls[name] = TypeDecl(name=name, kind="annotation", file_path=p, is_public=_is_public_java_decl_prefix(prefix))
                    decl_names.add(name)
                    continue

                m6 = JAVA_TYPE_DECL_RE.match(line)
                if m6:
                    name = m6.group("name")
                    prefix = m6.group("prefix") or ""
                    kind = m6.group("kw")
                    if name not in decls:
                        decls[name] = TypeDecl(name=name, kind=kind, file_path=p, is_public=_is_public_java_decl_prefix(prefix))
                    decl_names.add(name)
                    continue

            if suffix in {".h", ".m", ".mm"}:
                m2 = OBJC_INTERFACE_RE.match(line) or OBJC_IMPLEMENTATION_RE.match(line)
                if m2:
                    if OBJC_CATEGORY_RE.match(line):
                        continue  # category/extension on an existing class, not a declaration
                    name = m2.group(1)
                    if name not in decls:
                        decls[name] = TypeDecl(name=name, kind="objc_class", file_path=p, is_public=(p.suffix == ".h"))
                    decl_names.add(name)
                    continue

                m3 = OBJC_PROTOCOL_RE.match(line)
                if m3:
                    if OBJC_PROTOCOL_FWD_RE.match(line):
                        continue  # forward declaration, not a definition
                    name = m3.group(1)
                    if name not in decls:
                        decls[name] = TypeDecl(name=name, kind="objc_protocol", file_path=p, is_public=(p.suffix == ".h"))
                    decl_names.add(name)

        if decl_names:
            file_to_decls[p] = decl_names

    return decls, file_to_decls


def _collect_file_idents(module_root: Path, excludes: set[str]) -> dict[Path, set[str]]:
    file_idents: dict[Path, set[str]] = {}
    for p in iter_files(module_root, SOURCE_EXTS, excludes):
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cleaned = _strip_comments_and_strings(raw)
        file_idents[p] = set(IDENT_RE.findall(cleaned))
    return file_idents


def _pagerank(edges: dict[str, set[str]], damping: float = 0.85, iters: int = 50) -> dict[str, float]:
    nodes = list(edges.keys())
    if not nodes:
        return {}
    for outs in list(edges.values()):
        for dst in outs:
            if dst not in edges:
                edges[dst] = set()
    nodes = list(edges.keys())
    n = len(nodes)
    pr = {k: 1.0 / n for k in nodes}
    out_deg = {k: max(1, len(v)) for k, v in edges.items()}

    incoming: dict[str, list[str]] = {k: [] for k in nodes}
    for src, outs in edges.items():
        for dst in outs:
            incoming.setdefault(dst, []).append(src)

    for _ in range(iters):
        new_pr: dict[str, float] = {}
        sink_mass = sum(pr[k] for k, v in edges.items() if len(v) == 0)
        base = (1.0 - damping) / n
        for node in nodes:
            rank = base
            rank += damping * sink_mass / n
            for src in incoming.get(node, []):
                rank += damping * pr[src] / out_deg[src]
            new_pr[node] = rank
        pr = new_pr

    return pr


SWIFT_CONTROL_TOKENS_RE = re.compile(r"\b(if|else|for|while|switch|case|guard|catch|throw|try|defer|repeat)\b")
SWIFT_FUNC_TOKENS_RE = re.compile(r"\bfunc\b")
KOTLIN_CONTROL_TOKENS_RE = re.compile(r"\b(if|else|for|while|when|catch|throw|try|finally|return|break|continue)\b")
KOTLIN_FUNC_TOKENS_RE = re.compile(r"\bfun\b")
OBJC_CONTROL_TOKENS_RE = re.compile(r"\b(if|else|for|while|switch|case)\b|@(?:try|catch|finally|autoreleasepool)\b")
OBJC_METHOD_SIG_RE = re.compile(r"^[ \t]*[+-]\s*\(")
JAVA_CONTROL_TOKENS_RE = re.compile(r"\b(if|else|for|while|switch|case|catch|throw|try|finally|return|break|continue)\b")
JAVA_METHOD_SIG_RE = re.compile(
    r"^(?![ \t]*(?:if|for|while|switch|catch|do|try|else)\b)[ \t]*"
    r"(?:@[\w.]+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|protected|private|static|final|abstract|synchronized|native|strictfp)\s+)*"
    r"(?:[\w\<\>\[\], ?]+\s+)?"
    r"[A-Za-z_]\w*\s*\([^;]*\)\s*(?:throws\s+[\w\<\>\[\].,\s]+)?\s*\{"
)

# 方法签名匹配前压缩长空白 run（2026-07-23 MediaBox ademo_live 实锤修复）：
# _strip_comments_and_strings 用等长空格顶替字符串/注释（保列号），会产出上千个连续空格的
# 「剥离残迹行」；JAVA_METHOD_SIG_RE 的可选前缀组与含空格字符类在这类行上指数回溯——
# 单行 re.match 数秒~挂死（select-key-classes 整体超时、validator --strict 连带失败）。
# 签名判定与空白 run 长度无关，匹配前把 ≥8 连续空白压成单空格即免疫；仅用于签名匹配的
# 临时副本，不改 cleaned 文本本体（列号语义保留给其它消费方）。
_SIG_WS_RUN_RE = re.compile(r"[ \t]{8,}")


def _sig_line(l: str) -> str:
    return _SIG_WS_RUN_RE.sub(" ", l) if len(l) > 200 else l


def _brace_block_end(cleaned_lines: list[str], start_idx: int) -> int:
    n = len(cleaned_lines)
    brace_open_idx: Optional[int] = None
    depth = 0
    for i in range(start_idx, n):
        line = cleaned_lines[i]
        if brace_open_idx is None:
            if "{" not in line:
                continue
            brace_open_idx = i
            depth = line.count("{") - line.count("}")
            if depth <= 0:
                return i
            continue
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            return i
    return n - 1


def _swift_block_end(cleaned_lines: list[str], start_idx: int) -> int:
    return _brace_block_end(cleaned_lines, start_idx)


def _objc_block_end(cleaned_lines: list[str], start_idx: int) -> int:
    n = len(cleaned_lines)
    for i in range(start_idx, n):
        if "@end" in cleaned_lines[i]:
            return i
    return n - 1


def _accumulate_loc_complexity(
    loc_by_type: dict[str, int],
    cx_by_type: dict[str, int],
    type_name: str,
    block_cleaned_lines: list[str],
    lang: str,
) -> None:
    if not block_cleaned_lines:
        return
    loc = sum(1 for l in block_cleaned_lines if l.strip())
    text = "\n".join(block_cleaned_lines)
    if lang == "swift":
        control = len(SWIFT_CONTROL_TOKENS_RE.findall(text))
        funcs = len(SWIFT_FUNC_TOKENS_RE.findall(text))
        complexity = control + (2 * funcs)
    elif lang == "kotlin":
        control = len(KOTLIN_CONTROL_TOKENS_RE.findall(text))
        funcs = len(KOTLIN_FUNC_TOKENS_RE.findall(text))
        complexity = control + (2 * funcs)
    elif lang == "java":
        control = len(JAVA_CONTROL_TOKENS_RE.findall(text))
        funcs = sum(1 for l in block_cleaned_lines if JAVA_METHOD_SIG_RE.match(_sig_line(l)))
        complexity = control + (2 * funcs)
    else:
        control = len(OBJC_CONTROL_TOKENS_RE.findall(text))
        funcs = sum(1 for l in block_cleaned_lines if OBJC_METHOD_SIG_RE.match(_sig_line(l)))
        complexity = control + (2 * funcs)

    loc_by_type[type_name] = loc_by_type.get(type_name, 0) + loc
    cx_by_type[type_name] = cx_by_type.get(type_name, 0) + complexity


def _collect_type_loc_complexity(
    module_root: Path, excludes: set[str], decls: dict[str, TypeDecl]
) -> tuple[dict[str, int], dict[str, int]]:
    loc_by_type: dict[str, int] = {name: 0 for name in decls}
    cx_by_type: dict[str, int] = {name: 0 for name in decls}

    for p in iter_files(module_root, SOURCE_EXTS, excludes):
        suffix = p.suffix.lower()
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cleaned = _strip_comments_and_strings(raw)
        raw_lines = raw.splitlines()
        cleaned_lines = cleaned.splitlines()
        if len(cleaned_lines) < len(raw_lines):
            cleaned_lines += [""] * (len(raw_lines) - len(cleaned_lines))

        if suffix == ".swift":
            for idx, line in enumerate(raw_lines):
                m = SWIFT_TYPE_DECL_RE.match(line)
                if m:
                    type_name = m.group(2)
                    if type_name not in decls:
                        continue
                    end = _swift_block_end(cleaned_lines, idx)
                    _accumulate_loc_complexity(
                        loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="swift"
                    )
                    continue

                mext = SWIFT_EXT_DECL_RE.match(line)
                if mext:
                    type_name = mext.group(1)
                    if type_name not in decls:
                        continue
                    end = _swift_block_end(cleaned_lines, idx)
                    _accumulate_loc_complexity(
                        loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="swift"
                    )

        if suffix == ".kt":
            for idx, line in enumerate(raw_lines):
                m4 = KOTLIN_TYPE_DECL_RE.match(line)
                if not m4:
                    continue
                type_name = m4.group("name")
                if type_name not in decls:
                    continue
                end = _brace_block_end(cleaned_lines, idx)
                _accumulate_loc_complexity(loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="kotlin")

        if suffix == ".rs":
            for idx, line in enumerate(raw_lines):
                m6 = RUST_TYPE_DECL_RE.match(line) or RUST_IMPL_RE.match(line)
                if not m6:
                    continue
                type_name = m6.group("name")
                if type_name not in decls:
                    continue
                # 单行声明（`pub struct Unit;` / `type X = Y;`）没有大括号块，只算这一行
                end = _brace_block_end(cleaned_lines, idx) if "{" in cleaned_lines[idx] else idx
                _accumulate_loc_complexity(loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="rust")

        if suffix == ".java":
            for idx, line in enumerate(raw_lines):
                m5 = JAVA_ANNOTATION_TYPE_RE.match(line)
                if m5:
                    type_name = m5.group("name")
                    if type_name not in decls:
                        continue
                    end = _brace_block_end(cleaned_lines, idx)
                    _accumulate_loc_complexity(loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="java")
                    continue

                m6 = JAVA_TYPE_DECL_RE.match(line)
                if not m6:
                    continue
                type_name = m6.group("name")
                if type_name not in decls:
                    continue
                end = _brace_block_end(cleaned_lines, idx)
                _accumulate_loc_complexity(loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="java")

        if suffix in {".h", ".m", ".mm"}:
            for idx, line in enumerate(raw_lines):
                m = OBJC_INTERFACE_RE.match(line) or OBJC_IMPLEMENTATION_RE.match(line)
                if m:
                    type_name = m.group(1)
                    if type_name not in decls:
                        continue
                    end = _objc_block_end(cleaned_lines, idx)
                    _accumulate_loc_complexity(
                        loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="objc"
                    )
                    continue

                m2 = OBJC_PROTOCOL_RE.match(line)
                if m2:
                    if OBJC_PROTOCOL_FWD_RE.match(line):
                        continue  # forward declaration has no @end; would over-count to next block
                    type_name = m2.group(1)
                    if type_name not in decls:
                        continue
                    end = _objc_block_end(cleaned_lines, idx)
                    _accumulate_loc_complexity(
                        loc_by_type, cx_by_type, type_name, cleaned_lines[idx : end + 1], lang="objc"
                    )

    return loc_by_type, cx_by_type


SUPPORTED_LANG_LABEL = "Swift/ObjC/Kotlin/Java/C-family/Rust"

# 常见源码后缀（不在 SOURCE_EXTS 里的那些）：只用来在零候选时告诉人「这目录是别的语言」，
# 不参与扫描。列得不全没关系——兜底那句会把未识别的后缀原样列出来。
_KNOWN_OTHER_SOURCE_EXTS = {
    ".go", ".py", ".ts", ".tsx", ".js", ".jsx", ".dart", ".cs", ".rb", ".php", ".scala", ".lua", ".ex", ".exs",
}


def _explain_zero_candidates(module_root: Path, excludes: set[str]) -> str:
    """零候选时的诊断文案：分清「没源码 / 有源码但语言不支持 / 语言支持但没声明」三种。"""
    from collections import Counter

    scanned = list(iter_files(module_root, SOURCE_EXTS, excludes))
    if scanned:
        return (
            f"No {SUPPORTED_LANG_LABEL} type declarations found under: {module_root} "
            f"(scanned {len(scanned)} supported source files; module has no type-level declarations)"
        )
    # 没扫到任何支持的文件：看看目录里到底有什么
    other = Counter()
    for p in module_root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in excludes for part in p.parts):
            continue
        if p.suffix in _KNOWN_OTHER_SOURCE_EXTS or (p.suffix and p.suffix not in SOURCE_EXTS and len(p.suffix) <= 6):
            other[p.suffix] += 1
    if other:
        detail = ", ".join(f"{ext}×{n}" for ext, n in other.most_common(6))
        return (
            f"UNSUPPORTED LANGUAGE: no {SUPPORTED_LANG_LABEL} source files under {module_root}; "
            f"found only: {detail}. select-key-classes cannot score this module — "
            f"add the language to SOURCE_EXTS + a declaration matcher in kb_select_key_classes.py."
        )
    return f"No source files found under: {module_root}"


def select_key_classes(args: argparse.Namespace) -> int:
    repo = repo_root(Path.cwd())
    module_root = resolve_repo_path(args.path, repo)
    excludes = DEFAULT_EXCLUDES

    decls, file_to_decls = _collect_type_decls(module_root, excludes)
    if not decls:
        # 零候选时把「为什么是零」说清楚——上游 SOP 据此判 not_qualified，而那条路径是静默的
        # （exit 0、不建 MR）。2026-08-19 一个 Rust 模块就这样被判成 not_qualified：7 个 .rs 文件
        # 一个都没被打开，报错却只说「没有 Swift/ObjC/Kotlin/Java 声明」，看的人以为是模块太薄。
        # 现在分三种情况说：目录里压根没有源文件 / 有源文件但全是不支持的语言 / 支持的语言里确实没声明。
        print(_explain_zero_candidates(module_root, excludes))
        return 0

    file_idents = _collect_file_idents(module_root, excludes)
    symbol_names = set(decls.keys())

    fan_in_files: dict[str, int] = {name: 0 for name in symbol_names}
    fan_in_file_sets: dict[str, set[Path]] = {name: set() for name in symbol_names}

    for file_path, idents in file_idents.items():
        touched = idents.intersection(symbol_names)
        if not touched:
            continue
        for name in touched:
            decl_file = decls[name].file_path
            if file_path == decl_file:
                continue
            fan_in_file_sets[name].add(file_path)

    for name, s in fan_in_file_sets.items():
        fan_in_files[name] = len(s)

    file_refs: dict[Path, set[str]] = {}
    for file_path, idents in file_idents.items():
        file_refs[file_path] = idents.intersection(symbol_names)

    fan_out: dict[str, int] = {}
    edges: dict[str, set[str]] = {name: set() for name in symbol_names}
    for name, decl in decls.items():
        refs_in_file = set(file_refs.get(decl.file_path, set()))
        same_file_decls = file_to_decls.get(decl.file_path, set())
        refs_in_file.difference_update(same_file_decls)
        refs_in_file.discard(name)
        fan_out[name] = len(refs_in_file)
        edges[name] = refs_in_file

    pr = _pagerank({k: set(v) for k, v in edges.items()}, damping=args.damping, iters=args.iters)
    loc_by_type, cx_by_type = _collect_type_loc_complexity(module_root, excludes, decls)

    implementers: dict[str, int] = {name: 0 for name in symbol_names}
    protocol_names = {n for n, d in decls.items() if d.kind in {"protocol", "objc_protocol", "interface"}}

    for file_path, decl_names in file_to_decls.items():
        suffix = file_path.suffix.lower()
        if suffix not in {".swift", ".kt", ".java"}:
            continue
        try:
            raw = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in raw.splitlines():
            if suffix == ".swift":
                m = SWIFT_TYPE_DECL_RE.match(line)
                if not m:
                    continue
                _name = m.group(2)
                if _name not in decl_names:
                    continue
                if ":" not in line:
                    continue
                for proto in SWIFT_CONFORMANCE_RE.findall(line):
                    if proto in protocol_names:
                        implementers[proto] = implementers.get(proto, 0) + 1
                continue

            if suffix == ".kt":
                m4 = KOTLIN_TYPE_DECL_RE.match(line)
                if not m4:
                    continue
                _name = m4.group("name")
                if _name not in decl_names:
                    continue
                if ":" not in line:
                    continue
                tail = line.split(":", 1)[1]
                if "{" in tail:
                    tail = tail.split("{", 1)[0]
                for t in IDENT_RE.findall(tail):
                    if t in protocol_names:
                        implementers[t] = implementers.get(t, 0) + 1
                continue

            m6 = JAVA_TYPE_DECL_RE.match(line)
            if not m6:
                continue
            _name = m6.group("name")
            if _name not in decl_names:
                continue
            kw = m6.group("kw")
            if kw == "interface":
                if "extends" not in line:
                    continue
                tail = line.split("extends", 1)[1]
                if "{" in tail:
                    tail = tail.split("{", 1)[0]
                for t in IDENT_RE.findall(tail):
                    if t in protocol_names:
                        implementers[t] = implementers.get(t, 0) + 1
                continue

            if "implements" not in line:
                continue
            tail = line.split("implements", 1)[1]
            if "{" in tail:
                tail = tail.split("{", 1)[0]
            for t in IDENT_RE.findall(tail):
                if t in protocol_names:
                    implementers[t] = implementers.get(t, 0) + 1

    def norm_log_map(values: dict[str, float]) -> dict[str, float]:
        if not values:
            return {}
        min_v = min(values.values())
        max_v = max(values.values())
        if max_v <= 0 or max_v == min_v:
            return {k: 0.0 for k in values}
        max_log = math.log1p(max_v)
        if max_log <= 0:
            return {k: 0.0 for k in values}
        return {k: (math.log1p(v) / max_log) for k, v in values.items()}

    fan_in_norm = norm_log_map({k: float(v) for k, v in fan_in_files.items()})
    fan_out_norm = norm_log_map({k: float(v) for k, v in fan_out.items()})
    loc_norm = norm_log_map({k: float(v) for k, v in loc_by_type.items()})
    cx_norm = norm_log_map({k: float(v) for k, v in cx_by_type.items()})
    impl_norm = norm_log_map({k: float(v) for k, v in implementers.items()})
    pr_norm = norm_log_map({k: float(v) for k, v in pr.items()})

    scored: list[tuple[str, float]] = []
    for name, decl in decls.items():
        score = 0.27 * fan_out_norm.get(name, 0.0)
        score += 0.25 * loc_norm.get(name, 0.0)
        score += 0.25 * cx_norm.get(name, 0.0)
        score += 0.15 * pr_norm.get(name, 0.0)
        score += 0.06 * fan_in_norm.get(name, 0.0)
        score += 0.02 * impl_norm.get(name, 0.0)
        if decl.is_public:
            score += 0.05
        scored.append((name, score))

    scored.sort(
        key=lambda x: (
            x[1],
            fan_out.get(x[0], 0),
            loc_by_type.get(x[0], 0),
            cx_by_type.get(x[0], 0),
            fan_in_files.get(x[0], 0),
        ),
        reverse=True,
    )
    picked: list[tuple[str, float]] = []
    for name, score in scored:
        kind = decls[name].kind
        if kind in {"enum", "struct"}:
            continue
        picked.append((name, score))
        if len(picked) >= args.top:
            break

    def to_rel(p: Path) -> str:
        return str(p.relative_to(repo)) if p.is_relative_to(repo) else str(p)

    print("| Type | Kind | Score | LOC | CX | Fan-out(types) | Fan-in(files) | PR | Notes |")
    print("|------|------|-------|-----|----|---------------|--------------|----|-------|")
    if not picked:
        print("| _none_ | - | - | - | - | - | - | - | filtered out enum/struct |")
    for name, score in picked:
        decl = decls[name]
        notes: list[str] = []
        if decl.is_public:
            notes.append("public")
        impl = implementers.get(name, 0)
        if impl > 0 and decl.kind in {"protocol", "objc_protocol", "interface"}:
            notes.append(f"implemented:{impl}")
        notes_s = ", ".join(notes) if notes else ""
        print(
            f"| `{name}` | {decl.kind} | {score:.3f} | {loc_by_type.get(name, 0)} | {cx_by_type.get(name, 0)} | {fan_out.get(name, 0)} | {fan_in_files.get(name, 0)} | {pr.get(name, 0.0):.4g} | {notes_s} |"
        )

    print("")
    print("Key class candidates (one-line):")
    for name, score in picked:
        decl = decls[name]
        extras: list[str] = []
        extras.append(f"LOC {loc_by_type.get(name, 0)}")
        extras.append(f"complexity {cx_by_type.get(name, 0)}")
        extras.append(f"fan-out {fan_out.get(name, 0)} types")
        extras.append(f"fan-in {fan_in_files.get(name, 0)} files")
        if decl.kind in {"protocol", "objc_protocol", "interface"} and implementers.get(name, 0) > 0:
            extras.append(f"{implementers[name]} implementers")
        if decl.is_public:
            extras.append("public API")
        extras.append(f"score {score:.3f}")
        print(f"- `{name}` ({decl.kind}) — {', '.join(extras)}; defined at {to_rel(decl.file_path)}")

    return 0


def register(sub) -> None:
    p_key = sub.add_parser("select-key-classes")
    p_key.add_argument("path")
    p_key.add_argument("--top", type=int, default=20)
    p_key.add_argument("--damping", type=float, default=0.85)
    p_key.add_argument("--iters", type=int, default=50)
    p_key.set_defaults(func=select_key_classes)
