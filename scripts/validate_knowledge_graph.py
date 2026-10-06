#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识图谱校验（P1-7 DAG 节点）。

原为 daily-collect.yml 中的 heredoc ``python3 - <<'PY'`` 步骤；为纳入 DAG 编排
抽成独立脚本，校验逻辑与断言完全不变。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    graph = json.loads(Path(os.path.join(ROOT, "knowledge_graph.json")).read_text(encoding="utf-8"))
    assert graph["graph"] == "insureai_traceable_knowledge_graph"
    assert graph["stats"]["node_count"] == len(graph["nodes"])
    assert graph["stats"]["edge_count"] == len(graph["edges"])
    node_ids = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
        assert 0 <= edge["confidence"] <= 1
    assert graph["stats"]["node_count"] > 0, (
        "knowledge graph must not be empty when intelligence artifacts exist"
    )
    print("Knowledge graph valid:", graph["stats"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
