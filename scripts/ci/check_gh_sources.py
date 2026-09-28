#!/usr/bin/env python3
"""
Check that changed Grasshopper component sources were released properly.

    python scripts/ci/check_gh_sources.py --base origin/main

For every file in grasshopper_userobjects_src/ that changed since --base:

- its ``Version:`` declaration must have increased — CSC_Update compares these
  to decide which UserObjects a user needs;
- its compiled UserObject (grasshopper_userobjects/<name>.ghuser) and XML
  export (grasshopper_userobjects_xml/<name>.xml) must have changed too — they
  are exported by hand in Rhino, and a forgotten export ships stale code.

Without a usable --base (first push of a branch) the check is skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath

SRC_DIR = 'grasshopper_userobjects_src'
VERSION_RE = re.compile(r'version\s*[:=]\s*(\d+)(?:\.(\d+))?([a-zA-Z]?)',
                        re.IGNORECASE)


def git(*args: str) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True
                          ).stdout.decode('utf-8', 'replace')


def source_version(text: str):
    """Same rule as the backend's get_source_version: first declaration."""
    for line in text.splitlines():
        match = VERSION_RE.search(line)
        if match:
            major, minor, letter = match.groups()
            return int(major), int(minor or 0), letter.lower()
    return None


def show(ref: str, path: str):
    try:
        return git('show', f'{ref}:{path}')
    except subprocess.CalledProcessError:
        return None  # file did not exist at ref


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True, help='git ref to compare with')
    args = parser.parse_args()

    try:
        git('rev-parse', '--verify', f'{args.base}^{{commit}}')
    except subprocess.CalledProcessError:
        print(f'skip: base {args.base!r} is not a commit here')
        return 0

    # merge base -> working tree: in CI that is the pushed commit; locally it
    # also covers uncommitted work, so the check can run before committing
    base = git('merge-base', args.base, 'HEAD').strip()
    changed = set(git('diff', '--name-only', base).split())
    tracked = set(git('ls-files').split())
    errors, notes = [], []

    for path in sorted(p for p in changed if p.startswith(SRC_DIR + '/')):
        name = PurePosixPath(path).stem
        if not os.path.exists(path):
            notes.append(f'{name}: removed')
            continue
        # Rhino's editor saves Windows-1252; Version lines are ASCII (as in
        # the backend's get_source_version, decode tolerantly)
        with open(path, 'rb') as handle:
            new = source_version(handle.read().decode('utf-8', 'replace'))
        old_text = show(base, path)
        old = source_version(old_text) if old_text is not None else None
        if new is None:
            errors.append(f'{path}: no "Version:" declaration')
        elif old is not None and new <= old:
            errors.append(f'{path}: Version not increased ({old} -> {new})')
        for companion in (f'grasshopper_userobjects/{name}.ghuser',
                          f'grasshopper_userobjects_xml/{name}.xml'):
            if companion in tracked and companion not in changed:
                errors.append(f'{companion}: not re-exported although '
                              f'{path} changed')
            elif companion not in tracked:
                notes.append(f'{name}: no {companion} (source only)')

    for note in notes:
        print(f'note  {note}')
    for error in errors:
        print(f'ERROR {error}')
    if not errors:
        print(f'ok: Grasshopper sources consistent with {args.base}')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
