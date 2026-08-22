#!/usr/bin/env python3
"""Inject the current release marker into index.html without changing page semantics."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
MANIFEST = ROOT / "release_manifest.json"
START = "<!--INSUREAI_RELEASE_MARKER_START-->"
END = "<!--INSUREAI_RELEASE_MARKER_END-->"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    marker = str(manifest.get("release_marker") or "")
    if not marker:
        raise SystemExit("release_marker missing")
    text = INDEX.read_text(encoding="utf-8")
    block = f'{START}<meta name="insureai-release-marker" content="{html.escape(marker, quote=True)}">{END}'
    if START in text and END in text:
        before, rest = text.split(START, 1)
        _, after = rest.split(END, 1)
        text = before + block + after
    else:
        text += "\n" + block + "\n"
    INDEX.write_text(text, encoding="utf-8")
    print(f"release marker injected: {marker}")


if __name__ == "__main__":
    main()
