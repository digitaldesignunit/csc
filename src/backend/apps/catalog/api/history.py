#!/usr/bin/env python3.13
"""
``GET /identities/{id}/history`` --- the swimlane history of a component
(decision 8.140 g, h; data model spec section 7.1): lanes (the piece, its
parents above, its children below, to ``depth``), each with its events in
time order, and the links where a piece was cut or assembled.

Visibility is applied per lane: a relative the caller may not see is a stub
(``visible: false``, no content), and the lanes beyond twelve are a count.
Only the fields of the events are read (projections): the page is for people
on a metered database. An anonymous caller gets the public tier, no people.
``expand=all`` lists every evidence record as its own event (the data
export, 8.140 h); the default groups them per day and method.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Annotated, Any, Dict, List, Literal, Optional, Set

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.lanes import (
    MAX_LANES,
    cap_lanes,
    first_version,
    lane_events,
    lane_header,
    link_kind,
)
from apps.catalog.models import User
from apps.catalog.people import for_viewer
from apps.catalog.permissions import (
    Viewer,
    can_see_component,
    record_projection,
    withdrawn_projection,
)
from .access import EVER_PUBLISHED, dataset_of, viewer_of
from .auth import get_optional_current_user
from .catalog_common import validate_uuid
from .public_access import (
    ensure_identity_read_access,
    identity_allows_anonymous_read,
    viewer_headers,
)

router = APIRouter()

IDENTITY_FIELDS = {
    '_id': 1, 'catalog_number': 1, 'dataset': 1, 'is_public': 1,
    'parent_identities': 1, 'created_by_user_id': 1,
    'current_snapshot_id': 1, 'withdrawn': 1,
    'exit.kind': 1, 'exit.at': 1, 'exit.at_precision': 1,
    'origin.kind': 1, 'origin.at': 1, 'origin.at_precision': 1,
    'origin.planned': 1,
    'past_cycles.origin.kind': 1, 'past_cycles.origin.at': 1,
    'past_cycles.origin.at_precision': 1, 'past_cycles.exit.kind': 1,
    'past_cycles.exit.at': 1, 'past_cycles.exit.at_precision': 1,
}
SNAPSHOT_FIELDS = {
    '_id': 1, 'identity_id': 1, 'version': 1, 'status': 1,
    'effective_from': 1, 'effective_from_precision': 1, 'name': 1,
    'supersedes': 1, 'superseded_by': 1, 'added_by_user_id': 1,
    'created': 1,
}
EVIDENCE_FIELDS = {
    '_id': 1, 'identity_id': 1, 'method': 1, 'status': 1, 'observed_at': 1,
    'observed_at_precision': 1, 'superseded_by': 1,
    'recorded_by_user_id': 1, 'summary.quantity': 1,
}


async def _projections(request: Request, viewer: Viewer,
                       docs: List[Dict[str, Any]]
                       ) -> Dict[str, Dict[str, Any]]:
    """Per identity doc: how much of it the caller sees (``full``,
    ``tombstone`` or ``None``), and the facts the lane needs about its
    dataset (one query for what was ever published)."""
    if not docs:
        return {}
    ids = [d['_id'] for d in docs]
    ever: Set[str] = set(
        await request.app.mongodb_component_snapshots.distinct(
            'identity_id', {'identity_id': {'$in': ids},
                            'status': {'$in': list(EVER_PUBLISHED)}}))
    out: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        dataset = await dataset_of(request, doc.get('dataset'))
        published = bool(doc.get('current_snapshot_id')) or doc['_id'] in ever
        visible = can_see_component(
            viewer, dataset, is_public=doc.get('is_public') is True,
            published=published,
            created_by_user_id=doc.get('created_by_user_id'))
        if not visible:
            seen = None
        elif doc.get('withdrawn'):
            seen = withdrawn_projection(viewer, dataset,
                                        component_visible=True)
        else:
            seen = 'full'
        out[doc['_id']] = {'seen': seen, 'dataset': dataset,
                           'visible': visible}
    return out


def _rank(doc: Dict[str, Any]) -> tuple:
    number = doc.get('catalog_number')
    return (number is None, number if isinstance(number, int) else 0,
            doc['_id'])


@router.get('/identities/{identity_id}/history',
            summary='Lanes and events of a component and its relatives')
async def get_identity_history(
    request: Request,
    current_user: Annotated[Optional[User],
                            Depends(get_optional_current_user)],
    identity_id: str,
    depth: int = Query(1, ge=1, le=2, description='generations up and down'),
    expand: Literal['groups', 'all'] = Query(
        'groups', description='groups: evidence per day and method; all: '
                              'every record its own event'),
):
    """The piece is the middle lane (level 0), parents have negative levels
    and children positive ones. Every lane has ``id``, ``role``, ``level``
    and ``visible``; a visible one also its header and ``events``. ``links``
    join a parent and a child lane (``cut``: one parent; ``assemble``:
    several) at the child's first version. ``more`` counts the lanes left
    out beyond twelve."""
    validate_uuid(identity_id, label='identity id')
    viewer = viewer_of(current_user)
    root = await ensure_identity_read_access(
        request, identity_id, current_user, projection=IDENTITY_FIELDS)
    identities = request.app.mongodb_component_identities
    try:
        found: Dict[str, Dict[str, Any]] = {root['_id']: {
            'doc': root, 'level': 0, 'seen': 'full'}}
        root_seen = (await _projections(request, viewer, [root]))[root['_id']]
        found[root['_id']]['dataset'] = root_seen['dataset']
        found[root['_id']]['visible'] = True

        async def collect(ids: List[str], level: int, by_parent: bool
                          ) -> List[str]:
            if not ids:
                return []
            query = ({'parent_identities': {'$in': ids}} if by_parent
                     else {'_id': {'$in': ids}})
            docs = [d for d in await identities.find(
                query, IDENTITY_FIELDS).to_list(length=None)
                if d['_id'] not in found]
            seen = await _projections(request, viewer, docs)
            for doc in docs:
                found[doc['_id']] = {'doc': doc, 'level': level,
                                     **seen[doc['_id']]}
            # only a lane the caller sees leads further
            return [d['_id'] for d in docs
                    if seen[d['_id']]['seen'] == 'full']

        up = [p for p in root.get('parent_identities') or []]
        for step in range(1, depth + 1):
            full = await collect(up, -step, by_parent=False)
            up = [p for pid in full
                  for p in found[pid]['doc'].get('parent_identities') or []]
        down = [root['_id']]
        for step in range(1, depth + 1):
            down = await collect(down, step, by_parent=True)

        # which lanes: the piece, then by distance, then by number
        ordered = sorted(found, key=lambda i: (
            abs(found[i]['level']), found[i]['level'] > 0,
            _rank(found[i]['doc'])))
        kept, more = cap_lanes(ordered, MAX_LANES)
        full_ids = [i for i in kept if found[i]['seen'] == 'full']
        snapshots = await request.app.mongodb_component_snapshots.find(
            {'identity_id': {'$in': full_ids}},
            SNAPSHOT_FIELDS).to_list(length=None)
        evidence = await request.app.mongodb_component_evidence.find(
            {'identity_id': {'$in': full_ids}},
            EVIDENCE_FIELDS).to_list(length=None)
    except PyMongoError as exc:
        print(f'[ERROR] get_identity_history DB error: {exc}')
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail='Internal server error')

    def seen(kind: str, records: List[Dict[str, Any]], key: str
             ) -> Dict[str, List[Dict[str, Any]]]:
        """The records of each full lane the caller sees in full."""
        out: Dict[str, List[Dict[str, Any]]] = {i: [] for i in full_ids}
        for record in records:
            lane = found[record['identity_id']]
            shown = record_projection(
                viewer, lane['dataset'], kind=kind,
                status=record.get('status') or 'published',
                author_id=record.get(key),
                component_visible=lane['visible'])
            if shown == 'full':
                out[record['identity_id']].append(record)
        return out

    visible_snapshots = seen('snapshot', snapshots, 'added_by_user_id')
    visible_evidence = seen('evidence', evidence, 'recorded_by_user_id')

    lanes: List[Dict[str, Any]] = []
    for lane_id in sorted(kept, key=lambda i: (found[i]['level'],
                                               _rank(found[i]['doc']))):
        lane = found[lane_id]
        entry: Dict[str, Any] = {
            'id': lane_id, 'level': lane['level'],
            'role': ('piece' if lane['level'] == 0 else
                     'parent' if lane['level'] < 0 else 'child'),
            'visible': lane['seen'] == 'full'}
        if lane['seen'] == 'full':
            doc = lane['doc']
            entry.update(lane_header(doc, visible_snapshots[lane_id]))
            entry['events'] = lane_events(
                doc, visible_snapshots[lane_id], visible_evidence[lane_id],
                expand=expand)
        else:
            entry['label'] = 'not visible'
            if lane['seen'] == 'tombstone':
                entry['withdrawn'] = True
                entry['withdrawn_at'] = (lane['doc'].get('withdrawn')
                                         or {}).get('at')
                entry['catalog_number'] = lane['doc'].get('catalog_number')
        lanes.append(entry)

    links: List[Dict[str, Any]] = []
    for lane_id in kept:
        child = found[lane_id]['doc']
        for parent_id in child.get('parent_identities') or []:
            if parent_id not in kept:
                continue
            link: Dict[str, Any] = {'kind': link_kind(child),
                                    'from': parent_id, 'to': lane_id}
            first = first_version(visible_snapshots.get(lane_id) or [])
            if first is not None:
                link.update({'at': first.get('effective_from'),
                             'precision': first.get(
                                 'effective_from_precision'),
                             'version_id': first['_id']})
            links.append(link)

    body = for_viewer({'root': identity_id, 'depth': depth, 'expand': expand,
                       'lanes': lanes, 'links': links, 'more': more},
                      current_user)
    anonymous_public = (current_user is None
                        and identity_allows_anonymous_read(root))
    return JSONResponse(status_code=200, content=body,
                        headers=viewer_headers(
                            anonymous_public=anonymous_public))
