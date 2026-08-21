#!/usr/bin/env python3
"""Inject the static Daily Intelligence script into generated index.html."""
from pathlib import Path

INDEX = Path("index.html")
TAG = '<script src="intelligence-ui.js" defer></script>'
text = INDEX.read_text(encoding="utf-8")
if TAG not in text:
    marker = "</head>"
    if marker not in text:
        raise SystemExit("index.html has no </head> marker")
    text = text.replace(marker, f"  {TAG}\n{marker}", 1)
    INDEX.write_text(text, encoding="utf-8")
    print("Injected Daily Intelligence UI")
else:
    print("Daily Intelligence UI already present")
