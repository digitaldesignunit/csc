#!/usr/bin/env python3
"""
The pure parts of the release preparation (``invoke release-prep``,
``invoke bump-version --gh``); standard library only.

* ``changelog_section`` / ``section_is_empty``: the CHANGELOG section of a
  version and whether it holds anything to release.
* ``set_changelog_date``: ``## [<version>] - unreleased`` becomes the date,
  the file's line endings kept; a date that is already set is left alone.
* ``gh_client_update``: the Grasshopper client version in DDU_CSC_Session.py
  moves only when it is not the new version already; then ``CSC_CLIENT`` and
  the ``Version: <yymmdd>`` header change together (the header date has to
  keep matching the exported ``.ghuser``).
"""

from __future__ import annotations

import datetime
import re
from typing import Optional, Tuple

DATE_RE = r'\d{4}-\d{2}-\d{2}'

# the files a release preparation changes (bump-version and release-prep), by
# name, for the commit the next step asks for (no `git add -A`)
RELEASE_FILES = (
    'CHANGELOG.md',
    '.zenodo.json',
    'VERSION',
    'src/backend/csc_version.py',
    'src/frontend/package.json',
    'src/frontend/package-lock.json',
    'README.md',
)
# and with --gh, when the Grasshopper client version moved
GH_RELEASE_FILES = (
    'grasshopper_userobjects_src/DDU_CSC_Session.py',
)


def next_steps(version: str) -> str:
    """The text release-prep prints when it is done: the commit by file name,
    then the PR and the tag."""
    files = ' '.join(RELEASE_FILES)
    return (
        f'release-prep: v{version} is ready. Next, by you:\n'
        f'  1. git add {files}\n'
        f'     (with bump-version --gh also {" ".join(GH_RELEASE_FILES)} and the\n'
        f'     re-exported .ghuser / XML), then git commit\n'
        f'  2. invoke test-release, then open the PR into main and wait for CI\n'
        f'  3. after the merge: git tag v{version} && git push origin v{version}')


def _heading(version: str) -> str:
    return rf'^## \[{re.escape(version)}\][^\r\n]*'


def changelog_section(text: str, version: str) -> Optional[str]:
    """The body of the section of ``version`` (without its heading), or None
    when the CHANGELOG has no such section."""
    start = re.search(_heading(version), text, flags=re.MULTILINE)
    if start is None:
        return None
    rest = text[start.end():]
    end = re.search(r'^## \[', rest, flags=re.MULTILINE)
    return rest[:end.start() if end else len(rest)]


def section_is_empty(body: Optional[str]) -> bool:
    """A section says nothing when it has no line besides blanks and the
    ``###`` sub-headings."""
    if body is None:
        return True
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('###'):
            return False
    return True


def set_changelog_date(text: str, version: str, date: str
                       ) -> Tuple[str, str]:
    """``(new_text, state)``. ``state``: ``dated`` (unreleased replaced by
    ``date``), ``already`` (the heading has a date: nothing changes, whatever
    the date) or ``missing`` (no section). The line endings are untouched:
    only the text after the version in the heading line is replaced."""
    datetime.date.fromisoformat(date)                 # ValueError if not a date
    match = re.search(_heading(version), text, flags=re.MULTILINE)
    if match is None:
        return text, 'missing'
    heading = match.group(0)
    if re.search(rf'\] - {DATE_RE}\s*$', heading):
        return text, 'already'
    if not re.search(r'\] - unreleased\s*$', heading):
        return text, 'missing'
    done = re.sub(r'unreleased(\s*)$', rf'{date}\1', heading)
    return text[:match.start()] + done + text[match.end():], 'dated'


def existing_date(text: str, version: str) -> Optional[str]:
    """The date in the heading of ``version``, or None."""
    match = re.search(_heading(version), text, flags=re.MULTILINE)
    if match is None:
        return None
    found = re.search(rf'\] - ({DATE_RE})\s*$', match.group(0))
    return found.group(1) if found else None


def gh_client_update(text: str, version: str, today: datetime.date
                     ) -> Tuple[str, bool]:
    """``(new_text, changed)``: the Session source with the client version of
    ``version``. When ``CSC_CLIENT`` already is ``gh-userobjects/<version>``
    nothing changes (neither it nor the ``Version:`` header). Else both are
    rewritten: the client, and the header to ``today`` as ``yymmdd``. A source
    without either line is an error."""
    client = re.search(r"^CSC_CLIENT = 'gh-userobjects/([^']*)'", text,
                       flags=re.MULTILINE)
    header = re.search(r'^Version: \d+(\.\d+)?[a-z]?(?=\r?$)', text,
                       flags=re.MULTILINE)
    if client is None:
        raise ValueError('CSC_CLIENT line not found')
    if client.group(1) == version:
        return text, False
    if header is None:
        raise ValueError('Version: header not found')
    out = (text[:client.start()] + f"CSC_CLIENT = 'gh-userobjects/{version}'"
           + text[client.end():])
    header = re.search(r'^Version: \d+(\.\d+)?[a-z]?(?=\r?$)', out,
                       flags=re.MULTILINE)
    out = out[:header.start()] + f'Version: {today:%y%m%d}' + out[header.end():]
    return out, True
