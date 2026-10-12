#!/usr/bin/env python3
"""
Keep `.zenodo.json` (the metadata Zenodo's GitHub integration reads from the
tagged commit) in step with VERSION and CHANGELOG.md.

    python scripts/ci/zenodo_metadata.py           # rewrite .zenodo.json
    python scripts/ci/zenodo_metadata.py --check   # fail when it is stale

Generated: ``title`` (the fixed title plus the version), ``version`` and
``description`` (the fixed general description, then the CHANGELOG section of
the version as HTML, like the release notes). Everything else in
`.zenodo.json` (creators, contributors, keywords, licence, ...) is kept as it
is and edited by hand.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_notes import section  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / '.zenodo.json'
REPOSITORY = 'https://github.com/digitaldesignunit/csc'

# The title and the general description of the first Zenodo record
# (10.5281/zenodo.20156667); every release keeps them and adds its version.
TITLE = ('Catalog of Second Chances (CSC) - Digital Database and '
         'Corresponding Interfaces for ReUse of Architectural Components')
GENERAL = (
    '<p>The <em>Catalog of Second Chances (CSC)</em> is a prototypical '
    'digital component database. It catalogs digital representations of '
    'uniquely identifiable architectural components for reuse. Furthermore, '
    'it provides corresponding interfaces and tools to leverage them via a '
    'backend REST-API, a web-frontend as well as a interface for direct '
    'interaction within Rhino Grasshopper.</p>')


# MARKDOWN (the subset CHANGELOG.md uses) -> HTML ------------------------------
def inline(text: str) -> str:
    """Escape, then **bold**, *emphasis*, `code` and [text](url)."""
    out, parts = [], re.split(r'(`[^`]*`)', text)
    for part in parts:
        if part.startswith('`') and part.endswith('`') and len(part) > 1:
            out.append(f'<code>{html.escape(part[1:-1])}</code>')
            continue
        part = html.escape(part, quote=False)
        part = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', part)
        part = re.sub(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])',
                      r'<em>\1</em>', part)
        part = re.sub(
            r'\[([^\]]+)\]\((https?://[^)\s]+)\)',
            lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>',
            part)
        out.append(part)
    return ''.join(out)


def to_html(markdown: str) -> str:
    """Headings (``#`` .. ``####``), bullet lists (``- `` items whose lines
    may wrap without indentation) and paragraphs; blank lines separate."""
    blocks, items, para = [], [], []

    def flush_para():
        if para:
            blocks.append(f'<p>{inline(" ".join(para))}</p>')
            para.clear()

    def flush_list():
        if items:
            body = ''.join(f'<li>{inline(" ".join(item))}</li>'
                           for item in items)
            blocks.append(f'<ul>{body}</ul>')
            items.clear()

    for raw in markdown.splitlines():
        line = raw.strip()
        heading = re.match(r'^(#{1,4})\s+(.*)$', line)
        if not line:
            flush_para()
            flush_list()
        elif heading:
            flush_para()
            flush_list()
            level = max(len(heading.group(1)), 3)   # below the h2
            blocks.append(f'<h{level}>{inline(heading.group(2))}</h{level}>')
        elif line.startswith('- '):
            flush_para()
            items.append([line[2:]])
        elif items:
            items[-1].append(line)                      # a wrapped item
        else:
            para.append(line)
    flush_para()
    flush_list()
    return ''.join(blocks)


# METADATA -------------------------------------------------------------------
def release_date(version: str) -> str:
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## \[{re.escape(version)}\]\s*-\s*(\S+)', text,
                      flags=re.MULTILINE)
    return match.group(1) if match else ''


def generated(version: str) -> dict:
    when = release_date(version)
    heading = f'Changes in v{version}' + (f' ({when})' if when else '')
    changelog = (f'<p>Full history: <a href="{REPOSITORY}/blob/v{version}/'
                 f'CHANGELOG.md">CHANGELOG.md</a></p>')
    return {
        'title': f'{TITLE} (v{version})',
        'version': version,
        'description': (GENERAL + f'<h2>{html.escape(heading)}</h2>'
                        + to_html(section(version)) + changelog),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true',
                        help='report a stale .zenodo.json, write nothing')
    args = parser.parse_args(argv)

    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    current = json.loads(TARGET.read_text(encoding='utf-8'))
    wanted = {**current, **generated(version)}
    if args.check:
        stale = [k for k in ('title', 'version', 'description')
                 if current.get(k) != wanted[k]]
        if stale:
            print(f'.zenodo.json is stale for {version} ({", ".join(stale)}): '
                  f'run python scripts/ci/zenodo_metadata.py')
            return 1
        print(f'ok: .zenodo.json matches {version}')
        return 0
    TARGET.write_text(json.dumps(wanted, indent=2, ensure_ascii=True) + '\n',
                      encoding='ascii', newline='\n')
    print(f'.zenodo.json written for {version}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
