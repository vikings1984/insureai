#!/usr/bin/python3
"""P1-A Replay 发布门判定逻辑单元测试（不跑真实重放）。

只验证 decide() 的纯判定矩阵：
- replay 执行失败 → 任何模式下都 exit 0（warn，不误杀发布）；
- 观察期内回归 → exit 0（warn-only）；
- 观察期后回归 → exit 1（fail-closed）；
- 无回归 → exit 0。
"""
from __future__ import annotations

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "..", "scripts", "replay_compare_gate.py")


def _load():
    spec = importlib.util.spec_from_file_location("replay_compare_gate", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestReplayGateDecide(unittest.TestCase):
    def setUp(self):
        self.gate = _load()

    def test_replay_failure_never_blocks(self):
        # replay 执行本身失败：trial / enforced 都应是 warn + exit 0
        self.assertEqual(self.gate.decide(trial=True, regression=False, replay_ok=False),
                         (0, "warn"))
        self.assertEqual(self.gate.decide(trial=False, regression=False, replay_ok=False),
                         (0, "warn"))

    def test_regression_in_trial_is_warn_only(self):
        # 观察期内检测到回归：warn-only，不阻断
        self.assertEqual(self.gate.decide(trial=True, regression=True, replay_ok=True),
                         (0, "warn"))

    def test_regression_after_trial_is_fail_closed(self):
        # 观察期后检测到回归：发布硬门，exit 1
        self.assertEqual(self.gate.decide(trial=False, regression=True, replay_ok=True),
                         (1, "enforce"))

    def test_no_regression_passes(self):
        self.assertEqual(self.gate.decide(trial=True, regression=False, replay_ok=True),
                         (0, "ok"))
        self.assertEqual(self.gate.decide(trial=False, regression=False, replay_ok=True),
                         (0, "ok"))


if __name__ == "__main__":
    unittest.main()
