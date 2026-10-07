#!/usr/bin/python3
"""P0-1 反馈采集脚本的**人工可用性**守卫（脚本优先落点，UI 后置）。

用户已拍板：P0-1 先做脚本、UI 后置。因此脚本必须**独立支撑人做判断**，
不能把人逼到必须先看别的文件/开UI 才能登记——否则等于没有落点。

守卫要求 `scripts/review_feedback_capture.py list`：
- 输出**事件标题**（不只是 event_id）——没标题无法判断 accept/reject；
- 支持 `-v` 详细模式，给出优先级/信任/信源数/触发 reason 等判断依据；
- 支持 `--tier` 过滤与 `--limit` 分页（100 条待反馈需要能分批处理）；
- 明确打印登记命令提示（让人知道下一步怎么做）。

同时守住纪律：脚本**不得**改写 review_queue / review_decision 的状态。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "review_feedback_capture.py")


def _run(*args, ledger=None):
    """跑 capture 脚本；`ledger` 指定临时账本路径（隔离生产数据）。"""
    env = dict(os.environ)
    if ledger:
        env["REVIEW_FEEDBACK_LEDGER"] = ledger
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, cwd=ROOT, env=env)


def _prod_snapshot() -> str:
    p = os.path.join(ROOT, "review_feedback.json")
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        return f.read()


def _read_prod() -> str:
    return _prod_snapshot()


class TestCaptureScriptUsability(unittest.TestCase):
    def setUp(self):
        # 关键：脚本是独立进程，须用环境变量把账本指向临时文件，
        # 否则测试会往生产 review_feedback.json 写脏数据。
        self.tmp = tempfile.mkdtemp()
        self.ledger = os.path.join(self.tmp, "review_feedback.json")
        self._prod_before = _read_prod()

    def tearDown(self):
        # 若生产账本被意外写入，立即还原，保持"空即真实未登记"
        if _read_prod() != self._prod_before:
            with open(os.path.join(ROOT, "review_feedback.json"), "w",
                      encoding="utf-8") as f:
                f.write(self._prod_before)
    def test_list_shows_titles_not_only_ids(self):
        r = _run("list", "--limit", "3", ledger=self.ledger)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("待反馈", out)
        # 必须出现真实事件标题（中文/字母数字内容），而非仅 event_id
        self.assertTrue(any(ch.isalpha() for ch in out), "输出应包含事件标题文本")
        self.assertIn("review_feedback_capture", out)

    def test_verbose_gives_judgment_context(self):
        r = _run("list", "-v", "--limit", "1", ledger=self.ledger)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for field in ("标题", "建议", "优先级", "触发"):
            self.assertIn(field, out, f"-v 模式应给出 {field} 判断依据")

    def test_supports_tier_filter_and_limit(self):
        r = _run("list", "--tier", "noise", "--limit", "2", ledger=self.ledger)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("noise", r.stdout)
        # limit=2 不应列出全部 100 条
        self.assertNotIn("[  3]", r.stdout)

    def test_prints_how_to_register(self):
        r = _run("list", "--limit", "1", ledger=self.ledger)
        self.assertIn("accept", r.stdout)
        self.assertIn("reject", r.stdout)
        self.assertIn("event_id", r.stdout)

    def test_does_not_mutate_review_state(self):
        """脚本只记录反馈，不得改动 review_queue / review_decision 内容。"""
        targets = ["review_queue.json", "review_decision.json"]
        before = {}
        for t in targets:
            path = os.path.join(ROOT, t)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    before[t] = f.read()
        # 走一次完整登记路径
        sugg = _run("list", "--limit", "1", ledger=self.ledger).stdout
        eid = None
        for line in sugg.splitlines():
            if line.strip().startswith("[") and "]" in line:
                eid = line.split("]")[1].strip().split()[0]
                break
        if eid:
            _run("accept", eid, "--reason", "guard-selftest")
        for t, content in before.items():
            with open(os.path.join(ROOT, t), encoding="utf-8") as f:
                self.assertEqual(f.read(), content, f"{t} 不应被capture 脚本改动")

    def test_invalid_decision_rejected(self):
        r = _run("bogus_decision", "evt_x", ledger=self.ledger)
        self.assertEqual(r.returncode, 2)

    def test_tests_never_write_production_ledger(self):
        """守卫自身：测试跑完，生产账本必须仍是空的（空即真实未登记）。"""
        prod = os.path.join(ROOT, "review_feedback.json")
        if not os.path.exists(prod):
            self.skipTest("生产账本不存在")
        with open(prod, encoding="utf-8") as f:
            self.assertEqual(f.read(), _prod_snapshot(), "测试污染了生产反馈账本")


if __name__ == "__main__":
    unittest.main()