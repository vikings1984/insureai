#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-4 Source Snapshot 单测：生成 / 去重 / 不可变 / 回溯 / Evidence 透传。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import snapshot
from snapshot import (
    build_snapshot,
    canonicalize_url,
    find_snapshot,
    persist_snapshot,
    read_raw,
    snapshot_id_for,
)


class TestSnapshotBuild(unittest.TestCase):
    def test_keys_present(self):
        snap = build_snapshot("标题", "摘要", "https://www.reuters.com/a", "Reuters", "media")
        for k in ("snapshot_id", "source_id", "url", "canonical_url", "retrieved_at",
                  "content_hash", "parser_version", "raw_text"):
            self.assertIn(k, snap)
        self.assertEqual(snap["url"], "https://www.reuters.com/a")
        self.assertEqual(snap["raw_text"], "摘要")
        self.assertTrue(snap["snapshot_id"].startswith("snap_"))

    def test_source_id_uses_registry_group(self):
        snap = build_snapshot("t", "s", "https://www.reuters.com/x", "Reuters")
        self.assertEqual(snap["source_id"], "grp:reuters")

    def test_snapshot_id_deterministic(self):
        ts = "2026-10-06T03:00:00+08:00"
        a = snapshot_id_for("grp:reuters", "https://www.reuters.com/x", ts)
        b = snapshot_id_for("grp:reuters", "https://www.reuters.com/x", ts)
        self.assertEqual(a, b)

    def test_snapshot_id_differs_by_url(self):
        ts = "2026-10-06T03:00:00+08:00"
        a = snapshot_id_for("grp:reuters", "https://www.reuters.com/x", ts)
        b = snapshot_id_for("grp:reuters", "https://www.reuters.com/y", ts)
        self.assertNotEqual(a, b)

    def test_canonicalize_strips_utm(self):
        self.assertEqual(canonicalize_url("https://x.com/a?utm_source=news&id=1"),
                         "https://x.com/a?id=1")
        self.assertEqual(canonicalize_url("https://x.com/a#frag"), "https://x.com/a")


class TestSnapshotPersistImmutable(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = snapshot.SNAPSHOT_DIR
        snapshot.SNAPSHOT_DIR = self._tmp

    def tearDown(self):
        snapshot.SNAPSHOT_DIR = self._orig

    def test_persist_writes_and_find_roundtrip(self):
        snap = build_snapshot("t", "s", "https://www.reuters.com/a", "Reuters")
        sid = persist_snapshot(snap)
        self.assertEqual(find_snapshot(sid)["url"], "https://www.reuters.com/a")
        self.assertEqual(read_raw(sid), "s")

    def test_immutable_not_overwritten(self):
        snap = build_snapshot("t", "s", "https://www.reuters.com/a", "Reuters")
        sid = persist_snapshot(snap)
        p = os.path.join(self._tmp, f"{sid}.json")
        mtime1 = os.path.getmtime(p)
        # 同 id 重复 persist 必须跳过写盘（不可变）
        persist_snapshot(dict(snap))
        self.assertEqual(os.path.getmtime(p), mtime1)

    def test_dedup_by_content_hash(self):
        s1 = build_snapshot("t", "same body", "https://a.com/x")
        s2 = build_snapshot("t", "same body", "https://a.com/x")
        self.assertEqual(s1["content_hash"], s2["content_hash"])
        self.assertEqual(s1["snapshot_id"], s2["snapshot_id"])


class TestEvidenceThreadsSnapshotId(unittest.TestCase):
    """Evidence / Claim 须透传 source_snapshot_id，形成回溯链。"""

    def test_claims_evidence_carries_snapshot_id(self):
        import claims
        items = [{
            "id": "1", "title": "Munich Re to acquire At-Bay for $575 million",
            "summary": "Munich Re agreed to buy At-Bay", "source_name": "Reuters",
            "source_type": "media", "source_url": "https://www.reuters.com/a",
            "published_at": "2026-08-21T10:00:00+00:00", "date_verified": True,
            "snapshot_id": "snap_20260821_aaaaaaaa",
        }]
        event = {"event_id": "evt_1", "title": "Munich Re 收购 At-Bay", "event_type": "acquisition"}
        result = claims.build_claims(items, event)
        ev = result["claims"][0]["supporting_evidence"][0]
        self.assertEqual(ev["source_snapshot_id"], "snap_20260821_aaaaaaaa")

    def test_intelligence_evidence_carries_snapshot_id(self):
        import intelligence
        items = [{
            "id": "1", "title": "Reuters: Munich Re buys At-Bay",
            "summary": "Munich Re agreed to buy At-Bay", "source_name": "Reuters",
            "source_type": "media", "source_url": "https://www.reuters.com/a",
            "published_at": "2026-08-21T10:00:00+00:00", "date_verified": True,
            "snapshot_id": "snap_20260821_bbbbbbbb",
        }]
        ev = intelligence._evidence(items)
        self.assertEqual(ev[0]["source_snapshot_id"], "snap_20260821_bbbbbbbb")


if __name__ == "__main__":
    unittest.main()
