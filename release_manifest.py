#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a truthful release manifest and publishable release identity marker."""
from __future__ import annotations
import html, json, os, re
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent; OUTPUT=ROOT/"release_manifest.json"; INDEX=ROOT/"index.html"
START="<!--INSUREAI_RELEASE_MARKER_START-->"; END="<!--INSUREAI_RELEASE_MARKER_END-->"

def build_manifest(*, source_commit: str, site_url: str, quality_passed: bool=True) -> dict:
    source_commit=source_commit or "unknown"
    return {"version":1,"source_commit":source_commit,"release_marker":f"insureai:{source_commit}","release_channel":"github_pages","site_url":site_url,"quality_status":"passed" if quality_passed else "failed","deployment_status":"pending","deployment_verified":False,"deployment_note":"发布前质量门禁通过不代表生产站点已经完成部署与验收。","generated_at":datetime.now(timezone.utc).isoformat()}

def _inject_release_marker(marker: str) -> None:
    if not INDEX.exists(): return
    text=INDEX.read_text(encoding="utf-8")
    block=f'{START}<meta name="insureai-release-marker" content="{html.escape(marker, quote=True)}">{END}'
    pattern=re.compile(re.escape(START)+r".*?"+re.escape(END),re.S)
    text=pattern.sub(block,text) if pattern.search(text) else text+"\n"+block+"\n"
    INDEX.write_text(text,encoding="utf-8")

def main():
    manifest=build_manifest(source_commit=os.environ.get("GITHUB_SHA","unknown"),site_url=os.environ.get("SITE_URL",""),quality_passed=True)
    OUTPUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    _inject_release_marker(manifest["release_marker"])
    print(json.dumps(manifest,ensure_ascii=False))
if __name__=="__main__": main()
