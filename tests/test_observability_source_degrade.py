#!/usr/bin/python3
"""P1-C 信源降权建议清单单元测试（只读 / 不执行）。

验证 section_source_degrade 的排除逻辑：
- 不健康 且 低价值（relevance<0.8）→ 进入建议清单；
- 高价值（relevance>=0.8）→ 排除；
- 监管/官方命名（命中关键词）→ 排除；
- 健康源 → 不进入清单。
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import observability


def _write(d: str, name: str, obj) -> None:
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


class TestSourceDegrade(unittest.TestCase):
    def _setup(self, health: dict) -> str:
        d = tempfile.mkdtemp()
        _write(d, "data.json", {"source_health": health})
        self._orig = observability.HERE
        observability.HERE = d
        return d

    def tearDown(self):
        if hasattr(self, "_orig"):
            observability.HERE = self._orig

    def test_low_value_unhealthy_suggested(self):
        d = self._setup({
            "平安人寿": {"availability": 0.0, "freshness": 0.0, "insurance_relevance": 0.0},
        })
        sec = observability.section_source_degrade([])
        names = [s["source"] for s in sec["suggestions"]]
        self.assertIn("平安人寿", names)
        self.assertEqual(sec["suggestion_count"], 1)

    def test_high_value_unhealthy_excluded(self):
        d = self._setup({
            "某关键源": {"availability": 0.0, "freshness": 0.0, "insurance_relevance": 1.0},
        })
        sec = observability.section_source_degrade([])
        self.assertEqual(sec["suggestions"], [])

    def test_regulatory_named_excluded(self):
        d = self._setup({
            "地方银保监局": {"availability": 0.0, "freshness": 0.0, "insurance_relevance": 0.0},
        })
        sec = observability.section_source_degrade([])
        self.assertEqual(sec["suggestions"], [])

    def test_healthy_not_suggested(self):
        d = self._setup({
            "健康源": {"availability": 1.0, "freshness": 0.9, "insurance_relevance": 0.0},
        })
        sec = observability.section_source_degrade([])
        self.assertEqual(sec["suggestions"], [])

    def test_raises_no_alert(self):
        d = self._setup({
            "低值陈旧源": {"availability": 0.0, "freshness": 0.0, "insurance_relevance": 0.0},
        })
        alerts: list[dict] = []
        observability.section_source_degrade(alerts)
        # 建议清单是只读 advisory，不应因此产生告警
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
