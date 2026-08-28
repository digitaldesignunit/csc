"""Tests for provenance graph construction."""

from apps.catalog.provenance import (
    build_provenance_graph,
    identity_node_id,
    snapshot_node_id,
)


def test_provenance_graph_links_parent_child_and_snapshot_versions():
    parent_id = 'parent-1'
    child_id = 'child-1'
    snap_a = 'snap-a'
    snap_b = 'snap-b'
    child_snap = 'snap-c'

    graph = build_provenance_graph(
        root_identity_id=parent_id,
        identities={
            parent_id: {
                '_id': parent_id,
                'catalog_number': 1,
                'type': 'beam',
                'consumed_at': '2026-01-01T00:00:00Z',
                'current_snapshot_id': snap_b,
                'parent_identities': None,
            },
            child_id: {
                '_id': child_id,
                'catalog_number': 2,
                'type': 'beam',
                'consumed_at': None,
                'current_snapshot_id': child_snap,
                'parent_identities': [parent_id],
            },
        },
        snapshots_by_identity={
            parent_id: [
                {
                    '_id': snap_b,
                    'identity_id': parent_id,
                    'version': 1,
                    'virtual': False,
                    'validated': True,
                    'name': 'Parent v1',
                },
                {
                    '_id': snap_a,
                    'identity_id': parent_id,
                    'version': 0,
                    'virtual': False,
                    'validated': True,
                    'name': 'Parent v0',
                },
            ],
            child_id: [
                {
                    '_id': child_snap,
                    'identity_id': child_id,
                    'version': 0,
                    'virtual': False,
                    'validated': True,
                    'name': 'Child v0',
                },
            ],
        },
    )

    assert graph['root_identity_id'] == parent_id
    node_ids = {node['id'] for node in graph['nodes']}
    assert identity_node_id(parent_id) in node_ids
    assert identity_node_id(child_id) in node_ids
    assert snapshot_node_id(snap_a) in node_ids
    assert snapshot_node_id(snap_b) in node_ids

    parent_node = next(
        node for node in graph['nodes'] if node['id'] == identity_node_id(parent_id)
    )
    assert parent_node['is_root'] is True
    assert parent_node['consumed_at'] == '2026-01-01T00:00:00Z'
    assert parent_node['name'] == 'Parent v1'

    kinds = {(edge['kind'], edge['source'], edge['target']) for edge in graph['edges']}
    assert (
        'parent',
        identity_node_id(parent_id),
        identity_node_id(child_id),
    ) in kinds
    assert (
        'has_snapshot',
        identity_node_id(parent_id),
        snapshot_node_id(snap_a),
    ) in kinds
    assert (
        'version',
        snapshot_node_id(snap_a),
        snapshot_node_id(snap_b),
    ) in kinds


def test_provenance_graph_skips_parent_outside_collected_set():
    child_id = 'child-1'
    graph = build_provenance_graph(
        root_identity_id=child_id,
        identities={
            child_id: {
                '_id': child_id,
                'current_snapshot_id': None,
                'parent_identities': ['missing-parent'],
            },
        },
        snapshots_by_identity={},
    )

    assert graph['edges'] == []
    assert len(graph['nodes']) == 1
    assert graph['nodes'][0]['is_root'] is True
