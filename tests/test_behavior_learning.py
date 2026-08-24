#!/usr/bin/env python3
import os
import unittest
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBehaviorLearningContract(unittest.TestCase):
    def test_is_local_only(self):
        path = ROOT / "behavior_learning.js"
        text = path.read_text(encoding="utf-8")
        self.assertIn("localStorage", text)
        self.assertNotIn("navigator.sendBeacon", text)
        self.assertNotIn("fetch(", text)
        self.assertIn("['view','save','dismiss']", text)

    def test_feedback_is_bounded(self):
        path = ROOT / "behavior_learning.js"
        text = path.read_text(encoding="utf-8")
        self.assertIn("Math.max(-12, Math.min(12", text)
        self.assertIn("Math.max(-20, Math.min(20", text)
        self.assertIn("slice(-MAX_EVENTS)", text)

    def test_injection_order(self):
        path = ROOT / "scripts" / "inject_ui_assets.py"
        text = path.read_text(encoding="utf-8")
        self.assertLess(text.index("behavior_learning.js"), text.index("personalization-ui.js"))


if __name__ == "__main__":
    unittest.main()
