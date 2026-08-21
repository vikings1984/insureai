#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import promote_reviews


class TestPromoteReviews(unittest.TestCase):
    def test_human_review_becomes_regression_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = root / "review_labels.json"
            corpus = root / "evaluation_cases.json"
            labels.write_text(json.dumps({
                "reviews": [{
                    "review_id": "evt-x",
                    "label": "false_positive",
                    "notes": "wrong urgency",
                    "expected": {"type": "decision", "urgency": "watch"}
                }]
            }), encoding="utf-8")
            corpus.write_text(json.dumps({"version": 1, "cases": []}), encoding="utf-8")
            with patch.object(promote_reviews, "LABELS", labels), patch.object(promote_reviews, "CORPUS", corpus):
                self.assertEqual(promote_reviews.promote(), 1)
                self.assertEqual(promote_reviews.promote(), 0)
            result = json.loads(corpus.read_text(encoding="utf-8"))
            self.assertEqual(len(result["cases"]), 1)
            self.assertEqual(result["cases"][0]["source"], "human_review")
            self.assertEqual(result["cases"][0]["expected"]["urgency"], "watch")


if __name__ == "__main__":
    unittest.main()
