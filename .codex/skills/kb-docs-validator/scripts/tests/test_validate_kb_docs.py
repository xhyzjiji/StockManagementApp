#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "validate_kb_docs.py"
SPEC = importlib.util.spec_from_file_location("validate_kb_docs", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules["validate_kb_docs"] = validator
SPEC.loader.exec_module(validator)


class RuleDocQualityTests(unittest.TestCase):
    def test_medium_rule_doc_over_500_lines_is_hard_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Module\n", encoding="utf-8")
            (root / "Interface").mkdir()
            docs = root / "docs"
            docs.mkdir()
            rule = docs / "rule.md"
            rule.write_text(
                "# Rules\n"
                + "\n".join(f"line {idx}" for idx in range(501)),
                encoding="utf-8",
            )

            issues = validator._check_rule_doc_quality(rule, "docs/rule.md", root)

            titles = [issue.title for issue in issues]
            self.assertIn("docs/rule.md exceeds hard length limit", titles)
            self.assertTrue(any("scope=medium" in issue.details for issue in issues))

    def test_table_pseudo_rules_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Module\n", encoding="utf-8")
            docs = root / "docs"
            docs.mkdir()
            rule = docs / "rule.md"
            rule.write_text(
                "\n".join(
                    [
                        "# Rules",
                        "| Rule | Rationale |",
                        "|------|-----------|",
                        "| Show success feedback | User knows it worked |",
                    ]
                ),
                encoding="utf-8",
            )

            issues = validator._check_rule_doc_quality(rule, "docs/rule.md", root)

            titles = [issue.title for issue in issues]
            self.assertIn("docs/rule.md contains table-based pseudo rules", titles)
            self.assertIn("docs/rule.md has no scenario trigger", titles)

    def test_compact_local_rule_with_code_example_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Module\n", encoding="utf-8")
            (root / "GuideCamera.m").write_text(
                "[registry addFragment:GBLGuideCameraFragment.class];\n",
                encoding="utf-8",
            )
            docs = root / "docs"
            docs.mkdir()
            rule = docs / "rule.md"
            rule.write_text(
                "\n".join(
                    [
                        "# Rules",
                        "## Register Fragment",
                        "WHEN adding a camera guide fragment:",
                        "- MUST register it through `GuideCamera.plist`.",
                        "- MUST NOT instantiate the fragment from another component.",
                        "Example from GuideCamera.m:",
                        "```objc",
                        "[registry addFragment:GBLGuideCameraFragment.class];",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )

            issues = validator._check_rule_doc_quality(rule, "docs/rule.md", root)

            titles = [issue.title for issue in issues]
            self.assertNotIn("docs/rule.md contains many code examples", titles)
            self.assertNotIn("docs/rule.md has code examples without source paths", titles)
            self.assertNotIn("docs/rule.md has code examples with missing source paths", titles)
            self.assertNotIn("docs/rule.md has no scenario trigger", titles)
            self.assertNotIn("docs/rule.md has no MUST/MUST NOT actions", titles)

    def test_code_example_without_source_path_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Module\n", encoding="utf-8")
            docs = root / "docs"
            docs.mkdir()
            rule = docs / "rule.md"
            rule.write_text(
                "\n".join(
                    [
                        "# Rules",
                        "## Register Fragment",
                        "WHEN adding a camera guide fragment:",
                        "- MUST register it through `GuideCamera.plist`.",
                        "- MUST NOT instantiate the fragment from another component.",
                        "Example:",
                        "```objc",
                        "[registry addFragment:GBLGuideCameraFragment.class];",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )

            issues = validator._check_rule_doc_quality(rule, "docs/rule.md", root)

            titles = [issue.title for issue in issues]
            self.assertIn("docs/rule.md has code examples without source paths", titles)

    def test_generic_performance_stability_terms_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Module\n", encoding="utf-8")
            docs = root / "docs"
            docs.mkdir()
            rule = docs / "rule.md"
            rule.write_text(
                "\n".join(
                    [
                        "# Rules",
                        "## Reliability",
                        "WHEN changing loader behavior:",
                        "- MUST improve performance and reliability.",
                        "- MUST NOT reduce stability.",
                    ]
                ),
                encoding="utf-8",
            )

            issues = validator._check_rule_doc_quality(rule, "docs/rule.md", root)

            titles = [issue.title for issue in issues]
            self.assertIn("docs/rule.md contains generic rule text", titles)

    def test_duplicate_parent_rule_scenarios_are_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "Parent"
            child = parent / "Child"
            (parent / "docs").mkdir(parents=True)
            (child / "docs").mkdir(parents=True)
            (child / "CLAUDE.md").write_text("# Child\n", encoding="utf-8")

            (parent / "docs" / "rule.md").write_text(
                "\n".join(
                    [
                        "# Rules",
                        "## Register Fragment",
                        "WHEN adding a camera guide fragment:",
                        "- MUST register it through the owning plist.",
                    ]
                ),
                encoding="utf-8",
            )
            rule = child / "docs" / "rule.md"
            rule.write_text(
                "\n".join(
                    [
                        "# Rules",
                        "## Register Fragment",
                        "WHEN adding a camera guide fragment:",
                        "- MUST register it through `GuideCamera.plist`.",
                        "- MUST NOT bypass parent registration rules.",
                    ]
                ),
                encoding="utf-8",
            )

            issues = validator._check_rule_doc_quality(rule, "docs/rule.md", child)

            titles = [issue.title for issue in issues]
            self.assertIn("docs/rule.md duplicates ancestor rule scenarios", titles)

    def test_kotlin_source_files_promote_scope_to_medium(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# Module\n", encoding="utf-8")
            for idx in range(100):
                (root / f"Feature{idx}.kt").write_text(
                    f"class Feature{idx}\n",
                    encoding="utf-8",
                )

            scope = validator._detect_rule_scope(root)

            self.assertEqual(scope.name, "medium")
            self.assertEqual(scope.code_files, 100)


class MigrationDetectorTests(unittest.TestCase):
    """Old-template signals consumed by kb-update-docs Value-Aware Migration."""

    def test_claude_three_section_flags_extra_sections_only(self) -> None:
        clean = "## Module Overview\nx\n## Key Classes\n| `A` | y |\n## References\n- z\n"
        self.assertEqual(validator._check_claude_three_section(clean), [])
        old = clean + "## Architecture\nlayers\n## Directory Structure\n- d\n"
        titles = [i.title for i in validator._check_claude_three_section(old)]
        self.assertIn("CLAUDE.md is not the canonical 3-section format", titles)

    def test_domain_architecture_mixing_precision(self) -> None:
        # Real architecture sections -> flagged.
        for h in (
            "## 架构约束\nx\n", "## Dependencies\nx\n", "## Data Flow\nx\n", "## Layered Structure\nx\n",
            "## Technical Architecture\nx\n", "## Module Architecture\nx\n", "## System Architecture\nx\n",
        ):
            self.assertTrue(validator._check_domain_architecture_mixing(h, "docs/domain.md"), h)
        # Architecture word only inside a product name / parenthetical, or business headings -> NOT flagged.
        for h in (
            "### Repost Panel (Dual Panel Architecture)\nx\n",
            "## 双面板架构\nx\n",
            "## 业务概念\na\n## 埋点事件\nb\n## AB 实验\nc\n",
        ):
            self.assertEqual(validator._check_domain_architecture_mixing(h, "docs/domain.md"), [], h)

    def test_fullwidth_colon_when_is_recognized(self) -> None:
        # A zh rule doc using the full-width colon after WHEN must NOT be flagged "no scenario trigger".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# m\n", encoding="utf-8")
            (root / "docs").mkdir()
            rule = root / "docs" / "rule.md"
            rule.write_text("# 规则\n## 注册\nWHEN 新增服务：\n- MUST 用 `@ServiceImpl` 注册。\n", encoding="utf-8")
            titles = [i.title for i in validator._check_rule_doc_quality(rule, "docs/rule.md", root)]
            self.assertNotIn("docs/rule.md has no scenario trigger", titles)
            self.assertNotIn("docs/rule.md has no MUST/MUST NOT actions", titles)

    def test_template_meta_headings_excluded_from_ancestor_dup(self) -> None:
        sig = validator._extract_rule_signatures(
            "## Inherited Rules\nx\n## Context\ny\n## Register Fragment\nWHEN z:\n- MUST w\n"
        )
        self.assertNotIn("inherited rules", sig["headings"])
        self.assertNotIn("context", sig["headings"])
        self.assertIn("register fragment", sig["headings"])


    def test_interface_missing_sot_section_flagged(self) -> None:
        old_style = "# M Interfaces\n## Services & Protocols\n| P | m | d |\n"
        issues = validator._check_interface_sot_section(old_style, "docs/interface.md")
        self.assertEqual(len(issues), 1)
        self.assertIn("Source of Truth", issues[0].title)

    def test_interface_with_sot_heading_passes(self) -> None:
        mode_a = "# M Interfaces\n## Source of Truth（接口权威声明，REQUIRED）\n| f | d |\n## Services & Protocols\n"
        self.assertEqual(validator._check_interface_sot_section(mode_a, "docs/interface.md"), [])

    def test_interface_with_dispersed_token_passes(self) -> None:
        mode_b = "# M Interfaces\n## 接口声明\nDispersed: no dedicated interface file; the table below IS the aggregated public surface.\n"
        self.assertEqual(validator._check_interface_sot_section(mode_b, "docs/interface.md"), [])

    def test_network_api_short_or_invented_endpoint_flagged(self) -> None:
        doc = (
            "# M Interfaces\n## Network APIs\n"
            "| Endpoint | Method | Purpose |\n|---|---|---|\n"
            "| `/tiktok/v1/aimusic/create_music_task/` | POST | submit task |\n"
            "| `get_music_task` | GET (Mota) | poll status |\n"
            "| `ai_music_trending` | GET | trending list |\n"
            "## External Dependencies\nNone\n"
        )
        issues = validator._check_interface_network_api_endpoints(doc, "docs/interface.md")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "WARN")
        self.assertIn("`get_music_task`", issues[0].details)
        self.assertIn("`ai_music_trending`", issues[0].details)
        self.assertNotIn("create_music_task", issues[0].details)

    def test_network_api_full_paths_and_none_pass(self) -> None:
        doc = (
            "# M Interfaces\n## Network APIs (REQUIRED — write \"None\" if the module makes no network calls)\n"
            "| Endpoint | Method | Purpose |\n|---|---|---|\n"
            "| `/tiktok/v1/aimusic/get_music_task/` | GET | poll status |\n"
            "| None | - | - |\n"
        )
        self.assertEqual(validator._check_interface_network_api_endpoints(doc, "docs/interface.md"), [])

    def test_network_api_rpc_name_with_pointer_is_sanctioned(self) -> None:
        doc = (
            "# M Interfaces\n## Network APIs\n"
            "| Endpoint | Method | Purpose |\n|---|---|---|\n"
            "| `get_music_task` | GET | poll status; path declared in `idl/service/tiktok_aimusic_api_service.proto` |\n"
        )
        self.assertEqual(validator._check_interface_network_api_endpoints(doc, "docs/interface.md"), [])

    def test_network_api_absent_section_not_flagged(self) -> None:
        doc = "# M Interfaces\n## Services & Protocols\n| a | b |\n"
        self.assertEqual(validator._check_interface_network_api_endpoints(doc, "docs/interface.md"), [])

    def test_network_api_slash_bearing_verbatim_forms_pass(self) -> None:
        # Hugo probe 2026-07-10: verbatim forms that contain `/` but don't start with it.
        doc = (
            "# M Interfaces\n## Network APIs\n"
            "| Endpoint | Method | Purpose |\n|---|---|---|\n"
            "| `https://open.larkoffice.com/open-apis/bot/v2/hook/xxx` | POST | webhook push |\n"
            "| `wss://frontier.byted.org/ws/v2` | WS | long conn |\n"
            "| `GET /tiktok/v1/aimusic/get_music_task/` | GET | method plus path in one cell |\n"
            "| `com.ss.ugc.tiktok.service.tiktok_aimusic_api/get_music_task` | gRPC | full rpc name |\n"
        )
        self.assertEqual(validator._check_interface_network_api_endpoints(doc, "docs/interface.md"), [])


class WorkflowArchitectureDupTests(unittest.TestCase):
    WORKFLOW = (
        "# M Workflows\n"
        "## L2 · Core Flow Details\n"
        "### 2.1 Room Message Fan-Out\n"
        "1. **Receive** - `GBLMessageReceiver` hands payloads to `GBLMessageFactory`.\n"
        "2. **Fan out** - `GBLMessageFactory` iterates registered pipelines.\n"
        "3. **Filter** - `GBLMessageListPipeline` and `GBLMessageCenterPipeline` handle the scene.\n"
        "4. **Build** - `MessageNodeFactoryImpl` builds nodes.\n"
        "5. **Render** - `GBLMessageListViewController` updates the list.\n"
    )

    def test_architecture_restating_workflow_sequence_is_flagged(self) -> None:
        architecture = (
            "# M Architecture\n"
            "## Key Data Flow\n"
            "### Inbound Message Rendering\n"
            "1. `GBLMessageReceiver` receives messages.\n"
            "2. `GBLMessageFactory` forwards to every registered scene pipeline.\n"
            "3. `GBLMessageListPipeline` or `GBLMessageCenterPipeline` filters.\n"
            "4. `MessageNodeFactoryImpl` builds renderable node data.\n"
            "5. `GBLMessageListViewController` displays the result.\n"
        )
        issues = validator._check_workflow_architecture_dup(self.WORKFLOW, architecture)
        titles = [i.title for i in issues]
        self.assertIn("docs/architecture.md restates docs/workflow.md's runtime step sequences", titles)
        self.assertTrue(any("Inbound Message Rendering" in i.details for i in issues))

    def test_static_architecture_naming_same_classes_is_not_flagged(self) -> None:
        # Same class names, but in Layered-Structure bullets (no numbered step sequence) → legit static view.
        architecture = (
            "# M Architecture\n"
            "## Layered Structure\n"
            "- **Factory hub**: `GBLMessageFactory`, `GBLMessageReceiver` centralize delivery.\n"
            "- **Scene pipelines**: `GBLMessageListPipeline`, `GBLMessageCenterPipeline`.\n"
            "- **Node/render**: `MessageNodeFactoryImpl`, `GBLMessageListViewController`.\n"
            "## Key Data Flow\n"
            "Messages are owned by the factory hub and flow to the scene pipelines. "
            "运行时逐步时序见 `workflow.md`.\n"
        )
        self.assertEqual(validator._check_workflow_architecture_dup(self.WORKFLOW, architecture), [])

    def test_architecture_with_unrelated_numbered_steps_is_not_flagged(self) -> None:
        architecture = (
            "# M Architecture\n"
            "## Key Sequences\n"
            "1. `SomeUnrelatedThing` does A.\n"
            "2. `AnotherThing` does B.\n"
            "3. `ThirdThing` does C.\n"
        )
        self.assertEqual(validator._check_workflow_architecture_dup(self.WORKFLOW, architecture), [])

    def test_missing_architecture_is_not_flagged(self) -> None:
        self.assertEqual(validator._check_workflow_architecture_dup(self.WORKFLOW, ""), [])

    def test_dup_detected_across_blank_lines_and_subbullets(self) -> None:
        # nit① (Hugo re !1506): 真实 workflow L2 步骤间常带【空行 / 子 bullet】。分块器必须续块，
        # 否则一个序列被拆成 <3 符号的小块、达不到重叠阈值 → 漏判。这里步骤间夹空行+子 bullet，
        # architecture 复述同一序列，dup 仍须被抓（修前因拆块漏判、修后为一块抓到）。
        workflow = (
            "# M Workflows\n"
            "## L2 · Core Flow Details\n"
            "### 2.1 Fan-Out\n"
            "1. **Receive** - `GBLMessageReceiver` hands to `GBLMessageFactory`.\n"
            "   - detail: validates payload first\n"
            "\n"
            "2. **Fan out** - `GBLMessageFactory` iterates registered pipelines.\n"
            "\n"
            "3. **Filter** - `GBLMessageListPipeline` handles the scene.\n"
            "   - edge: `GBLMessageCenterPipeline` for the center scene\n"
            "4. **Build** - `MessageNodeFactoryImpl` builds nodes.\n"
        )
        architecture = (
            "# M Architecture\n"
            "## Key Data Flow\n"
            "### Inbound Rendering\n"
            "1. `GBLMessageReceiver` receives.\n"
            "\n"
            "2. `GBLMessageFactory` forwards to pipelines.\n"
            "   - note: iterates registered scene pipelines\n"
            "3. `GBLMessageListPipeline` filters.\n"
            "4. `MessageNodeFactoryImpl` builds renderable node data.\n"
        )
        issues = validator._check_workflow_architecture_dup(workflow, architecture)
        titles = [i.title for i in issues]
        self.assertIn(
            "docs/architecture.md restates docs/workflow.md's runtime step sequences", titles
        )

    def test_two_sequences_under_different_headings_stay_separate(self) -> None:
        # nit① 护栏（Hugo）：续块只跨空行/子 bullet，遇【标题】仍断——两个不同标题下的独立编号
        # 序列不该并成一块（否则符号集虚高）。这里 architecture 的两小段各自 <3 步、且分属不同标题，
        # 不构成对 workflow 单一序列的复述 → 不 flag。
        architecture = (
            "# M Architecture\n"
            "## Seq A\n"
            "1. `GBLMessageReceiver` does A.\n"
            "2. `GBLMessageFactory` does B.\n"
            "## Seq B\n"
            "1. `GBLMessageListPipeline` does C.\n"
            "2. `MessageNodeFactoryImpl` does D.\n"
        )
        self.assertEqual(validator._check_workflow_architecture_dup(self.WORKFLOW, architecture), [])


if __name__ == "__main__":
    unittest.main()
