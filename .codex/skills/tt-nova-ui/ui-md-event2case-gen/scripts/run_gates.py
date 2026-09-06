#!/usr/bin/env python3
"""交付门禁总入口：一条命令跑完全部检查，失败时直接给「下一步做什么」。

存在的理由：门禁脚本本身早就有了，但要求 agent 自己记住跑哪几个、自己拼对
`{vc}/{module}/{ui_path}` 四套路径、跑挂了自己修 —— 指令遵循弱的模型会漏跑、
路径拼错后当成「文件不存在，跳过」，于是门禁形同虚设。本脚本把这些从模型脑子
里搬进代码：路径自动发现，检查顺序固定，输出直接说下一步动作。

用法：
  python run_gates.py                      # 自动找最近的工作目录
  python run_gates.py --workdir tt-nova/ui/tmp/live/anchor-cues/ui-md-event2case-gen
  python run_gates.py --self-check

退出码：0 = 全过可交付；1 = 有未通过项，禁止交付；2 = 运行错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKDIR_GLOBS = (
    "tt-nova/ui/tmp/*/*/ui-md-event2case-gen",
    "tt-nova/ui/tmp/*/*/ui-md-newcase-gen",  # legacy
)
# KB clone 的候选位置，找不到就跳过红线门禁并明确说明（不静默当通过）
KB_CANDIDATES = ("tt-nova/ui/tmp/_kb_live_tracking", "/tmp/live_tracking_knowledge_base")


class Result:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = True
        self.skipped = False
        self.details: list[str] = []
        self.next_action = ""

    def fail(self, detail: str, next_action: str) -> Result:
        self.ok = False
        self.details.append(detail)
        self.next_action = next_action
        return self

    def skip(self, detail: str, next_action: str) -> Result:
        self.skipped = True
        self.details.append(detail)
        self.next_action = next_action
        return self


def find_workdir(explicit: str | None, root: Path) -> Path:
    if explicit:
        p = Path(explicit)
        return p if p.is_absolute() else root / p
    candidates = [
        d for pattern in WORKDIR_GLOBS for d in root.glob(pattern) if d.is_dir()
    ]
    if not candidates:
        raise SystemExit(
            f"[run_gates] 没找到工作目录（{list(WORKDIR_GLOBS)}）。"
            "先按 SKILL.md Step 1.55 落盘 etd_scope.json，或用 --workdir 指定。"
        )
    return max(candidates, key=lambda d: d.stat().st_mtime)


def discover(workdir: Path) -> dict[str, Path | None]:
    cases = sorted(workdir.glob("*_source_cases.md"))
    # G8: etd_sheet_load.py --emit-scope-draft 产出的草稿
    draft = _existing(workdir / "etd_scope.draft.json")
    if draft is None:
        # 兼容历史命名
        draft = _existing(workdir / "etd_scope_draft.json")
    # G2: 找转换后 xmind richtext（可能在业务 xmind 目录或 workdir）
    richtext = _existing(workdir / "cases_richtext.md")
    if richtext is None:
        candidates = sorted(workdir.glob("*_richtext.md"))
        richtext = candidates[0] if candidates else None
    if richtext is None:
        # 在 kb 上传目录里找同名
        for p in workdir.parent.rglob("*_richtext.md"):
            richtext = p
            break
    return {
        "scope": _existing(workdir / "etd_scope.json"),
        "etd_raw": _existing(workdir / "etd_raw.json"),
        "etd_draft": draft,
        "cases": cases[0] if cases else None,
        "richtext": richtext,
        "kb_gaps": _existing(workdir / "kb_gaps.json"),
    }


def _existing(p: Path) -> Path | None:
    return p if p.is_file() else None


def gate_artifacts(files: dict[str, Path | None], workdir: Path) -> Result:
    r = Result("产物齐全")
    wanted = {
        "scope": ("etd_scope.json", "回 SKILL.md Step 1.55 落盘范围文件"),
        "etd_raw": ("etd_raw.json", "回 Step 1.55 第 8 条把 ETD 机读正文留档"),
        "cases": ("*_source_cases.md", "回 Step 4 生成自动化 md 用例"),
    }
    for key, (label, action) in wanted.items():
        if files[key] is None:
            r.fail(f"缺 {label}", f"{action}（目录：{workdir}）")
    return r


def gate_scope(files: dict[str, Path | None]) -> Result:
    r = Result("scope + 用例覆盖 + ETD 反查 + 草稿删减校验")
    if files["scope"] is None:
        return r.skip("没有 etd_scope.json，跳过", "先补 etd_scope.json 再跑本命令")
    cmd = [sys.executable, str(HERE / "check_etd_scope.py"), "--scope", str(files["scope"])]
    if files["cases"]:
        cmd += ["--cases", str(files["cases"])]
    if files["etd_raw"]:
        cmd += ["--etd-text", str(files["etd_raw"])]
    if files["etd_draft"]:
        cmd += ["--etd-draft", str(files["etd_draft"])]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stderr or "") + (proc.stdout or "")
    if "NOTE: ETD 结构化列头未识别" in out:
        r.details.append("⚠ ETD 是 Docx/非标准表格，已执行 Docx 弱反查（启发式），仍需人工核对 scope 枚举/上报端完整性")
    elif "WARN: ETD 表头未识别" in out:
        r.details.append("⚠ ETD 表头未识别且无法弱反查，枚举/上报端反查已跳过 —— 需人工逐列核对，WARN 不等于通过")
    if proc.returncode != 0:
        for line in out.splitlines():
            if line.strip().startswith("- "):
                r.details.append(line.strip()[2:])
        if not r.details:
            r.details.append(out.strip()[:400])
        r.ok = False
        r.next_action = (
            "逐条按报错修：缺事件/枚举 → 补进 etd_scope.json 或写 out_of_scope；"
            "缺用例/角色错误 → 回 Step 3 补用例+设备前缀；"
            "多操作合并(G11) → 按操作拆条，前置步骤去掉埋点断言；"
            "test_kit/Precondition 格式问题 → 回 Step 1.55/Step 4 从提测文档抽"
        )
    return r


def gate_xmind_precondition(files: dict[str, Path | None]) -> Result:
    r = Result("BITS xmind 前置条件工具节点（G2）")
    if files["richtext"] is None:
        return r.skip(
            "没找到 *_richtext.md（尚未做 xmind 转换），跳过",
            "跑完 md→xmind 转换（md_case_skill_upload.py / build_mapping.py）后重跑本命令；"
            "如果只做 md 交付可忽略本项，但上传 BITS 前必须通过",
        )
    # 从 scope 里读期望 env/flights
    expect_env: str | None = None
    expect_flights: list[str] = []
    if files["scope"] is not None:
        try:
            scope = json.loads(files["scope"].read_text(encoding="utf-8"))
            kit = scope.get("test_kit") if isinstance(scope, dict) else None
            if isinstance(kit, dict):
                expect_env = str(kit.get("env") or "").strip() or None
                expect_flights = [str(f) for f in kit.get("libra_flights") or [] if str(f).strip()]
        except (json.JSONDecodeError, OSError):
            pass
    cmd = [sys.executable, str(HERE / "check_xmind_precondition.py"), "--richtext", str(files["richtext"])]
    if expect_env:
        cmd += ["--expect-env", expect_env]
    if expect_flights:
        cmd += ["--expect-flights", ",".join(expect_flights)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stderr or "") + (proc.stdout or "")
    if proc.returncode != 0:
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("FAIL:"):
                r.details.append(s[5:].strip())
            elif s.startswith("- "):
                r.details.append(s[2:])
        if not r.details:
            r.details.append(out.strip()[:400])
        r.ok = False
        r.next_action = (
            "前置工具未正确落地：检查 md→xmind 是否按选型传了 "
            "--precondition-tools-json（env→环境名称，flight→libra实验 region+libra_id+group_id，"
            "AB KV→ttmock ab_settings JSON 对象）；并确认 Precondition mock 行是 `- mock | env=xxx` 管道格式"
        )
    return r


def gate_kb_gaps(files: dict[str, Path | None]) -> Result:
    r = Result("kb_gaps 阻塞项（R9）")
    path = files["kb_gaps"]
    if path is None:
        return r  # 本轮无盲区，或已 resolve 后删除
    try:
        gaps = json.loads(path.read_text(encoding="utf-8")).get("gaps") or []
    except (json.JSONDecodeError, AttributeError) as exc:
        return r.fail(f"kb_gaps.json 读不动：{exc}", "修好 JSON 格式")
    done = {"resolved", "waived", "deferred", "noted", "out_of_scope"}
    stuck = [
        g
        for g in gaps
        if isinstance(g, dict)
        and str(g.get("severity", "")).lower() == "blocking"
        and str(g.get("status", "")).lower() not in done
    ]
    for g in stuck:
        r.fail(
            f"{g.get('id', '?')}: {str(g.get('question', ''))[:80]}",
            "停下来反问用户（R9 硬停），拿到答案写回 answer + status=resolved 后再交付",
        )
    return r


def gate_redline(files: dict[str, Path | None], root: Path) -> Result:
    r = Result("事故红线覆盖表（R7）")
    if files["cases"] is None:
        return r.skip("没有用例文件，跳过", "先生成用例")
    kb = next(
        (p for c in KB_CANDIDATES for p in [Path(c) if Path(c).is_absolute() else root / c]
         if (p / "tools/check_redline_coverage.py").is_file()),
        None,
    )
    if kb is None:
        return r.skip(
            "没找到 live_tracking_knowledge_base 本地 clone，红线门禁未执行",
            f"按 Step 1 把 KB clone 到 {KB_CANDIDATES[0]} 后重跑 —— 未执行 ≠ 通过",
        )
    proc = subprocess.run(
        [sys.executable, "tools/check_redline_coverage.py", str(files["cases"].resolve())],
        capture_output=True,
        text=True,
        cwd=kb,
    )
    if proc.returncode != 0:
        for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines():
            if line.strip() and not line.startswith("红线登记表共"):
                r.details.append(line.strip())
        r.ok = False
        r.next_action = (
            "在用例文档末尾补「命中红线覆盖表」，表头用 `| 红线ID | 覆盖情况 | 覆盖用例 / 不适用理由 |`，"
            "对每条 RL 给 ✅/⚪/❌ 且不适用必须写理由"
        )
    return r


_TODO_RE = re.compile(r"TODO-KNOWLEDGE|待补|<[^>\n]{0,40}(?:占位|填写|待定)[^>\n]{0,40}>")
_GAP_ID_RE = re.compile(r"G-[A-Z]+-\d+")


def _registered_gap_ids(path: Path | None) -> set[str]:
    """kb_gaps 里已登记（含 deferred）的 gap id —— 引用了它们的占位属于「已知会缺」。"""
    if path is None:
        return set()
    try:
        gaps = json.loads(path.read_text(encoding="utf-8")).get("gaps") or []
    except (json.JSONDecodeError, AttributeError):
        return set()
    done = {"resolved", "waived", "deferred", "noted", "out_of_scope"}
    return {
        str(g["id"])
        for g in gaps
        if isinstance(g, dict) and g.get("id") and str(g.get("status", "")).lower() in done
    }


def gate_todo(files: dict[str, Path | None]) -> Result:
    r = Result("终稿无未登记占位")
    if files["cases"] is None:
        return r.skip("没有用例文件，跳过", "先生成用例")
    known = _registered_gap_ids(files["kb_gaps"])
    naked: list[str] = []
    unverifiable: list[str] = []
    registered = 0
    for i, line in enumerate(files["cases"].read_text(encoding="utf-8").splitlines(), 1):
        if not _TODO_RE.search(line):
            continue
        # 占位本身不是错，「没登记过就默默交付」才是。引用了已登记 gap 的放行。
        cited = set(_GAP_ID_RE.findall(line))
        if known & cited:
            registered += 1
        elif cited and files["kb_gaps"] is None:
            unverifiable.append(f"第 {i} 行引用了 {sorted(cited)[0]}")
        else:
            naked.append(f"第 {i} 行: {line.strip()[:70]}")

    if registered:
        r.details.append(
            f"{registered} 处占位已在 kb_gaps 登记（放行，但交付说明里要告知用户哪些用例还不可执行）"
        )
    if unverifiable:
        r.ok = False
        r.details.extend(unverifiable[:5])
        r.next_action = (
            "占位引用了 gap id，但 kb_gaps.json 不在工作目录里，无法核验。"
            "**有 deferred 项时 kb_gaps.json 必须随终稿保留**（它是交付说明和下次重跑的依据），"
            "只有全部 gap 都 resolved 才可删除"
        )
    if naked:
        r.ok = False
        r.details.extend(naked[:5])
        if len(naked) > 5:
            r.details.append(f"…共 {len(naked)} 处未登记")
        r.next_action = (
            "这些占位没在 kb_gaps 里登记：要么反问用户补实（R9），要么登记成 "
            "deferred 并在占位处写上 gap id（如 evidence=user_supplied:G-REL-002）—— 不能默默交付"
        )
    return r


def run_all(workdir: Path, root: Path) -> tuple[list[Result], dict[str, Path | None]]:
    files = discover(workdir)
    return [
        gate_artifacts(files, workdir),
        gate_scope(files),
        gate_xmind_precondition(files),
        gate_kb_gaps(files),
        gate_redline(files, root),
        gate_todo(files),
    ], files


def report(results: list[Result], workdir: Path) -> int:
    print("=" * 60)
    print("ui-md-event2case-gen 交付门禁")
    print(f"工作目录: {workdir}")
    print("=" * 60)
    for i, r in enumerate(results, 1):
        mark = "❌ 未通过" if not r.ok else ("⚠ 未执行" if r.skipped else "✅ 通过")
        print(f"[{i}/{len(results)}] {r.name:26s} {mark}")
        for d in r.details:
            print(f"        - {d}")
        if r.next_action and (not r.ok or r.skipped):
            print(f"        → 下一步: {r.next_action}")
    print("=" * 60)
    failed = [r for r in results if not r.ok]
    skipped = [r for r in results if r.skipped and r.ok]
    if failed:
        print(f"结论: {len(failed)} 项未通过 —— 禁止交付。按上面「下一步」修完再跑一次本命令。")
        return 1
    if skipped:
        print(f"结论: 全部已执行项通过，但有 {len(skipped)} 项未执行（见上），需人工确认后才可交付。")
        return 0
    print("结论: 全部通过，可以交付。")
    return 0


def self_check() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        wd = Path(td) / "tt-nova/ui/tmp/live/demo/ui-md-event2case-gen"
        wd.mkdir(parents=True)

        # 空目录：产物门禁必须报缺三样，且不能崩
        results, _ = run_all(wd, Path(td))
        art = results[0]
        assert not art.ok and len(art.details) == 3, art.details

        # 未 resolve 的 blocking gap 必须拦住
        (wd / "kb_gaps.json").write_text(
            json.dumps(
                {"gaps": [
                    {"id": "G-1", "severity": "blocking", "status": "open", "question": "路径是啥"},
                    {"id": "G-2", "severity": "blocking", "status": "resolved"},
                    {"id": "G-3", "severity": "soft", "status": "open"},
                ]}
            ),
            encoding="utf-8",
        )
        r = gate_kb_gaps(discover(wd))
        assert not r.ok and len(r.details) == 1 and "G-1" in r.details[0], r.details

        # 未登记的裸占位必须拦住
        (wd / "demo_source_cases.md").write_text(
            "> 用例A\n**Precondition**:\n- mock | 账号 TODO-KNOWLEDGE 待补\n", encoding="utf-8"
        )
        r = gate_todo(discover(wd))
        assert not r.ok and "TODO-KNOWLEDGE" in r.details[0], r.details

        # 引用了已登记（deferred）gap 的占位放行，不误报
        (wd / "kb_gaps.json").write_text(
            json.dumps({"gaps": [{"id": "G-REL-002", "severity": "blocking", "status": "deferred"}]}),
            encoding="utf-8",
        )
        (wd / "demo_source_cases.md").write_text(
            "> 用例A\n- 账号 TODO-KNOWLEDGE（evidence=user_supplied:G-REL-002，待 RD 补）\n",
            encoding="utf-8",
        )
        r = gate_todo(discover(wd))
        assert r.ok and "已在 kb_gaps 登记" in r.details[0], r.details

        # 登记过但把台账删了 → 拦住，且提示保留 kb_gaps.json（而不是「你没登记」）
        (wd / "kb_gaps.json").unlink()
        r = gate_todo(discover(wd))
        assert not r.ok and "必须随终稿保留" in r.next_action, (r.details, r.next_action)

        # 干净用例不应误报
        (wd / "demo_source_cases.md").write_text("> 用例A\n**Steps**:\n1. 点。\n", encoding="utf-8")
        assert gate_todo(discover(wd)).ok

        # KB 不存在时必须是「未执行」而不是「通过」
        r = gate_redline(discover(wd), Path(td))
        assert r.skipped and not r.details[0].startswith("没有用例"), r.details

    print("run_gates self-check OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workdir", help="tt-nova/ui/tmp/{vc}/{module}/ui-md-event2case-gen；缺省自动找最近的")
    ap.add_argument("--repo-root", default=os.getcwd())
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    root = Path(args.repo_root).resolve()
    workdir = find_workdir(args.workdir, root)
    if not workdir.is_dir():
        print(f"[run_gates] 工作目录不存在: {workdir}", file=sys.stderr)
        return 2
    results, _ = run_all(workdir, root)
    return report(results, workdir)


if __name__ == "__main__":
    raise SystemExit(main())
