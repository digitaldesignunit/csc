"""The personal profile of an account (decision 8.133): editable, validated,
copied into the actors of records when they are written, blanked by the
redaction; and ``Actor.url`` (8.133 item 2)."""

from __future__ import annotations

import copy

import pytest

from apps.catalog.migration06.steps import CUTOVER_STEPS, Context, run
from apps.catalog.profile import (
    fill_actor,
    normalize_orcid,
    normalize_ror,
    normalize_url,
    orcid_check_digit,
)
from apps.catalog.documents import Actor
from evidence_samples import rebound_body
from support import iid, seed_05_catalog

BEAM = iid('beam')
ORCID = '0000-0002-1825-0097'
ROR = '03yrm5c26'


# THE PURE PARTS --------------------------------------------------------------
def test_an_orcid_is_checked_and_normalised():
    assert orcid_check_digit('000000021825009') == '7'
    for given in (ORCID, '0000000218250097', f'https://orcid.org/{ORCID}',
                  ' 0000 0002 1825 0097 '):
        assert normalize_orcid(given) == ORCID
    assert normalize_orcid('0000-0001-5109-3700') == '0000-0001-5109-3700'
    assert normalize_orcid('0000-0002-1694-233x') == '0000-0002-1694-233X'
    for bad in ('0000-0002-1825-0098', '0000-0002-1825', 'abcd-0002-1825-0097',
                '0000-0002-1825-009'):
        with pytest.raises(ValueError):
            normalize_orcid(bad)


def test_a_ror_id_is_checked_by_format_and_normalised():
    for given in (ROR, f'https://ror.org/{ROR}', f'ROR.org/{ROR}'.replace(
            'ROR.org', 'https://ror.org'), f' {ROR.upper()} '):
        assert normalize_ror(given) == f'https://ror.org/{ROR}'
    for bad in ('13yrm5c26', '03yrm5c2', '03yrm5cl26', 'hello', '03yrm5c2x'):
        with pytest.raises(ValueError):
            normalize_ror(bad)


def test_the_web_page_of_an_organization_is_http_or_https_only():
    assert normalize_url(' https://lab.example.org/about ') == 'https://lab.example.org/about'
    assert normalize_url('HTTP://lab.example.org') == 'HTTP://lab.example.org'
    for bad in ('lab.example.org', 'ftp://lab.example.org', 'javascript:alert(1)',
                '//lab.example.org', 'https://' + 'a' * 500):
        with pytest.raises(ValueError):
            normalize_url(bad)
        # the same refusal as the url of an actor
        with pytest.raises(ValueError):
            Actor(kind='organization', organization='Lab', url=bad)


def test_the_profile_url_is_copied_into_the_url_of_an_account_actor():
    profile = {'organization': 'Lab', 'organization_url': 'https://lab.example.org'}
    filled = fill_actor({'kind': 'user', 'user_id': 'u1', 'role': 'operator'}, profile)
    assert filled['url'] == 'https://lab.example.org'
    typed = fill_actor({'kind': 'user', 'user_id': 'u1', 'url': 'https://mine.example.org'}, profile)
    assert typed['url'] == 'https://mine.example.org'                # typed wins


def test_a_profile_fills_only_the_empty_fields_of_an_account_actor():
    profile = {'full_name': 'Ada L.', 'organization': 'Lab', 'orcid': ORCID,
               'organization_ror': f'https://ror.org/{ROR}'}
    actor = {'kind': 'user', 'user_id': 'u1', 'role': 'operator',
             'organization': 'Typed Org'}
    filled = fill_actor(actor, profile)
    assert filled['name'] == 'Ada L.' and filled['orcid'] == ORCID
    assert filled['organization'] == 'Typed Org'                # typed wins
    assert filled['organization_ror'] == f'https://ror.org/{ROR}'
    assert actor == {'kind': 'user', 'user_id': 'u1', 'role': 'operator',
                     'organization': 'Typed Org'}               # a copy
    person = {'kind': 'person', 'name': 'X'}
    assert fill_actor(person, profile) == person
    redacted = {'kind': 'user', 'user_id': 'u1', 'redacted_at': '2026-01-01T00:00:00Z'}
    assert fill_actor(redacted, profile) == redacted


# THE ROUTES ------------------------------------------------------------------
@pytest.fixture
def world(api, db, auth_headers, member_headers):
    seed_05_catalog(db)
    run(Context(db=db, files=False, log=lambda _m: None), CUTOVER_STEPS)
    c, cid = member_headers({'dbu_zirkus': ['contributor']})
    m, mid = member_headers({'dbu_zirkus': ['moderator']})
    return {'api': api, 'db': db, 'c': c, 'cid': cid, 'm': m, 'mid': mid,
            'admin': auth_headers('admin')}


def patch_me(w, headers, body):
    return w['api'].patch('/users/me', json=body, headers=headers)


def test_the_profile_is_read_and_edited_in_users_me(world):
    w = world
    me = w['api'].get('/users/me', headers=w['c']).json()
    assert me['default_role'] == 'operator'
    assert me['organization'] is None and me['orcid'] is None
    got = patch_me(w, w['c'], {
        'full_name': '  Ada Example ', 'organization': ' Example Lab ',
        'organization_ror': f'https://ror.org/{ROR}',
        'orcid': '0000000218250097', 'default_role': 'supervisor'})
    assert got.status_code == 200, got.text
    body = got.json()
    assert body['full_name'] == 'Ada Example'
    assert body['organization'] == 'Example Lab'
    assert body['organization_ror'] == f'https://ror.org/{ROR}'
    assert body['orcid'] == ORCID and body['default_role'] == 'supervisor'
    assert w['api'].get('/users/me', headers=w['c']).json()['orcid'] == ORCID
    # only what is sent changes; an empty text clears an optional field
    again = patch_me(w, w['c'], {'orcid': '', 'organization': '  '}).json()
    assert again['orcid'] is None and again['organization'] is None
    assert again['organization_ror'] == f'https://ror.org/{ROR}'
    assert again['full_name'] == 'Ada Example'


def test_the_web_page_of_the_organization_is_edited_in_the_profile(world):
    w = world
    assert w['api'].get('/users/me', headers=w['c']).json()['organization_url'] is None
    got = patch_me(w, w['c'], {'organization': 'Lab', 'organization_url': ' https://lab.example.org/ '})
    assert got.status_code == 200, got.text
    assert got.json()['organization_url'] == 'https://lab.example.org/'
    assert w['api'].get('/users/me', headers=w['c']).json()['organization_url'] == 'https://lab.example.org/'
    assert patch_me(w, w['c'], {'orcid': ''}).json()['organization_url'] == 'https://lab.example.org/'
    assert patch_me(w, w['c'], {'organization_url': '  '}).json()['organization_url'] is None


def test_a_new_record_takes_the_profile_url_into_the_you_performer(world):
    w = world
    patch_me(w, w['c'], {'organization': 'Lab', 'organization_url': 'https://lab.example.org'})
    got = w['api'].post(f'/identities/{BEAM}/evidence', headers=w['c'],
                        json=rebound_body(performed_by=[_performer(w['cid'])]))
    assert got.status_code == 201, got.text
    actor = got.json()['performed_by'][0]
    assert actor['organization'] == 'Lab' and actor['url'] == 'https://lab.example.org'
    # a later change of the profile never rewrites the record
    patch_me(w, w['c'], {'organization_url': 'https://other.example.org'})
    stored = w['db']['component_evidence'].find_one({'_id': got.json()['_id']})
    assert stored['performed_by'][0]['url'] == 'https://lab.example.org'


@pytest.mark.parametrize('body', [
    {'orcid': '0000-0002-1825-0098'},               # wrong check digit
    {'orcid': 'nope'},
    {'organization_ror': 'x'},
    {'organization_url': 'lab.example.org'},          # not http or https
    {'organization_url': 'ftp://lab.example.org'},
    {'organization_url': 'https://' + 'a' * 500},
    {'full_name': '   '},                            # the name stays
    {'default_role': 'president'},
    {'role': 'admin'},                               # not a profile field
    {'organization': 'x' * 201},
])
def test_a_bad_profile_is_a_422(world, body):
    assert patch_me(world, world['c'], body).status_code == 422


def test_anonymous_cannot_edit_a_profile(world):
    assert world['api'].patch('/users/me', json={'organization': 'x'}
                              ).status_code == 401


def _performer(user_id, **over):
    return {'kind': 'user', 'user_id': user_id, 'role': 'operator', **over}


def test_a_record_takes_the_profile_when_it_is_written_and_keeps_it(world):
    w = world
    patch_me(w, w['c'], {'full_name': 'Ada Example', 'organization': 'Lab A',
                         'orcid': ORCID})
    body = rebound_body(performed_by=[_performer(w['cid'])])
    got = w['api'].post(f'/identities/{BEAM}/evidence', json=body,
                        headers=w['c'])
    assert got.status_code == 201, got.text
    actor = got.json()['performed_by'][0]
    assert (actor['name'], actor['organization'], actor['orcid']) == (
        'Ada Example', 'Lab A', ORCID)
    eid = got.json()['_id']
    # a typed value wins over the profile
    typed = rebound_body(performed_by=[_performer(
        w['cid'], organization='Typed Org')])
    typed_actor = w['api'].post(f'/identities/{BEAM}/evidence', json=typed,
                                headers=w['c']).json()['performed_by'][0]
    assert typed_actor['organization'] == 'Typed Org'
    assert typed_actor['name'] == 'Ada Example'
    # a later profile change never rewrites the record
    patch_me(w, w['c'], {'organization': 'Lab B', 'orcid': ''})
    stored = w['db']['component_evidence'].find_one({'_id': eid})
    assert stored['performed_by'][0]['organization'] == 'Lab A'
    assert stored['performed_by'][0]['orcid'] == ORCID
    # the bulk route and an edit take the profile as well
    bulk = w['api'].post('/evidence/bulk', headers=w['c'], json={'records': [
        {**rebound_body(performed_by=[_performer(w['cid'])]),
         'identity_id': BEAM}]})
    assert bulk.status_code == 201, bulk.text
    assert bulk.json()['records'][0]['performed_by'][0]['organization'] == 'Lab B'
    draft = w['api'].post(f'/identities/{BEAM}/evidence', headers=w['c'],
                          json=rebound_body(performed_by=[_performer(w['cid'])])
                          ).json()
    patch_me(w, w['c'], {'organization': 'Lab C'})
    edit = copy.deepcopy(rebound_body(performed_by=[_performer(w['cid'])]))
    edited = w['api'].patch(f'/evidence/{draft["_id"]}', json=edit,
                            headers=w['c'])
    assert edited.status_code == 200, edited.text
    # the edit writes the record again: the empty field takes today's profile
    assert edited.json()['performed_by'][0]['organization'] == 'Lab C'


def test_an_origin_written_by_a_person_takes_the_profile(world):
    w = world
    patch_me(w, w['m'], {'full_name': 'Mo Derator', 'organization': 'Crew Ltd'})
    origin = copy.deepcopy(
        w['db']['component_identities'].find_one({'_id': BEAM})['origin'])
    origin['performed_by'] = [_performer(w['mid'])]
    got = w['api'].patch(f'/identities/{BEAM}', json={'origin': origin},
                         headers=w['m'])
    assert got.status_code == 200, got.text
    actor = got.json()['origin']['performed_by'][0]
    assert actor['name'] == 'Mo Derator' and actor['organization'] == 'Crew Ltd'
    patch_me(w, w['m'], {'organization': 'Other'})
    stored = w['db']['component_identities'].find_one({'_id': BEAM})
    assert stored['origin']['performed_by'][0]['organization'] == 'Crew Ltd'


def test_the_redaction_of_an_account_blanks_its_profile_too(world):
    w = world
    patch_me(w, w['c'], {'full_name': 'Ada Example', 'organization': 'Lab A',
                         'orcid': ORCID,
                         'organization_ror': f'https://ror.org/{ROR}',
                         'organization_url': 'https://lab.example.org',
                         'default_role': 'witness'})
    dry = w['api'].post('/actors/redact', json={'user_id': w['cid'],
                                                'dry_run': True},
                        headers=w['admin']).json()
    assert dry['profile'] == 1
    assert w['db']['users'].find_one({'_id': w['cid']})['orcid'] == ORCID
    done = w['api'].post('/actors/redact', json={'user_id': w['cid']},
                         headers=w['admin']).json()
    assert done['profile'] == 1
    account = w['db']['users'].find_one({'_id': w['cid']})
    for key in ('full_name', 'organization', 'organization_ror',
                'organization_url', 'orcid'):
        assert account.get(key) is None, key
    assert account['username'] and account['default_role'] == 'witness'  # stays
    me = w['api'].get('/users/me', headers=w['c'])
    assert me.status_code == 200                                   # still works
    again = w['api'].post('/actors/redact', json={'user_id': w['cid']},
                          headers=w['admin']).json()
    assert again['profile'] == 0


# ACTOR.URL -------------------------------------------------------------------
def test_an_organization_actor_may_carry_a_web_address(world):
    w = world
    lab = {'kind': 'organization', 'organization': 'Test Lab', 'role': 'laboratory',
           'url': ' https://lab.example.org/about '}
    got = w['api'].post(f'/identities/{BEAM}/evidence', headers=w['c'],
                        json=rebound_body(performed_by=[lab]))
    assert got.status_code == 201, got.text
    assert got.json()['performed_by'][0]['url'] == 'https://lab.example.org/about'
    for bad in ('javascript:alert(1)', 'ftp://x.org', 'lab.example.org'):
        refused = w['api'].post(
            f'/identities/{BEAM}/evidence', headers=w['c'],
            json=rebound_body(performed_by=[{**lab, 'url': bad}]))
        assert refused.status_code == 422, bad
    # public like the organisation: the people filter keeps it
    from apps.catalog.people import strip_people
    stripped = strip_people({'performed_by': [{
        'kind': 'user', 'user_id': 'u', 'name': 'N', 'organization': 'O',
        'url': 'https://o.example.org'}]})
    assert stripped == {'performed_by': [{
        'kind': 'user', 'organization': 'O', 'url': 'https://o.example.org'}]}
