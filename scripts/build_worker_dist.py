#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InsureAI Workers 精简构建（F-03）。

把前端静态资源 + 首屏分片打包进 dist/，剔除体积最大的分析产物
（19 个 JSON，合计约 30 MB），这些文件改由 GitHub Pages CDN 提供
（运行时由 data-cdn.js 把对应 fetch 路由到 Pages）。

dist/ 不进仓库（见 .gitignore）。

前置条件：intelligence_shards.py 已在仓库根生成分片
（deploy-cloudflare.yml 的 "Build intelligence shards" 步骤负责）。
本脚本只负责把分片从仓库根移入 dist/，并清理仓库根的分片。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # scripts/.. → 仓库根
DIST = ROOT / "dist"
SCRIPTS = ROOT / "scripts"

# 随构建复制到 dist 的前端资源（allowlist，避免把大 JSON / 生成物目录带进去）
COPY_DIRS = ["css", "js", "assets"]
COPY_ROOT_FILES = ["og-image.png", "sitemap.xml", "rss.xml", "release_manifest.json"]

# 运行时会 fetch、但被外置到 Pages CDN 的大文件（与 data-cdn.js EXTERNAL 一致）
EXTERNAL_JSON = {
    "intelligence.json", "knowledge_graph.json", "claims.json", "data.json",
    "research.json", "kg_viz.json", "canonical_events.json", "second_brain.json",
    "p2_personal_memory.json", "p2_daily_brief.json", "p2_state.json", "p2_alerts.json",
    "decisions_pending.json", "review_queue.json", "event_replays.json",
    "action_triggers.json", "owner_risk_view.json", "execution_readiness.json",
    "executive_terminal.json",
}

CDN_INJECT = '<script src="data-cdn.js"></script>'


def _rm_dist() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)


def _copy_frontend() -> None:
    # 顶层 HTML（不含 archive / benchmarks 等子目录里的旧副本）
    for html in ROOT.glob("*.html"):
        shutil.copy2(html, DIST / html.name)
    # 目录整体拷贝
    for d in COPY_DIRS:
        src = ROOT / d
        if src.is_dir():
            shutil.copytree(src, DIST / d)
    # 顶层 JS（浏览器脚本，含 data-cdn.js）
    for js in ROOT.glob("*.js"):
        shutil.copy2(js, DIST / js.name)
    # 顶层小文件（SEO / 标识）
    for f in COPY_ROOT_FILES:
        src = ROOT / f
        if src.exists():
            shutil.copy2(src, DIST / f)


def _move_shards() -> int:
    moved = 0
    for name in ("intelligence.summary.json", "intelligence.events.json"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, DIST / name)
            moved += 1
    for src in ROOT.glob("intelligence.detail.*.json"):
        shutil.copy2(src, DIST / src.name)
        moved += 1
    # 清理仓库根的分片（不入库，见 .gitignore）
    subprocess.run(
        [sys.executable, str(ROOT / "intelligence_shards.py"), "--clean"],
        check=False, capture_output=True,
    )
    return moved


def _inject_cdn_head() -> None:
    for html in DIST.glob("*.html"):
        text = html.read_text(encoding="utf-8")
        if "data-cdn.js" in text:
            continue
        if "<head>" in text:
            text = text.replace("<head>", "<head>\n  " + CDN_INJECT, 1)
        elif "<HEAD>" in text:
            text = text.replace("<HEAD>", "<HEAD>\n  " + CDN_INJECT, 1)
        else:
            # 无 <head>：插到最前
            text = CDN_INJECT + "\n" + text
        html.write_text(text, encoding="utf-8")


def _inject_ui_assets() -> None:
    # 在 dist 上运行现有注入脚本（注入 feature UI 标签 + release marker）
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "inject_ui_assets.py")],
        cwd=str(DIST), capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("inject_ui_assets 失败:", r.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    print(r.stdout.strip())


def _verify() -> None:
    idx = DIST / "index.html"
    assert idx.exists(), "dist/index.html 缺失"
    t = idx.read_text(encoding="utf-8")
    assert "data-cdn.js" in t, "data-cdn.js 未注入 dist/index.html"
    assert "insureai-release-marker" in t, "release marker 未注入 dist/index.html"
    # 外置文件不应出现在 dist
    leaked = [j.name for j in DIST.glob("*.json") if j.name in EXTERNAL_JSON]
    assert not leaked, f"外置文件泄漏进 dist: {leaked}"
    # 首屏分片应存在
    assert (DIST / "intelligence.summary.json").exists(), "首屏分片缺失"


def main() -> int:
    _rm_dist()
    _copy_frontend()
    moved = _move_shards()
    _inject_cdn_head()
    _inject_ui_assets()
    _verify()
    size_mb = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1_048_576
    print(
        f"Workers dist 构建完成: {size_mb:.2f} MB | 分片 {moved} 个 | "
        f"外置大文件 {len(EXTERNAL_JSON)} 个改走 Pages CDN"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
