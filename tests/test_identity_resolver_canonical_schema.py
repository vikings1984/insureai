#!/usr/bin/python3
"""P0-1 Identity Resolver 字段错位回归（第六阶段「真实性与生产闭环」）。

根因：second_brain 实体线程事件**只带 canonical_event_id**（无 event_id），
而propose_merges_from_entity_threads 原先只读 ev["event_id"] → eids 恒空 →
候选恒0（candidate_merges=0、resolution recall=0）。本测试锁定：

- canonical_event_id schema 能正常提出候选（生产真实schema）；
- event_id schema仍兼容（向后兼容，不破坏既有用例）；
- 两种 schema 混用也能提出；
- **只提出 proposal，绝不执行合并**（status 恒为 proposed）；
- 跨 domain 分区门在 canonical schema 下**依然生效**（不得因修复而放宽）。
"""
from __future__ import annotations

import unittest

import identity_resolver as ir


def _reg():
    """两个同domain CE 的最小registry。"""
    return {
        "canonical_events": {
            "cev_a": {"domain": "other", "event_type": "product", "aliases": [],
                      "merged_from": [], "split_into": []},
            "cev_b": {"domain": "other", "event_type": "product", "aliases": [],
                      "merged_from": [], "split_into": []},
        }
    }


def _reg_two_domains():
    return {
        "canonical_events": {
            "cev_acq": {"domain": "acquisition", "event_type": "acquisition", "aliases": [],
                        "merged_from": [], "split_into": []},
            "cev_reg": {"domain": "regulatory", "event_type": "regulatory", "aliases": [],
                        "merged_from": [], "split_into": []},
        }
    }


class TestCanonicalIdSchema(unittest.TestCase):
    """second_brain 生产 schema：events 只有 canonical_event_id。"""

    def test_canonical_id_schema_proposes(self):
        threads = [{"entity": "某实体", "type": "org", "type_": None, "events": [
            {"canonical_event_id": "cev_a"}, {"canonical_event_id": "cev_b"}]}]
        cands = ir.propose_merges_from_entity_threads(threads, _reg())
        self.assertEqual(len(cands), 1, "canonical_event_id schema 必须能提出候选")
        self.assertEqual(set(cands[0]["canonical_ids"]), {"cev_a", "cev_b"})

    def test_event_id_schema_still_works(self):
        """向后兼容：老 schema 行为不变。"""
        threads = [{"entity": "某实体", "type": "org",
                    "events": [{"event_id": "cev_a"}, {"event_id": "cev_b"}]}]
        cands = ir.propose_merges_from_entity_threads(threads, _reg())
        self.assertEqual(len(cands), 1)
        self.assertEqual(set(cands[0]["canonical_ids"]), {"cev_a", "cev_b"})

    def test_mixed_schema(self):
        threads = [{"entity": "某实体", "type": "org", "events": [
            {"canonical_event_id": "cev_a"}, {"event_id": "cev_b"}]}]
        cands = ir.propose_merges_from_entity_threads(threads, _reg())
        self.assertEqual(len(cands), 1)
        self.assertEqual(set(cands[0]["canonical_ids"]), {"cev_a", "cev_b"})

    def test_only_proposal_never_merged(self):
        """修复只影响 proposal：status 恒 proposed，registry 的 merged_from 不得被改。"""
        reg = _reg()
        threads = [{"entity": "某实体", "type": "org", "events": [
            {"canonical_event_id": "cev_a"}, {"canonical_event_id": "cev_b"}]}]
        cands = ir.propose_merges_from_entity_threads(threads, reg)
        self.assertEqual(cands[0]["status"], "proposed")
        # 不得执行合并：两个 CE 仍在、merged_from 仍空
        self.assertEqual(len(reg["canonical_events"]), 2)
        for ce in reg["canonical_events"].values():
            self.assertEqual(ce["merged_from"], [])

    def test_cross_domain_gate_still_blocks(self):
        """跨 domain 分区门在 canonical schema 下依然拒绝（不得因修复而放宽）。"""
        threads = [{"entity": "跨域实体", "type": "org", "events": [
            {"canonical_event_id": "cev_acq"}, {"canonical_event_id": "cev_reg"}]}]
        cands = ir.propose_merges_from_entity_threads(threads, _reg_two_domains())
        self.assertEqual(cands, [], "跨 domain 共现实体不得提议合并")

    def test_single_event_skipped(self):
        threads = [{"entity": "单事件", "type": "org",
                    "events": [{"canonical_event_id": "cev_a"}]}]
        self.assertEqual(ir.propose_merges_from_entity_threads(threads, _reg()), [])


if __name__ == "__main__":
    unittest.main()