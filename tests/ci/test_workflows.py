"""
S15 (decision 8.144): every action in the workflows is pinned to a full commit
SHA with its tag as a comment, Dependabot watches the actions weekly, and the
release workflow writes to the repository in its publish job only.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / '.github' / 'workflows').glob('*.yml'))
USES = re.compile(r'^\s*-?\s*uses:\s*(?P<ref>\S+)(?P<rest>.*)$')
PINNED = re.compile(r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$')


def _lines(path):
    return path.read_text(encoding='utf-8').splitlines()


def test_there_are_workflows():
    assert {p.name for p in WORKFLOWS} == {'ci.yml', 'deploy.yml',
                                           'release.yml'}


def test_every_action_is_pinned_to_a_commit_with_its_tag_as_a_comment():
    seen = 0
    for path in WORKFLOWS:
        for number, line in enumerate(_lines(path), 1):
            match = USES.match(line)
            if not match or match['ref'].startswith('./'):
                continue          # a workflow of this repository
            seen += 1
            where = f'{path.name}:{number}'
            assert PINNED.match(match['ref']), f'{where} {match["ref"]}'
            assert re.match(r'^\s+#\s*v\d+(\.\d+)*\s*$', match['rest']), where
    assert seen >= 14


def test_the_same_action_is_pinned_to_one_commit_everywhere():
    commits: dict = {}
    for path in WORKFLOWS:
        for line in _lines(path):
            match = USES.match(line)
            if match and '@' in match['ref'] and not match['ref'].startswith('./'):
                name, sha = match['ref'].split('@')
                commits.setdefault(name, set()).add(sha)
    assert commits and all(len(v) == 1 for v in commits.values()), commits


def test_dependabot_watches_the_actions_weekly():
    text = (ROOT / '.github' / 'dependabot.yml').read_text(encoding='utf-8')
    assert re.search(r'^version: 2$', text, re.M)
    assert re.search(r'package-ecosystem:\s*github-actions', text)
    assert re.search(r'directory:\s*/\s*$', text, re.M)
    assert re.search(r'interval:\s*weekly', text)


def _job_block(lines, job):
    """The lines of one job of a workflow (indented two spaces under jobs:)."""
    start = lines.index(f'  {job}:')
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r'^  \S', lines[i]) or re.match(r'^\S', lines[i]):
            end = i
            break
    return lines[start:end]


def test_the_release_workflow_writes_only_in_the_publish_job():
    lines = _lines(ROOT / '.github' / 'workflows' / 'release.yml')
    top = lines.index('permissions:')
    assert lines[top + 1].strip() == 'contents: read'
    writers = [i for i, line in enumerate(lines)
               if re.match(r'^\s+contents:\s*write\b', line)]
    assert len(writers) == 1
    publish = _job_block(lines, 'publish')
    assert any(re.match(r'^\s+contents:\s*write\b', line) for line in publish)
    for job in ('ci', 'build', 'deploy'):
        assert not any('write' in line and 'contents' in line
                       for line in _job_block(lines, job)), job


def test_no_other_workflow_writes_to_the_repository():
    for name in ('ci.yml', 'deploy.yml'):
        text = (ROOT / '.github' / 'workflows' / name).read_text(
            encoding='utf-8')
        assert not re.search(r':\s*write\b', text), name
