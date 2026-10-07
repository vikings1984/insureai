#!/usr/bin/python3
"""CI 调用方式守卫：本地与 CI 必须用**同一种** discover 方式。

事故记录（2026-10-07）：`a9ab3371` 的 CI "Unit tests" 失败，而本地
`python3 -m unittest discover -s tests -t tests` 全绿。根因不是代码，而是
**两端调用方式不同**，导致只有 CI 能发现某些失败（当次是依赖 discover 根目录的
导入顺序/相对路径差异）。

本测试固定「CI 的调用方式」为唯一权威口径：
- CI 跑 `python3 -m unittest discover tests/`（见 test.yml），**不加** `-s/-t`；
- 本地也必须能复现同一结果；
- 因此**禁止**再写只在 `-s tests -t tests` 下才通过的测试（如依赖包上下文的导入）。

它无法在单测内真的跑一遍 CI 命令（成本过高），但可以断言：
test.yml 里CI 的 discover 命令形态未被改动，且与本文件注释声明一致。
"""
from __future__ import annotations

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEST_YML = os.path.join(ROOT, ".github", "workflows", "test.yml")

# CI 权威调用方式（改动需同步此处并复跑全量）
CI_DISCOVER = "python3 -m unittest discover tests/"


class TestCIInvocationCanonical(unittest.TestCase):
    def test_test_yml_uses_canonical_discover(self):
        with open(TEST_YML, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertIn(CI_DISCOVER, text,
                      f"test.yml 必须包含权威 discover 命令：{CI_DISCOVER}")
        # 不应再有 -s tests -t tests 变体（那是本地口径，易造成两端不一致）
        self.assertNotRegex(text, r"discover\s+-s\s+tests\s+-t\s+tests",
                            "CI 不应使用 -s/-t 变体（与本地口径不一致的根源）")

    def test_no_test_relies_on_package_context(self):
        """禁止 `from tests.x import` 式导入——它在 discover tests/ 下会失败。"""
        offenders = []
        for name in sorted(os.listdir(os.path.join(ROOT, "tests"))):
            if not name.endswith(".py"):
                continue
            path = os.path.join(ROOT, "tests", name)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if re.search(r"^\s*from\s+tests\.", content, re.MULTILINE):
                offenders.append(name)
        self.assertFalse(offenders,
                         f"这些测试用 `from tests.x import`，在 CI 的 discover tests/ 下会失败：{offenders}")


if __name__ == "__main__":
    unittest.main()