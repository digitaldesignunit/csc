"""Create, list, read and delete a component through the 0.5 API."""

from support import panel_payload


def test_create_list_compose_delete(api, db, auth_headers):
    user = auth_headers('user')
    admin = auth_headers('admin')

    created = api.post('/identities', json=panel_payload(), headers=user)
    assert created.status_code == 201, created.text
    passport = created.json()
    identity_id = passport['identity']['_id']
    assert passport['snapshots'][0]['version'] == 0
    assert db['component_identities'].count_documents({}) == 1

    # new components wait for validation, so the default list hides them
    listed = api.get('/identities', headers=user).json()
    assert identity_id not in str(listed)
    listed_all = api.get('/identities', params={'validated': 0},
                         headers=user).json()
    assert identity_id in str(listed_all)

    compose = api.get(f'/identities/{identity_id}/compose', headers=user)
    assert compose.status_code == 200
    assert compose.json()['identity']['material'] == 'corian'

    assert api.delete(f'/identities/{identity_id}',
                      headers=user).status_code == 403
    assert api.delete(f'/identities/{identity_id}',
                      headers=admin).status_code == 200
    assert db['component_identities'].count_documents({}) == 0
    assert db['component_snapshots'].count_documents({}) == 0


def test_anonymous_cannot_create(api, db):
    assert api.post('/identities', json=panel_payload()).status_code == 401
