#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化质量门（P1-7 DAG 节点）。

原为 daily-collect.yml 中的内联 ``python3 -c "..."`` 步骤；为纳入 DAG 编排
（dag.py 以 ``python3 <script>`` 形式调度节点）抽成独立脚本，逻辑与断言完全不变。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from evaluation_metrics import build_metrics  # noqa: E402


def main() -> int:
    m = build_metrics()
    assert m["macro_quality"] >= 0.95, m
    assert m["production"]["claim_evidence_match_rate"] >= 0.6, m
    print(m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
