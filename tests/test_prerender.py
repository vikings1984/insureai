#!/usr/bin/env python3
"""prerender.py 注入契约测试。

背景（2026-09-09 生产事故）：部分信源把换行二次编码成字面量 ``\\x0a``、
把 ``&`` 二次编码成 ``\\x26#39;``。inject() 此前把待注入内容直接作为
``re.sub`` 的**替换模板**传入，``\\x0a`` 被当成正则转义解析，抛出
``re.error: bad escape \\x``，导致 prerender 失败、整条采集流水线中断、
部署被质量门禁拦下。

这个测试锁住：注入内容一律按字面写入，不得被解释为转义模板。
"""
import os
import tempfile
import unittest

import prerender

START = "<!--SEO_FALLBACK_START-->"
END = "<!--SEO_FALLBACK_END-->"


class InjectTests(unittest.TestCase):
    def setUp(self):
        self._original = prerender.INDEX
        self._tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self._tmpdir, "index.html")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"<html><body>{START}old{END}</body></html>")
        prerender.INDEX = self.path

    def tearDown(self):
        prerender.INDEX = self._original

    def injected(self) -> str:
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_plain_content_is_injected(self):
        prerender.inject(START, END, "<p>hello</p>")
        self.assertIn(f"{START}<p>hello</p>{END}", self.injected())

    def test_backslash_sequences_are_written_literally(self):
        """\\x0a 一类的字面转义必须原样写入，不能被 re 解析。"""
        content = "<p>倒计时\\x0a\\x0a政策背景\\x26#39;交多少\\x26#39;</p>"
        prerender.inject(START, END, content)
        self.assertIn(content, self.injected())

    def test_group_reference_is_not_expanded(self):
        r"""内容里的 \1 \g<0> 同样不得被当作分组引用展开。"""
        content = r"<p>价格 \1 与 \g<0> 元</p>"
        prerender.inject(START, END, content)
        self.assertIn(content, self.injected())

    def test_missing_marker_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            prerender.inject("<!--NOPE_START-->", "<!--NOPE_END-->", "x")


if __name__ == "__main__":
    unittest.main()
