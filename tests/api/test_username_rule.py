"""
The character set of a new username (decision 8.161): `^[a-z0-9][a-z0-9._-]{2,31}$`
after the input is stripped and lowercased. Names that exist stay as they are.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apps.catalog.models import USERNAME_PATTERN, RegisterPayload
from support import DEFAULT_PASSWORD

REPO = Path(__file__).resolve().parents[2]


def payload(username):
    return {'username': username, 'full_name': 'Sample', 'email': 'sample@stud.tu-darmstadt.de',
            'password': DEFAULT_PASSWORD}


@pytest.mark.parametrize('typed, stored', [
    ('abc', 'abc'), ('Sample.User', 'sample.user'), (' a-b_c ', 'a-b_c'),
    ('9lives', '9lives'), ('x' * 32, 'x' * 32),
])
def test_a_username_that_fits_is_lowercased(typed, stored):
    assert RegisterPayload(**payload(typed)).username == stored


@pytest.mark.parametrize('typed', [
    'ab', 'x' * 33, '.abc', '-abc', '_abc', 'a b c', 'a@b.de', 'a/b/c', 'ab\u00e4',
    '', '   ', 'abc\nxyz',
])
def test_a_username_that_does_not_fit_is_refused(typed):
    with pytest.raises(ValueError):
        RegisterPayload(**payload(typed))


def test_registration_answers_422_for_a_bad_name(api, db):
    response = api.post('/auth/register', json=payload('bad name!'))
    assert response.status_code == 422, response.text
    assert db['users'].count_documents({'email': 'sample@stud.tu-darmstadt.de'}) == 0
    ok = api.post('/auth/register', json=payload('Sample.User'))
    assert ok.status_code in (200, 201), ok.text
    assert db['users'].find_one({'username': 'sample.user'}) is not None


def _newest_local_dump():
    root = REPO / 'mongodb_collections_local'
    dumps = sorted(p for p in root.glob('*') if (p / 'csc.users.json').is_file()) \
        if root.is_dir() else []
    return dumps[-1] if dumps else None


def test_the_names_in_the_newest_local_dump_fit_the_rule():
    """Read at run time, nothing is copied into the repository (the dumps are
    not in it); skipped where there is none. A name that fails is reported by
    its position only."""
    dump = _newest_local_dump()
    if dump is None:
        pytest.skip('no local dump with a users export')
    from bson import json_util
    users = json_util.loads((dump / 'csc.users.json').read_text(encoding='utf-8'))
    assert users, 'the users export is empty'
    pattern = re.compile(USERNAME_PATTERN)
    misfits = [i for i, user in enumerate(users) if not pattern.fullmatch(user['username'])]
    assert not misfits, f'{len(misfits)} of {len(users)} usernames misfit, at positions {misfits}'
