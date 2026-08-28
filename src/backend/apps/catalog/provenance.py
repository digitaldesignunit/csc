"""Provenance graph: identity lineage plus snapshot version chains."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


IDENTITY_NODE_PREFIX = 'identity:'
SNAPSHOT_NODE_PREFIX = 'snapshot:'

DEFAULT_PROVENANCE_DEPTH = 8
MAX_PROVENANCE_DEPTH = 16


def identity_node_id(identity_id: str) -> str:
    return f'{IDENTITY_NODE_PREFIX}{identity_id}'


def snapshot_node_id(snapshot_id: str) -> str:
    return f'{SNAPSHOT_NODE_PREFIX}{snapshot_id}'


def _as_id_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    ids: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            ids.append(text)
    return ids


def _current_snapshot_name(
    identity_doc: Dict[str, Any],
    snapshots: List[Dict[str, Any]],
) -> Optional[str]:
    current_id = identity_doc.get('current_snapshot_id')
    if current_id:
        for snap in snapshots:
            if str(snap.get('_id')) == str(current_id):
                name = snap.get('name')
                if isinstance(name, str) and name.strip():
                    return name.strip()
    if snapshots:
        name = snapshots[0].get('name')
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def build_provenance_graph(
    *,
    root_identity_id: str,
    identities: Dict[str, Dict[str, Any]],
    snapshots_by_identity: Dict[str, Iterable[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Build a directed provenance graph.

    Nodes: identities and their snapshots.
    Edges:
      - ``parent``: parent identity -> child identity
      - ``has_snapshot``: identity -> first (lowest-version) snapshot
      - ``version``: snapshot vN -> snapshot vN+1
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    for ident_id, ident in identities.items():
        raw_snaps = list(snapshots_by_identity.get(ident_id) or [])
        snaps = sorted(
            raw_snaps,
            key=lambda row: (
                int(row.get('version') or 0),
                str(row.get('_id') or ''),
            ),
        )
        current_id = str(ident.get('current_snapshot_id') or '')
        nodes.append(
            {
                'id': identity_node_id(ident_id),
                'kind': 'identity',
                'identity_id': ident_id,
                'catalog_number': ident.get('catalog_number'),
                'name': _current_snapshot_name(ident, snaps),
                'type': ident.get('type'),
                'consumed_at': ident.get('consumed_at'),
                'is_root': ident_id == root_identity_id,
            }
        )
        for parent_id in _as_id_list(ident.get('parent_identities')):
            if parent_id not in identities:
                continue
            edges.append(
                {
                    'id': f'parent:{parent_id}:{ident_id}',
                    'source': identity_node_id(parent_id),
                    'target': identity_node_id(ident_id),
                    'kind': 'parent',
                }
            )

        prev_snapshot_id: Optional[str] = None
        for snap in snaps:
            snapshot_id = str(snap.get('_id') or '')
            if not snapshot_id:
                continue
            nodes.append(
                {
                    'id': snapshot_node_id(snapshot_id),
                    'kind': 'snapshot',
                    'snapshot_id': snapshot_id,
                    'identity_id': ident_id,
                    'version': int(snap.get('version') or 0),
                    'virtual': bool(snap.get('virtual')),
                    'validated': bool(snap.get('validated')),
                    'is_current': snapshot_id == current_id,
                    'name': snap.get('name'),
                }
            )
            if prev_snapshot_id is None:
                edges.append(
                    {
                        'id': f'has_snapshot:{ident_id}:{snapshot_id}',
                        'source': identity_node_id(ident_id),
                        'target': snapshot_node_id(snapshot_id),
                        'kind': 'has_snapshot',
                    }
                )
            else:
                edges.append(
                    {
                        'id': f'version:{prev_snapshot_id}:{snapshot_id}',
                        'source': snapshot_node_id(prev_snapshot_id),
                        'target': snapshot_node_id(snapshot_id),
                        'kind': 'version',
                    }
                )
            prev_snapshot_id = snapshot_id

    return {
        'root_identity_id': root_identity_id,
        'nodes': nodes,
        'edges': edges,
    }
