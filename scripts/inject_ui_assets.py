#!/usr/bin/env python3
"""Inject feature UI assets and the release identity marker into index.html."""
from __future__ import annotations

import json
from pathlib import Path

INDEX = Path("index.html")
MANIFEST = Path("release_manifest.json")

TAGS = [
    '<script src="intelligence-ui.js" defer></script>',
    '<script src="behavior_learning.js" defer></script>',
    '<script src="personalization-ui.js" defer></script>',
    '<script src="trust-ui.js" defer></script>',
    '<script src="claim-evidence-ui.js" defer></script>',
    '<script src="temporal-ui.js" defer></script>',
    '<script src="decision-ui.js" defer></script>',
    '<script src="review-ui.js" defer></script>',
    '<script src="action-triggers-ui.js" defer></script>',
    '<script src="execution-readiness-ui.js" defer></script>',
    '<script src="owner-risk-ui.js" defer></script>',
]

text = INDEX.read_text(encoding="utf-8")
missing = [tag for tag in TAGS if tag not in text]
marker_value = "InsureAI"
if MANIFEST.exists():
    try:
        marker_value = str(json.loads(MANIFEST.read_text(encoding="utf-8")).get("release_marker") or marker_value)
    except (OSError, json.JSONDecodeError):
        pass
marker_tag = f'<meta name="insureai-release-marker" content="{marker_value}">'
marker_missing = marker_tag not in text

if missing or marker_missing:
    head_marker = "</head>"
    if head_marker not in text:
        raise SystemExit("index.html has no </head> marker")
    injection = "".join(f"  {tag}\n" for tag in missing)
    if marker_missing:
        injection += f"  {marker_tag}\n"
    INDEX.write_text(text.replace(head_marker, injection + head_marker, 1), encoding="utf-8")
    print(f"Injected {len(missing)} UI assets; release_marker={'yes' if marker_missing else 'existing'}")
else:
    print("All UI assets and release marker already present")
