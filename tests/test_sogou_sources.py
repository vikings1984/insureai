#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_sogou_sources.py — 搜狗搜索通道解析单测（离线，fixture HTML）

覆盖：结果页解析 / 跳转页 JS 片段拼接 / 微信文章页 og 元数据提取。

运行：
    python3 -m unittest tests/test_sogou_sources.py -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import collect


SOGOU_RESULTS_FIXTURE = """
<div class="results">
  <div class="vrwrap">
    <h3><a href="/link?url=ABC123&amp;type=2&amp;query=%E4%BF%9D%E9%99%A9" title="忽略此属性">
      巨灾保险理赔启动!所有人已投保怎么赔</a></h3>
  </div>
  <div class="vrwrap">
    <h3><a uelog="page" href="/link?url=DEF456">
      <em>养老保险</em>个人养老金制度全面实施</a></h3>
  </div>
  <div class="vrwrap">
    <h3><a href="/link?url=GHI789">太短</a></h3>
  </div>
</div>
"""

SOGOU_REDIRECT_FIXTURE = """
<script>
    (new Image()).src = 'https://weixin.sogou.com/approve?uuid=x';
    setTimeout(function () {
        var url = '';
        url += 'https://mp.';
        url += 'weixin.qq.c';
        url += 'om/s?src=11';
        url += '&timestamp=1787017855&ver=6911';
        url += '&signature=abc123&new=1';
        url.replace("@", "");
        window.location.replace(url)
    },100);
</script>
"""

WECHAT_ARTICLE_FIXTURE = """
<html><head>
<meta property="og:title" content="治愈巨灾之殇:巨灾保险的三个试点样本">
<meta property="og:description" content="巨灾保险是治愈巨灾之殇的一颗药,从试点到扩面...">
<meta property="og:article:author" content="今日保">
</head><body>
<a id="js_name" class="wx_tap_link js_wx_tap_highlight weui-flex__item">今日保</a>
<script>var createTime = '2026-08-12 08:30'</script>
</body></html>
"""


class TestParseSogouResults(unittest.TestCase):
    """搜狗结果页 <h3><a> 解析"""

    def test_extracts_links_and_titles(self):
        out = collect.parse_sogou_results(SOGOU_RESULTS_FIXTURE)
        titles = [t for _, t in out]
        self.assertIn("巨灾保险理赔启动!所有人已投保怎么赔", titles)

    def test_highlight_tags_stripped(self):
        out = dict(collect.parse_sogou_results(SOGOU_RESULTS_FIXTURE))
        self.assertIn("养老保险个人养老金制度全面实施", out.values())

    def test_html_entities_unescaped_in_href(self):
        out = collect.parse_sogou_results(SOGOU_RESULTS_FIXTURE)
        hrefs = [h for h, _ in out]
        # &amp; 须还原为 &，空格转 %20（防 InvalidURL）
        self.assertTrue(any("&type=2" in h for h in hrefs))
        self.assertFalse(any(" " in h for h in hrefs))

    def test_short_title_filtered(self):
        out = collect.parse_sogou_results(SOGOU_RESULTS_FIXTURE)
        titles = [t for _, t in out]
        self.assertNotIn("太短", titles)


class _FakeOpener:
    """resolve_sogou_link 的网络替身：返回预置页面。"""

    def __init__(self, page):
        self.page = page
        self.calls = []

    def open(self, url, timeout=None):
        # resolve_sogou_link 传入的是 Request 对象，记录其 URL
        self.calls.append(getattr(url, "full_url", url))

        class _R:
            def __init__(self, data):
                self.data = data.encode("utf-8")

            def read(self):
                return self.data
        return _R(self.page)


class TestResolveSogouLink(unittest.TestCase):
    """跳转页 JS 片段拼接还原真实 URL"""

    def test_fragments_joined(self):
        opener = _FakeOpener(SOGOU_REDIRECT_FIXTURE)
        url = collect.resolve_sogou_link(opener, "/link?url=ABC123", "https://weixin.sogou.com/weixin?type=2")
        self.assertTrue(url.startswith("https://mp.weixin.qq.com/s?src=11"))
        self.assertIn("signature=abc123", url)

    def test_relative_href_prefixed(self):
        opener = _FakeOpener(SOGOU_REDIRECT_FIXTURE)
        collect.resolve_sogou_link(opener, "/link?url=ABC123", "ref")
        self.assertTrue(opener.calls[0].startswith("https://weixin.sogou.com/link?"))

    def test_absolute_href_kept(self):
        opener = _FakeOpener(SOGOU_REDIRECT_FIXTURE)
        collect.resolve_sogou_link(opener, "https://weixin.sogou.com/link?url=X", "ref")
        self.assertEqual(opener.calls[0], "https://weixin.sogou.com/link?url=X")

    def test_no_fragments_returns_empty(self):
        opener = _FakeOpener("<html>验证码页面，无跳转</html>")
        self.assertEqual(collect.resolve_sogou_link(opener, "/link?url=X", "ref"), "")


class TestParseWechatArticle(unittest.TestCase):
    """微信文章页 og 元数据提取"""

    def test_full_metadata(self):
        title, summary, account, date = collect.parse_wechat_article(WECHAT_ARTICLE_FIXTURE)
        self.assertEqual(title, "治愈巨灾之殇:巨灾保险的三个试点样本")
        self.assertTrue(summary.startswith("巨灾保险是治愈巨灾之殇"))
        self.assertEqual(account, "今日保")
        self.assertEqual(date, "2026-08-12")

    def test_empty_page(self):
        title, summary, account, date = collect.parse_wechat_article("")
        self.assertEqual((title, summary, account, date), ("", "", "", ""))

    def test_og_before_content_fallback(self):
        # content 在前 property 在后的写法也能命中
        page = '<meta content="反向顺序的标题" property="og:title">'
        t, _, _, _ = collect.parse_wechat_article(page)
        self.assertEqual(t, "反向顺序的标题")


if __name__ == "__main__":
    unittest.main()
