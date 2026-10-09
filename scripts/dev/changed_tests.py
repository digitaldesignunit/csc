"""
Which tests belong to a set of changed paths (decision 8.114, ``invoke
test-changed``).

Pure mapping plus the git calls around it. Mapping:

* ``src/backend/apps/catalog/api/**``  -> ``tests/api``
* other ``src/backend/**``              -> ``tests/catalog`` and ``tests/api``
* ``grasshopper_lib/**``, ``grasshopper_userobjects_src/**`` ->
  ``tests/grasshopper``
* ``tests/**``: a ``test_*.py`` is itself; a helper or conftest in a folder
  means that folder; a file straight in ``tests/`` means all of them
* ``src/frontend/**`` -> lint and ``tsc``, plus the ``*.test.ts`` next to a
  changed ``lib`` file (or the changed test itself)
* ``pytest.ini``, ``requirements-dev.txt`` -> ``tests/api`` and
  ``tests/catalog``
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

API_PREFIX = 'src/backend/apps/catalog/api/'
GH_PREFIXES = ('grasshopper_lib/', 'grasshopper_userobjects_src/')
FRONTEND_PREFIX = 'src/frontend/'
TEST_FOLDERS = ('tests/api', 'tests/catalog', 'tests/grasshopper')


@dataclass
class Plan:
    pytest_targets: List[str] = field(default_factory=list)
    frontend: bool = False
    frontend_tests: List[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.pytest_targets or self.frontend)


def _is_under(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder + '/')


def _minimal(targets: Iterable[str]) -> List[str]:
    """Targets without those a listed folder already covers."""
    found = sorted(set(targets))
    return [t for t in found
            if not any(o != t and _is_under(t, o) for o in found)]


def frontend_test_for(path: str, exists=os.path.exists) -> Optional[str]:
    """The ``*.test.ts`` of a changed frontend file, relative to
    ``src/frontend`` --- the file itself when it is one."""
    rel = path[len(FRONTEND_PREFIX):]
    if not rel.startswith('lib/') or not rel.endswith('.ts'):
        return None
    if rel.endswith('.test.ts'):
        return rel
    sibling = rel[:-3] + '.test.ts'
    return sibling if exists(os.path.join(FRONTEND_PREFIX, sibling)) else None


def plan(paths: Iterable[str], exists=os.path.exists) -> Plan:
    targets: Set[str] = set()
    frontend_tests: Set[str] = set()
    frontend = False
    for raw in paths:
        path = raw.replace('\\', '/')
        if path.startswith(API_PREFIX):
            targets.add('tests/api')
        elif path.startswith('src/backend/'):
            targets.update(('tests/catalog', 'tests/api'))
        elif path.startswith(GH_PREFIXES):
            targets.add('tests/grasshopper')
        elif path.startswith('tests/'):
            parts = path.split('/')
            if path.endswith('.py') and parts[-1].startswith('test_'):
                if exists(path):         # a deleted test has nothing to run
                    targets.add(path)
            elif len(parts) > 2 and f'{parts[0]}/{parts[1]}' in TEST_FOLDERS:
                targets.add(f'{parts[0]}/{parts[1]}')
            elif len(parts) == 2:        # tests/conftest.py
                targets.update(TEST_FOLDERS)
        elif path in ('pytest.ini', 'requirements-dev.txt'):
            targets.update(('tests/api', 'tests/catalog'))
        elif path.startswith(FRONTEND_PREFIX):
            frontend = True
            related = frontend_test_for(path, exists)
            if related:
                frontend_tests.add(related)
    return Plan(pytest_targets=_minimal(targets), frontend=frontend,
                frontend_tests=sorted(frontend_tests))


def changed_paths(repo_dir: str, base: str = 'HEAD') -> List[str]:
    """Working tree and index against ``base``, plus untracked files."""
    def git(*args: str) -> List[str]:
        out = subprocess.run(['git', *args], cwd=repo_dir, check=True,
                             capture_output=True, text=True).stdout
        return [line for line in out.splitlines() if line]
    return sorted({*git('diff', '--name-only', base),
                   *git('ls-files', '--others', '--exclude-standard')})
