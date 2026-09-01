#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""event_registry.py 单测 — 覆盖自举 / resolve / alias / merge / split / migrate / validate。"""
import unittest

from event_registry import (
    VERSION,
    alias,
    build,
    merge,
    migrate,
    resolve,
    split,
    validate,
)


def _ev(eid, **kw):
    return {"event_id": eid, "title": kw.get("title", ""), "topic": kw.get("topic", ""),
            "event_type": kw.get("event_type", ""), "published_at": kw.get("published_at", "")}


class EventRegistryTests(unittest.TestCase):
    def test_build_bootstrap_is_1to1_and_covers_all(self):
        evs = [(_ev("evt_1", title="A"), "daily_brief"),
               (_ev("evt_2", title="B"), "daily_brief"),
               (_ev("evt_3", title="C"), "review_queue")]
        reg = build(evs, "2026-09-01T00:00:00Z")
        self.assertEqual(reg["count"], 3)
        self.assertEqual(len(reg["by_event_id"]), 3)
        for eid in ("evt_1", "evt_2", "evt_3"):
            self.assertIn(eid, reg["by_event_id"])
        validate(reg)  # 不应抛

    def test_build_dedup_cross_origin_keeps_two_sources(self):
        evs = [(_ev("evt_x", title="X"), "daily_brief"),
               (_ev("evt_x", title="X"), "review_queue")]
        reg = build(evs)
        cev = reg["by_event_id"]["evt_x"]
        rec = reg["canonical_events"][cev]
        self.assertEqual(len(rec["sources"]), 2)  # 跨来源合并为 2 个 source
        self.assertEqual(reg["count"], 1)

    def test_build_skips_event_without_id_no_fabrication(self):
        evs = [(_ev("evt_ok"), "daily_brief"), ({"title": "无 id"}, "daily_brief")]
        reg = build(evs)
        self.assertEqual(reg["count"], 1)
        self.assertIn("evt_ok", reg["by_event_id"])

    def test_resolve_event_id_and_canonical(self):
        reg = build([(_ev("evt_9"), "daily_brief")])
        cev = reg["by_event_id"]["evt_9"]
        self.assertEqual(resolve("evt_9", reg), cev)
        self.assertEqual(resolve(cev, reg), cev)  # 直接传 canonical 也返回自身
        self.assertIsNone(resolve("nope", reg))

    def test_alias_maps_arbitrary_id_to_canonical(self):
        reg = build([(_ev("evt_a"), "daily_brief")])
        cev = reg["by_event_id"]["evt_a"]
        alias(reg, "legacy_id_1", cev)
        self.assertEqual(resolve("legacy_id_1", reg), cev)
        self.assertIn("legacy_id_1", reg["canonical_events"][cev]["aliases"])
        validate(reg)

    def test_merge_absorbs_sources_and_marks_inactive(self):
        reg = build([(_ev("evt_m1", title="M1"), "daily_brief"),
                     (_ev("evt_m2", title="M2"), "review_queue")])
        tgt = reg["by_event_id"]["evt_m1"]
        src = reg["by_event_id"]["evt_m2"]
        merge(reg, tgt, src)
        self.assertEqual(reg["canonical_events"][src]["status"], "merged")
        self.assertEqual(reg["canonical_events"][src]["merged_into"], tgt)
        self.assertIn("evt_m2", reg["by_event_id"])
        self.assertEqual(reg["by_event_id"]["evt_m2"], tgt)  # 重新指向 target
        self.assertIn(src, reg["canonical_events"][tgt]["merged_from"])
        validate(reg)

    def test_split_moves_subset_sources_to_new_canonical(self):
        reg = build([(_ev("evt_s1"), "daily_brief"),
                     (_ev("evt_s2"), "daily_brief"),
                     (_ev("evt_s3"), "daily_brief")])
        s1 = reg["by_event_id"]["evt_s1"]
        s2 = reg["by_event_id"]["evt_s2"]
        s3 = reg["by_event_id"]["evt_s3"]
        merge(reg, s1, s2)
        merge(reg, s1, s3)  # s1 现含 evt_s1/s2/s3
        new_id = split(reg, s1, ["evt_s2"])
        self.assertNotEqual(new_id, s1)
        self.assertEqual(reg["by_event_id"]["evt_s2"], new_id)
        self.assertEqual(reg["by_event_id"]["evt_s1"], s1)
        self.assertEqual(reg["by_event_id"]["evt_s3"], s1)
        self.assertIn(new_id, reg["canonical_events"][s1]["split_into"])
        validate(reg)

    def test_migrate_repoints_single_event_id(self):
        reg = build([(_ev("evt_p1"), "daily_brief"), (_ev("evt_p2"), "review_queue")])
        a = reg["by_event_id"]["evt_p1"]
        b = reg["by_event_id"]["evt_p2"]
        migrate(reg, "evt_p1", b)
        self.assertEqual(reg["by_event_id"]["evt_p1"], b)
        self.assertNotIn("evt_p1", [s["event_id"] for s in reg["canonical_events"][a]["sources"]])
        validate(reg)

    def test_validate_fail_closed_on_dangling_by_event_id(self):
        reg = build([(_ev("evt_d"), "daily_brief")])
        reg["by_event_id"]["ghost"] = "cev_deadbeef0000"  # 悬空引用
        with self.assertRaises(AssertionError):
            validate(reg)

    def test_build_is_deterministic(self):
        evs = [(_ev("evt_z"), "daily_brief")]
        r1 = build(evs, "2026-09-01T00:00:00Z")
        r2 = build(evs, "2026-09-01T00:00:00Z")
        self.assertEqual(r1["by_event_id"]["evt_z"], r2["by_event_id"]["evt_z"])
        self.assertEqual(r1["canonical_events"][r1["by_event_id"]["evt_z"]]["canonical_event_id"],
                         r2["canonical_events"][r2["by_event_id"]["evt_z"]]["canonical_event_id"])


if __name__ == "__main__":
    unittest.main()
