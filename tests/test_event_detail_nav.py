#!/usr/bin/env python3
"""Event Detail 导航与关联视图契约测试。

P1-9：intelligence.html 的事件详情必须支持
  1) 深链直达（?event=<event_id>）—— 分享链接可定位到具体事件；
  2) 相关事件关联视图 —— 同主题事件可一键跳转，形成事件间导航。

两条硬约束：
  - 导航类代码一律置于 /* detail-renderer:start */ … /* detail-renderer:end */
    **锁定区块之外**，不污染 ED-1 渲染契约（见 test_event_detail_ui.py 白名单）；
  - 关联视图只读事件索引已有字段，不引入 artifact 之外的事实。
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "intelligence.html"
INTELLIGENCE = ROOT / "intelligence.json"

LOCK_START = "/* detail-renderer:start"
LOCK_END = "/* detail-renderer:end"

# renderRelated 允许读取的字段：artifact 字段 + JS 方法/属性 + 状态容器
RELATED_FIELDS = {"event_id", "topic", "topic_label", "title", "scores", "intelligence_score", "source_count"}
RELATED_JS = {
    "filter", "sort", "slice", "map", "join", "indexOf", "innerHTML", "length",
    "getElementById", "querySelectorAll", "forEach", "addEventListener", "dataset",
}
RELATED_STATE = {"state", "data", "events"}
# DOM 选择器 / data-* 属性名，非 artifact 字段
RELATED_DOM = {"j", "event"}


def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


def fn_body(text: str, name: str) -> str:
    start = text.index(f"function {name}(")
    end = text.index("\n  }", start)
    return text[start:end]


def offset_of(text: str, needle: str) -> int:
    return text.index(needle)


class DeepLinkTests(unittest.TestCase):
    """深链：URL ?event=<id> → 定位事件 → 回写 URL。"""

    def test_event_id_from_query_reads_event_param(self):
        body = fn_body(page_text(), "eventIdFromQuery")
        self.assertIn("URLSearchParams", body)
        self.assertIn("location.search", body)
        self.assertIn("'event'", body)

    def test_event_id_from_query_is_exception_safe(self):
        body = fn_body(page_text(), "eventIdFromQuery")
        self.assertIn("try{", body)
        self.assertIn("catch(", body)

    def test_index_of_event_matches_on_event_id(self):
        body = fn_body(page_text(), "indexOfEvent")
        self.assertIn("findIndex", body)
        self.assertIn("event_id", body)

    def test_index_of_event_falls_back_to_first(self):
        """深链失效（事件已归档/ID 变更）时回退首个事件，不打断页面。"""
        body = fn_body(page_text(), "indexOfEvent")
        self.assertIn("if(!eventId) return 0;", body)
        self.assertIn("i >= 0 ? i : 0", body)

    def test_sync_url_writes_event_param_without_history_noise(self):
        """用 replaceState 而非 pushState：切换事件不污染浏览器后退栈。"""
        body = fn_body(page_text(), "syncUrl")
        self.assertIn("history.replaceState", body)
        self.assertNotIn("history.pushState", body)
        self.assertIn("searchParams.set('event'", body)

    def test_sync_url_is_exception_safe(self):
        body = fn_body(page_text(), "syncUrl")
        self.assertIn("try{", body)
        self.assertIn("catch(", body)

    def test_load_uses_deep_link_on_first_render(self):
        text = page_text()
        self.assertIn("indexOfEvent(state.data.events || [], eventIdFromQuery())", text)


class LockedRendererIsolationTests(unittest.TestCase):
    """导航代码不得进入 ED-1 锁定渲染区块。"""

    def test_navigation_functions_outside_locked_block(self):
        text = page_text()
        start = offset_of(text, LOCK_START)
        end = offset_of(text, LOCK_END)
        for name in ("eventIdFromQuery", "indexOfEvent", "syncUrl", "renderRelated"):
            with self.subTest(fn=name):
                pos = offset_of(text, f"function {name}(")
                self.assertTrue(
                    pos < start or pos > end,
                    f"{name} 落在 detail-renderer 锁定区块内，会污染 ED-1 白名单契约",
                )

    def test_whitelist_contract_still_holds(self):
        """锁定区块内的字段访问集合不受导航代码影响。"""
        from test_event_detail_ui import renderer_body

        self.assertIn("what_happened", renderer_body())


class RelatedEventsTests(unittest.TestCase):
    """关联视图：同主题、排除自身、限量、转义、字段白名单。"""

    def test_related_block_present_in_aside(self):
        text = page_text()
        aside_start = text.index("<aside")
        aside_end = text.index("</aside>")
        aside = text[aside_start:aside_end]
        self.assertIn('id="related"', aside)
        self.assertIn('id="related-body"', aside)

    def test_related_excludes_self(self):
        body = fn_body(page_text(), "renderRelated")
        self.assertIn("x.event_id !== e.event_id", body)

    def test_related_requires_non_empty_topic(self):
        """无主题事件不得按空串归并互相关联。"""
        body = fn_body(page_text(), "renderRelated")
        self.assertIn("const related = topic", body)
        self.assertIn("? ev.filter(", body)
        self.assertIn(": []", body)

    def test_related_capped_at_five(self):
        body = fn_body(page_text(), "renderRelated")
        self.assertIn("slice(0, 5)", body)

    def test_related_ranked_by_intelligence_score(self):
        body = fn_body(page_text(), "renderRelated")
        self.assertIn("intelligence_score", body)
        self.assertIn(".sort(", body)

    def test_related_renders_only_whitelisted_fields(self):
        body = fn_body(page_text(), "renderRelated")
        accessed = set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)", body))
        unexpected = accessed - (RELATED_FIELDS | RELATED_JS | RELATED_STATE | RELATED_DOM)
        self.assertFalse(unexpected, f"renderRelated 读取了白名单之外的字段: {sorted(unexpected)}")

    def test_related_escapes_untrusted_text(self):
        """标题来自外部信源，必须经 esc() 转义后再插入 innerHTML。"""
        body = fn_body(page_text(), "renderRelated")
        self.assertIn("${esc(x.title)}", body)
        self.assertIn("${esc(x.topic_label", body)

    def test_related_cards_are_clickable(self):
        body = fn_body(page_text(), "renderRelated")
        self.assertIn("addEventListener('click'", body)
        self.assertIn("showEvent(", body)

    def test_related_invoked_on_event_show(self):
        text = page_text()
        self.assertIn("renderRelated(lean)", text)
        self.assertIn("renderRelated(full)", text)


class ArtifactGroundingTests(unittest.TestCase):
    """关联视图依赖的字段必须在真实 artifact 中存在。"""

    @classmethod
    def setUpClass(cls):
        if not INTELLIGENCE.exists():
            raise unittest.SkipTest("intelligence.json 不存在（未本地运行采集）")
        cls.data = json.loads(INTELLIGENCE.read_text(encoding="utf-8"))

    def test_topic_field_exists_on_events(self):
        events = self.data.get("events") or []
        self.assertTrue(events, "intelligence.json 无事件，无法校验")
        self.assertIn("topic", events[0])

    def test_intelligence_score_exists_on_events(self):
        events = self.data.get("events") or []
        scores = (events[0].get("scores") or {})
        self.assertIn("intelligence_score", scores)

    def test_untopiced_events_would_be_falsely_grouped(self):
        """回归依据：确实存在多条 topic 为空的事件，故必须有非空守卫。"""
        events = self.data.get("events") or []
        untopiced = [e for e in events if not e.get("topic")]
        self.assertGreater(len(untopiced), 1, "无主题事件不足 2 条，守卫用例失去意义")


if __name__ == "__main__":
    unittest.main()
