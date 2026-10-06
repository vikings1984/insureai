"""P1-7 DAG Workflow：analyze 长链 DAG 编排回归（不执行真实流水线命令）。

覆盖：
  - DAG 无环；拓扑序**严格等于**原 CI 声明顺序（零行为变更的关键保证）
  - 数据边由 produces ∩ requires 自动推导（如 review 依赖 change_impact/counterfactual）
  - select：all / only / from（子树下游）/ to（含全部上游）
  - 未知节点被拒绝；--only 时缺少上游产物应被识别
  - upstream / downstream 传递闭包
"""
import os
import unittest

import dag


class TestGraphShape(unittest.TestCase):
    def test_acyclic(self):
        order, acyclic = dag.topo_order()
        self.assertTrue(acyclic)
        self.assertEqual(len(order), len(dag.NODES))

    def test_topo_order_equals_declaration_order(self):
        """顺序边兜底：拓扑序必须与原 CI 执行顺序完全一致（否则就是行为变更）。"""
        order, _ = dag.topo_order()
        self.assertEqual(order, [n["id"] for n in dag.NODES])

    def test_data_edges_derived_from_artifacts(self):
        edges = dag.build_edges()
        # review 声明依赖 change_impact.json / counterfactual.json，二者应指向 review
        self.assertIn("review", edges["change_impact"])
        self.assertIn("review", edges["counterfactual"])
        # module_health_trend 依赖 module_health.json
        self.assertIn("module_health_trend", edges["module_health"])
        # evidence_availability 依赖 freshness.json
        self.assertIn("evidence_availability", edges["freshness"])
        # validate_kg 依赖 knowledge_graph.json
        self.assertIn("validate_kg", edges["knowledge_graph"])

    def test_every_node_has_id_and_cmd(self):
        seen = set()
        for n in dag.NODES:
            self.assertTrue(n["id"])
            self.assertTrue(n["cmd"])
            self.assertNotIn(n["id"], seen, f"duplicate node id: {n['id']}")
            seen.add(n["id"])


class TestSelect(unittest.TestCase):
    def test_select_all(self):
        self.assertEqual(dag.select(None, None), [n["id"] for n in dag.NODES])

    def test_select_only(self):
        self.assertEqual(dag.select("only", "review"), ["review"])

    def test_select_to_includes_upstream(self):
        ids = dag.select("to", "evaluation")
        self.assertIn("evaluation", ids)
        self.assertIn("intelligence", ids)   # evaluation 的上游
        self.assertNotIn("module_health", ids)  # 下游不应包含
        # 结果仍按拓扑序
        self.assertEqual(ids, [n["id"] for n in dag.NODES if n["id"] in set(ids)])

    def test_select_from_includes_downstream(self):
        ids = dag.select("from", "module_health")
        self.assertIn("module_health", ids)
        self.assertIn("module_health_trend", ids)
        self.assertIn("trend_attribution", ids)
        self.assertNotIn("intelligence", ids)  # 上游不应包含

    def test_unknown_node_raises(self):
        with self.assertRaises(KeyError):
            dag.select("only", "nope")
        with self.assertRaises(KeyError):
            dag.select("from", "nope")
        with self.assertRaises(KeyError):
            dag.select("to", "nope")

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            dag.select("sideways", "review")


class TestClosureAndRequires(unittest.TestCase):
    def test_downstream_transitive(self):
        edges = dag.build_edges()
        ds = dag.downstream(edges, "module_health")
        self.assertIn("module_health_trend", ds)
        self.assertIn("trend_attribution", ds)

    def test_upstream_transitive(self):
        edges = dag.build_edges()
        us = dag.upstream(edges, "trend_attribution")
        self.assertIn("module_health_trend", us)
        self.assertIn("module_health", us)

    def test_missing_requires_detects_absent_files(self):
        node = {"requires": ["definitely_not_a_real_file_xyz.json"]}
        self.assertEqual(len(dag.missing_requires(node)), 1)
        self.assertEqual(dag.missing_requires({"requires": []}), [])
        # 真实存在的仓库文件应被识别为已就绪
        if os.path.exists(os.path.join(dag.HERE, "dag.py")):
            self.assertEqual(dag.missing_requires({"requires": ["dag.py"]}), [])

    def test_missing_requires_tolerates_empty_and_none(self):
        # 未声明 / 声明为 None 的节点不应报错，也不应被当成"缺上游"而阻断
        self.assertEqual(dag.missing_requires({"requires": []}), [])
        self.assertEqual(dag.missing_requires({"requires": None}), [])
        self.assertEqual(dag.missing_requires({}), [])


if __name__ == "__main__":
    unittest.main()
