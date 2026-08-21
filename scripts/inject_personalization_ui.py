#!/usr/bin/env python3
from pathlib import Path

INDEX = Path("index.html")
TAGS = ['<script src="behavior_learning.js" defer></script>', '<script src="personalization-ui.js" defer></script>']
text = INDEX.read_text(encoding="utf-8")
missing = [tag for tag in TAGS if tag not in text]
if missing:
    marker = "</head>"
    if marker not in text:
        raise SystemExit("index.html has no </head> marker")
    injection = ''.join(f"  {tag}\n" for tag in missing)
    INDEX.write_text(text.replace(marker, injection + marker, 1), encoding="utf-8")
    print("Injected Personal Intelligence assets")
else:
    print("Personal Intelligence assets already present")
