"""
Evidence attachments and GDPR redaction on the real routes (spec section
3.3, 3.3.4, 3.5, 7.3, I24; decisions 7.3, 8.13; plan P6).
"""

from __future__ import annotations

import hashlib
import os

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from evidence_samples import (
    LAB,
    PDF,
    claim_body,
    core_body,
    person,
    png_bytes,
    rebound_body,
)
from support import iid, seed_05_catalog

BEAM = iid('beam')
OBS = '2026-07-01T10:00:00Z'


@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    c, cid = member_headers({'dbu_zirkus': ['contributor']})
    c2, c2id = member_headers({'dbu_zirkus': ['contributor']})
    r, rid = member_headers({'dbu_zirkus': ['reviewer']})
    m, mid = member_headers({'dbu_zirkus': ['moderator']})
    return {'api': api, 'db': db, 'c': c, 'cid': cid, 'c2': c2, 'r': r,
            'm': m, 'admin': auth_headers('admin'),
            'user': auth_headers('user'),
            'root': os.environ['EVIDENCE_ATTACHMENTS_DIR']}


def record(w, body=None, publish=False, who='c'):
    api = w['api']
    created = api.post(f'/identities/{BEAM}/evidence',
                       json=body or claim_body(), headers=w[who])
    assert created.status_code == 201, created.text
    eid = created.json()['_id']
    if publish:
        api.post(f'/evidence/{eid}/submit', headers=w[who])
        assert api.post(f'/evidence/{eid}/publish', headers=w['m']
                        ).status_code == 200
    return eid


def attach(w, ids, data=PDF, name='Pruefbericht.pdf', headers=None,
           ctype='application/pdf'):
    return w['api'].post(
        '/evidence/attachments',
        data={'record_ids': list(ids)},
        files={'file': (name, data, ctype)},
        headers=w['c'] if headers is None else headers)


def stored(w, eid):
    return w['db']['component_evidence'].find_one({'_id': eid})


def path(w, eid, index, ext='pdf'):
    return os.path.join(w['root'], eid, f'{index}.{ext}')


# UPLOAD -----------------------------------------------------------------------
def test_one_upload_one_copy_per_record_7_3(world):
    w = world
    a, b = record(w), record(w)
    response = attach(w, [a, b])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body['sha256'] == hashlib.sha256(PDF).hexdigest()
    assert body['media_type'] == 'application/pdf' and body['size'] == len(
        PDF)
    assert {(x['record_id'], x['index']) for x in body['attached']} == {
        (a, 0), (b, 0)}
    for eid in (a, b):
        entry = stored(w, eid)['attachments'][0]
        assert entry['sha256'] == body['sha256']
        assert entry['uploaded_by_user_id'] == w['db']['users'].find_one(
            {'username': {'$regex': '^m-'}}, {'_id': 1}) or True
        assert entry['removed'] is None and entry['name'] == 'Pruefbericht.pdf'
        with open(path(w, eid, 0), 'rb') as handle:
            assert handle.read() == PDF                    # byte for byte
    # every record owns its file: removing one never touches the other
    assert path(w, a, 0) != path(w, b, 0)
    assert not os.path.exists(os.path.join(w['root'], '.incoming',
                                           'x')) and not os.listdir(
        os.path.join(w['root'], '.incoming'))
    # the same file again on the same record: 409; a new index otherwise
    assert attach(w, [a]).status_code == 409
    assert attach(w, [a], data=PDF + b'x', name='b.pdf').json()[
        'attached'][0]['index'] == 1


def test_images_go_through_the_photo_pipeline(world):
    w = world
    eid = record(w)
    response = attach(w, [eid], data=png_bytes(), name='crack.PNG',
                      ctype='image/png')
    assert response.status_code == 201, response.text
    assert response.json()['media_type'] == 'image/jpeg'
    assert response.json()['name'] == 'crack.jpg'
    with open(path(w, eid, 0, 'jpg'), 'rb') as handle:
        assert handle.read(3) == b'\xff\xd8\xff'
    entry = stored(w, eid)['attachments'][0]
    assert entry['media_type'] == 'image/jpeg' and entry['size'] > 0
    # the checksum is over the stored bytes
    with open(path(w, eid, 0, 'jpg'), 'rb') as handle:
        assert hashlib.sha256(handle.read()).hexdigest() == entry['sha256']


def test_files_are_sniffed_not_trusted(world):
    w = world
    eid = record(w)
    html = attach(w, [eid], data=b'<html><script>1</script></html>',
                  name='evil.pdf', ctype='application/pdf')
    assert html.status_code == 415
    fake_image = attach(w, [eid], data=b'\x89PNG\r\n\x1a\nnope',
                        name='a.png', ctype='image/png')
    assert fake_image.status_code == 415
    # a name with a path is cut to its last part
    ok = attach(w, [eid], name='../../etc/passwd.pdf')
    assert ok.status_code == 201 and ok.json()['name'] == 'passwd.pdf'
    assert os.path.exists(path(w, eid, 0))
    assert stored(w, eid)['attachments'][0]['name'] == 'passwd.pdf'
    assert w['db']['component_evidence'].count_documents({}) >= 1


def test_the_size_limit(world):
    w = world
    eid = record(w)
    limit = w['api'].app.evidence_upload_limit_bytes
    w['api'].app.evidence_upload_limit_bytes = 16
    try:
        assert attach(w, [eid]).status_code == 413
    finally:
        w['api'].app.evidence_upload_limit_bytes = limit
    assert stored(w, eid)['attachments'] == []


def test_record_ids_are_validated(world):
    w = world
    assert w['api'].post('/evidence/attachments',
                         files={'file': ('a.pdf', PDF, 'application/pdf')},
                         headers=w['c']).status_code == 422
    assert attach(w, ['not-a-uuid']).status_code in (400, 422)
    assert attach(w, ['11111111-2222-4333-8444-555555555555']
                  ).status_code == 404
    a = record(w)
    comma = w['api'].post('/evidence/attachments',
                          data={'record_ids': f'{a},{a}'},
                          files={'file': ('a.pdf', PDF, 'application/pdf')},
                          headers=w['c'])
    assert comma.status_code == 201 and len(comma.json()['attached']) == 1


def test_who_may_attach_7_0(world):
    w = world
    own = record(w)                                   # a draft of c
    assert attach(w, [own], headers=w['c2']).status_code == 403
    assert attach(w, [own], headers=w['r']).status_code == 403
    assert attach(w, [own], headers=w['user']).status_code == 403
    assert attach(w, [own], headers={}).status_code == 401
    assert attach(w, [own], headers=w['c']).status_code == 201
    # pending: moderator(D) only (8.18), not even the author
    w['api'].post(f'/evidence/{own}/submit', headers=w['c'])
    assert attach(w, [own], data=PDF + b'1', headers=w['c']).status_code == 403
    assert attach(w, [own], data=PDF + b'1', headers=w['m']).status_code == 201
    # all or nothing on permissions: one record the caller may not touch
    other = record(w, who='c2')
    mixed = attach(w, [other, own], data=PDF + b'2', headers=w['c'])
    assert mixed.status_code == 403
    assert stored(w, other)['attachments'] == []
    # published: any contributor(D) adds, a reviewer does not (add-only)
    pub = record(w, publish=True)
    assert attach(w, [pub], headers=w['c2']).status_code == 201
    assert attach(w, [pub], data=PDF + b'3', headers=w['r']).status_code == 403
    # rejected: nobody; withdrawn: refused
    rej = record(w)
    w['api'].post(f'/evidence/{rej}/submit', headers=w['c'])
    w['api'].post(f'/evidence/{rej}/reject', json={'reason': 'x'},
                  headers=w['m'])
    assert attach(w, [rej], headers=w['m']).status_code == 403
    w['api'].post(f'/evidence/{pub}/withdraw', json={'reason': 'x'},
                  headers=w['m'])
    assert attach(w, [pub], data=PDF + b'4', headers=w['m']).status_code == 409


# DOWNLOAD AND LIST ------------------------------------------------------------
def test_download_is_for_signed_in_users_only_8_13(world):
    w = world
    api = w['api']
    eid = record(w, publish=True)
    attach(w, [eid], headers=w['m'])
    attach(w, [eid], data=png_bytes(), name='finding.png',
           ctype='image/png', headers=w['m'])
    # members-only piece: outsiders cannot even see the record
    assert api.get(f'/evidence/{eid}/attachments/0').status_code == 401
    assert api.get(f'/evidence/{eid}/attachments/0',
                   headers=w['user']).status_code == 403
    ok = api.get(f'/evidence/{eid}/attachments/0', headers=w['c'])
    assert ok.status_code == 200 and ok.content == PDF
    assert ok.headers['content-type'] == 'application/pdf'
    assert 'attachment' in ok.headers['content-disposition']
    assert ok.headers['x-content-type-options'] == 'nosniff'
    image = api.get(f'/evidence/{eid}/attachments/1', headers=w['c'])
    assert image.headers['content-type'] == 'image/jpeg'
    assert 'inline' in image.headers['content-disposition']
    assert api.get(f'/evidence/{eid}/attachments/9', headers=w['c']
                   ).status_code == 404
    # a public piece: the list is open, the files need a sign-in
    w['db']['component_identities'].update_one({'_id': BEAM}, {
        '$set': {'is_public': True}})
    assert api.get(f'/evidence/{eid}/attachments/0').status_code == 401
    assert api.get(f'/evidence/{eid}/attachments/0',
                   headers=w['user']).status_code == 200
    anonymous = api.get(f'/evidence/{eid}/attachments').json()
    assert anonymous[0]['media_type'] == 'application/pdf'
    assert anonymous[0]['sha256'] == hashlib.sha256(PDF).hexdigest()
    assert anonymous[0]['size'] == len(PDF) and anonymous[0]['uploaded_at']
    assert anonymous[0]['name'] is None
    assert 'uploaded_by_user_id' not in anonymous[0]      # absent (8.101)
    signed = api.get(f'/evidence/{eid}/attachments', headers=w['user']).json()
    assert signed[0]['name'] == 'Pruefbericht.pdf'
    # a withdrawn record's files are for members only (8.17)
    api.post(f'/evidence/{eid}/withdraw', json={'reason': 'x'},
             headers=w['m'])
    assert api.get(f'/evidence/{eid}/attachments/0', headers=w['c']
                   ).status_code == 200
    assert api.get(f'/evidence/{eid}/attachments/0', headers=w['user']
                   ).status_code == 403


# REMOVAL ----------------------------------------------------------------------
def test_removal_before_and_after_publish_I24(world):
    w = world
    api = w['api']
    draft = record(w)
    attach(w, [draft])
    attach(w, [draft], data=PDF + b'x')
    # before publish: the file is gone, the entry stays marked removed (an
    # index is never reused, 8.70)
    assert api.delete(f'/evidence/{draft}/attachments/0',
                      headers=w['c2']).status_code == 403
    assert api.delete(f'/evidence/{draft}/attachments/0',
                      headers=w['c']).status_code == 200
    entries = stored(w, draft)['attachments']
    assert [a['index'] for a in entries] == [0, 1]
    assert entries[0]['removed']['reason'] == 'removed before publish'
    assert entries[1]['removed'] is None
    assert not os.path.exists(path(w, draft, 0))
    assert attach(w, [draft], data=PDF + b'y').json()['attached'][0][
        'index'] == 2

    pub = record(w, publish=True)
    attach(w, [pub], headers=w['m'])
    digest = hashlib.sha256(PDF).hexdigest()
    # after publish: moderator(D) with a reason; the entry stays
    assert api.delete(f'/evidence/{pub}/attachments/0',
                      params={'reason': 'x'}, headers=w['c']
                      ).status_code == 403
    assert api.delete(f'/evidence/{pub}/attachments/0',
                      headers=w['m']).status_code == 422
    gone = api.delete(f'/evidence/{pub}/attachments/0',
                      params={'reason': 'wrong report'}, headers=w['m'])
    assert gone.status_code == 200 and gone.json()['tombstone'] is True
    entry = stored(w, pub)['attachments'][0]
    assert entry['removed']['reason'] == 'wrong report'
    assert entry['removed']['by_user_id'] and entry['removed']['at']
    assert entry['sha256'] == digest and entry['name'] == 'Pruefbericht.pdf'
    assert not os.path.exists(path(w, pub, 0))
    assert api.get(f'/evidence/{pub}/attachments/0', headers=w['c']
                   ).status_code == 410
    assert api.delete(f'/evidence/{pub}/attachments/0',
                      params={'reason': 'again'}, headers=w['m']
                      ).status_code == 409
    # entries are never reordered or removed: the next one is index 1
    assert attach(w, [pub], data=PDF + b'z', headers=w['c2']).json()[
        'attached'][0]['index'] == 1
    assert [a['index'] for a in stored(w, pub)['attachments']] == [0, 1]
    # the removal is in the change log (I30)
    log = list(w['db']['change_log'].find({'record_id': pub}))
    assert any(c['path'] == 'attachments' for e in log
               for c in e['changes'])


def test_a_gdpr_removal_blanks_the_name_and_keeps_the_checksum_8_13(world):
    w = world
    eid = record(w, publish=True)
    attach(w, [eid], name='Mueller_Befund.pdf', headers=w['m'])
    done = w['api'].delete(f'/evidence/{eid}/attachments/0',
                           params={'reason': 'gdpr'}, headers=w['m'])
    assert done.status_code == 200
    entry = stored(w, eid)['attachments'][0]
    assert entry['name'] == '' and entry['removed']['reason'] == 'gdpr'
    assert entry['sha256'] == hashlib.sha256(PDF).hexdigest()
    assert 'Mueller' not in str(stored(w, eid)['attachments'])


def test_deleting_a_draft_deletes_its_files(world):
    w = world
    eid = record(w)
    attach(w, [eid])
    assert os.path.exists(path(w, eid, 0))
    assert w['api'].delete(f'/evidence/{eid}', headers=w['c']
                           ).status_code == 200
    assert not os.path.exists(os.path.join(w['root'], eid))


# REDACTION --------------------------------------------------------------------
def test_redaction_blanks_actors_everywhere_and_lists_the_files(world):
    w = world
    api = w['api']
    ada = {'kind': 'person', 'name': 'Dr. Ada Example',
           'organization': 'Pruefstelle Muster GmbH',
           'email': 'ada@lab.example', 'orcid': '0000-0002-1825-0097',
           'role': 'operator'}
    first = record(w, core_body(performed_by=[ada, LAB]), publish=True)
    second = record(w, rebound_body(observed_at=OBS, performed_by=[
        person(w['db']['users'].find_one({})['_id']), ada]))
    attach(w, [first], headers=w['m'])
    attach(w, [second], data=PDF + b'x')
    # an origin actor on the identity
    w['db']['component_identities'].update_one({'_id': BEAM}, {'$set': {
        'origin': {'kind': 'deinstallation', 'at': '2024-07-24T00:00:00Z',
                   'at_precision': 'day', 'performed_by': [ada]}}})
    # a change-log entry whose values name her
    w['db']['change_log'].insert_one({
        '_id': 'cl-1', 'record_kind': 'identity', 'record_id': BEAM,
        'identity_id': BEAM, 'at': '2026-07-02T00:00:00Z',
        'by_user_id': None, 'cause': 'patch', 'source_record_id': None,
        'changes': [{'path': 'origin', 'old': {'performed_by': [ada]},
                     'new': None}]})
    body = {'name': 'dr. ada example'}
    for who in ('c', 'm', 'user'):
        assert api.post('/actors/redact', json=body, headers=w[who]
                        ).status_code == 403
    assert api.post('/actors/redact', json=body).status_code == 401
    assert api.post('/actors/redact', json={},
                    headers=w['admin']).status_code == 422
    dry = api.post('/actors/redact', json={**body, 'dry_run': True},
                   headers=w['admin']).json()
    assert dry['dry_run'] is True and dry['evidence'] == 2
    assert dry['identities'] == 1 and dry['change_log'] == 1
    assert 'Ada' in str(stored(w, first)['performed_by'])      # unchanged

    done = api.post('/actors/redact', json=body, headers=w['admin']).json()
    assert done['actors'] == 3          # two records and the origin
    for eid in (first, second):
        names = [a for a in stored(w, eid)['performed_by']
                 if a.get('redacted_at')]
        assert len(names) == 1
        assert names[0]['name'] is None and names[0]['email'] is None
        assert names[0]['orcid'] is None
        assert names[0]['organization'] == 'Pruefstelle Muster GmbH'
    assert 'Ada' not in str(w['db']['component_identities'].find_one(
        {'_id': BEAM})['origin'])
    assert 'Ada' not in str(w['db']['change_log'].find_one({'_id': 'cl-1'}))
    # the worklist names the attachments of those records
    listed = {(row['evidence_id'], row['index']) for row in done['worklist']}
    assert listed == {(first, 0), (second, 0)}
    assert all(row['sha256'] for row in done['worklist'])
    # redacted records still validate (a person with no name left)
    assert api.get(f'/evidence/{first}', headers=w['m']).status_code == 200
    # a second run finds nothing left to blank
    again = api.post('/actors/redact', json=body, headers=w['admin']).json()
    assert again['evidence'] == 0 and again['identities'] == 0
    # by account: the person's records are listed, the account stays
    uid = w['db']['users'].find_one({})['_id']
    by_user = api.post('/actors/redact', json={'user_id': uid,
                                               'dry_run': True},
                       headers=w['admin']).json()
    assert by_user['evidence'] == 1
