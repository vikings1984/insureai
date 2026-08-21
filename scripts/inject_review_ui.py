#!/usr/bin/env python3
from pathlib import Path

INDEX = Path('index.html')
TAG = '<script src="review-ui.js" defer></script>'
text = INDEX.read_text(encoding='utf-8')
if TAG not in text:
    marker = '</head>'
    if marker not in text:
        raise SystemExit('index.html has no </head> marker')
    INDEX.write_text(text.replace(marker, f'  {TAG}\n{marker}', 1), encoding='utf-8')
    print('Injected review queue UI')
else:
    print('Review queue UI already present')
