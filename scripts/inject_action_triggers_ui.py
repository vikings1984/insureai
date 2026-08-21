from pathlib import Path

INDEX = Path('index.html')
TAG = '<script src="action-triggers-ui.js" defer></script>'
text = INDEX.read_text(encoding='utf-8')
if TAG not in text:
    marker = '</head>'
    if marker not in text:
        raise SystemExit('index.html has no </head> marker')
    INDEX.write_text(text.replace(marker, f'  {TAG}\n{marker}', 1), encoding='utf-8')
    print('Injected action trigger UI')
else:
    print('Action trigger UI already present')
