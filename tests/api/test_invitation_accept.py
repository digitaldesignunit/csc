"""
S7 (decision 8.144 b--e): a dataset an admin has not reviewed invites only,
with one answer and one mail whether or not an address has an account; an
existing account joins by accepting at /invite; at most 50 invitation mails
per user per day; member e-mail addresses only for admins and moderators of a
reviewed dataset; resend needs the caller's current ``invite`` permission.
Mails are captured, never sent.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from apps.catalog.api import invitations as invitations_api
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from services import email_service
from support import seed_05_catalog

DS = 'dbu_zirkus'
NOT_VALID = 'This invitation code is not valid for this email address.'


@pytest.fixture
def mails(monkeypatch):
    sent = {'all': [], 'fail': set()}

    def send_mails(config, batch):
        batch = list(batch)
        out = []
        for mail in batch:
            sent['all'].append(mail)
            out.append('SMTPRecipientsRefused: {%r: (550, b"no")}' % mail.to
                       if mail.to in sent['fail'] else None)
        return out

    monkeypatch.setattr(email_service, 'send_mails', send_mails)
    return sent


@pytest.fixture
def world(api, db, auth_headers, member_headers, make_user, login, mails):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    moderator, moderator_id = member_headers({DS: ['moderator']})
    return {'api': api, 'db': db, 'mails': mails, 'moderator': moderator,
            'moderator_id': moderator_id, 'admin': auth_headers('admin'),
            'user': auth_headers('user'), 'make_user': make_user,
            'login': login}


def _unreview(world):
    world['db']['datasets'].update_one({'_id': DS},
                                       {'$set': {'reviewed': False}})


def _headers_of(world, name):
    """A fresh signed-in account ``name`` (address name@tu-darmstadt.de)."""
    user = world['make_user'](name)
    token = world['login'](name).json()['access_token']
    return {'Authorization': f'Bearer {token}'}, user['id']


def _invite(world, headers, emails, dataset=DS, roles=('contributor',)):
    body = {'emails': list(emails), 'roles': list(roles)}
    if dataset:
        body['dataset'] = dataset
    return world['api'].post('/invitations', json=body, headers=headers)


def _code_of(mail) -> str:
    return mail.text.split('invite?code=')[1].split()[0]


def _shape(mail):
    """A mail with the address and the code taken out."""
    text = mail.text.replace(mail.to, '<to>').replace(_code_of(mail), '<code>')
    return mail.subject, text, mail.reply_to


# UNREVIEWED DATASETS INVITE ONLY ---------------------------------------------
def test_an_unreviewed_dataset_answers_alike_for_every_address(world):
    _unreview(world)
    known = world['make_user']('carol')['username'] + '@tu-darmstadt.de'
    answer = _invite(world, world['moderator'],
                     [known, 'stranger@partner.example']).json()
    assert [(r['email'], r['result']) for r in answer] == [
        (known, 'invited'), ('stranger@partner.example', 'invited')]
    assert all('exists' not in str(r) for r in answer)
    # one mail each, the same words, the same kind of link
    first, second = world['mails']['all']
    assert {first.to, second.to} == {known, 'stranger@partner.example'}
    assert _shape(first)[1:] == _shape(second)[1:]
    assert _shape(first)[0] == _shape(second)[0]
    for mail in (first, second):
        assert re.search(r'/invite\?code=[A-Z2-7]{16}\b', mail.text)
        assert 'register' not in mail.text.lower().replace('registered', '')


def test_the_member_route_does_not_add_an_account_in_an_unreviewed_dataset(
        world):
    _unreview(world)
    api, db = world['api'], world['db']
    known_user = world['make_user']('carol')
    known = 'carol@tu-darmstadt.de'
    one = api.post(f'/datasets/{DS}/members', headers=world['moderator'],
                   json={'email': known, 'roles': ['reviewer']}).json()
    two = api.post(f'/datasets/{DS}/members', headers=world['moderator'],
                   json={'email': 'stranger@partner.example',
                         'roles': ['reviewer']}).json()
    for answer in (one, two):
        assert answer['result'] == 'invited' and 'user_id' not in answer
        assert answer['invitation']['dataset'] == DS
    assert set(one) == set(two)
    zirkus = db['datasets'].find_one({'_id': DS})
    assert all(m['user_id'] != known_user['id'] for m in zirkus['members'])
    first, second = world['mails']['all']
    assert _shape(first)[1:] == _shape(second)[1:]
    assert 'added' not in first.subject


def test_admins_and_reviewed_datasets_keep_exists_and_added(world):
    api = world['api']
    world['make_user']('carol')
    known = 'carol@tu-darmstadt.de'
    # a reviewed dataset: as before
    answer = _invite(world, world['moderator'], [known, 'new@partner.example'])
    assert [r['result'] for r in answer.json()] == ['exists', 'invited']
    _unreview(world)
    # an admin in an unreviewed dataset: as before
    answer = _invite(world, world['admin'], [known, 'new2@partner.example'])
    assert [r['result'] for r in answer.json()] == ['exists', 'invited']
    added = api.post(f'/datasets/{DS}/members', headers=world['admin'],
                     json={'email': known, 'roles': ['reviewer']}).json()
    assert added['result'] == 'added'


# ACCEPT ----------------------------------------------------------------------
def _issue(world, address, roles=('reviewer',)):
    """An invitation mailed to ``address`` (an unreviewed dataset invites
    existing accounts too)."""
    _unreview(world)
    before = len(world['mails']['all'])
    assert _invite(world, world['moderator'], [address],
                   roles=roles).status_code == 200
    return _code_of(world['mails']['all'][before])


def test_an_existing_account_accepts_with_its_own_address(world):
    api, db = world['api'], world['db']
    carol, carol_id = _headers_of(world, 'carol')
    code = _issue(world, 'carol@tu-darmstadt.de')
    preview = api.post('/invitations/preview', json={'code': code},
                       headers=carol)
    assert preview.status_code == 200, preview.text
    assert preview.json()['dataset'] == DS
    assert preview.json()['roles'] == ['reviewer']
    assert preview.json()['dataset_name']
    # nothing is granted by looking
    zirkus = db['datasets'].find_one({'_id': DS})
    assert all(m['user_id'] != carol_id for m in zirkus['members'])
    done = api.post('/invitations/accept', json={'code': code.lower()},
                    headers=carol)
    assert done.status_code == 200, done.text
    assert done.json()['roles'] == ['reviewer'] and done.json()['dataset'] == DS
    member = next(m for m in db['datasets'].find_one({'_id': DS})['members']
                  if m['user_id'] == carol_id)
    assert member['roles'] == ['reviewer']
    used = db['invitations'].find_one({'email': 'carol@tu-darmstadt.de'})
    assert used['used_by_user_id'] == carol_id and used['used_at']
    # single use
    again = api.post('/invitations/accept', json={'code': code}, headers=carol)
    assert again.status_code == 400 and 'used' in again.json()['detail']
    me = api.get('/users/me', headers=carol).json()
    assert [m['dataset'] for m in me['memberships']] == [DS]


def test_another_account_and_an_unknown_code_get_the_same_answer(world):
    api, db = world['api'], world['db']
    carol, _ = _headers_of(world, 'carol')
    dave, dave_id = _headers_of(world, 'dave')
    code = _issue(world, 'carol@tu-darmstadt.de')
    wrong = api.post('/invitations/accept', json={'code': code}, headers=dave)
    unknown = api.post('/invitations/accept',
                       json={'code': 'ABCDEFGHABCDEFGH'}, headers=dave)
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json() == unknown.json() == {'detail': NOT_VALID}
    for route in ('preview', 'accept'):
        other = api.post(f'/invitations/{route}', json={'code': code},
                         headers=dave)
        assert other.json() == {'detail': NOT_VALID}, route
    zirkus = db['datasets'].find_one({'_id': DS})
    assert all(m['user_id'] != dave_id for m in zirkus['members'])
    # the invitation is still open for the account it names
    assert api.post('/invitations/accept', json={'code': code},
                    headers=carol).status_code == 200


def test_an_anonymous_visitor_cannot_preview_or_accept(world):
    code = _issue(world, 'carol@tu-darmstadt.de')
    for route in ('preview', 'accept'):
        assert world['api'].post(f'/invitations/{route}',
                                 json={'code': code}).status_code == 401


def test_an_invitation_that_is_expired_or_revoked_cannot_be_accepted(world):
    api, db = world['api'], world['db']
    carol, _ = _headers_of(world, 'carol')
    code = _issue(world, 'carol@tu-darmstadt.de')
    db['invitations'].update_one({'email': 'carol@tu-darmstadt.de'},
                                 {'$set': {'expires_at': '2020-01-01T00:00:00Z'}})
    out = api.post('/invitations/accept', json={'code': code}, headers=carol)
    assert out.status_code == 400 and 'expired' in out.json()['detail']
    db['invitations'].update_one({'email': 'carol@tu-darmstadt.de'},
                                 {'$set': {'expires_at': '2999-01-01T00:00:00Z',
                                           'revoked_at': '2026-10-01T00:00:00Z'}})
    out = api.post('/invitations/accept', json={'code': code}, headers=carol)
    assert out.status_code == 400 and 'revoked' in out.json()['detail']


def test_the_code_is_not_a_short_guess(world):
    carol, _ = _headers_of(world, 'carol')
    assert world['api'].post('/invitations/accept', json={'code': 'A'},
                             headers=carol).status_code == 422


def test_accepting_is_limited_per_user(world):
    from limiter import limiter
    carol, _ = _headers_of(world, 'carol')
    limiter.reset()
    limiter.enabled = True              # the fixtures switch it off
    try:
        codes = [world['api'].post(
            '/invitations/accept', json={'code': 'ABCDEFGHABCDEFGH'},
            headers=carol).status_code for _ in range(31)]
        assert set(codes[:30]) == {400} and codes[30] == 429
    finally:
        limiter.enabled = False
        limiter.reset()


# RESEND NEEDS THE CURRENT PERMISSION -----------------------------------------
def test_a_demoted_moderator_cannot_resend_but_can_still_revoke(world):
    api, db = world['api'], world['db']
    made = _invite(world, world['moderator'], ['late@partner.example'])
    iid = made.json()[0]['invitation']['_id']
    db['datasets'].update_one(
        {'_id': DS, 'members.user_id': world['moderator_id']},
        {'$set': {'members.$.roles': ['contributor']}})
    assert api.post(f'/invitations/{iid}/resend',
                    headers=world['moderator']).status_code == 403
    # an admin may; so may a moderator of the dataset
    assert api.post(f'/invitations/{iid}/resend',
                    headers=world['admin']).status_code == 200
    # revoke stays with the creator
    assert api.delete(f'/invitations/{iid}',
                      headers=world['moderator']).status_code == 200


def test_a_moderator_of_another_dataset_and_a_user_cannot_resend(
        world, member_headers):
    other, _ = member_headers({'schoenes_neues_feld': ['moderator']})
    made = _invite(world, world['moderator'], ['late@partner.example'])
    iid = made.json()[0]['invitation']['_id']
    for headers in (other, world['user']):
        assert world['api'].post(f'/invitations/{iid}/resend',
                                 headers=headers).status_code == 403


def test_an_invitation_without_a_dataset_is_resent_by_an_admin_only(world):
    made = _invite(world, world['admin'], ['free@partner.example'],
                   dataset=None, roles=())
    iid = made.json()[0]['invitation']['_id']
    assert world['api'].post(f'/invitations/{iid}/resend',
                             headers=world['moderator']).status_code == 403
    assert world['api'].post(f'/invitations/{iid}/resend',
                             headers=world['admin']).status_code == 200


# THE DAILY CAP ---------------------------------------------------------------
def _log_mails(world, user_id, count, age=timedelta(minutes=5)):
    at = (datetime.now(timezone.utc) - age).isoformat().replace('+00:00', 'Z')
    world['db']['invitations'].insert_one({
        '_id': f'earlier-{user_id}-{count}-{age.total_seconds():.0f}',
        'email': 'earlier@partner.example', 'code_sha256': f'x{count}{age}',
        'dataset': DS, 'roles': ['contributor'],
        'created_by_user_id': user_id, 'created': at,
        'expires_at': '2999-01-01T00:00:00Z',
        'mail_log': [{'at': at, 'by': user_id}] * count})


def test_the_cap_is_50_invitation_mails_in_24_hours(world):
    cap = invitations_api.INVITATION_MAILS_PER_DAY
    assert cap == 50
    _log_mails(world, world['moderator_id'], cap - 2)
    ok = _invite(world, world['moderator'], ['a@partner.example',
                                             'b@partner.example'])
    assert ok.status_code == 200
    over = _invite(world, world['moderator'], ['c@partner.example'])
    assert over.status_code == 429
    assert '50' in over.json()['detail'] and 'try again' in \
        over.json()['detail'].lower()
    assert world['db']['invitations'].find_one(
        {'email': 'c@partner.example'}) is None
    assert len(world['mails']['all']) == 2


def test_mails_older_than_a_day_do_not_count(world):
    _log_mails(world, world['moderator_id'], 60, age=timedelta(hours=25))
    assert _invite(world, world['moderator'],
                   ['a@partner.example']).status_code == 200


def test_a_bulk_that_does_not_fit_sends_nothing(world):
    _log_mails(world, world['moderator_id'], 40)
    many = [f'p{i}@partner.example' for i in range(11)]
    assert _invite(world, world['moderator'], many).status_code == 429
    assert world['mails']['all'] == []
    assert _invite(world, world['moderator'], many[:10]).status_code == 200


def test_resends_and_member_by_email_count_and_an_admin_is_exempt(world):
    api = world['api']
    _log_mails(world, world['moderator_id'], 48)
    made = _invite(world, world['moderator'], ['a@partner.example'])   # 49
    iid = made.json()[0]['invitation']['_id']
    assert api.post(f'/invitations/{iid}/resend',
                    headers=world['moderator']).status_code == 200      # 50
    assert api.post(f'/invitations/{iid}/resend',
                    headers=world['moderator']).status_code == 429
    by_email = api.post(f'/datasets/{DS}/members', headers=world['moderator'],
                        json={'email': 'z@partner.example',
                              'roles': ['contributor']})
    assert by_email.status_code == 429
    # an admin has no cap
    _log_mails(world, 'an-admin-id', 80)
    for number in range(3):
        assert _invite(world, world['admin'],
                       [f'x{number}@partner.example']).status_code == 200


def test_the_cap_counts_the_sender_not_the_creator(world, member_headers):
    other, other_id = member_headers({DS: ['moderator']})
    made = _invite(world, world['moderator'], ['a@partner.example'])
    iid = made.json()[0]['invitation']['_id']
    _log_mails(world, other_id, 50)
    # the other moderator resends the first one's invitation: it counts for them
    assert world['api'].post(f'/invitations/{iid}/resend',
                             headers=other).status_code == 429
    # the creator is not affected
    assert world['api'].post(f'/invitations/{iid}/resend',
                             headers=world['moderator']).status_code == 200


def test_the_count_comes_from_the_database_not_from_memory(world):
    """A new request handler, a restart or the other worker sees the same
    count: nothing is kept in the process."""
    assert not hasattr(invitations_api, '_COUNTS')
    _invite(world, world['moderator'], ['a@partner.example'])
    doc = world['db']['invitations'].find_one({'email': 'a@partner.example'})
    assert [e['by'] for e in doc['mail_log']] == [world['moderator_id']]
    assert 'mail_log' not in str(_invite(
        world, world['moderator'], ['b@partner.example']).json())


# MEMBER E-MAIL ADDRESSES -----------------------------------------------------
def test_member_addresses_go_to_admins_and_moderators_of_a_reviewed_dataset(
        world):
    api = world['api']

    def emails(headers):
        view = api.get(f'/datasets/{DS}', headers=headers).json()
        return [m.get('email') for m in view['members']]

    assert all(emails(world['moderator']))          # reviewed: shown
    assert all(emails(world['admin']))
    _unreview(world)
    assert emails(world['moderator']) == [None] * len(
        api.get(f'/datasets/{DS}', headers=world['moderator']
                ).json()['members'])
    view = api.get(f'/datasets/{DS}', headers=world['moderator']).json()
    assert all(m.get('username') for m in view['members'])
    assert all(emails(world['admin']))              # an admin still sees them
    assert '@' not in api.get(f'/datasets/{DS}', headers=world['moderator']
                              ).text.replace('"@', '')


# LOGS HOLD NO ADDRESS --------------------------------------------------------
def test_a_failed_mail_logs_the_kind_and_no_address(world, capsys):
    world['mails']['fail'].add('secret.person@partner.example')
    out = _invite(world, world['moderator'], ['secret.person@partner.example'])
    assert out.json()[0]['result'] == 'mail_failed'
    iid = out.json()[0]['invitation']['_id']
    world['api'].post(f'/invitations/{iid}/resend', headers=world['moderator'])
    world['api'].post(f'/datasets/{DS}/members', headers=world['moderator'],
                      json={'email': 'secret.person@partner.example',
                            'roles': ['contributor']})
    world['make_user']('carol')
    world['mails']['fail'].add('carol@tu-darmstadt.de')
    world['api'].post(f'/datasets/{DS}/members', headers=world['moderator'],
                      json={'email': 'carol@tu-darmstadt.de',
                            'roles': ['contributor']})
    printed = capsys.readouterr().out
    assert 'SMTPRecipientsRefused' in printed
    assert 'secret.person' not in printed and 'carol' not in printed
    assert 'partner.example' not in printed
