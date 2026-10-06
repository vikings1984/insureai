"""P1-4 Human Review State Machine：人工复核状态机回归。

覆盖：
  - 合法转移链路 pending → assigned → in_review → approved → resolved
  - 非法转移被拒且不改变状态（fail-closed）
  - resolved 为终态，不可再转移
  - 未知状态 / 缺失条目被拒绝
  - 审计流（from/to/actor/reason/at）完整记录
  - sync_items：每日重建队列时已有状态与历史被继承，仅新项为 pending
  - load/save 往返、items_with_status / approved_reviews 查询
"""
import json
import os
import shutil
import tempfile
import unittest

import review_state


class _TmpState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "review_state.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestTransitions(_TmpState):
    def test_happy_path(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        for to in ("assigned", "in_review", "approved", "resolved"):
            ok, err = review_state.transition(state, "evt1", to, actor="vikings", reason="step")
            self.assertTrue(ok, f"{to} should be allowed, got {err}")
        self.assertEqual(review_state.status_of(state, "evt1"), "resolved")
        self.assertEqual(len(review_state.history_of(state, "evt1")), 4)

    def test_illegal_transition_refused_and_state_unchanged(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        # pending 不能直接跳到 approved
        ok, err = review_state.transition(state, "evt1", "approved")
        self.assertFalse(ok)
        self.assertIn("illegal_transition", err)
        self.assertEqual(review_state.status_of(state, "evt1"), "pending")
        self.assertEqual(review_state.history_of(state, "evt1"), [])

    def test_terminal_state_cannot_transition(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        for to in ("assigned", "in_review", "approved", "resolved"):
            review_state.transition(state, "evt1", to)
        ok, err = review_state.transition(state, "evt1", "in_review")
        self.assertFalse(ok)
        self.assertIn("illegal_transition", err)
        self.assertEqual(review_state.status_of(state, "evt1"), "resolved")

    def test_approved_can_reopen_and_resolved_after(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        review_state.transition(state, "evt1", "in_review")
        review_state.transition(state, "evt1", "approved")
        ok, _ = review_state.transition(state, "evt1", "in_review")  # 纠错重开
        self.assertTrue(ok)
        # 重开回到 in_review 后必须先裁决，才能归档为 resolved（in_review 不可直达 resolved）
        self.assertFalse(review_state.transition(state, "evt1", "resolved")[0])
        ok, _ = review_state.transition(state, "evt1", "approved")
        self.assertTrue(ok)
        ok, _ = review_state.transition(state, "evt1", "resolved")
        self.assertTrue(ok)

    def test_unknown_state_and_missing_item(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        self.assertFalse(review_state.transition(state, "evt1", "bogus")[0])
        self.assertFalse(review_state.transition(state, "nope", "assigned")[0])
        self.assertFalse(review_state.transition(state, "", "assigned")[0])

    def test_audit_trail_fields(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        review_state.transition(state, "evt1", "assigned", actor="alice", reason="pick up")
        h = review_state.history_of(state, "evt1")[0]
        self.assertEqual(h["from"], "pending")
        self.assertEqual(h["to"], "assigned")
        self.assertEqual(h["actor"], "alice")
        self.assertEqual(h["reason"], "pick up")
        self.assertTrue(h["at"])

    def test_can_transition_table(self):
        self.assertTrue(review_state.can_transition("pending", "assigned"))
        self.assertFalse(review_state.can_transition("pending", "approved"))
        self.assertFalse(review_state.can_transition("resolved", "pending"))
        self.assertFalse(review_state.can_transition("bogus", "pending"))


class TestSyncAndPersist(_TmpState):
    def test_sync_preserves_existing_status_and_history(self):
        # 先建立：evt1 已裁决 approved
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        review_state.transition(state, "evt1", "in_review", actor="a")
        review_state.transition(state, "evt1", "approved", actor="a")
        review_state.save_state(state, self.path)

        # 次日队列重建：evt1 仍在队列 + 新项 evt2
        items = [{"event_id": "evt1", "title": "old"}, {"event_id": "evt2", "title": "new"}]
        loaded = review_state.load_state(self.path)
        review_state.sync_items(loaded, items)
        self.assertEqual(items[0]["status"], "approved")   # 继承，不被覆盖
        self.assertEqual(items[1]["status"], "pending")    # 新项
        self.assertEqual(review_state.history_of(loaded, "evt1")[-1]["to"], "approved")

    def test_sync_backfills_status_on_item(self):
        state = review_state.load_state(self.path)
        items = [{"event_id": "evt9"}]
        review_state.sync_items(state, items)
        self.assertEqual(items[0]["status"], "pending")
        self.assertIn("review_updated_at", items[0])

    def test_load_save_roundtrip(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        review_state.transition(state, "evt1", "assigned", actor="bob")
        review_state.save_state(state, self.path)
        again = review_state.load_state(self.path)
        self.assertEqual(review_state.status_of(again, "evt1"), "assigned")
        self.assertEqual(len(review_state.history_of(again, "evt1")), 1)

    def test_load_missing_or_corrupt_returns_empty(self):
        self.assertEqual(review_state.load_state(os.path.join(self.tmp, "nope.json"))["items"], {})
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(review_state.load_state(bad)["items"], {})

    def test_queries(self):
        state = review_state.new_state()
        state["items"]["a"] = review_state.init_item()
        state["items"]["b"] = review_state.init_item()
        review_state.transition(state, "a", "in_review")
        review_state.transition(state, "a", "approved")
        self.assertIn("a", review_state.approved_reviews(state))
        self.assertNotIn("b", review_state.approved_reviews(state))
        self.assertIn("b", review_state.items_with_status(state, "pending"))

    def test_apply_transition_only_saves_on_success(self):
        state = review_state.new_state()
        state["items"]["evt1"] = review_state.init_item()
        review_state.save_state(state, self.path)
        ok, err = review_state.apply_transition("evt1", "approved", path=self.path)
        self.assertFalse(ok)
        self.assertIn("illegal_transition", err)
        self.assertEqual(review_state.load_state(self.path)["items"]["evt1"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
