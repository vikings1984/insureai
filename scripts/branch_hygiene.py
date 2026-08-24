#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Identify remote branches merged into insureai as cleanup candidates.

Read-only: this script never deletes a branch. It reports branches whose tip is
reachable from origin/insureai (i.e. fully merged, no unique commits), excluding
the protected branches. Open-PR and workflow-reference checks remain human gates
per BRANCHING.md.
"""
from __future__ import annotations

import json
import subprocess

PROTECTED = {"insureai", "cloudflare/workers-autoconfig"}


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def merged_branches() -> list[str]:
    raw = _run(["git", "branch", "-r", "--merged", "origin/insureai"])
    candidates: list[str] = []
    for line in raw.splitlines():
        name = line.strip()
        if not name or not name.startswith("origin/") or " -> " in name:
            continue
        short = name.removeprefix("origin/")
        if short in PROTECTED:
            continue
        candidates.append(short)
    return sorted(candidates)


def main() -> None:
    candidates = merged_branches()
    print(json.dumps({"candidates": candidates, "count": len(candidates)}, ensure_ascii=False))


if __name__ == "__main__":
    main()