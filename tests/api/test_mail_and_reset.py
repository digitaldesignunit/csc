"""
Mail and password reset (decision 8.124): one template for the four mails,
a visible send failure with Resend, a self-service password reset with a
single-use token, and tokens that die with a password change. Mails are
captured (``send_mails`` is replaced), never sent.
"""

from __future__ import annotations

import smtplib
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from apps.catalog.api.auth import (
    reset_token_sha256,
    token_predates_password,
)
from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from services import email_service
from support import DEFAULT_PASSWORD, seed_05_catalog

NEW_PASSWORD = 'a different horse staple'


@pytest.fixture
def outbox(monkeypatch):
    """What would be mailed, per batch; ``fail`` names addresses whose send
    is reported as failed."""
    box = {'mails': [], 'batches': [], 'fail': set()}

    def send_mails(config, batch):
        batch = list(batch)
        box['batches'].append([m.to for m in batch])
        out = []
        for mail in batch:
            if mail.to in box['fail']:
                out.append('SMTPRecipientsRefused: refused')
            else:
                box['mails'].append(mail)
                out.append(None)
        return out

    monkeypatch.setattr(email_service, 'send_mails', send_mails)
    return box


def _token_of(mail) -> str:
    return mail.text.split('token=')[1].split()[0]


def _code_of(mail) -> str:
    return mail.text.split('code=')[1].split()[0]


# PASSWORD RESET ----------------------------------------------------------------
def test_an_unknown_address_gets_the_same_answer_and_no_mail(api, db, outbox,
                                                             make_user):
    make_user(username='known')
    unknown = api.post('/auth/password-reset',
                       json={'email': 'nobody@tu-darmstadt.de'})
    known = api.post('/auth/password-reset',
                     json={'email': 'known@tu-darmstadt.de'})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    assert [m.to for m in outbox['mails']] == ['known@tu-darmstadt.de']
    # a disabled account gets nothing either, and says nothing
    make_user(username='gone', disabled=True)
    assert api.post('/auth/password-reset',
                    json={'email': 'gone@tu-darmstadt.de'}).status_code == 202
    assert len(outbox['mails']) == 1


def test_the_token_is_stored_as_a_hash_and_works_once(api, db, outbox,
                                                      make_user, login):
    make_user(username='resetter')
    api.post('/auth/password-reset', json={'email': 'resetter@tu-darmstadt.de'})
    mail = outbox['mails'][0]
    token = _token_of(mail)
    stored = db['users'].find_one({'username': 'resetter'})
    assert stored['password_reset_sha256'] == reset_token_sha256(token)
    assert token not in str(stored)                    # only the hash is kept
    assert mail.reply_to is None                       # no Reply-To on a reset

    bad = api.post('/auth/password-reset/confirm',
                   json={'token': 'x' * 40, 'new_password': NEW_PASSWORD})
    assert bad.status_code == 400
    short = api.post('/auth/password-reset/confirm',
                     json={'token': token, 'new_password': 'short'})
    assert short.status_code == 422                    # the register rules
    done = api.post('/auth/password-reset/confirm',
                    json={'token': token, 'new_password': NEW_PASSWORD})
    assert done.status_code == 200, done.text
    again = api.post('/auth/password-reset/confirm',
                     json={'token': token, 'new_password': 'yet another one'})
    assert again.status_code == 400                    # single use
    assert login('resetter', DEFAULT_PASSWORD).status_code == 401
    assert login('resetter', NEW_PASSWORD).status_code == 200
    after = db['users'].find_one({'username': 'resetter'})
    assert 'password_reset_sha256' not in after and after['password_changed_at']


def test_an_expired_token_is_refused(api, db, outbox, make_user):
    make_user(username='late')
    api.post('/auth/password-reset', json={'email': 'late@tu-darmstadt.de'})
    token = _token_of(outbox['mails'][0])
    db['users'].update_one(
        {'username': 'late'},
        {'$set': {'password_reset_expires':
                  datetime.now(timezone.utc) - timedelta(minutes=1)}})
    refused = api.post('/auth/password-reset/confirm',
                       json={'token': token, 'new_password': NEW_PASSWORD})
    assert refused.status_code == 400
    assert 'expired' in refused.json()['detail']


def test_at_most_three_mails_an_hour_to_one_address(api, db, outbox,
                                                    make_user):
    make_user(username='eager')
    for _ in range(5):
        assert api.post('/auth/password-reset', json={
            'email': 'eager@tu-darmstadt.de'}).status_code == 202
    assert len(outbox['mails']) == 3


def test_a_reset_also_verifies_the_address_and_a_mail_failure_stays_quiet(
        api, db, outbox, make_user, login):
    make_user(username='unverified', verified=False)
    outbox['fail'].add('unverified@tu-darmstadt.de')
    answer = api.post('/auth/password-reset',
                      json={'email': 'unverified@tu-darmstadt.de'})
    assert answer.status_code == 202                   # 202 on a mail failure
    assert outbox['mails'] == []
    outbox['fail'].clear()
    api.post('/auth/password-reset', json={'email': 'unverified@tu-darmstadt.de'})
    token = _token_of(outbox['mails'][0])
    assert api.post('/auth/password-reset/confirm', json={
        'token': token, 'new_password': NEW_PASSWORD}).status_code == 200
    assert login('unverified', NEW_PASSWORD).status_code == 200   # the mailbox proved it


# TOKENS DIE WITH A PASSWORD CHANGE ---------------------------------------------
def _old_token(app, user_id: str, seconds_ago: int = 100) -> str:
    now = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return jwt.encode(
        {'sub': user_id, 'role': 'user', 'iat': int(now.timestamp()),
         'exp': int((now + timedelta(hours=1)).timestamp())},
        app.state.jwt_secret, algorithm=app.state.jwt_algorithm)


def test_a_token_issued_before_a_reset_or_a_change_is_refused(
        app, api, db, outbox, make_user, login):
    user = make_user(username='signedin')
    old = {'Authorization': f'Bearer {_old_token(app, user["id"])}'}
    assert api.get('/users/me', headers=old).status_code == 200
    # a reset signs the old token out; the sign-in that follows works at once
    api.post('/auth/password-reset', json={'email': 'signedin@tu-darmstadt.de'})
    api.post('/auth/password-reset/confirm', json={
        'token': _token_of(outbox['mails'][0]), 'new_password': NEW_PASSWORD})
    assert api.get('/users/me', headers=old).status_code == 401
    fresh = login('signedin', NEW_PASSWORD).json()['access_token']
    headers = {'Authorization': f'Bearer {fresh}'}
    assert api.get('/users/me', headers=headers).status_code == 200
    # change-password does the same: the other device is out, this call is
    # answered, a new sign-in works
    other = {'Authorization': f'Bearer {_old_token(app, user["id"], 50)}'}
    db['users'].update_one({'_id': user['id']},
                           {'$unset': {'password_changed_at': ''}})
    assert api.get('/users/me', headers=other).status_code == 200
    changed = api.post('/auth/change-password', headers=headers, json={
        'current_password': NEW_PASSWORD, 'new_password': 'third password ok'})
    assert changed.status_code == 200, changed.text
    assert api.get('/users/me', headers=other).status_code == 401
    assert login('signedin', 'third password ok').status_code == 200


def test_a_token_of_the_same_second_stands_and_one_without_iat_does_not():
    changed = datetime(2026, 10, 7, 12, 0, 0, 900000, tzinfo=timezone.utc)
    second = int(changed.timestamp())
    doc = {'password_changed_at': changed}
    assert not token_predates_password({'iat': second}, doc)
    assert not token_predates_password({'iat': second + 5}, doc)
    assert token_predates_password({'iat': second - 1}, doc)
    assert token_predates_password({}, doc)                 # no iat, after a change
    assert not token_predates_password({}, {})              # never changed
    naive = {'password_changed_at': changed.replace(tzinfo=None)}
    assert token_predates_password({'iat': second - 1}, naive)


# INVITATIONS: A FAILED SEND IS VISIBLE, RESEND ISSUES A NEW CODE -----------------
@pytest.fixture
def world(api, db, auth_headers, member_headers, outbox):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    moderator, moderator_id = member_headers({'dbu_zirkus': ['moderator']})
    contributor, _ = member_headers({'dbu_zirkus': ['contributor']})
    return {'api': api, 'db': db, 'outbox': outbox, 'moderator': moderator,
            'moderator_id': moderator_id, 'contributor': contributor,
            'admin': auth_headers('admin')}


def _invite(api, headers, emails, roles=('contributor',)):
    return api.post('/invitations', headers=headers, json={
        'emails': list(emails), 'dataset': 'dbu_zirkus', 'roles': list(roles)})


def _register(api, email, code, username):
    return api.post('/auth/register', json={
        'username': username, 'full_name': 'New Person', 'email': email,
        'password': DEFAULT_PASSWORD, 'code': code})


def test_a_failed_invitation_mail_is_reported_and_resend_voids_the_old_code(
        world):
    api, box = world['api'], world['outbox']
    moderator = world['moderator']
    box['fail'].add('flaky@partner.example')
    rows = _invite(api, moderator,
                   ['ok@partner.example', 'flaky@partner.example']).json()
    assert [(r['email'], r['result']) for r in rows] == [
        ('ok@partner.example', 'invited'), ('flaky@partner.example',
                                            'mail_failed')]
    assert rows[1]['invitation']['mail_failed'] is True
    assert box['batches'] == [['ok@partner.example', 'flaky@partner.example']]
    assert 'code' not in str(rows).replace('code_sha256', '')   # never shown
    assert 'register' not in str(rows)

    # the list shows it too, and Resend issues a new code over a working mail
    listed = api.get('/invitations', headers=moderator).json()
    flaky = next(i for i in listed if i['email'] == 'flaky@partner.example')
    assert flaky['mail_failed'] is True
    box['fail'].clear()
    box['mails'].clear()
    resent = api.post(f'/invitations/{flaky["_id"]}/resend', headers=moderator)
    assert resent.status_code == 200, resent.text
    assert resent.json()['result'] == 'invited'
    assert resent.json()['invitation']['mail_failed'] is False
    assert 'register?code=' not in resent.text
    assert _code_of(box['mails'][0])
    assert box['mails'][0].reply_to                       # the moderator


def test_resend_voids_the_old_code_and_keeps_the_rules(world):
    api, box, moderator = world['api'], world['outbox'], world['moderator']
    _invite(api, moderator, ['again@partner.example'])
    old_code = _code_of(box['mails'][0])
    iid = api.get('/invitations', headers=moderator).json()[0]['_id']
    assert api.post(f'/invitations/{iid}/resend',
                    headers=world['contributor']).status_code == 403
    assert api.post('/invitations/none/resend',
                    headers=moderator).status_code == 404
    resent = api.post(f'/invitations/{iid}/resend', headers=moderator)
    assert resent.status_code == 200
    new_code = _code_of(box['mails'][1])
    assert new_code != old_code
    old = _register(api, 'again@partner.example', old_code, 'oldcode')
    assert old.status_code == 400
    new = _register(api, 'again@partner.example', new_code, 'newcode')
    assert new.status_code == 201, new.text
    # used: no more resend; revoked likewise
    assert api.post(f'/invitations/{iid}/resend',
                    headers=moderator).status_code == 409
    _invite(api, moderator, ['gone@partner.example'])
    gone = next(i for i in api.get('/invitations', headers=moderator).json()
                if i['email'] == 'gone@partner.example')
    api.delete(f'/invitations/{gone["_id"]}', headers=moderator)
    assert api.post(f'/invitations/{gone["_id"]}/resend',
                    headers=moderator).status_code == 409


def test_an_expired_invitation_can_be_resent_with_the_expiry_of_a_new_one(
        world):
    api, db = world['api'], world['db']
    moderator = world['moderator']
    _invite(api, moderator, ['late@partner.example'])
    doc = db['invitations'].find_one({'email': 'late@partner.example'})
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace('+00:00', 'Z')
    db['invitations'].update_one({'_id': doc['_id']}, {'$set': {'expires_at': past}})
    assert api.get('/invitations', headers=moderator).json()[0]['state'] == 'expired'
    resent = api.post(f'/invitations/{doc["_id"]}/resend', headers=moderator)
    assert resent.status_code == 200
    body = resent.json()['invitation']
    expires = datetime.fromisoformat(body['expires_at'].replace('Z', '+00:00'))
    assert abs((expires - datetime.now(timezone.utc)) - timedelta(days=14)) < timedelta(minutes=1)
    assert body['state'] == 'open'
    # a second resend does not stretch it: the rule is the same every time
    again = api.post(f'/invitations/{doc["_id"]}/resend?expires_days=3',
                     headers=moderator).json()['invitation']
    expires = datetime.fromisoformat(again['expires_at'].replace('Z', '+00:00'))
    assert abs((expires - datetime.now(timezone.utc)) - timedelta(days=3)) < timedelta(minutes=1)


def test_the_member_notice_reports_a_failed_mail_and_the_membership_stands(
        world):
    api, db, box = world['api'], world['db'], world['outbox']
    moderator = world['moderator']
    db['users'].insert_one({
        '_id': 'known-user', 'username': 'known-user',
        'email': 'known-user@partner.example', 'full_name': 'Known User',
        'hashed_password': 'x', 'role': 'user', 'disabled': False,
        'email_verified': True})
    box['fail'].add('known-user@partner.example')
    out = api.post('/datasets/dbu_zirkus/members', headers=moderator, json={
        'email': 'known-user@partner.example', 'roles': ['contributor']})
    assert out.status_code == 200, out.text
    assert out.json()['result'] == 'added' and out.json()['mail_failed'] is True
    members = db['datasets'].find_one({'_id': 'dbu_zirkus'})['members']
    assert any(m['user_id'] == 'known-user' for m in members)
    # an unknown address is invited; a failed mail shows the same way
    box['fail'].add('stranger@partner.example')
    invited = api.post('/datasets/dbu_zirkus/members', headers=moderator, json={
        'email': 'stranger@partner.example', 'roles': ['contributor']}).json()
    assert invited['result'] == 'invited' and invited['mail_failed'] is True
    assert 'register' not in str(invited)
    box['fail'].clear()
    ok = api.post('/datasets/dbu_zirkus/members', headers=moderator, json={
        'email': 'known-user@partner.example', 'roles': ['reviewer']}).json()
    assert ok['mail_failed'] is False
    assert box['mails'][-1].reply_to                    # the acting moderator


# THE ONE TEMPLATE ------------------------------------------------------------
CONFIG = {'frontend_url': 'https://csc.example.org/', 'from_email': 'csc@example.org',
          'from_name': 'Catalog of Second Chances', 'dev_mode': False}


def test_all_four_mails_share_the_template_and_escape_what_they_insert():
    evil = '<script>alert(1)</script> & "co"'
    mails = [
        email_service.verification_mail(CONFIG, 'a@x.org', evil, 'tok'),
        email_service.reset_mail(CONFIG, 'a@x.org', evil, 'tok'),
        email_service.invitation_mail(CONFIG, 'a@x.org', 'CODE', evil,
                                      'mod@x.org', evil, ['contributor'],
                                      '2026-12-01T00:00:00Z'),
        email_service.member_added_mail(CONFIG, 'a@x.org', evil, evil,
                                        ['reviewer'], evil, 'mod@x.org'),
    ]
    for mail in mails:
        assert mail.subject.startswith('[CSC] ')
        assert '<script>' not in mail.html                 # escaped
        assert '&lt;script&gt;' in mail.html or 'script' not in mail.html
        assert '"co"' not in mail.html or '&quot;co&quot;' in mail.html
        assert 'Please do not reply' not in mail.text + mail.html
        assert 'https://csc.example.org/imprint' in mail.text
        assert 'https://csc.example.org/imprint' in mail.html
        assert 'You received this email because' in mail.text
        assert '#4080ff' in mail.html
    verification, reset, invitation, member = mails
    assert verification.reply_to is None and reset.reply_to is None
    # nothing to say about replies where nobody gets them (no SMTP_REPLY_TO)
    assert 'Replies to this email' not in verification.text + reset.text
    assert 'mod@x.org' in invitation.reply_to and 'mod@x.org' in member.reply_to
    assert 'auth/verify-email?token=tok' in verification.text
    assert 'auth/reset-password?token=tok' in reset.text
    assert 'auth/register?code=CODE' in invitation.text
    # a quote in a link is escaped in the attribute too
    odd = email_service.render(CONFIG, to='a@x.org', subject='s', title='t',
                               paragraphs=['p'], reason='r',
                               button=('Go', 'https://x.org/?a="b"&c=<d>'))
    assert 'a="b"' not in odd.html and '&quot;b&quot;' in odd.html


class FakeSMTP:
    """smtplib.SMTP stand-in: counts connections, refuses chosen addresses."""
    connections = 0
    refuse = set()
    sent = []
    fail_connect = False

    def __init__(self, host, port, timeout=None):
        if FakeSMTP.fail_connect:
            raise OSError('unreachable')
        FakeSMTP.connections += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        if msg['To'] in FakeSMTP.refuse:
            raise smtplib.SMTPRecipientsRefused({msg['To']: (550, b'no')})
        FakeSMTP.sent.append(msg)


def test_a_bulk_goes_over_one_connection_and_says_per_mail_what_happened(
        monkeypatch):
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    FakeSMTP.connections, FakeSMTP.sent, FakeSMTP.refuse = 0, [], {'b@x.org'}
    FakeSMTP.fail_connect = False
    config = {**CONFIG, 'smtp_host': 'h', 'smtp_port': '587',
              'smtp_user': 'u', 'smtp_password': 'p'}
    batch = [email_service.invitation_mail(
        config, to, 'C', 'Mod', 'mod@x.org', 'D', ['contributor'],
        '2026-12-01T00:00:00Z') for to in ('a@x.org', 'b@x.org', 'c@x.org')]
    results = email_service.send_mails(config, batch)
    assert FakeSMTP.connections == 1
    assert results[0] is None and results[2] is None
    assert results[1] and 'SMTPRecipientsRefused' in results[1]
    assert [m['To'] for m in FakeSMTP.sent] == ['a@x.org', 'c@x.org']
    sent = FakeSMTP.sent[0]
    assert sent['From'] == 'Catalog of Second Chances <csc@example.org>'
    assert 'mod@x.org' in sent['Reply-To']
    assert sent['Subject'].startswith('[CSC] ')
    parts = [p.get_content_type() for p in sent.walk()]
    assert 'text/plain' in parts and 'text/html' in parts
    # a server that cannot be reached fails every mail, and raises nothing
    FakeSMTP.fail_connect = True
    down = email_service.send_mails(config, batch)
    assert all(r and 'OSError' in r for r in down)
    assert email_service.send_mails(config, []) == []


def test_support_gets_the_replies_to_verification_and_reset_when_it_is_set(
        capsys):
    """Amends 8.124 c: mails come from the noreply mailbox; a reply to the
    verification or the reset goes to SMTP_REPLY_TO, a reply to an invitation
    or a member notice to the moderator who sent it."""
    dev = {**CONFIG, 'dev_mode': True, 'reply_to': 'support@x.org'}
    mails = [email_service.verification_mail(dev, 'a@x.org', 'Ada', 'tok'),
             email_service.reset_mail(dev, 'a@x.org', 'Ada', 'tok')]
    assert [m.reply_to for m in mails] == ['support@x.org'] * 2
    for mail in mails:
        assert 'Replies to this email reach the support' in mail.text
        assert 'Replies to this email reach the support' in mail.html
        assert 'do not reply' not in (mail.text + mail.html).lower()
    assert email_service.send_mails(dev, mails) == [None, None]
    shown = capsys.readouterr().out
    assert shown.count('Reply-To: support@x.org') == 2
    # not set (or empty): no header, as before
    for unset in ({**CONFIG, 'dev_mode': True},
                  {**CONFIG, 'dev_mode': True, 'reply_to': ''}):
        mail = email_service.reset_mail(unset, 'a@x.org', 'Ada', 'tok')
        assert mail.reply_to is None
        email_service.send_mails(unset, [mail])
        assert 'Reply-To' not in capsys.readouterr().out
    # the acting moderator stays the reply address of the other two
    invitation = email_service.invitation_mail(
        dev, 'a@x.org', 'C', 'Mod', 'mod@x.org', 'D', ['contributor'],
        '2026-12-01T00:00:00Z')
    member = email_service.member_added_mail(
        dev, 'a@x.org', 'Ada', 'D', ['reviewer'], 'Mod', 'mod@x.org')
    for mail in (invitation, member):
        assert 'mod@x.org' in mail.reply_to and 'support' not in mail.reply_to
        assert 'Replies to this email reach Mod.' in mail.text


def test_the_reply_address_is_read_from_the_environment(monkeypatch):
    for key, value in (('SMTP_HOST', 'h'), ('SMTP_USER', 'u'),
                       ('SMTP_PASSWORD', 'p'), ('SMTP_FROM_EMAIL', 'n@x.org'),
                       ('FRONTEND_URL', 'https://csc.example.org')):
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('SMTP_REPLY_TO', raising=False)
    assert email_service.load_email_config()['reply_to'] == ''
    monkeypatch.setenv('SMTP_REPLY_TO', ' support@x.org ')
    assert email_service.load_email_config()['reply_to'] == 'support@x.org'


def test_dev_mode_prints_instead_of_sending(capsys):
    mail = email_service.reset_mail({**CONFIG, 'dev_mode': True}, 'a@x.org',
                                    'Ada', 'tok')
    assert email_service.send_mails({**CONFIG, 'dev_mode': True}, [mail]) == [None]
    assert 'auth/reset-password?token=tok' in capsys.readouterr().out
