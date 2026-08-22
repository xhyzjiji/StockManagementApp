#!/usr/bin/env python3
"""契约：用量采集不到时必须【省略字段】，不许写 0；通过率缺失必须拒发整份报告。

为什么要有这组测试：一次真实运行（2026-08-10）上报出 `totalTokens: 0` /
`totalToolCalls: 0`，使用者看到的是「这次跑没花 token」，真相是「没采集到」。
两者在看板上完全不可分辨，而 0 是这个指标的**合法取值**——所以占位值绝不能取
合法取值，只能省略。

反向用例是重点：正向用例只能证明「有数据时不出错」，而这个缺陷的全部危险在于
**没数据时也不出错**。
"""
import importlib.util
import pathlib
import sys
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location("report_telemetry", SCRIPTS / "report_telemetry.py")
rt = importlib.util.module_from_spec(_spec)
sys.modules["report_telemetry"] = rt
_spec.loader.exec_module(rt)


def bench(with_usage=True, with_pass=True):
    run = {"with_docs": {}, "without_docs": {}}
    usage = {"with_docs": {}, "without_docs": {}}
    if with_pass:
        run["with_docs"]["pass_rate"] = {"mean": 0.9063}
        run["without_docs"]["pass_rate"] = {"mean": 0.7188}
    if with_usage:
        for cfg, tok in (("with_docs", 148712), ("without_docs", 107670)):
            usage[cfg] = {
                "total_tokens": {"mean": tok},
                "normalized_total_tokens": {"mean": tok},
                "total_time_seconds": {"mean": 410.7},
                "total_tool_calls": {"mean": 49},
            }
    return {"run_summary": run, "usage_summary": usage, "metadata": {}}


class MeanKeepsMissingDistinctFromZero(unittest.TestCase):
    def test_missing_returns_none_not_zero(self):
        self.assertIsNone(rt._mean(None))
        self.assertIsNone(rt._mean({}))            # 没有 mean 键 = 没采集到
        self.assertIsNone(rt._mean("n/a"))

    def test_real_zero_is_preserved(self):
        """真的零必须原样保留——把 0 也当成缺失，会反过来抹掉真实的零消耗。"""
        self.assertEqual(rt._mean({"mean": 0}), 0.0)
        self.assertEqual(rt._mean(0), 0.0)


class UsageFieldsOmittedWhenUncollected(unittest.TestCase):
    def test_fields_present_when_collected(self):
        s = rt.config_summary(bench(with_usage=True), "with_docs")
        self.assertEqual(s["totalTokens"], 148712)
        self.assertEqual(s["totalToolCalls"], 49)
        self.assertEqual(s["totalTimeSeconds"], 410.7)

    def test_token_source_is_carried_through(self):
        """0 必须能被解释：write_timing 判定的来源要一路带到上报。"""
        b = bench(with_usage=False)
        b["usage_summary"]["with_docs"] = {"total_tokens": {"mean": 0}, "token_sources": ["missing"]}
        s = rt.config_summary(b, "with_docs")
        self.assertEqual(s["totalTokens"], 0)
        self.assertEqual(s["tokenSource"], "missing", "没有它，这个 0 又变回不可解释")

    def test_token_source_absent_when_unknown(self):
        s = rt.config_summary(bench(with_usage=True), "with_docs")
        self.assertNotIn("tokenSource", s)

    def test_fields_absent_when_not_collected(self):
        s = rt.config_summary(bench(with_usage=False), "with_docs")
        self.assertEqual(s["passRate"], 0.9063)
        for k in ("totalTokens", "normalizedTokens", "totalTimeSeconds", "totalToolCalls"):
            self.assertNotIn(k, s, f"{k} 没采集到就该整个键省略，出现即会被读成 0")

    def test_zero_usage_still_reported_as_zero(self):
        b = bench(with_usage=False)
        b["usage_summary"]["with_docs"] = {"total_tokens": {"mean": 0}}
        s = rt.config_summary(b, "with_docs")
        self.assertEqual(s["totalTokens"], 0, "真的零必须发出去，否则又反过来丢信息")


class MissingPassRateRefusesToReport(unittest.TestCase):
    def test_config_summary_returns_none(self):
        self.assertIsNone(rt.config_summary(bench(with_pass=False), "with_docs"))

    def test_build_payload_raises(self):
        class A:
            agent = "claude-code"; model = None; doc_root = "docs"; repo_root = "/tmp/x"
            platform = None; user = "tester"; department = ""
        with self.assertRaises(rt.MissingPassRate):
            rt.build_payload(A(), bench(with_pass=False))

    def test_build_payload_ok_when_pass_rates_present(self):
        class A:
            agent = "claude-code"; model = None; doc_root = "docs"; repo_root = "/tmp/x"
            platform = None; user = "tester"; department = ""
        payload = rt.build_payload(A(), bench())
        data = payload["entries"][0]["data"]
        self.assertAlmostEqual(data["deltaPassRate"], 0.1875, places=4)
        self.assertIn("totalTokens", data["withDocs"])


if __name__ == "__main__":
    unittest.main()
