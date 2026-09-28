#!/usr/bin/env python3
"""
Print the CHANGELOG.md section of one version (the body of its GitHub Release).

    python scripts/ci/release_notes.py 0.5.1.0 > notes.md
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def section(version: str) -> str:
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    start = re.search(rf'^## \[{re.escape(version)}\].*$', text, flags=re.MULTILINE)
    if start is None:
        raise SystemExit(f'CHANGELOG.md has no section for {version}')
    rest = text[start.end():]
    end = re.search(r'^## \[', rest, flags=re.MULTILINE)
    return rest[:end.start() if end else len(rest)].strip() + '\n'


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.stdout.buffer.write(section(sys.argv[1]).encode('utf-8'))
