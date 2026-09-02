"""X1 收口契约测试：Executive Home 换源，不增卡片。

X1 把「事件变化」卡从 review_queue.change_impact 换成 S4 `p2_alerts.json`
（semantic_alerts），把「待决决策」卡从 review_queue.decision===null 换成
S5 `decisions_pending.json`（top_pending + meta.pending_by_tier），并要求所有
事件卡以 S1 `canonical_events.json` 的 canonical_event_id 为单一事实源锚点。

本测试同时校验「代码契约」与「数据契约」：
- 代码侧：executive_home.html 必须引用三个新数据源、使用约定的字段、渲染 ⌖ 锚点；
  不再以 review_queue 派生这两张卡片（杜绝旧路径回归）。
- 数据侧：三个 JSON 真实存在的字段必须覆盖代码所用字段；且每张卡片里的
  canonical_event_id 能在 S1 Registry 中解析（单一事实源完整性）。
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    p = ROOT / name
    if not p.exists():
        raise unittest.SkipTest(f"{name} 缺失，跳过数据契约校验")
    return json.loads(p.read_text(encoding="utf-8"))


def _home_text() -> str:
    return (ROOT / "executive_home.html").read_text(encoding="utf-8")


class X1CodeContractTests(unittest.TestCase):
    def setUp(self):
        self.html = _home_text()

    def test_event_changes_points_to_s4(self):
        self.assertIn("./p2_alerts.json", self.html, "Event Changes 未换源到 S4 p2_alerts.json")
        self.assertIn("semantic_alerts", self.html, "未从 p2_alerts.json 读取 semantic_alerts")

    def test_decisions_pending_points_to_s5(self):
        self.assertIn("./decisions_pending.json", self.html, "Decisions Pending 未换源到 S5 decisions_pending.json")
        self.assertIn("top_pending", self.html, "未从 decisions_pending.json 读取 top_pending")
        self.assertIn("pending_by_tier", self.html, "未使用 S5 决策漏斗分层（now/soon/watch）")

    def test_canonical_anchor_wired(self):
        self.assertIn("./canonical_events.json", self.html, "未引入 S1 canonical_events.json")
        self.assertIn("by_event_id", self.html, "未使用 by_event_id 映射做事件身份归一")
        self.assertIn("ceTag", self.html, "事件卡未定义 canonical_event_id 锚点渲染器")
        self.assertIn("⌖", self.html, "事件卡未渲染 ⌖ canonical_event_id 锚点")

    def test_old_review_queue_path_removed(self):
        """换源后不应再用 review_queue 派生这两张卡片，杜绝旧路径回归。"""
        # 旧 Event Changes 来源
        self.assertNotIn("change_impact", self.html, "仍存在旧 change_impact 派生路径")
        # 旧 Decisions Pending 来源：以 decision===null 过滤 review_queue
        self.assertNotIn("decision===null", self.html, "仍存在旧 decision===null 派生路径")


class X1DataContractTests(unittest.TestCase):
    def setUp(self):
        self.alerts = _load("p2_alerts.json")
        self.pending = _load("decisions_pending.json")
        self.canon = _load("canonical_events.json")

    def test_s4_alert_fields(self):
        lst = self.alerts.get("semantic_alerts")
        self.assertIsInstance(lst, list, "p2_alerts.json.semantic_alerts 非数组")
        self.assertTrue(lst, "semantic_alerts 为空（X1 依赖其渲染 Event Changes）")
        for a in lst:
            for k in ("type", "canonical_event_id", "title", "topic", "severity"):
                self.assertIn(k, a, f"alert 缺字段 {k}: {a.get('title','?')}")

    def test_s5_funnel_fields(self):
        meta = self.pending.get("meta", {})
        for k in ("pending", "decided", "reached_threshold", "decided_sample_size"):
            self.assertIn(k, meta, f"decisions_pending.meta 缺字段 {k}")
        tiers = meta.get("pending_by_tier", {})
        for t in ("now", "soon", "watch"):
            self.assertIn(t, tiers, f"决策漏斗缺分层 {t}")
        tp = self.pending.get("top_pending")
        self.assertIsInstance(tp, list, "decisions_pending.top_pending 非数组")
        self.assertTrue(tp, "top_pending 为空（X1 依赖其渲染 Decisions Pending）")
        for i in tp:
            for k in ("tier", "canonical_event_id", "title", "topic", "priority", "trust_level", "reason_types"):
                self.assertIn(k, i, f"top_pending 项缺字段 {k}: {i.get('title','?')}")

    def test_canonical_registry_fields(self):
        self.assertIn("by_event_id", self.canon, "canonical_events.json 缺 by_event_id 映射")
        self.assertIn("canonical_events", self.canon, "canonical_events.json 缺 canonical_events 主体")
        self.assertIn("count", self.canon, "canonical_events.json 缺 count")
        self.assertIsInstance(self.canon["by_event_id"], dict)
        self.assertGreater(len(self.canon["by_event_id"]), 0, "by_event_id 为空，无法做身份归一")

    def test_canonical_anchor_resolves(self):
        """单事实源完整性：每张卡片里的 canonical_event_id 必须在 S1 Registry 中存在。"""
        ceids = set(self.canon.get("canonical_events", {}).keys())
        self.assertTrue(ceids, "canonical_events 主体为空")

        def check(ceid, where):
            self.assertIn(ceid, ceids, f"{where} 的 canonical_event_id {ceid} 不在 S1 Registry 中")

        for a in self.alerts.get("semantic_alerts", []):
            check(a["canonical_event_id"], "S4 alert")
        for i in self.pending.get("top_pending", []):
            check(i["canonical_event_id"], "S5 top_pending")

    def test_event_id_fallback_map_covers_alert_items(self):
        """代码用 CEMAP[event_id] 兜底；校验 by_event_id 至少覆盖最直接依赖的 alert event_id。"""
        by_event_id = self.canon.get("by_event_id", {})
        for a in self.alerts.get("semantic_alerts", []):
            eid = a.get("event_id")
            if eid:  # alert 通常同时带 canonical_event_id；兜底路径要求 event_id 可映射
                self.assertIn(eid, by_event_id,
                              f"alert event_id {eid} 不在 by_event_id 兜底映射中")


if __name__ == "__main__":
    unittest.main()
