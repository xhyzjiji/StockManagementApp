#!/usr/bin/env python3
"""Regression test for `kb_tool.py scan-types` ObjC declaration attribution.

Guards two bugs found running kb-init-docs/kb-update-docs on IESLiveMTKit/PublicScreen
(the same family fixed in kb-init-docs select-key-classes):
  - `@protocol Foo;` forward declarations were counted as a type and mis-attributed
    first_seen to the forward-declaring .h, shadowing the real definition;
  - `@interface Base (Cat)` categories on an externally-defined base class (e.g.
    GPBMessage) registered the base class as a module type.
Real classes, protocols, and same-module categories on real classes must be unaffected.

Self-contained synthetic fixture; no network. Run:

    python3 plugins/ttadk/mobile-core/skills/kb-update-docs/tests/test_scan_types_objc.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "scripts" / "kb_tool.py"
FAILURES: list[str] = []


def write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def scan(repo: Path, paths: list[str]) -> dict[str, dict]:
    argv = [sys.executable, str(TOOL), "scan-types", "--path", *paths, "--format", "json", "--max-items", "100"]
    r = subprocess.run(argv, cwd=str(repo), capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"scan-types failed rc={r.returncode}: {r.stderr}")
    return {item["name"]: item for item in json.loads(r.stdout.strip())}


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if (detail and not cond) else ""))
    if not cond:
        FAILURES.append(name)


def main() -> int:
    print("== ObjC scan-types attribution ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)

        # Umbrella header forward-declares WaveLike; real definition is the Swift file.
        write(repo, "mod/Umbrella.h", "\n".join([
            "@protocol WaveLike;",
            "@protocol AlsoFwd, AndThis;",
            "@interface Umbrella : NSObject",
            "@end",
        ]) + "\n")
        write(repo, "mod/SubInterface/WaveLike.swift", "public protocol WaveLike: NSObjectProtocol {\n    func wave()\n}\n")
        # Category on an externally-defined base class — base must NOT become a module type.
        write(repo, "mod/GPBMessage+Capsule.h", "@interface GPBMessage (Capsule)\n- (void)cap;\n@end\n")
        write(repo, "mod/GPBMessage+Capsule.m", "@implementation GPBMessage (Capsule)\n- (void)cap {}\n@end\n")
        # A real class with a same-module category: real class kept, attributed to its real file.
        write(repo, "mod/RealClass.h", "@interface RealClass : NSObject\n@end\n")
        write(repo, "mod/RealClass+Ext.h", "@interface RealClass (Ext)\n- (void)ext;\n@end\n")
        # A genuinely-defined protocol (has conformance / body, not a forward decl).
        write(repo, "mod/RealProto.h", "@protocol RealProto <NSObject>\n- (void)go;\n@end\n")
        # Category on a lightweight-generic external base class + a real generic class def.
        write(repo, "mod/NSArray+Mine.h", "@interface NSArray<ObjectType> (MyCat)\n- (void)mine;\n@end\n")
        write(repo, "mod/RealGeneric.h", "@interface RealGeneric<T> : NSObject\n@end\n")

        got = scan(repo, ["mod"])

        # Bug 1: forward declarations are not types
        check("forward @protocol Foo; not counted from .h", got.get("WaveLike", {}).get("kind") != "objc-protocol",
              str(got.get("WaveLike")))
        check("WaveLike attributed to the Swift definition",
              got.get("WaveLike", {}).get("first_seen", "").endswith("WaveLike.swift"), str(got.get("WaveLike")))
        check("multi-name forward decl not counted (AlsoFwd)", "AlsoFwd" not in got)

        # Bug 2: categories do not declare the (external) base class
        check("category does not declare GPBMessage", "GPBMessage" not in got, str(got.get("GPBMessage")))

        # Real declarations still detected
        check("real @interface counted", got.get("RealClass", {}).get("kind") == "objc-interface")
        check("RealClass attributed to its real header",
              got.get("RealClass", {}).get("first_seen", "").endswith("RealClass.h"), str(got.get("RealClass")))
        check("real class category does not inflate elsewhere",
              got.get("RealClass", {}).get("first_seen", "").endswith("RealClass.h"))
        check("real @protocol with body counted", got.get("RealProto", {}).get("kind") == "objc-protocol")
        check("real @interface Umbrella counted", got.get("Umbrella", {}).get("kind") == "objc-interface")

        # Generic-class category must not declare the base class; real generic class still counts.
        check("category on generic class does not declare NSArray", "NSArray" not in got, str(got.get("NSArray")))
        check("real generic class counted", got.get("RealGeneric", {}).get("kind") == "objc-interface")

    if FAILURES:
        print(f"==== {len(FAILURES)} FAILURE(S) ====")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("==== OK ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
