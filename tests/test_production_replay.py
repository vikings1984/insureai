#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import production_replay


class TestProductionReplay(unittest.TestCase):
    def test_empty_production_dataset_is_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps({"news": []}), encoding="utf-8")
            with patch.object(production_replay, "DATA", path):
                result = production_replay.run_replay()
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["input_count"], 0)

    def test_replay_is_stable_under_input_order(self):
        rows = [
            {"id": "1", "title": "A acquires B", "summary": "A acquires B", "tags": "A,B", "source_name": "R1", "source_url": "https://r1.example/a", "published_at": "2026-08-20T10:00:00+00:00", "source_authority": 90, "ai_score": 90, "research_topic": "capital_reinsurance"},
            {"id": "2", "title": "A agrees to buy B", "summary": "A agrees to buy B", "tags": "A,B", "source_name": "R2", "source_url": "https://r2.example/a", "published_at": "2026-08-20T11:00:00+00:00", "source_authority": 90, "ai_score": 90, "research_topic": "capital_reinsurance"},
            {"id": "3", "title": "A appoints a CFO", "summary": "A appoints a CFO", "tags": "A", "source_name": "R1", "source_url": "https://r1.example/b", "published_at": "2026-08-20T12:00:00+00:00", "source_authority": 80, "ai_score": 70, "research_topic": "digital_transformation"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            path.write_text(json.dumps({"news": rows}), encoding="utf-8")
            with patch.object(production_replay, "DATA", path):
                result = production_replay.run_replay()
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["quality"]["replay_stability"], 0.99)
        self.assertEqual(result["quality"]["event_integrity"]["duplicate_event_ids"], 0)
        self.assertEqual(result["quality"]["event_integrity"]["duplicate_article_assignments"], 0)
        self.assertEqual(result["quality"]["event_integrity"]["article_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
