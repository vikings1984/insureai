#!/usr/bin/python3
"""第六阶段 P0-5/口径守卫：CI 步骤顺序 + aging/compression 分母口径。

两个真实缺陷的回归防护：

1. **CI 顺序缺陷（P0-5 根因）**：observability 曾排在 Event OS 主脊柱（S1 registry /
   S2 resolver / S4 alert / S5 funnel）**之前**，导致它读到上一轮的 canonical_events /
   decisions_pending → ce_linkage 报陈旧 CE 池（2620，实际 2622）、review 联动假性 0.98。
   本测试断言 observability 步骤必须位于 S1/S2/S4/S5 之后。

2. **分母口径缺陷**：aging 基于 review_state、compression 基于 review_queue，
   两者分母不同（实测113 vs 100，差 13 条陈旧state 项）却都叫pending，易被混用相加。
   本测试断言两者必须各自显式声明 basis 与对方分母（stale_state_entries）。
"""
from __future__ import annotations

import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "daily-collect.yml")


def _step_positions():
    """返回 {步骤名: 出现行号}（按首次出现）。"""
    pos = {}
    with open(WORKFLOW, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            s = line.strip()
            if s.startswith("- name:"):
                name = s.split("- name:", 1)[1].strip()
                pos.setdefault(name, i)
    return pos


class TestWorkflowOrdering(unittest.TestCase):
    def test_observability_runs_after_event_os_chain(self):
        pos = _step_positions()
        obs = pos.get("Build observability snapshot (P1-8, after Event OS chain)")
        self.assertIsNotNone(obs, "未找到 observability 步骤（名称可能已变）")
        for upstream in (
            "Build S1 canonical event registry",
            "Build S2 identity resolver report",
            "Build S4 semantic alerts",
            "Build S5 decision funnel",
        ):
            up = pos.get(upstream)
            self.assertIsNotNone(up, f"未找到上游步骤：{upstream}")
            self.assertGreater(obs, up,
                               f"observability(line {obs}) 必须晚于 {upstream}(line {up})，"
                               "否则会聚合到上一轮的陈旧产物")


class TestDenominatorDisclosure(unittest.TestCase):
    """口径守卫：aging 与 compression 必须各自声明 basis + 交叉分母。"""

    def _obs(self):
        path = os.path.join(ROOT, "observability.json")
        if not os.path.exists(path):
            self.skipTest("observability.json 未生成")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_aging_declares_basis_and_queue_size(self):
        rev = self._obs()["sections"]["review"]
        aging = rev["aging"]
        self.assertEqual(aging.get("basis"), "review_state")
        self.assertIsInstance(aging.get("queue_items"), int)

    def test_compression_declares_basis_and_state_tracked(self):
        rev = self._obs()["sections"]["review"]
        comp = rev["compression"]
        self.assertEqual(comp.get("basis"), "review_queue")
        self.assertIsInstance(comp.get("state_tracked"), int)
        self.assertIsInstance(comp.get("stale_state_entries"), int)

    def test_compression_total_equals_queue_items(self):
        rev = self._obs()["sections"]["review"]
        comp = rev["compression"]
        # compression 的分母必须严格等于 queue 侧item 数，不得混入 state 项
        self.assertEqual(comp["total_pending"], comp["queue_items"])


if __name__ == "__main__":
    unittest.main()