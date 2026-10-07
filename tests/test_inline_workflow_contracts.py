#!/usr/bin/python3
"""把 test.yml 里**内联**的 workflow 契约断言纳入单测（此前完全无覆盖）。

根因（P1 收口）：`Daily collect workflow contract` 是 test.yml 里的内联 `python3 - <<PY`，
不在 tests/*.py，因此 `python3 -m unittest discover` **永远跑不到它**。P1-7 DAG 重构把
`Build owner-facing risk view` 迁进 dag.py 后，该内联断言因`text.index()` 找不到标记而
抛 ValueError → InsureAI Tests 从 6189ac8e 起连续 4 次 failure，而本地全量单测一直绿。

本测试直接从 test.yml 提取内联契约脚本并执行，确保「CI 契约」与「本地单测」同一套判定，
不再出现「本地绿 / CI 红」的盲区。
"""
from __future__ import annotations

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEST_YML = os.path.join(ROOT, ".github", "workflows", "test.yml")

# 内联契约块形如：
#   - name: Daily collect workflow contract
#     run: |
#       python3 - <<'PY'
#       ...python...
#       PY
_BLOCK_RE = re.compile(
    r"- name: (?P<name>[^\n]+)\n\s*run: \|\n(?P<body>(?:\s+[^\n]*\n)*?)"
    r"(?=\s*-\sname:|\Z)",
    re.MULTILINE,
)
_HEREDOC_RE = re.compile(r"python3 - <<'PY'\n(?P<code>.*?)\n\s*PY", re.DOTALL)


def _inline_contract_scripts() -> list[tuple[str, str]]:
    """返回 [(step_name, python_code)]，只提取含 heredoc 的内联契约。"""
    with open(TEST_YML, "r", encoding="utf-8") as f:
        text = f.read()
    out: list[tuple[str, str]] = []
    for m in _BLOCK_RE.finditer(text):
        body = m.group("body")
        h = _HEREDOC_RE.search("\n".join(l[10:] if len(l) > 10 else l
                                         for l in body.splitlines()))
        if h:
            out.append((m.group("name").strip(), h.group("code")))
    return out


class TestInlineWorkflowContracts(unittest.TestCase):
    def test_found_inline_contracts(self):
        scripts = _inline_contract_scripts()
        self.assertTrue(scripts, "未从 test.yml 提取到任何内联契约，解析逻辑可能失效")
        names = [n for n, _ in scripts]
        self.assertIn("Daily collect workflow contract", names)

    def test_inline_contracts_all_pass(self):
        """逐个执行内联契约脚本（含 daily-collect 步骤顺序断言）。"""
        failures: list[str] = []
        for name, code in _inline_contract_scripts():
            try:
                exec(compile(code, f"<test.yml:{name}>", "exec"), {"__name__": "__main__"})
            except Exception as e:  # noqa: BLE001
                failures.append(f"{name}: {type(e).__name__}: {e}")
        self.assertFalse(failures, "内联 workflow 契约失败：\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()