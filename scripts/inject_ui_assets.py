#!/usr/bin/env python3
"""Inject all feature UI scripts into generated index.html in one pass.

Consolidates the formerly per-feature inject_*_ui.py scripts into a single
entry point. Order matters: behavior_learning.js must precede
personalization-ui.js (asserted by tests/test_behavior_learning.py).
"""
from pathlib import Path

INDEX = Path("index.html")

# Order mirrors the legacy workflow step order. Keep behavior_learning.js before
# personalization-ui.js.
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
if missing:
    marker = "</head>"
    if marker not in text:
        raise SystemExit("index.html has no </head> marker")
    injection = ''.join(f"  {tag}\n" for tag in missing)
    INDEX.write_text(text.replace(marker, injection + marker, 1), encoding="utf-8")
    print(f"Injected {len(missing)} UI assets")
else:
    print("All UI assets already present")