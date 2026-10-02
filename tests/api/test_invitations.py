"""
Invitations, registration by code, adding people by email, the admin user
list and user search (spec section 3.7, section 7.7; decisions 8.14,
8.20, 8.21; plan P3). Mails are captured, never sent.
"""

from __future__ import annotations

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from support import DEFAULT_PASSWORD, seed_05_catalog
from services import email_service


@pytest.fixture
def mails(monkeypatch):
    sent = {'invitations': [], 'added': []}

    def invitation(config, to_email, code, *args, **kwargs):
        sent['invitations'].append({'to': to_email, 'code': code})
        return True

    def added(config, to_email, *args, **kwargs):
        sent['added'].append({'to': to_email})
        return True

    monkeypatch.setattr(email_service, 'send_invitation_email', invitation)
    monkeypatch.setattr(email_service, 'send_member_added_email', added)
    return sent


@pytest.fixture
def world(api, db, auth_headers, member_headers, mails):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    moderator, moderator_id = member_headers({'dbu_zirkus': ['moderator']})
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    return {'api': api, 'db': db, 'mails': mails, 'moderator': moderator,
            'moderator_id': moderator_id, 'contributor': contributor,
            'user': auth_headers('user'), 'admin': auth_headers('admin')}


def _invite(api, headers, emails, dataset='dbu_zirkus', roles=('contributor',)):
    body = {'emails': list(emails), 'roles': list(roles)}
    if dataset:
        body['dataset'] = dataset
    return api.post('/invitations', json=body, headers=headers)


def _register(api, email, code=None, username='newbie'):
    body = {'username': username, 'full_name': 'New Person', 'email': email,
            'password': DEFAULT_PASSWORD}
    if code:
        body['code'] = code
    return api.post('/auth/register', json=body)


def test_who_invites_where(world):
    api = world['api']
    assert _invite(api, world['user'], ['a@partner.example']).status_code == 403
    assert _invite(api, world['contributor'],
                   ['a@partner.example']).status_code == 403
    assert _invite(api, world['moderator'], ['a@partner.example'],
                   dataset='schoenes_neues_feld').status_code == 403
    assert _invite(api, world['moderator'], ['a@partner.example'],
                   dataset=None, roles=()).status_code == 403
    assert _invite(api, world['admin'], ['b@partner.example'],
                   dataset=None, roles=()).status_code == 200
    mixed = _invite(api, world['moderator'],
                    ['A@Partner.example', 'alice@example.org']).json()
    assert [(r['email'], r['result']) for r in mixed] == [
        ('a@partner.example', 'invited'), ('alice@example.org', 'exists')]
    assert 'code_sha256' not in str(mixed)
    assert [m['to'] for m in world['mails']['invitations']] == [
        'b@partner.example', 'a@partner.example']


def test_registration_by_code(world):
    api, db, mails = world['api'], world['db'], world['mails']
    assert _register(api, 'ext@partner.example').status_code == 400
    _invite(api, world['moderator'], ['ext@partner.example'])
    code = mails['invitations'][-1]['code']
    assert len(code) == 16
    assert _register(api, 'other@partner.example', code).status_code == 400
    done = _register(api, 'ext@partner.example', code.lower())
    assert done.status_code == 201, done.text
    user = db['users'].find_one({'email': 'ext@partner.example'})
    assert user['email_verified'] is True and user['invitation_id']
    zirkus = db['datasets'].find_one({'_id': 'dbu_zirkus'})
    assert {'user_id': user['_id'], 'roles': ['contributor']}.items() <= {
        **next(m for m in zirkus['members']
               if m['user_id'] == user['_id'])}.items()
    login = api.post('/auth/token', data={'username': 'newbie',
                                          'password': DEFAULT_PASSWORD})
    assert login.status_code == 200
    again = _register(api, 'ext@partner.example', code, username='twice')
    assert again.status_code == 400 and 'used' in again.text

    # open domains need no code
    assert _register(api, 'x@stud.tu-darmstadt.de',
                     username='student').status_code == 201


def test_revoke_and_expiry(world, monkeypatch):
    api, db, mails = world['api'], world['db'], world['mails']
    invited = _invite(api, world['moderator'], ['late@partner.example']).json()
    iid = invited[0]['invitation']['_id']
    code = mails['invitations'][-1]['code']
    assert api.delete(f'/invitations/{iid}',
                      headers=world['contributor']).status_code == 403
    revoked = api.delete(f'/invitations/{iid}', headers=world['moderator'])
    assert revoked.json()['state'] == 'revoked'
    assert 'revoked' in _register(api, 'late@partner.example', code).text
    assert api.delete(f'/invitations/{iid}',
                      headers=world['admin']).status_code == 409

    _invite(api, world['moderator'], ['old@partner.example'])
    db['invitations'].update_one({'email': 'old@partner.example'},
                                 {'$set': {'expires_at': '2020-01-01T00:00:00Z'}})
    code = mails['invitations'][-1]['code']
    assert 'expired' in _register(api, 'old@partner.example', code).text

    def states(headers, **params):
        response = api.get('/invitations', params=params, headers=headers)
        return response.status_code, [i['state'] for i in response.json()] \
            if response.status_code == 200 else None
    assert states(world['user'])[0] == 403
    assert sorted(states(world['moderator'])[1]) == ['expired', 'revoked']
    assert states(world['admin'], state='expired')[1] == ['expired']

    monkeypatch.setenv('CSC_OPEN_REGISTRATION_DOMAINS', 'partner.example')
    assert _register(api, 'free@partner.example',
                     username='free').status_code == 201


def test_member_editor_by_email(world):
    api, db, mails = world['api'], world['db'], world['mails']
    body = {'email': 'Alice@Example.org', 'roles': ['reviewer']}
    assert api.post('/datasets/dbu_zirkus/members', json=body,
                    headers=world['contributor']).status_code == 403
    added = api.post('/datasets/dbu_zirkus/members', json=body,
                     headers=world['moderator']).json()
    assert (added['result'], added['user_id']) == ('added', 'u-alice')
    assert mails['added'] == [{'to': 'alice@example.org'}]
    zirkus = db['datasets'].find_one({'_id': 'dbu_zirkus'})
    assert next(m for m in zirkus['members']
                if m['user_id'] == 'u-alice')['roles'] == ['reviewer']
    invited = api.post('/datasets/dbu_zirkus/members',
                       json={'email': 'student@stud.tu-darmstadt.de',
                             'roles': ['contributor']},
                       headers=world['moderator']).json()
    assert invited['result'] == 'invited'
    assert invited['invitation']['dataset'] == 'dbu_zirkus'


def test_admin_user_list_and_search(world):
    api = world['api']

    def names(**params):
        response = api.get('/users', params=params, headers=world['admin'])
        assert response.status_code == 200, response.text
        return {u['username'] for u in response.json()}

    assert api.get('/users', headers=world['moderator']).status_code == 403
    rows = api.get('/users', headers=world['admin']).json()
    mod = next(u for u in rows if u['_id'] == world['moderator_id'])
    assert mod['memberships'] == [{'dataset': 'dbu_zirkus',
                                   'roles': ['moderator']}]
    assert 'alice' not in names(dataset='dbu_zirkus')
    assert names(dataset='dbu_zirkus', dataset_role='moderator') == {
        mod['username']}
    assert 'alice' in names(no_dataset=True)
    assert names(role='admin') >= {'admin'}
    assert 'ali' in str(names(q='ALI'))

    search = api.get('/users/search', params={'q': 'ali'},
                     headers=world['admin']).json()
    assert [u['username'] for u in search] == ['alice']
    assert api.get('/users/search', params={'q': 'ali'},
                   headers=world['moderator']).status_code == 403
