#!/usr/bin/env python3
"""方法签名正则灾难回溯回归测试（2026-07-23 MediaBox ademo_live 实锤）。

_strip_comments_and_strings 用等长空格顶替字符串/注释（保列号），长字符串字面量会产出
上千连续空格的剥离残迹行；JAVA_METHOD_SIG_RE 的可选前缀组与含空格字符类在这类行上指数
回溯——单行 re.match 数秒到挂死（select-key-classes 超时→validator --strict 连带失败，
自愈 agent 门禁全挂）。修复 = 签名匹配走 _sig_line()（≥8 连续空白压单空格的临时副本）。

本测试锁两点：① _sig_line 压缩语义（真签名照常命中、残迹行免疫）；② 病态输入在时限内
返回（回归即超时报错，不是静默变慢）。
"""
import signal
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kb_select_key_classes as k  # noqa: E402


class SigBacktrackTest(unittest.TestCase):
    def _match_with_deadline(self, line, seconds=3):
        def _alarm(signum, frame):
            raise TimeoutError(f'regex exceeded {seconds}s — catastrophic backtracking is back')
        old = signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(seconds)
        try:
            return k.JAVA_METHOD_SIG_RE.match(k._sig_line(line))
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    def test_real_signature_still_matches(self):
        line = '    public static synchronized Map<String, List<int[]>> buildIndex(String key, int n) throws IOException {'
        self.assertIsNotNone(self._match_with_deadline(line))

    def test_signature_with_squeezed_run_still_matches(self):
        # 签名中间夹长空白 run（剥离残迹叠加真实签名）——压缩后仍应命中
        line = '    public void doWork(' + ' ' * 900 + 'String a) {'
        self.assertIsNotNone(self._match_with_deadline(line))

    def test_stripped_residue_line_returns_fast(self):
        # 1600+ 空格 + 词尾残迹：修复前该行单次 match 数秒~挂死
        line = ' ' * 1605 + 'trailingIdentifier'
        self._match_with_deadline(line)   # 不关心命中与否，只要按时返回

    def test_residue_with_scattered_tokens_returns_fast(self):
        line = ('  word ' * 60) + (' ' * 1200) + ' another , tokens < > [ ] end'
        self._match_with_deadline(line)


if __name__ == '__main__':
    unittest.main()
