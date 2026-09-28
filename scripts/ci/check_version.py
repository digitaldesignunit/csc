#!/usr/bin/env python3
"""
Check that every place carrying the CSC product version agrees with VERSION.

    python scripts/ci/check_version.py            # consistency only
    python scripts/ci/check_version.py --tag v0.5.1.0   # also: the tag matches

Backend, web frontend and Grasshopper interface are released together under
one version (tag v<version>). The Grasshopper client version may lag behind:
it only moves when the UserObjects themselves changed (CSC_Session re-export).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = r'\d+\.\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?'


def version_key(version: str):
    """Order versions; a pre-release sorts before its final release."""
    core, _, pre = version.partition('-')
    return tuple(int(x) for x in core.split('.')), (0, pre) if pre else (1, '')


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def find(pattern: str, text: str, what: str, errors: list):
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        errors.append(f'{what}: version not found')
        return None
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', help='release tag to check, e.g. v0.5.1.0')
    args = parser.parse_args()

    errors: list = []
    version = read('VERSION').strip()
    if not re.fullmatch(VERSION_RE, version):
        print(f'VERSION: "{version}" is not MAJOR.MINOR.PATCH.HOTFIX[-pre]')
        return 1

    found = {
        'src/backend/csc_version.py': find(
            rf"^CSC_VERSION = '({VERSION_RE})'", read('src/backend/csc_version.py'),
            'csc_version.py', errors),
        'src/frontend/package.json': json.loads(
            read('src/frontend/package.json')).get('version'),
        'README.md': find(rf'^- \*\*CSC\*\*: ({VERSION_RE})', read('README.md'),
                          'README.md', errors),
    }
    lock = json.loads(read('src/frontend/package-lock.json'))
    found['src/frontend/package-lock.json'] = lock.get('version')
    found['src/frontend/package-lock.json (packages[""])'] = (
        lock.get('packages', {}).get('', {}).get('version'))

    for where, value in found.items():
        if value is not None and value != version:
            errors.append(f'{where}: {value} != VERSION {version}')

    gh = find(rf"^CSC_CLIENT = 'gh-userobjects/({VERSION_RE})'",
              read('grasshopper_userobjects_src/DDU_CSC_Session.py'),
              'DDU_CSC_Session.py', errors)
    if gh is not None and version_key(gh) > version_key(version):
        errors.append(f'DDU_CSC_Session.py: client {gh} is newer than VERSION {version}')

    if not re.search(rf'^## \[{re.escape(version)}\]', read('CHANGELOG.md'),
                     flags=re.MULTILINE):
        errors.append(f'CHANGELOG.md: no "## [{version}]" section')

    if args.tag is not None and args.tag != f'v{version}':
        errors.append(f'tag {args.tag} != v{version} (VERSION)')

    for error in errors:
        print(f'ERROR {error}')
    if not errors:
        print(f'ok: CSC {version}' + (f', GH client {gh}' if gh else ''))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
