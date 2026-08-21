#!/usr/bin/env python3
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestBehaviorLearningContract(unittest.TestCase):
    def test_is_local_only(self):
        path = os.path.join(ROOT, "behavior_learning.js")
        text = open(path, encoding="utf-8").read()
        self.assertIn("localStorage", text)
        self.assertNotIn("navigator.sendBeacon", text)
        self.assertNotIn("fetch(", text)
        self.assertIn("['view','save','dismiss']", text)

    def test_feedback_is_bounded(self):
        path = os.path.join(ROOT, "behavior_learning.js")
        text = open(path, encoding="utf-8").read()
        self.assertIn("Math.max(-12, Math.min(12", text)
        self.assertIn("Math.max(-20, Math.min(20", text)
        self.assertIn("slice(-MAX_EVENTS)", text)

    def test_injection_order(self):
        path = os.path.join(ROOT, "scripts", "inject_personalization_ui.py")
        text = open(path, encoding="utf-8").read()
        self.assertLess(text.index("behavior_learning.js"), text.index("personalization-ui.js"))


if __name__ == "__main__":
    unittest.main()
