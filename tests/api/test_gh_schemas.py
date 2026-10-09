"""The create schemas served to clients are the 0.6 bodies (8.95 12)."""

from __future__ import annotations


def test_create_identity_schema_is_the_0_6_body(api):
    response = api.get('/schema/create-identity')
    assert response.status_code == 200
    schema = response.json()
    props = schema['properties']
    assert {'id', 'dataset', 'original_function', 'material', 'origin',
            'parent_identities', 'snapshot'} <= set(props)
    # none of the 0.5 fields is offered any more
    assert not {'type', 'complexity', 'assembly', 'iframe', 'pca_frame',
                'bbx', 'bbx_origin', 'validated', 'condition',
                'salvage_source', 'salvaged_at', 'marker_points'} & set(props)
    assert schema['required'] == ['dataset', 'snapshot']
    assert props['snapshot']['$ref'] == '#/$defs/SnapshotDraftBody'
    snapshot = schema['$defs']['SnapshotDraftBody']
    assert {'geometry', 'capture', 'fragment', 'quantity', 'effective_from',
            'color', 'location', 'notes'} <= set(snapshot['properties'])
    assert 'Origin' in schema['$defs']


def test_create_snapshot_schema_is_the_draft_body(api):
    response = api.get('/schema/create-snapshot')
    assert response.status_code == 200
    schema = response.json()
    assert schema['title'] == 'SnapshotDraftBody'
    assert schema['additionalProperties'] is False
    assert not {'_id', 'id', 'identity_id', 'iframe', 'pca_frame', 'bbx',
                'virtual', 'condition', 'marker_points'} & set(
                    schema['properties'])
    assert schema['required'] == ['geometry']


def test_create_schemas_answer_a_conditional_request(api):
    for path in ('/schema/create-identity', '/schema/create-snapshot'):
        first = api.get(path)
        etag = first.headers['etag']
        again = api.get(path, headers={'If-None-Match': etag})
        assert again.status_code == 304, path
