#!/usr/bin/env python3
"""Regression test for `kb_tool.py scan-types` Kotlin/Java support.

Android repos are Kotlin/Java; before this support, scan-types returned zero
types there and the SKILL's first evidence path was dead. Checks:
  - Kotlin declarations (class/data class/sealed class/enum class/object/
    fun interface/typealias, annotated and modifier-stacked) are detected
    in .kt/.kts files with bare kinds;
  - Java declarations (class/interface/enum/record) get the `java-` kind
    prefix, mirroring `objc-`;
  - comment/KDoc lines and unnamed `companion object {` do not match;
  - Swift/ObjC results in the same scan are unchanged by the dispatch
    (frozen cascade: a C++ `class` line in a .h is still caught by the
    Swift regex).

Self-contained synthetic fixture; no network. Run:

    python3 plugins/ttadk/mobile-core/skills/kb-update-docs/tests/test_scan_types_kotlin_java.py
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
    print("== Kotlin/Java scan-types ==")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / ".git").mkdir(parents=True)

        write(repo, "mod/src/A.kt", "\n".join([
            "package com.example",
            "",
            "object PayloadParser {",
            "    fun parse() {}",
            "}",
            "",
            "data class WatchNextParams(val id: String)",
            "internal sealed class RewardState",
            "enum class RewardScenario { A, B }",
            "@Keep",
            "abstract class BaseModule",
            "fun interface RewardListener { fun onEvent() }",
            "typealias RewardMap = Map<String, String>",
            "// class CommentedOut should not match",
            " * class KdocLine should not match",
            "companion object {",  # unnamed: must not match
        ]) + "\n")
        write(repo, "mod/src/B.java", "\n".join([
            "package com.example;",
            "",
            "public final class JavaService {}",
            "interface JavaCallback {}",
            "public enum JavaKind { X }",
            "record JavaPoint(int x, int y) {}",
        ]) + "\n")
        write(repo, "mod/src/C.swift", "\n".join([
            "import Foundation",
            "final class SwiftThing {}",
            "struct SwiftValue {}",
        ]) + "\n")
        write(repo, "mod/src/D.h", "\n".join([
            "@interface ObjcThing : NSObject",
            "@end",
            "class CppHeaderThing {};",  # frozen cascade: Swift regex catches it
        ]) + "\n")
        write(repo, "mod/src/E.kts", "object ScriptObject {}\n")

        got = scan(repo, ["mod"])

        # Kotlin
        check("kt object", got.get("PayloadParser", {}).get("kind") == "object")
        check("kt data class", got.get("WatchNextParams", {}).get("kind") == "class")
        check("kt sealed class", got.get("RewardState", {}).get("kind") == "class")
        check("kt enum class", got.get("RewardScenario", {}).get("kind") == "class")
        check("kt annotated abstract class", got.get("BaseModule", {}).get("kind") == "class")
        check("kt fun interface", got.get("RewardListener", {}).get("kind") == "interface")
        check("kt typealias", got.get("RewardMap", {}).get("kind") == "typealias")
        check("kts object", got.get("ScriptObject", {}).get("kind") == "object")
        check("kt comment not matched", "CommentedOut" not in got)
        check("kt kdoc not matched", "KdocLine" not in got)

        # Java (java- kind prefix, mirroring objc-)
        check("java class", got.get("JavaService", {}).get("kind") == "java-class")
        check("java interface", got.get("JavaCallback", {}).get("kind") == "java-interface")
        check("java enum", got.get("JavaKind", {}).get("kind") == "java-enum")
        check("java record", got.get("JavaPoint", {}).get("kind") == "java-record")

        # Swift/ObjC untouched by the suffix dispatch
        check("swift class", got.get("SwiftThing", {}).get("kind") == "class")
        check("swift struct", got.get("SwiftValue", {}).get("kind") == "struct")
        check("objc interface", got.get("ObjcThing", {}).get("kind") == "objc-interface")
        check("frozen .h cascade (C++ class via Swift regex)", got.get("CppHeaderThing", {}).get("kind") == "class")

        # first_seen points into the fixture
        check("first_seen path", got.get("PayloadParser", {}).get("first_seen", "").endswith("mod/src/A.kt"))

        # repo boundary: walking subcommands refuse paths that resolve outside
        # the repo (Aime P1 — was a silent filesystem-wide walk before).
        outside = Path(td) / "outside"
        outside.mkdir()
        for sub in ("scan-types", "list-doc-roots", "list-doc-targets", "list-doc-ancestors"):
            r = subprocess.run(
                [sys.executable, str(TOOL), sub, "--path", str(outside), "--format", "json"],
                cwd=str(repo), capture_output=True, text=True,
            )
            check(f"{sub} refuses outside-repo path",
                  r.returncode != 0 and "refusing to scan outside the repo" in (r.stderr + r.stdout))
        r = subprocess.run(
            [sys.executable, str(TOOL), "plan-doc-update", "--path", str(outside)],
            cwd=str(repo), capture_output=True, text=True,
        )
        plan_ok = r.returncode == 0 and str(outside) in json.loads(r.stdout.strip()).get("uncovered", [])
        check("plan-doc-update still reports outside path as uncovered", plan_ok)

    if FAILURES:
        print(f"==== {len(FAILURES)} FAILURE(S) ====")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("==== OK ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
