"""Tests for the P1-4.1 real-data candidate promotion helper (human-in-loop).

These test the deterministic glue (field mapping, engine-agreement logic,
bundle structure) without requiring a human to approve anything. The engine is
monkeypatched so the agreement logic is fully controlled.
"""
import sys
from pathlib import Path
from unittest import TestCase, mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import promote_real_v2_candidates as prom  # noqa: E402


def _fake_build(one_event: bool):
    """Return a build() stand-in: all articles in one event, or each its own."""
    def _build(data):
        news = data.get("news", [])
        if one_event:
            return {"events": [{"event_id": "evt_x", "article_ids": [x.get("id") for x in news]}]}
        return {"events": [{"event_id": f"evt_{x.get('id')}", "article_ids": [x.get("id")]} for x in news]}
    return _build


class TestMapArticle(TestCase):
    def test_source_url_maps_to_url(self):
        a = {"id": 7, "title": "T", "source_url": "http://x", "published_at": "2026-01-01",
             "source_name": "S", "research_topic": "r", "tags": ""}
        m = prom._map_article(a)
        self.assertEqual(m["url"], "http://x")
        self.assertEqual(m["id"], 7)
        self.assertEqual(m["title"], "T")


class TestEngineAgrees(TestCase):
    def test_same_event_merged(self):
        arts = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]
        with mock.patch.object(prom.intelligence, "build", _fake_build(one_event=True)):
            self.assertTrue(prom._engine_agrees(arts, "same_event"))

    def test_same_event_split_is_false(self):
        arts = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]
        with mock.patch.object(prom.intelligence, "build", _fake_build(one_event=False)):
            self.assertFalse(prom._engine_agrees(arts, "same_event"))

    def test_different_event_separate_is_true(self):
        arts = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]
        with mock.patch.object(prom.intelligence, "build", _fake_build(one_event=False)):
            self.assertTrue(prom._engine_agrees(arts, "different_event"))

    def test_different_event_merged_is_false(self):
        arts = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]
        with mock.patch.object(prom.intelligence, "build", _fake_build(one_event=True)):
            self.assertFalse(prom._engine_agrees(arts, "different_event"))

    def test_single_article_is_false(self):
        arts = [{"id": 1, "title": "a"}]
        with mock.patch.object(prom.intelligence, "build", _fake_build(one_event=True)):
            self.assertFalse(prom._engine_agrees(arts, "same_event"))


class TestPrepareBundle(TestCase):
    def test_prepare_writes_pending_bundle(self):
        import tempfile
        # write to a temp bundle so the real review artifact is never clobbered by tests
        bpath = Path(tempfile.mkdtemp()) / "review_bundle.json"
        with mock.patch.object(prom, "BUNDLE", bpath), \
             mock.patch.object(prom.intelligence, "build", _fake_build(one_event=False)):
            prom.prepare()
        self.assertTrue(bpath.exists())
        import json
        b = json.loads(bpath.read_text(encoding="utf-8"))
        self.assertEqual(b["review_status"], "pending_human")
        entries = b["entries"]
        self.assertGreater(len(entries), 0)
        for e in entries:
            self.assertEqual(e["decision"], "pending")
            self.assertIn("suggested_same_event_pairs", e)
            self.assertIn("suggested_different_event_pairs", e)
            # >=2 article clusters must produce pairs of the matching relation
            if len(e["article_ids"]) >= 2:
                if e["proposed_relation"] == "same_event":
                    self.assertTrue(len(e["suggested_same_event_pairs"]) >= 1)
                else:
                    self.assertTrue(len(e["suggested_different_event_pairs"]) >= 1)


class TestApplyGuard(TestCase):
    def test_apply_refuses_while_pending(self):
        """apply must never auto-validate; pending entries block a real apply.

        Self-contained: builds a temp bundle with one pending entry so the test
        does not depend on the real review_bundle.json's decision state.
        """
        import json
        import tempfile
        bpath = Path(tempfile.mkdtemp()) / "review_bundle_pending.json"
        bundle = {
            "version": "real-v2.0-review-bundle",
            "entries": [
                {"candidate_id": "c1", "dimension": "multi_source_3_5",
                 "decision": "approve", "article_ids": [1, 2],
                 "suggested_same_event_pairs": [[1, 2]], "suggested_different_event_pairs": []},
                {"candidate_id": "c2", "dimension": "same_company_diff_event",
                 "decision": "pending", "article_ids": [3, 4],
                 "suggested_same_event_pairs": [], "suggested_different_event_pairs": [[3, 4]]},
            ],
        }
        bpath.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        with mock.patch.object(prom, "BUNDLE", bpath):
            with self.assertRaises(SystemExit):
                prom.apply(dry_run=False)


if __name__ == "__main__":
    import unittest
    unittest.main()
