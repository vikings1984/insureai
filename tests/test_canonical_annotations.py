"""X2 / Sprint 1 质量门：event_type 分区 + 30 条标注集（false merge = 硬失败）。

评审修订核心约束：
- Canonical Identity 按 event_type 分区、先窄后宽：acquisition/regulatory 可自动归并，
  product/personnel/industry_update/catastrophe/other 只做别名、不自动 merge；
- split 必须人工（MANUAL_SPLIT_REQUIRED）；
- 标注集 `canonical_annotation_set.json` 是归并行为的回归基线，false merge = 硬失败。
"""
import json
import unittest
from pathlib import Path

import event_registry

ROOT = Path(__file__).resolve().parents[1]


class PolicyTests(unittest.TestCase):
    def test_canonicalize_only_acquisition_regulatory(self):
        self.assertTrue(event_registry.may_auto_merge("acquisition"))
        self.assertTrue(event_registry.may_auto_merge("regulatory"))
        for t in ("product", "personnel", "industry_update", "catastrophe", "other", "merger", ""):
            self.assertFalse(event_registry.may_auto_merge(t), f"{t} 不应可自动归并")

    def test_event_type_domain(self):
        self.assertEqual(event_registry.event_type_domain("acquisition"), "acquisition")
        self.assertEqual(event_registry.event_type_domain("merger"), "acquisition")
        self.assertEqual(event_registry.event_type_domain("regulatory"), "regulatory")
        self.assertEqual(event_registry.event_type_domain("catastrophe"), "catastrophe")
        self.assertEqual(event_registry.event_type_domain("whatever"), "other")


class ShouldMergeTests(unittest.TestCase):
    def test_same_entity_same_type_merges(self):
        a = {"event_type": "acquisition", "key_entity": "At-Bay", "title": "At-Bay 融资"}
        b = {"event_type": "acquisition", "key_entity": "At-Bay", "title": "At-Bay 再融资"}
        self.assertTrue(event_registry.should_merge(a, b))

    def test_different_entity_same_type_no_merge(self):
        a = {"event_type": "acquisition", "key_entity": "Farmers Insurance"}
        b = {"event_type": "acquisition", "key_entity": "Cover-More"}
        self.assertFalse(event_registry.should_merge(a, b))

    def test_cross_type_never_merges(self):
        a = {"event_type": "acquisition", "key_entity": "At-Bay"}
        b = {"event_type": "regulatory", "key_entity": "At-Bay"}
        self.assertFalse(event_registry.should_merge(a, b))

    def test_alias_only_type_never_merges(self):
        a = {"event_type": "product", "key_entity": "车险条款"}
        b = {"event_type": "product", "key_entity": "车险条款"}
        self.assertFalse(event_registry.should_merge(a, b), "alias-only 即使同 key_entity 也不自动合")

    def test_one_sided_key_entity_no_assume(self):
        a = {"event_type": "acquisition", "key_entity": "At-Bay"}
        b = {"event_type": "acquisition"}
        self.assertFalse(event_registry.should_merge(a, b))


class AnnotationQualityGateTests(unittest.TestCase):
    def test_validate_against_annotations_passes(self):
        res = event_registry.validate_against_annotations()
        self.assertEqual(res["cases"], 30, f"标注集应为 30 条，实得 {res['cases']}")
        self.assertEqual(res["failed"], [], f"标注质量门失败：{res['failed']}")
        self.assertEqual(res["passed"], 30)

    def test_hard_cases_from_review(self):
        anno = json.loads((ROOT / "canonical_annotation_set.json").read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in anno["cases"]}
        # 必合：同一收购多源
        self.assertEqual(by_id["atbay-multisource-merge"]["expect_ce_count"], 1)
        # 必拆：Zurich Farmers vs Cover-More
        self.assertEqual(by_id["zurich-farmers-vs-covermore"]["expect_ce_count"], 2)
        # 必拆：中保协车险指南 vs 非车险治理
        self.assertEqual(by_id["cia-motor-vs-nonmotor"]["expect_ce_count"], 2)


class ManualSplitGateTests(unittest.TestCase):
    def test_auto_split_rejected(self):
        reg = event_registry.build([({"event_id": "e1", "event_type": "acquisition", "key_entity": "At-Bay"}, "t")])
        with self.assertRaises(RuntimeError):
            event_registry.split(reg, list(reg["canonical_events"])[0], ["e1"], method="auto")

    def test_manual_split_ok(self):
        reg = event_registry.build([({"event_id": "e1", "event_type": "acquisition"}, "t"),
                                     ({"event_id": "e2", "event_type": "acquisition"}, "t")])
        cev = list(reg["canonical_events"])[0]
        new_id = event_registry.split(reg, cev, ["e1"], method="manual")
        self.assertTrue(new_id)
        event_registry.validate(reg)  # 不得破坏结构


class BuildBackwardCompatTests(unittest.TestCase):
    def test_build_records_domain_and_key_entity(self):
        reg = event_registry.build([({"event_id": "e1", "event_type": "acquisition",
                                       "key_entity": "At-Bay", "title": "At-Bay 融资"}, "t")])
        rec = reg["canonical_events"][list(reg["canonical_events"])[0]]
        self.assertEqual(rec["domain"], "acquisition")
        self.assertEqual(rec["key_entity"], "At-Bay")
        # X1 依赖字段保持不变
        self.assertIn("by_event_id", reg)
        self.assertIn("count", reg)
        self.assertTrue(reg["by_event_id"]["e1"])


if __name__ == "__main__":
    unittest.main()
