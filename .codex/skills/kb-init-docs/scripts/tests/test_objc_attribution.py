#!/usr/bin/env python3
"""Regression tests for ObjC type-declaration attribution in select-key-classes.

Guards two bugs found while running kb-init-docs on IESLiveMTKit/PublicScreen:
  - a `@protocol Foo;` forward declaration in a .h was treated as the definition and
    shadowed the real Swift `protocol Foo` (mis-attributing the type to the wrong file);
  - a `@interface Base (Cat)` category on an externally-defined base class (e.g. GPBMessage)
    was registered as a class of this module and surfaced as a key class.
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

from kb_common import DEFAULT_EXCLUDES  # noqa: E402


class ObjCAttributionTests(unittest.TestCase):
    def _collect(self, files: dict[str, str]) -> dict[str, tuple[str, str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, content in files.items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            decls, _ = mod._collect_type_decls(root, DEFAULT_EXCLUDES)
            return {name: (d.kind, Path(d.file_path).name) for name, d in decls.items()}

    def test_forward_protocol_does_not_shadow_swift_definition(self) -> None:
        decls = self._collect(
            {
                "Umbrella.h": "@protocol WaveLike;\n@interface Umbrella : NSObject\n@end\n",
                "SubInterface/WaveLike.swift": "public protocol WaveLike: NSObjectProtocol {\n    func wave()\n}\n",
            }
        )
        self.assertIn("WaveLike", decls)
        kind, fname = decls["WaveLike"]
        self.assertEqual(kind, "protocol")
        self.assertEqual(fname, "WaveLike.swift")

    def test_category_does_not_declare_external_base_class(self) -> None:
        decls = self._collect(
            {
                "GPBMessage+Capsule.h": "@interface GPBMessage (Capsule)\n- (void)cap;\n@end\n",
                "GPBMessage+Capsule.m": "@implementation GPBMessage (Capsule)\n- (void)cap {}\n@end\n",
            }
        )
        self.assertNotIn("GPBMessage", decls)

    def test_category_does_not_shadow_real_in_module_class(self) -> None:
        decls = self._collect(
            {
                "RealClass.h": "@interface RealClass : NSObject\n@end\n",
                "RealClass+Ext.h": "@interface RealClass (Ext)\n- (void)ext;\n@end\n",
            }
        )
        self.assertIn("RealClass", decls)
        kind, fname = decls["RealClass"]
        self.assertEqual(kind, "objc_class")
        self.assertEqual(fname, "RealClass.h")

    def test_category_on_generic_class_is_not_a_declaration(self) -> None:
        # `@interface NSArray<ObjectType> (MyCat)` is a category on a lightweight-generic
        # external base class; the optional <...> clause must not let it register NSArray.
        decls = self._collect(
            {
                "NSArray+Mine.h": "@interface NSArray<ObjectType> (MyCat)\n- (void)mine;\n@end\n",
                "RealGeneric.h": "@interface RealGeneric<T> : NSObject\n@end\n",
            }
        )
        self.assertNotIn("NSArray", decls)
        # a real generic class definition is still detected
        self.assertIn("RealGeneric", decls)
        self.assertEqual(decls["RealGeneric"][0], "objc_class")


if __name__ == "__main__":
    unittest.main()
