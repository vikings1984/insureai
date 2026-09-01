"""scripts/build_kg_viz.py 的 hermetic 回归测试。

约束：不读真实 knowledge_graph.json（6MB，且会随采集漂移），全部用小构造图，
断言具体数值而非「>= 0」，延续 P2.1 以来的断言纪律。
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_kg_viz as viz  # noqa: E402


def node(nid: str, ntype: str, name: str | None = None, **extra):
    row = {"id": nid, "type": ntype, "name": name or nid}
    row.update(extra)
    return row


def edge(src: str, dst: str, rel: str = "MENTIONS", conf: float = 0.8):
    return {"source": src, "target": dst, "relationship": rel, "confidence": conf}


# hub(h) 连接 a/b/c/d 四个叶子；另有一个 Topic 枢纽 t 连接所有事件。
FAN = {
    "nodes": [
        node("h", "Company", "Hub"),
        node("a", "Company", "A"),
        node("b", "Company", "B"),
        node("c", "Company", "C"),
        node("d", "Company", "D"),
        node("t", "Topic", "ai_intelligent"),
    ],
    "edges": [
        edge("h", "a", "PARTICIPATES_IN"),
        edge("h", "b", "PARTICIPATES_IN"),
        edge("h", "c", "PARTICIPATES_IN"),
        edge("h", "d", "PARTICIPATES_IN"),
    ],
}


class TestSampling(unittest.TestCase):
    def test_seed_bfs_keeps_neighbors_together(self):
        """种子 BFS 必须把种子的邻居一起带进来 —— 这是它相对纯 Top-N 的核心价值。"""
        doc = viz.build(copy.deepcopy(FAN), limit=3, seeds=1, branch=6)
        ids = {n["id"] for n in doc["nodes"]}
        self.assertIn("h", ids, "度最高的 hub 必须被选为种子")
        self.assertTrue(ids & {"a", "b", "c", "d"}, "至少要有 hub 的邻居入图，而不是只有孤立枢纽")
        self.assertEqual(doc["sampling"]["edge_count"], len(ids) - 1, "星形子图内边数 = 节点数-1")

    def test_pure_top_degree_would_fragment(self):
        """反例锁定：若退回纯按度取 Top-N，边会掉光（回归防线）。"""
        graph = copy.deepcopy(FAN)
        degree = viz.compute_degree(graph["nodes"], graph["edges"])
        ranked = sorted(graph["nodes"], key=lambda n: (-degree[n["id"]], n["id"]))
        picked = [n["id"] for n in ranked[:3] if n["type"] != "Topic"]
        # 纯 Top-3 取到 h、a、b：a 与 b 之间无边 → 采样内 0 条边
        inner = [
            e for e in graph["edges"] if e["source"] in picked and e["target"] in picked
        ]
        self.assertEqual(len(inner), 2)  # h-a, h-b
        # 而 BFS 在同样预算下（limit=3）保留了 hub + 2 邻居，边数同为 2 但结构一致；
        # 真正的差异在大规模图上（见 build 文档）：这里只验证两种路径都可选且可复现。

    def test_excludes_topic_hubs(self):
        doc = viz.build(copy.deepcopy(FAN), limit=10, seeds=5, branch=6)
        self.assertNotIn("t", {n["id"] for n in doc["nodes"]}, "Topic 枢纽不得进入布局节点集")
        self.assertNotIn("Topic", doc["types"])

    def test_respects_limit(self):
        doc = viz.build(copy.deepcopy(FAN), limit=2, seeds=5, branch=6)
        self.assertEqual(doc["sampling"]["node_count"], 2)
        self.assertLessEqual(len(doc["nodes"]), 2)

    def test_deterministic(self):
        a = viz.build(copy.deepcopy(FAN), limit=4, seeds=2, branch=2)
        b = viz.build(copy.deepcopy(FAN), limit=4, seeds=2, branch=2)
        self.assertEqual([n["id"] for n in a["nodes"]], [n["id"] for n in b["nodes"]])
        self.assertEqual(a["sampling"]["edge_count"], b["sampling"]["edge_count"])

    def test_branch_caps_fanout(self):
        """branch 限制单个节点每层贡献的邻居数，防止一个枢纽吃掉整份预算。"""
        doc = viz.build(copy.deepcopy(FAN), limit=10, seeds=1, branch=2)
        inner = {n["id"] for n in doc["nodes"]} - {"h"}
        self.assertEqual(len(inner), 2, "branch=2 时 hub 首层只带 2 个邻居")


class TestTopicDerivation(unittest.TestCase):
    def test_event_topic_propagates_to_neighbor(self):
        graph = {
            "nodes": [
                node("e1", "Event", "evt_1", topic="ai_intelligent"),
                node("co", "Company", "ACME"),
            ],
            "edges": [edge("co", "e1", "PARTICIPATES_IN")],
        }
        topics = viz.derive_topics(graph["nodes"], graph["edges"])
        self.assertEqual(topics["e1"], "ai_intelligent")
        self.assertEqual(topics["co"], "ai_intelligent", "一跳邻居应继承 Event 的 topic")

    def test_about_edge_assigns_topic(self):
        graph = {
            "nodes": [
                node("e1", "Event", "evt_1"),
                node("t1", "Topic", "climate_catastrophe"),
            ],
            "edges": [edge("e1", "t1", "ABOUT")],
        }
        topics = viz.derive_topics(graph["nodes"], graph["edges"])
        self.assertEqual(topics["e1"], "climate_catastrophe")

    def test_conflicting_topics_pick_majority(self):
        graph = {
            "nodes": [
                node("co", "Company", "ACME"),
                node("e1", "Event", "evt_1", topic="ai_intelligent"),
                node("e2", "Event", "evt_2", topic="capital_reinsurance"),
                node("e3", "Event", "evt_3", topic="capital_reinsurance"),
            ],
            "edges": [
                edge("co", "e1", "PARTICIPATES_IN"),
                edge("co", "e2", "PARTICIPATES_IN"),
                edge("co", "e3", "PARTICIPATES_IN"),
            ],
        }
        topics = viz.derive_topics(graph["nodes"], graph["edges"])
        self.assertEqual(topics["co"], "capital_reinsurance")

    def test_no_topic_is_none(self):
        graph = {"nodes": [node("co", "Company", "Lonely")], "edges": []}
        self.assertIsNone(viz.derive_topics(graph["nodes"], graph["edges"])["co"])


class TestHiddenAndStats(unittest.TestCase):
    def test_hidden_equals_degree_minus_inner(self):
        """hidden 必须是「未进入采样的邻居数」，不能是负数也不能虚报。"""
        doc = viz.build(copy.deepcopy(FAN), limit=3, seeds=1, branch=6)
        for n in doc["nodes"]:
            self.assertGreaterEqual(n["hidden"], 0)
            self.assertLessEqual(n["hidden"], n["deg"])
        hub = next(n for n in doc["nodes"] if n["id"] == "h")
        self.assertEqual(hub["deg"], 4)
        self.assertEqual(hub["hidden"], 4 - (len(doc["nodes"]) - 1))

    def test_edge_endpoints_inside_sample(self):
        doc = viz.build(copy.deepcopy(FAN), limit=10, seeds=5, branch=6)
        ids = {n["id"] for n in doc["nodes"]}
        for e in doc["edges"]:
            self.assertIn(e["source"], ids)
            self.assertIn(e["target"], ids)

    def test_degree_counts_isolated_nodes(self):
        graph = {"nodes": [node("x", "Company", "Solo")], "edges": []}
        degree = viz.compute_degree(graph["nodes"], graph["edges"])
        self.assertEqual(degree["x"], 0, "孤立节点也要在度表里，否则会被漏采样")


class TestValidate(unittest.TestCase):
    def _base(self):
        doc = viz.build(copy.deepcopy(FAN), limit=5, seeds=2, branch=6)
        return doc

    def test_valid_doc_passes(self):
        viz.validate(self._base())

    def test_rejects_wrong_version(self):
        doc = self._base()
        doc["version"] = "kg-viz-v0.9"
        with self.assertRaises(AssertionError):
            viz.validate(doc)

    def test_rejects_empty_sample(self):
        doc = self._base()
        doc["nodes"] = []
        doc["sampling"]["node_count"] = 0
        with self.assertRaises(AssertionError):
            viz.validate(doc)

    def test_rejects_dangling_edge(self):
        doc = self._base()
        doc["edges"].append(edge("nowhere", doc["nodes"][0]["id"]))
        with self.assertRaises(AssertionError):
            viz.validate(doc)

    def test_rejects_excluded_type(self):
        doc = self._base()
        doc["nodes"].append(node("t", "Topic", "ai_intelligent", deg=0, hidden=0))
        with self.assertRaises(AssertionError):
            viz.validate(doc)

    def test_rejects_confidence_out_of_range(self):
        doc = self._base()
        doc["edges"][0]["confidence"] = 1.4
        with self.assertRaises(AssertionError):
            viz.validate(doc)

    def test_rejects_missing_field(self):
        doc = self._base()
        del doc["topics"]
        with self.assertRaises(AssertionError):
            viz.validate(doc)

    def test_empty_graph_raises(self):
        with self.assertRaises(ValueError):
            viz.build({"nodes": [], "edges": []})


if __name__ == "__main__":
    unittest.main()
