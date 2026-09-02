"""站点页面与 E3 反馈契约测试。

覆盖两类此前真实踩到的缺陷：
1. 站内死链：`executive_home.html` 曾链接到不存在的 `./review-ui.html`（页面缺失，
   只有 JS 存在）。这里对全部根页面做内部链接可达性检查，杜绝回归。
2. UI ↔ 导入器标签漂移：Review UI 发出的 label / status 必须被 `p2_import_feedback`
   接受，而导入器的允许集又必须等于 `p2_intelligence`（schema 权威）。
   三者一旦漂移，用户反馈会在导入环节被**静默拒绝**，是最难发现的一类失效。
"""
import ast
import re
import unittest
from pathlib import Path

import p2_import_feedback
import p2_intelligence

ROOT = Path(__file__).resolve().parents[1]
_PAIR = re.compile(r"\[\s*'([a-z_]+)'\s*,\s*'[^']*'\s*\]")


def _js_codes(text: str, name: str) -> set[str]:
    """从形如 var LABELS = [['useful', '有用'], ...] 的 JS 数组中取出英文 code。"""
    match = re.search(r"var\s+" + name + r"\s*=\s*\[(.*?)\]\s*;", text, re.DOTALL)
    assert match, f"未在 review-ui.js 中找到 var {name}"
    return set(_PAIR.findall(match.group(1)))


def _intelligence_labels() -> set[str]:
    """从 p2_intelligence.record_feedback 的报错中解析权威 label 集，避免硬编码副本。"""
    try:
        p2_intelligence.record_feedback({}, "probe", "__invalid__")
    except ValueError as exc:
        match = re.search(r"label must be one of (\[.*\])", str(exc))
        assert match, f"无法从 record_feedback 报错中解析允许集：{exc}"
        return set(ast.literal_eval(match.group(1)))
    raise AssertionError("record_feedback 未拒绝非法 label，允许集无法确认")


class SiteLinkIntegrityTests(unittest.TestCase):
    def test_internal_links_resolve(self):
        pages = sorted(ROOT.glob("*.html"))
        self.assertTrue(pages, "根目录下未找到任何 html 页面")
        broken = []
        for page in pages:
            text = page.read_text(encoding="utf-8")
            for href in re.findall(r'href="(\./[^"#?]*)"', text):
                target = href[2:].split("#")[0].split("?")[0]
                if target and not (ROOT / target).exists():
                    broken.append((page.name, target))
        self.assertEqual([], broken, f"存在站内死链：{broken}")

    def test_review_ui_page_exists_and_wires_script(self):
        page = ROOT / "review-ui.html"
        self.assertTrue(page.exists(), "review-ui.html 缺失（executive_home 依赖它）")
        text = page.read_text(encoding="utf-8")
        self.assertIn('src="review-ui.js"', text)
        self.assertIn('name="github-repo"', text, "缺少 Issue 提交目标仓库声明")
        self.assertIn('name="review-limit"', text, "缺少本页展示条数声明")

    def test_review_ui_page_declares_mount_point(self):
        text = (ROOT / "review-ui.html").read_text(encoding="utf-8")
        self.assertIn('id="rv-mount"', text, "缺少 rv-mount 挂载点，队列将退化为主站顶部注入")

    def test_executive_home_links_to_review_page(self):
        text = (ROOT / "executive_home.html").read_text(encoding="utf-8")
        self.assertIn('href="./review-ui.html"', text)


class FeedbackContractTests(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / "review-ui.js").read_text(encoding="utf-8")

    def test_ui_labels_are_accepted_by_importer(self):
        ui = _js_codes(self.js, "LABELS")
        self.assertTrue(ui, "未能从 review-ui.js 解析出标签")
        self.assertEqual(set(), ui - p2_import_feedback.ALLOWED_LABELS,
                         "UI 发出的 label 会被导入器拒绝")

    def test_ui_statuses_are_accepted_by_importer(self):
        ui = _js_codes(self.js, "STATUSES")
        self.assertTrue(ui, "未能从 review-ui.js 解析出跟踪状态")
        self.assertEqual(set(), ui - p2_import_feedback.ALLOWED_STATUS,
                         "UI 发出的 status 会被导入器拒绝")

    def test_importer_labels_match_intelligence_authority(self):
        self.assertEqual(_intelligence_labels(), p2_import_feedback.ALLOWED_LABELS,
                         "导入器允许集与 p2_intelligence 不一致")

    def test_importer_covers_every_ui_label(self):
        """UI 上的每个可点标签都必须有入库通道，否则点了等于白点。"""
        ui = _js_codes(self.js, "LABELS")
        self.assertEqual(ui, p2_import_feedback.ALLOWED_LABELS,
                         "UI 标签集与导入器允许集应完全一致")


if __name__ == "__main__":
    unittest.main()
