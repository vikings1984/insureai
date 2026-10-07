#!/usr/bin/python3
"""P2 Source Health 人工确认台账单元测试（只记录，不执行）。

验证：
- section_source_degrade 从 source_degrade_ledger.json 读取最新人工动作，标注每条建议 status；
- 无台账时默认 status="suggested"；
- confirm 脚本把动作追加到台账（不触碰 data.json）。
全部用临时目录，不污染生产台账。
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest

import observability

# 加载 confirm 脚本模块
_spec = importlib.util.spec_from_file_location(
    "source_degrade_confirm",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts",
                 "source_degrade_confirm.py"),
)
_confirm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_confirm)


def _write(d, name, obj):
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


class TestSourceDegradeConfirm(unittest.TestCase):
    def _setup(self, ledger=None):
        d = tempfile.mkdtemp()
        _write(d, "data.json", {"source_health": {
            "低值源": {"availability": 0.0, "freshness": 0.0, "insurance_relevance": 0.0},
        }})
        if ledger is not None:
            _write(d, "source_degrade_ledger.json", ledger)
        self._orig = observability.HERE
        observability.HERE = d
        return d

    def tearDown(self):
        if hasattr(self, "_orig"):
            observability.HERE = self._orig

    def test_default_status_suggested(self):
        self._setup()
        sec = observability.section_source_degrade([])
        self.assertEqual(sec["suggestions"][0]["status"], "suggested")
        self.assertEqual(sec["confirmed_count"], 0)

    def test_status_from_ledger(self):
        self._setup(ledger={"actions": [
            {"source": "低值源", "action": "confirm", "at": "2026-10-07T00:00:00+00:00"},
        ]})
        sec = observability.section_source_degrade([])
        self.assertEqual(sec["suggestions"][0]["status"], "confirm")
        self.assertEqual(sec["confirmed_count"], 1)

    def test_latest_action_wins(self):
        self._setup(ledger={"actions": [
            {"source": "低值源", "action": "confirm", "at": "t1"},
            {"source": "低值源", "action": "recover", "at": "t2"},
        ]})
        sec = observability.section_source_degrade([])
        self.assertEqual(sec["suggestions"][0]["status"], "recover")

    def test_confirm_script_appends_only(self):
        d = tempfile.mkdtemp()
        lp = os.path.join(d, "ledger.json")
        orig = _confirm.LEDGER_PATH
        _confirm.LEDGER_PATH = lp
        try:
            self.assertEqual(_confirm.main(["confirm", "某源", "--note", "人工确认"]), 0)
            self.assertEqual(_confirm.main(["suspend", "某源"]), 0)
            with open(lp, encoding="utf-8") as f:
                doc = json.load(f)
            self.assertEqual([a["action"] for a in doc["actions"]], ["confirm", "suspend"])
            self.assertEqual(doc["actions"][0]["note"], "人工确认")
            # 台账文件存在，但同目录不应出现 data.json（脚本不改数据）
            self.assertFalse(os.path.exists(os.path.join(d, "data.json")))
        finally:
            _confirm.LEDGER_PATH = orig

    def test_confirm_script_rejects_bad_action(self):
        d = tempfile.mkdtemp()
        orig = _confirm.LEDGER_PATH
        _confirm.LEDGER_PATH = os.path.join(d, "ledger.json")
        try:
            self.assertEqual(_confirm.main(["bogus_action", "某源"]), 2)
        finally:
            _confirm.LEDGER_PATH = orig


if __name__ == "__main__":
    unittest.main()
