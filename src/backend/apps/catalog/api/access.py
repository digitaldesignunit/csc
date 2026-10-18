#!/usr/bin/env python3.13
"""
Who may see and do what, applied to requests (data model spec section 3.6,
section 7.0; plan P3).

``permissions.py`` holds the pure rules; this module loads what they need
(the datasets, the target's status and author), answers reads with the
visibility rule and writes with ``require(action, ...)``. Enforcement lives
only here; the frontend merely hides controls.

A piece the caller cannot see is not hidden behind a 404 (8.11): anonymous
callers get 401 ("not public, sign in"), signed-in callers 403 ("no access").
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Tuple, Union

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from fastapi import HTTPException, Request, status

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Dataset
from apps.catalog.evidence.projection import evidence_tombstone
from apps.catalog.models import User
from apps.catalog.permissions import (
    ANONYMOUS,
    Target,
    Viewer,
    can,
    can_see_component,
    dataset_roles,
    record_projection,
    withdrawn_projection,
)

NOT_PUBLIC = 'This component is not public. Sign in to view it.'
NO_ACCESS = 'You have no access to this component.'
EVER_PUBLISHED = ('published', 'withdrawn')


def viewer_of(user: Optional[User]) -> Viewer:
    if user is None or getattr(user, 'disabled', False):
        return ANONYMOUS
    return Viewer(user_id=user.id, role=user.role)


# DATASETS --------------------------------------------------------------------
async def load_datasets(request: Request) -> Dict[str, Dataset]:
    """Every dataset by slug, read once per request (there are few)."""
    cached = getattr(request.state, 'csc_datasets', None)
    if cached is not None:
        return cached
    docs = await request.app.mongodb_datasets.find({}).to_list(length=None)
    datasets = {d['_id']: Dataset.model_validate(d) for d in docs}
    request.state.csc_datasets = datasets
    return datasets


def _unknown_dataset(slug: Optional[str]) -> Dataset:
    """A dataset the catalog does not know: members only, nobody's."""
    return Dataset.model_validate({
        '_id': slug or 'unknown', 'name': slug or 'unknown',
        'visibility': 'members', 'members': [],
        'created': '1970-01-01T00:00:00Z',
        'lastmodified': '1970-01-01T00:00:00Z'})


async def dataset_of(request: Request, slug: Optional[str]) -> Dataset:
    return (await load_datasets(request)).get(slug) or _unknown_dataset(slug)


def visible_dataset_slugs(viewer: Viewer,
                          datasets: Iterable[Dataset]) -> Tuple[str, ...]:
    """Datasets whose published components the viewer sees in full:
    member of, or ``catalog`` while signed in (3.6)."""
    return tuple(sorted(
        d.id for d in datasets
        if dataset_roles(viewer, d)
        or (viewer.logged_in and d.visibility == 'catalog')))


async def visible_identity_match(request: Request,
                                 viewer: Viewer) -> Dict[str, Any]:
    """The 3.6 visibility rule as a match on identities, for every list,
    count, stats, map and graph query. Admin sees everything."""
    if viewer.is_admin:
        return {}
    if not viewer.logged_in:
        return {'is_public': True}
    datasets = (await load_datasets(request)).values()
    slugs = visible_dataset_slugs(viewer, datasets)
    return {'$or': [{'dataset': {'$in': list(slugs)}}, {'is_public': True}]}


def and_match(*matches: Dict[str, Any]) -> Dict[str, Any]:
    """Combine match documents without one overwriting another's keys."""
    parts = [m for m in matches if m]
    if not parts:
        return {}
    return parts[0] if len(parts) == 1 else {'$and': parts}


# READS -----------------------------------------------------------------------
async def identity_ever_published(request: Request,
                                  identity: Dict[str, Any]) -> bool:
    """Section 3.1.5: an identity is published once any snapshot of it was."""
    if identity.get('current_snapshot_id'):
        return True
    found = await request.app.mongodb_component_snapshots.find_one(
        {'identity_id': identity['_id'],
         'status': {'$in': list(EVER_PUBLISHED)}},
        {'_id': 1})
    return found is not None


UNREVIEWED = ('This dataset has not been reviewed by an admin yet: it stays '
              'visible to its members only, and its pieces cannot be made '
              'public until it is reviewed.')


def refuse_unreviewed(dataset: Dataset, viewer: Viewer) -> None:
    """8.139 c: a dataset an admin has not reviewed cannot be `catalog` and
    its pieces cannot be public. An admin overrides (they can mark it
    reviewed anyway)."""
    if not dataset.reviewed and not viewer.is_admin:
        raise HTTPException(status_code=409, detail=UNREVIEWED)


def deny_read(viewer: Viewer) -> HTTPException:
    if not viewer.logged_in:
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail=NOT_PUBLIC,
                             headers={'WWW-Authenticate': 'Bearer'})
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                         detail=NO_ACCESS)


async def component_visible(request: Request, viewer: Viewer,
                            identity: Dict[str, Any]) -> bool:
    dataset = await dataset_of(request, identity.get('dataset'))
    return can_see_component(
        viewer, dataset,
        is_public=identity.get('is_public') is True,
        published=await identity_ever_published(request, identity),
        created_by_user_id=identity.get('created_by_user_id'))


class TombstoneHit(Exception):
    """Raised where a caller sees a withdrawn record only as a tombstone
    (8.17); the app answers 200 with the tombstone body."""

    def __init__(self, body: Dict[str, Any]):
        super().__init__('tombstone')
        self.body = body


def not_found(what: str) -> HTTPException:
    """The one wording of a record that is not there (decision 8.158)."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                         detail=f'{what} not found')


def check_id(value: Any, what: str) -> str:
    """A malformed id is a record that is not there: 404, not 400."""
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise not_found(what)
    return str(value)


async def raise_if_purged(request: Request, record_id: str,
                          what: str) -> None:
    """A purged id answers 410 Gone, an unknown one 404 (3.1.4)."""
    stub = await request.app.mongodb_purged_records.find_one(
        {'_id': record_id}, {'purged_at': 1})
    if stub is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE,
                            detail=f'{what} {record_id} was purged on '
                                   f'{stub.get("purged_at")}')
    raise not_found(what)


async def find_identity(request: Request, identity_id: str,
                        projection: Optional[Dict[str, int]] = None,
                        what: str = 'Identity') -> Dict[str, Any]:
    """The identity document; 404 / 410 when it is not there. No access
    check: ``load_identity`` is the entry for a route."""
    check_id(identity_id, what)
    if projection is not None:
        projection = {**projection, 'dataset': 1, 'is_public': 1,
                      'current_snapshot_id': 1, 'created_by_user_id': 1,
                      'withdrawn': 1, 'catalog_number': 1}
    doc = await request.app.mongodb_component_identities.find_one(
        {'_id': identity_id}, projection)
    if doc is None:
        await raise_if_purged(request, identity_id, what)
    return doc


def identity_tombstone(identity: Dict[str, Any]) -> Dict[str, Any]:
    """What a withdrawn identity shows outside its dataset (8.17): never
    the reason."""
    withdrawn = identity.get('withdrawn') or {}
    return {'_id': identity['_id'], 'kind': 'identity',
            'status': 'withdrawn', 'withdrawn_at': withdrawn.get('at'),
            'catalog_number': identity.get('catalog_number'),
            'identity_id': identity['_id'],
            'current_snapshot_id': identity.get('current_snapshot_id'),
            'duplicate_of': withdrawn.get('duplicate_of'), 'version': None}


def snapshot_tombstone(snapshot: Dict[str, Any],
                       identity: Dict[str, Any]) -> Dict[str, Any]:
    if snapshot.get('status') == 'withdrawn':
        at = snapshot.get('status_changed_at')
    else:                                   # a snapshot of a withdrawn piece
        at = (identity.get('withdrawn') or {}).get('at')
    return {'_id': snapshot['_id'], 'kind': 'snapshot',
            'status': 'withdrawn', 'withdrawn_at': at,
            'catalog_number': identity.get('catalog_number'),
            'identity_id': identity['_id'],
            'current_snapshot_id': identity.get('current_snapshot_id'),
            'duplicate_of': (identity.get('withdrawn') or {}).get(
                'duplicate_of'),
            'version': snapshot.get('version')}


async def identity_projection(request: Request, viewer: Viewer,
                              identity: Dict[str, Any]) -> Optional[str]:
    """'full', 'tombstone' (withdrawn, outside D) or None (not visible)."""
    if not await component_visible(request, viewer, identity):
        return None
    if not identity.get('withdrawn'):
        return 'full'
    dataset = await dataset_of(request, identity.get('dataset'))
    return withdrawn_projection(viewer, dataset, component_visible=True)


@dataclass
class Loaded:
    """What a ``load_<kind>`` returns: the record, the identity it belongs to
    (loaded once, passed on), the viewer, and for a dataset the dataset."""
    record: Any
    viewer: Viewer
    identity: Optional[Dict[str, Any]] = None
    dataset: Optional[Dataset] = None


Action = Union[str, Callable[[Dict[str, Any]], str]]


def _action_of(action: Action, record: Dict[str, Any]) -> str:
    """The action, or a function of the record where the action depends on
    its state (a submit is ``submit_snapshot`` of a draft, ...)."""
    return action(record) if callable(action) else action


async def load_identity(request: Request, user: Optional[User],
                        identity_id: str, action: Optional[Action] = 'read',
                        *, projection: Optional[Dict[str, int]] = None
                        ) -> Loaded:
    """One identity for a route (decision 8.158). A malformed id is 404, a
    missing one 404 "Identity not found", a purged one 410. ``read``: the
    visibility rule (401 / 403) and the tombstone of a withdrawn piece
    outside its dataset (8.17); any other action: ``require(action, ...)``;
    ``action=None``: the route does the permission check itself (a delete is
    a purge or not)."""
    viewer = viewer_of(user)
    doc = await find_identity(request, identity_id, projection)
    if action == 'read':
        seen = await identity_projection(request, viewer, doc)
        if seen is None:
            raise deny_read(viewer)
        if seen == 'tombstone':
            raise TombstoneHit(identity_tombstone(doc))
    elif action is not None:
        await require(request, user, _action_of(action, doc), identity=doc)
    return Loaded(record=doc, identity=doc, viewer=viewer)


async def snapshot_projection(request: Request, viewer: Viewer,
                              snapshot: Dict[str, Any],
                              identity: Optional[Dict[str, Any]] = None
                              ) -> Tuple[Optional[str], Dict[str, Any]]:
    """How much of a snapshot the viewer sees ('full', 'tombstone' or
    None), and its identity. The snapshots of a withdrawn identity are
    tombstones outside D, whatever their own status (8.17)."""
    if identity is None:
        identity = await find_identity(request, str(snapshot['identity_id']))
    dataset = await dataset_of(request, identity.get('dataset'))
    visible = await component_visible(request, viewer, identity)
    projection = record_projection(
        viewer, dataset, kind='snapshot',
        status=snapshot.get('status') or 'published',
        author_id=snapshot.get('added_by_user_id'),
        component_visible=visible)
    if projection == 'full' and identity.get('withdrawn'):
        projection = withdrawn_projection(viewer, dataset,
                                          component_visible=visible)
    return projection, identity


async def find_snapshot(request: Request, snapshot_id: str) -> Dict[str, Any]:
    """The snapshot document; 404 / 410 when it is not there. No access
    check: ``load_snapshot`` is the entry for a route."""
    check_id(snapshot_id, 'Snapshot')
    doc = await request.app.mongodb_component_snapshots.find_one(
        {'_id': snapshot_id})
    if doc is None:
        await raise_if_purged(request, snapshot_id, 'Snapshot')
    if not doc.get('identity_id'):
        raise HTTPException(status_code=500,
                            detail=f'Snapshot {snapshot_id} has no '
                                   'identity_id')
    return doc


async def load_snapshot(request: Request, user: Optional[User],
                        snapshot_id: str, action: Optional[Action] = 'read',
                        *, allow_tombstone: bool = False, files: bool = False,
                        frozen: bool = False) -> Loaded:
    """One snapshot and its identity for a route (decision 8.158). ``read``:
    the snapshot if the caller sees it in full; a tombstone viewer gets the
    tombstone where JSON is served (``allow_tombstone``), files of withdrawn
    records are for members only (8.17). Any other action: ``require``.
    ``files``: a write to the snapshot's files, which needs the snapshot to
    be visible in full; ``frozen`` adds that the geometry of a published
    snapshot is frozen for everyone (409, 6.6). ``action=None``: the route
    does the permission check itself (a publish needs the parents' datasets,
    a delete is a purge or not)."""
    viewer = viewer_of(user)
    doc = await find_snapshot(request, snapshot_id)
    projection, identity = await snapshot_projection(request, viewer, doc)
    if action == 'read':
        if projection == 'tombstone':
            if allow_tombstone:
                raise TombstoneHit(snapshot_tombstone(doc, identity))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Withdrawn: its files are for dataset members only.')
        if projection != 'full':
            raise deny_read(viewer)
        return Loaded(record=doc, identity=identity, viewer=viewer)
    if files and projection != 'full':
        raise deny_read(viewer)
    if frozen:
        ensure_unfrozen(doc)
    if action is not None:
        await require(request, user, _action_of(action, doc),
                      identity=identity, snapshot=doc)
    return Loaded(record=doc, identity=identity, viewer=viewer)


# WRITES ----------------------------------------------------------------------
def deny_write(viewer: Viewer, action: str) -> HTTPException:
    if not viewer.logged_in:
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                             detail='Authentication required',
                             headers={'WWW-Authenticate': 'Bearer'})
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                         detail=f'Not allowed: {action}')


async def require(request: Request, user: Optional[User], action: str, *,
                  identity: Optional[Dict[str, Any]] = None,
                  snapshot: Optional[Dict[str, Any]] = None,
                  evidence: Optional[Dict[str, Any]] = None,
                  dataset: Optional[Dataset] = None,
                  invitation: Optional[Dict[str, Any]] = None) -> Viewer:
    """
    Section 7.0 for one action: builds the ``Target`` from the documents
    and raises 401 / 403 unless ``can`` allows it. Read access to the
    component is part of every action on it.
    """
    viewer = viewer_of(user)
    if snapshot is not None and identity is None:
        identity = await find_identity(request, str(snapshot['identity_id']))
    if evidence is not None and identity is None:
        identity = await find_identity(request, str(evidence['identity_id']))
    if dataset is None:
        dataset = await dataset_of(request, (identity or {}).get('dataset'))
    readable = True
    published = True
    if identity is not None:
        readable = await component_visible(request, viewer, identity)
        published = await identity_ever_published(request, identity)
        if not readable and not viewer.is_admin:
            raise deny_read(viewer)
    performers: tuple = ()
    if snapshot is not None:
        kind, status_, author = ('snapshot', snapshot.get('status'),
                                 snapshot.get('added_by_user_id'))
    elif evidence is not None:
        kind, status_, author = ('evidence', evidence.get('status'),
                                 evidence.get('recorded_by_user_id'))
        performers = tuple(a['user_id'] for a in
                           evidence.get('performed_by') or []
                           if a.get('user_id'))
    elif identity is not None:
        kind, status_, author = ('identity', None,
                                 identity.get('created_by_user_id'))
    elif invitation is not None:
        kind, status_, author = ('invitation', None,
                                 invitation.get('created_by_user_id'))
    else:
        kind, status_, author = ('dataset', None, None)
    target = Target(
        dataset=dataset, kind=kind, status=status_, author_id=author,
        identity_published=published,
        reserved_by=(identity or {}).get('reserved') or None,
        readable=readable, performer_ids=performers,
        correction=bool(kind == 'evidence' and evidence.get('supersedes')))
    if not can(viewer, action, target):
        raise deny_write(viewer, action)
    return viewer


def ensure_unfrozen(snapshot: Dict[str, Any]) -> None:
    """Geometry of a published snapshot is frozen for everyone, admin
    included (6.6, I21): a change is a correction."""
    if snapshot.get('status') in EVER_PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='The snapshot is published and its geometry is frozen; '
                   'record a correction (POST /snapshots/{sid}/supersede).')


_TOMBSTONE_SUMMARY_KEYS = (
    '_id', 'identity_id', 'version', 'effective_from',
    'effective_from_precision', 'status_changed_at', 'supersedes',
    'superseded_by', 'created', 'lastmodified')


async def visible_snapshot_docs(request: Request, user: Optional[User],
                                identity: Dict[str, Any],
                                docs: Iterable[Dict[str, Any]], *,
                                tombstones: bool = False) -> list:
    """
    The snapshots of one identity the caller may see in full: drafts /
    pending / rejected only for their author and moderator(D) (7.0).
    With ``tombstones``, withdrawn ones seen from outside D are kept as
    bare rows (version, dates, ``status: withdrawn``, no content, 8.17) ---
    for version lists and graphs, never for the passport. The documents
    need ``status`` and ``added_by_user_id``.
    """
    docs = list(docs)
    viewer = viewer_of(user)
    if viewer.is_admin:
        return docs
    out = []
    for doc in docs:
        seen, _ = await snapshot_projection(request, viewer, doc, identity)
        if seen == 'full':
            out.append(doc)
        elif seen == 'tombstone' and tombstones:
            out.append({**{k: doc[k] for k in _TOMBSTONE_SUMMARY_KEYS
                           if k in doc},
                        'status': 'withdrawn', 'name': None})
    return out


async def visible_identity_ids(request: Request, viewer: Viewer,
                               ids: Iterable[str]) -> set:
    """Of the given identity ids, those the viewer may see (the map)."""
    ids = list(ids)
    if viewer.is_admin:
        return set(ids)
    match = and_match({'_id': {'$in': ids}},
                      await visible_identity_match(request, viewer))
    docs = await request.app.mongodb_component_identities.find(
        match, {'_id': 1}).to_list(length=None)
    return {d['_id'] for d in docs}


# THE OTHER KINDS -------------------------------------------------------------
async def evidence_projection(request: Request, viewer: Viewer,
                              record: Dict[str, Any],
                              identity: Dict[str, Any]) -> Optional[str]:
    """'full', 'tombstone' or None. The records of a withdrawn identity
    are tombstones outside D whatever their own status (8.17)."""
    dataset = await dataset_of(request, identity.get('dataset'))
    visible = await component_visible(request, viewer, identity)
    projection = record_projection(
        viewer, dataset, kind='evidence',
        status=record.get('status') or 'published',
        author_id=record.get('recorded_by_user_id'),
        component_visible=visible)
    if projection == 'full' and identity.get('withdrawn'):
        projection = withdrawn_projection(viewer, dataset,
                                          component_visible=visible)
    return projection


async def find_evidence(request: Request, evidence_id: str) -> Dict[str, Any]:
    """The evidence record; 404 / 410 when it is not there. No access
    check: ``load_evidence`` is the entry for a route."""
    check_id(evidence_id, 'Evidence')
    doc = await request.app.mongodb_component_evidence.find_one(
        {'_id': evidence_id})
    if doc is None:
        await raise_if_purged(request, evidence_id, 'Evidence')
    return doc


async def load_evidence(request: Request, user: Optional[User],
                        evidence_id: str, action: Optional[Action] = 'read',
                        *, allow_tombstone: bool = False,
                        files: bool = False) -> Loaded:
    """One evidence record and its identity for a route (decision 8.158).
    ``read``: the record if the caller sees it in full; a tombstone viewer
    gets the tombstone where JSON is served, files and writes are for members
    only (8.17). Any other action: ``require``; ``files`` adds that the
    record has to be visible in full; ``action=None``: the route does the
    permission check itself."""
    viewer = viewer_of(user)
    record = await find_evidence(request, evidence_id)
    identity = await find_identity(request, str(record['identity_id']))
    if action != 'read':
        if files and await evidence_projection(
                request, viewer, record, identity) != 'full':
            raise deny_read(viewer)
        if action is not None:
            await require(request, user, _action_of(action, record),
                          identity=identity, evidence=record)
        return Loaded(record=record, identity=identity, viewer=viewer)
    projection = await evidence_projection(request, viewer, record, identity)
    if projection == 'full':
        return Loaded(record=record, identity=identity, viewer=viewer)
    if projection == 'tombstone':
        if allow_tombstone:
            raise TombstoneHit(evidence_tombstone(record, identity))
        raise HTTPException(
            status_code=403,
            detail='Withdrawn: its files are for dataset members only.')
    raise deny_read(viewer)


NO_CURRENT_STATE = 'The component has no current state.'


async def load_current_snapshot(request: Request,
                                identity: Dict[str, Any]) -> Dict[str, Any]:
    """The current snapshot of an identity, which has to be there: 409 when
    the identity names none or names one that is gone (decision 8.158)."""
    snapshot_id = identity.get('current_snapshot_id')
    doc = None
    if snapshot_id:
        doc = await request.app.mongodb_component_snapshots.find_one(
            {'_id': snapshot_id})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=NO_CURRENT_STATE)
    return doc


NO_DATASET_ACCESS = 'You have no access to this dataset.'


async def load_dataset(request: Request, user: Optional[User], slug: str,
                       action: Action = 'read') -> Loaded:
    """One dataset for a route (decision 8.158): 404 "Dataset not found".
    ``read``: members, and everyone signed in for a ``catalog`` dataset (an
    admin always); any other action: ``require``."""
    viewer = viewer_of(user)
    dataset = (await load_datasets(request)).get(slug)
    if dataset is None:
        raise not_found('Dataset')
    if action == 'read':
        if not (viewer.is_admin or dataset_roles(viewer, dataset)
                or (viewer.logged_in and dataset.visibility == 'catalog')):
            raise HTTPException(
                status_code=401 if not viewer.logged_in else 403,
                detail=NO_DATASET_ACCESS)
    else:
        await require(request, user, _action_of(action, dataset),
                      dataset=dataset)
    return Loaded(record=dataset, viewer=viewer, dataset=dataset)


async def load_invitation(request: Request, user: Optional[User],
                          invitation_id: str, action: Action
                          ) -> Loaded:
    """One invitation for a route (decision 8.158): 404 "Invitation not
    found". ``invite``: the caller's current invite permission on the
    invitation's dataset (an admin for one without a dataset);
    ``revoke_invitation``: its creator, moderator(D) or an admin."""
    viewer = viewer_of(user)
    check_id(invitation_id, 'Invitation')
    doc = await request.app.mongodb_invitations.find_one(
        {'_id': invitation_id})
    if doc is None:
        raise not_found('Invitation')
    dataset = (await load_datasets(request)).get(doc.get('dataset') or '')
    action = _action_of(action, doc)
    if action == 'invite' and dataset is None:
        if not viewer.is_admin:
            raise deny_write(viewer, 'invite without a dataset')
    elif action == 'invite':
        await require(request, user, 'invite', dataset=dataset)
    else:
        await require(request, user, action, invitation=doc,
                      dataset=dataset or _unknown_dataset('none'))
    return Loaded(record=doc, viewer=viewer, dataset=dataset)


async def load_material(request: Request, user: Optional[User], mid: str,
                        action: Action = 'read') -> Loaded:
    """One material of the controlled list for a route (decision 8.158): 404
    "Material not found". Any other action: ``require`` (``manage_materials``
    is for an admin)."""
    viewer = viewer_of(user)
    doc = await request.app.mongodb_materials.find_one({'_id': mid})
    if doc is None:
        raise not_found('Material')
    if action != 'read':
        await require(request, user, _action_of(action, doc))
    return Loaded(record=doc, viewer=viewer)
