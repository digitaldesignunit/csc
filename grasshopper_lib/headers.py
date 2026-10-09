"""The ``# venv:`` / ``# r:`` header of the script components and the checks
of a component file (decision 8.95 3; the library itself is the package
``csc_gh`` since decision 8.111, nothing is embedded any more).

``envs.json`` holds one pinned list; ``invoke gh-headers`` writes the header
lines of every component listed there (``--check`` only reports) and
``tests/grasshopper/test_headers.py`` fails when a header differs. The updater
reads the first ``Version:`` line of a component: ``check_version_line`` keeps
that line the component's own.

Pure standard library; runs on the dev machine, never in Rhino.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent
REPO_DIR = LIB_DIR.parent
SRC_DIR = REPO_DIR / 'grasshopper_userobjects_src'
ENVS_FILE = LIB_DIR / 'envs.json'

# The updater (backend ghinterface.get_source_version) takes the first line
# with "version", ":" or "=", then a number as the version of a script: that
# must be the Version: line of the component itself, not another line.
VERSION_RE = re.compile(r'version\s*[:=]\s*(\d+(?:\.\d+)?[a-zA-Z]?)')


def first_version_line(text):
    for number, line in enumerate(text.splitlines(), 1):
        if VERSION_RE.search(line.lower()):
            return number, line
    return None


def check_version_line(text, label='component'):
    found = first_version_line(text)
    if found is None:
        return ['%s: no Version: declaration' % label]
    number, line = found
    if not line.strip().lower().startswith('version'):
        return ['%s: the first version declaration is line %d (%r), not the '
                'Version: line of the component itself'
                % (label, number, line.strip()[:50])]
    return []


def component_files():
    return sorted(SRC_DIR.glob('DDU_CSC_*.py'))


def envs():
    return json.loads(ENVS_FILE.read_text(encoding='utf-8'))


def header_lines(component_name):
    """``# venv:`` and ``# r:`` lines of a component from ``envs.json``."""
    table = envs()
    spec = table['components'].get(component_name)
    if spec is None:
        return None
    pins = dict(table['extras'])
    pins.update(table['envs'][spec['env']])
    lines = ['# venv: %s' % spec['env']]
    for need in spec['needs']:
        # an empty pin is a bare name (charset_normalizer)
        lines.append('# r: %s==%s' % (need, pins[need]) if pins[need]
                     else '# r: %s' % need)
    return lines


_HEADER = re.compile(
    r"^# venv: .*\n(?:# r: .*\n)*(print\('ENV OK!'\)\n)?(?:# r: .*\n)*",
    re.M)


def header_text(text, component_name):
    """The component text with its venv / requirement header rewritten: the
    first ``# venv:`` line with the ``# r:`` lines around an optional
    ``print('ENV OK!')``; unchanged when the component is not listed in
    ``envs.json``. The output is the venv line, the ``# r:`` lines, then the
    print line."""
    lines = header_lines(component_name)
    if lines is None:
        return text
    match = _HEADER.search(text)
    if match is None:
        raise ValueError('%s: no # venv header' % component_name)
    block = '\n'.join(lines) + '\n'
    if match.group(1):
        block += match.group(1)
    return text[:match.start()] + block + text[match.end():]


def check_header(text, component_name):
    lines = header_lines(component_name)
    if lines is None:
        return []
    if header_text(text, component_name) != text:
        return ['%s: the # venv / # r: header differs from envs.json (run: '
                'invoke gh-headers)' % component_name]
    return []


def sync(write=True):
    """Set the header of every component; returns the changed file names
    (and writes them unless ``write`` is False)."""
    changed = []
    for path in component_files():
        raw = path.read_bytes().decode('utf-8')
        crlf = '\r\n' in raw            # keep the line ends of the file
        text = raw.replace('\r\n', '\n')
        new = header_text(text, path.stem[len('DDU_CSC_'):])
        if new != text:
            changed.append(path.name)
            if write:
                out = new.replace('\n', '\r\n') if crlf else new
                path.write_bytes(out.encode('utf-8'))
    return changed


def check():
    problems = []
    for path in component_files():
        text = path.read_text(encoding='utf-8')
        name = path.stem[len('DDU_CSC_'):]
        problems += check_version_line(text, path.name)
        problems += check_header(text, name)
    return problems


if __name__ == '__main__':
    import sys
    if '--check' in sys.argv:
        found = check()
        print('\n'.join(found) or 'headers are current')
        sys.exit(1 if found else 0)
    print('changed: %s' % (', '.join(sync()) or 'nothing'))
