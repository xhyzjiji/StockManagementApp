#!/usr/bin/env python3
"""Rust support in select-key-classes.

Guards the failure found on live_client/LinkMicSDK_Rust (a Rust SDK bound as a client
package): `link_mic_sdk/src/state_manager` has 7 `.rs` files and zero Swift/ObjC/Kotlin/Java,
so the scanner opened nothing, produced 0 candidates, and kb-init judged the root
not_qualified — silently, with exit 0. The extension set simply did not include `.rs`.

Covers: struct / enum / trait / type alias / union are collected; `pub` (incl. pub(crate))
marks public and bare items stay private; `impl Foo` / `impl Trait for Foo` contribute
references but never declare a new type; single-line declarations do not break block
scanning; and the existing mobile languages are untouched by the new branch.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

SCRIPT_PATH = SCRIPTS_DIR / "kb_select_key_classes.py"
SPEC = importlib.util.spec_from_file_location("kb_select_key_classes", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
sys.modules["kb_select_key_classes"] = mod
SPEC.loader.exec_module(mod)

from kb_common import DEFAULT_EXCLUDES, SOURCE_EXTS  # noqa: E402


class RustSupportTests(unittest.TestCase):
    def _collect(self, files: dict[str, str]) -> dict[str, tuple[str, bool, str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, content in files.items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            decls, _ = mod._collect_type_decls(root, DEFAULT_EXCLUDES)
            return {name: (d.kind, d.is_public, Path(d.file_path).name) for name, d in decls.items()}

    def test_rs_is_a_source_extension(self) -> None:
        self.assertIn(".rs", SOURCE_EXTS)

    def test_collects_all_rust_type_kinds(self) -> None:
        decls = self._collect(
            {
                "state.rs": (
                    "pub struct StateManager { inner: Inner }\n"
                    "pub enum UpdateSource { Local, Remote }\n"
                    "pub trait Delegate { fn on_change(&self); }\n"
                    "pub type AckCallback = Box<dyn Fn()>;\n"
                    "pub union Raw { a: u32, b: f32 }\n"
                ),
            }
        )
        self.assertEqual(decls["StateManager"][0], "rust_struct")
        self.assertEqual(decls["UpdateSource"][0], "rust_enum")
        self.assertEqual(decls["Delegate"][0], "rust_trait")
        self.assertEqual(decls["AckCallback"][0], "rust_type_alias")
        self.assertEqual(decls["Raw"][0], "rust_union")

    def test_pub_visibility_including_scoped_pub(self) -> None:
        decls = self._collect(
            {
                "vis.rs": (
                    "pub struct Open {}\n"
                    "pub(crate) struct CrateOnly {}\n"
                    "pub(super) enum SuperOnly { A }\n"
                    "struct Private {}\n"
                    "#[derive(Debug, Clone)]\npub struct Attributed {}\n"
                ),
            }
        )
        self.assertTrue(decls["Open"][1])
        self.assertTrue(decls["CrateOnly"][1])
        self.assertTrue(decls["SuperOnly"][1])
        self.assertFalse(decls["Private"][1])
        # 属性行在声明上一行，不能吞掉 pub
        self.assertTrue(decls["Attributed"][1])

    def test_impl_blocks_do_not_declare_types(self) -> None:
        decls = self._collect(
            {
                "a.rs": "pub struct Core {}\n",
                "b.rs": (
                    "impl Core { pub fn new() -> Self { Core {} } }\n"
                    "impl Delegate for Core { fn on_change(&self) {} }\n"
                    "impl<T> Wrapper<T> { }\n"
                ),
            }
        )
        # Core 只在 a.rs 声明一次；impl 不会把它归到 b.rs，也不会凭空造出 Delegate / Wrapper
        self.assertEqual(decls["Core"][2], "a.rs")
        self.assertNotIn("Delegate", decls)
        self.assertNotIn("Wrapper", decls)

    def test_mobile_languages_unaffected(self) -> None:
        decls = self._collect(
            {
                "A.swift": "public class SwiftThing {}\n",
                "B.kt": "class KotlinThing\n",
                "C.java": "public class JavaThing {}\n",
                "D.h": "@interface ObjcThing : NSObject\n@end\n",
            }
        )
        self.assertEqual(decls["SwiftThing"][0], "class")
        self.assertIn("KotlinThing", decls)
        self.assertIn("JavaThing", decls)
        self.assertIn("ObjcThing", decls)

    def test_end_to_end_rust_module_yields_candidates(self) -> None:
        # 昨晚那种形状：目录下只有 .rs，没有任何移动端语言文件。改前候选为 0 → not_qualified。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.rs").write_text("pub mod state;\npub mod model;\n", encoding="utf-8")
            (root / "state.rs").write_text(
                "use crate::model::StateModel;\n"
                "pub struct StateManager { model: StateModel }\n"
                "impl StateManager {\n"
                "    pub fn new(model: StateModel) -> Self { StateManager { model } }\n"
                "    pub fn apply(&mut self) { if self.model.dirty { self.model.flush(); } }\n"
                "}\n",
                encoding="utf-8",
            )
            (root / "model.rs").write_text(
                "pub struct StateModel { pub dirty: bool }\n"
                "impl StateModel { pub fn flush(&mut self) { self.dirty = false; } }\n",
                encoding="utf-8",
            )
            decls, _ = mod._collect_type_decls(root, DEFAULT_EXCLUDES)
            self.assertIn("StateManager", decls)
            self.assertIn("StateModel", decls)
            loc, cx = mod._collect_type_loc_complexity(root, DEFAULT_EXCLUDES, decls)
            # impl 块的行数与分支归到类型名下——不然 Rust 类型永远 LOC 1 / CX 0，排不上关键类
            self.assertGreater(loc.get("StateManager", 0), 1)
            self.assertGreaterEqual(cx.get("StateManager", 0), 1)


if __name__ == "__main__":
    unittest.main()
