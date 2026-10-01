#!/usr/bin/env python3.13
"""
The steps of the 0.5 -> 0.6 migration (data model spec section 8.1).

Each step reads what it needs, computes the new values with the pure
functions of ``mappings.py``, then writes everything in one bulk operation
--- or nothing, if a guard raises ``MigrationAbort`` or ``--dry-run`` is on.
Every step is idempotent: it selects only documents that still carry the
0.5 shape, so a second run changes nothing.

``STEPS`` lists them in run order. The geometry runner steps (5, 7, 8) are
listed as ``runner`` and belong to ``main_geometry.py`` (plan P5); step 14
touches only photo files (``migrate_strip_photo_gps.py``, run with 0.5.1.0);
step 11b runs after cutover, once personal accounts exist.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import ValidationError
from pymongo import ReplaceOne, UpdateMany, UpdateOne

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Capture, Evidence, Exit, Origin, Proxy
from apps.catalog.vocab import DATASET_ROLES
from apps.catalog.migration06.mappings import (
    ATTRIBUTE_KEYS,
    DATASET_RENAMES,
    EMPTY_CAPTURE,
    RIG_COORDINATE_SYSTEM,
    MigrationAbort,
    assert_effector,
    attribution_target,
    capture_from_attributes,
    condition_evidence,
    dataset_document,
    effective_from_all,
    exit_for,
    fixture_file,
    inheritance_for,
    lineage_order,
    material_documents,
    material_for,
    original_function_for,
    origin_for,
    parse_ts,
    proxies_from_extrusions,
    reinforcement_evidence,
    remaining_attributes,
    split_markers,
    varying_condition_datasets,
)

IDENTITIES = 'component_identities'
SNAPSHOTS = 'component_snapshots'
EVIDENCE = 'component_evidence'
MEASUREMENTS = 'component_measurements'
DATASETS = 'datasets'
MATERIALS = 'materials'
USERS = 'users'

Report = Dict[str, Any]


@dataclass
class Context:
    """What a step may touch. ``files = False`` skips file moves (a
    rehearsal without the asset folder); the report says so."""
    db: Any
    dry_run: bool = False
    now: str = field(default_factory=lambda: datetime.now(timezone.utc)
                     .strftime('%Y-%m-%dT%H:%M:%SZ'))
    meshes_dir: Optional[Path] = None
    capture_dir: Optional[Path] = None
    archive_dir: Optional[Path] = None
    files: bool = True
    condition_datasets: Optional[Sequence[str]] = None
    shared_account: str = 'ddu'
    shared_mapping: Optional[dict] = None
    operator_user_id: Optional[str] = None
    log: Callable[[str], None] = print


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    after: Tuple[str, ...]
    kind: str                       # 'db' | 'runner' | 'files' | 'post'
    apply: Optional[Callable[[Context], Report]] = None


# HELPERS ---------------------------------------------------------------------
def _write(ctx: Context, collection: str, ops: List[Any]) -> int:
    if ops and not ctx.dry_run:
        ctx.db[collection].bulk_write(ops, ordered=True)
    return len(ops)


def _check(model, block: dict, what: str) -> None:
    """Validate a block this step builds before anything is written."""
    try:
        model.model_validate(block)
    except ValidationError as exc:
        raise MigrationAbort(f'{what}: {exc.errors()[0]["msg"]}') from exc


def _snapshots_by_identity(ctx: Context,
                           projection: Optional[dict] = None
                           ) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for snap in ctx.db[SNAPSHOTS].find({}, projection):
        grouped[snap['identity_id']].append(snap)
    return grouped


def _v0(snapshots: Sequence[dict]) -> Optional[dict]:
    return min(snapshots, key=lambda s: s['version']) if snapshots else None


def _datasets_of(ctx: Context) -> Dict[str, str]:
    return {i['_id']: i.get('dataset')
            for i in ctx.db[IDENTITIES].find({}, {'dataset': 1})}


# STEP 1 --- effective_from (8.10) --------------------------------------------
def step_1(ctx: Context) -> Report:
    grouped = _snapshots_by_identity(ctx)
    ops = []
    for identity in ctx.db[IDENTITIES].find({}):
        snaps = grouped.get(identity['_id'], [])
        if not snaps or all(s.get('effective_from') for s in snaps):
            continue
        values = effective_from_all(identity, snaps)
        for snap in snaps:
            if snap.get('effective_from'):
                continue
            value, precision = values[snap['_id']]
            ops.append(UpdateOne({'_id': snap['_id']}, {'$set': {
                'effective_from': value,
                'effective_from_precision': precision}}))
    return {'snapshots set': _write(ctx, SNAPSHOTS, ops)}


# STEP 1b --- validated -> status ---------------------------------------------
def step_1b(ctx: Context) -> Report:
    ops = []
    counts = {'published': 0, 'pending': 0}
    for snap in ctx.db[SNAPSHOTS].find({'validated': {'$exists': True}},
                                       {'validated': 1}):
        status = 'published' if snap['validated'] else 'pending'
        counts[status] += 1
        ops.append(UpdateOne({'_id': snap['_id']}, {
            '$set': {'status': status}, '$unset': {'validated': ''}}))
    _write(ctx, SNAPSHOTS, ops)
    return counts


# STEP 1c --- initialise every new field --------------------------------------
_SNAPSHOT_DEFAULTS = {
    'supersedes': None, 'superseded_by': None,
    'status_changed_by_user_id': None, 'status_changed_at': None,
    'capture': None, 'properties': {}, 'properties_version': 1,
    'photo_count': 0, 'notes': None,
}
_IDENTITY_DEFAULTS = {
    'withdrawn': None, 'past_cycles': [], 'properties': {},
    'properties_version': 1,
}


def step_1c(ctx: Context) -> Report:
    snap_ops = []
    for snap in ctx.db[SNAPSHOTS].find({}):
        update = {k: v for k, v in _SNAPSHOT_DEFAULTS.items()
                  if k not in snap}
        geometry = snap.get('geometry') or {}
        for key in ('meshes', 'point_clouds'):
            if geometry.get(key) is None:
                update[f'geometry.{key}'] = []
        if snap.get('mesh_ply_resolutions') is None:
            update['mesh_ply_resolutions'] = {}
        if update:
            snap_ops.append(UpdateOne({'_id': snap['_id']},
                                      {'$set': update}))
    grouped = _snapshots_by_identity(ctx, {'identity_id': 1, 'version': 1,
                                           'added_by_user_id': 1})
    identity_ops = []
    for identity in ctx.db[IDENTITIES].find({}):
        update = {k: v for k, v in _IDENTITY_DEFAULTS.items()
                  if k not in identity}
        if identity.get('manufactured_precision') is None:
            update['manufactured_precision'] = 'unknown'
        if not identity.get('created_by_user_id'):
            v0 = _v0(grouped.get(identity['_id'], []))
            if v0 is None:
                raise MigrationAbort(f'identity {identity["_id"]} has no '
                                     f'snapshot to take its creator from')
            update['created_by_user_id'] = v0['added_by_user_id']
        if update:
            identity_ops.append(UpdateOne({'_id': identity['_id']},
                                          {'$set': update}))
    return {'snapshots': _write(ctx, SNAPSHOTS, snap_ops),
            'identities': _write(ctx, IDENTITIES, identity_ops)}


# STEP 9 --- drop fields 6.13 / 7.11 / 7.12 made meaningless ------------------
_DROPPED_SNAPSHOT_FIELDS = ('processes', 'assembly', 'virtual', 'iframe')


def step_9(ctx: Context) -> Report:
    query = {'$or': [{f: {'$exists': True}}
                     for f in _DROPPED_SNAPSHOT_FIELDS]}
    projection = {f: 1 for f in _DROPPED_SNAPSHOT_FIELDS}
    ops = []
    for snap in ctx.db[SNAPSHOTS].find(query, projection):
        # each dropped field was constant in 260916; anything else is drift
        for name in ('virtual', 'assembly', 'processes'):
            if snap.get(name):
                raise MigrationAbort(f'snapshot {snap["_id"]}: {name} = '
                                     f'{snap[name]!r} --- decide before '
                                     f'dropping it')
        ops.append(UpdateOne({'_id': snap['_id']}, {'$unset': {
            f: '' for f in _DROPPED_SNAPSHOT_FIELDS}}))
    return {'snapshots': _write(ctx, SNAPSHOTS, ops)}


# STEP 2 --- component_measurements -> component_evidence ---------------------
def step_2(ctx: Context) -> Report:
    names = set(ctx.db.list_collection_names())
    dropped = 0
    if MEASUREMENTS in names:
        count = ctx.db[MEASUREMENTS].estimated_document_count()
        if count:
            raise MigrationAbort(f'{MEASUREMENTS} holds {count} documents; '
                                 f'it was expected to be empty')
        if not ctx.dry_run:
            ctx.db[MEASUREMENTS].drop()
        dropped = 1
    created = 0
    if EVIDENCE not in names:
        created = 1
        if not ctx.dry_run:
            ctx.db.create_collection(EVIDENCE)
    if not ctx.dry_run:
        ctx.db[EVIDENCE].create_index('identity_id')
        ctx.db[EVIDENCE].create_index([('status', 1), ('method', 1)])
    return {'measurements dropped': dropped, 'evidence created': created}


# STEP 11a --- rename dataset slugs (8.24) ------------------------------------
def step_11a(ctx: Context) -> Report:
    """Rename 0.5 dataset slugs before anything reads them; a ``datasets``
    document already created under the old slug moves to the new one."""
    report: Report = {}
    for old, new in DATASET_RENAMES.items():
        ops = [UpdateMany({'dataset': old}, {'$set': {'dataset': new}})]
        count = ctx.db[IDENTITIES].count_documents({'dataset': old})
        if count:
            _write(ctx, IDENTITIES, ops)
        doc = ctx.db[DATASETS].find_one({'_id': old})
        if doc is not None and not ctx.dry_run:
            if ctx.db[DATASETS].find_one({'_id': new}) is None:
                doc['_id'] = new
                doc['name'] = dataset_document(new, ctx.now)[0]['name']
                ctx.db[DATASETS].insert_one(doc)
            ctx.db[DATASETS].delete_one({'_id': old})
        report[f'{old} -> {new}'] = count
    return report


# STEP 11 --- datasets collection ---------------------------------------------
def step_11(ctx: Context) -> Report:
    existing = {d['_id'] for d in ctx.db[DATASETS].find({}, {'_id': 1})}
    ops = []
    for slug in sorted(ctx.db[IDENTITIES].distinct('dataset')):
        if slug in existing:
            continue
        doc, known = dataset_document(slug, ctx.now)
        if not known:
            ctx.log(f'  warning: dataset {slug!r} is not in the visibility '
                    f'table --- created with visibility members')
        ops.append(ReplaceOne({'_id': slug}, doc, upsert=True))
    return {'datasets created': _write(ctx, DATASETS, ops)}


# STEP 12 --- materials collection + material / class / trade name ------------
def step_12(ctx: Context) -> Report:
    existing = {m['_id'] for m in ctx.db[MATERIALS].find({}, {'_id': 1})}
    seed_ops = [ReplaceOne({'_id': m['_id']}, m, upsert=True)
                for m in material_documents() if m['_id'] not in existing]
    ops = []
    for identity in ctx.db[IDENTITIES].find({}):
        update = material_for(identity)
        if any(identity.get(k) != v for k, v in update.items()) \
                or 'trade_name' not in identity:
            ops.append(UpdateOne({'_id': identity['_id']},
                                 {'$set': update}))
    return {'materials seeded': _write(ctx, MATERIALS, seed_ops),
            'identities': _write(ctx, IDENTITIES, ops)}


# STEP 3 --- type -> original_function ----------------------------------------
def step_3(ctx: Context) -> Report:
    ops = []
    for identity in ctx.db[IDENTITIES].find({'type': {'$exists': True}}):
        ops.append(UpdateOne({'_id': identity['_id']}, {
            '$set': {'original_function': original_function_for(identity)},
            '$unset': {'type': ''}}))
    missing = ctx.db[IDENTITIES].count_documents(
        {'type': {'$exists': False}, 'original_function': {'$exists': False}})
    if missing:
        raise MigrationAbort(f'{missing} identities have neither type nor '
                             f'original_function')
    return {'identities': _write(ctx, IDENTITIES, ops)}


# STEP 10 --- salvage -> origin -----------------------------------------------
def step_10(ctx: Context) -> Report:
    ops = []
    kinds: Dict[str, int] = defaultdict(int)
    identities = list(ctx.db[IDENTITIES].find({}))
    origins: Dict[str, dict] = {}
    for identity in lineage_order(identities):      # parents first
        parents = [origins[p] for p in identity.get('parent_identities') or []
                   if p in origins]
        origin = origin_for(identity, parents)
        origins[identity['_id']] = origin
        if isinstance(identity.get('origin'), dict):
            continue
        _check(Origin, origin, f'identity {identity["_id"]} origin')
        kinds[origin['kind']] += 1
        ops.append(UpdateOne({'_id': identity['_id']}, {
            '$set': {'origin': origin},
            '$unset': {'salvage_source': '', 'salvaged_at': ''}}))
    _write(ctx, IDENTITIES, ops)
    return dict(kinds)


# STEP 10c --- consumed_at -> exit --------------------------------------------
def step_10c(ctx: Context) -> Report:
    grouped = _snapshots_by_identity(ctx, {'identity_id': 1,
                                           'effective_from': 1})
    identities = list(ctx.db[IDENTITIES].find({}))
    children: Dict[str, List[str]] = defaultdict(list)
    for identity in identities:
        for parent in identity.get('parent_identities') or []:
            children[parent].append(identity['_id'])

    def first_effective(child_id: str) -> Optional[str]:
        values = [s.get('effective_from') for s in grouped.get(child_id, [])]
        if not all(values):
            raise MigrationAbort(f'identity {child_id}: snapshots without '
                                 f'effective_from --- run step 1 first')
        return min(values, key=parse_ts) if values else None

    ops = []
    kinds: Dict[str, int] = defaultdict(int)
    for identity in identities:
        if 'exit' in identity and 'consumed_at' not in identity:
            continue
        kids = [first_effective(c) for c in children.get(identity['_id'], [])]
        earliest = min(kids, key=parse_ts) if kids else None
        exit_ = exit_for(identity, earliest)
        if exit_ is not None:
            _check(Exit, exit_, f'identity {identity["_id"]} exit')
            kinds[exit_['kind']] += 1
            consumed = identity.get('consumed_at')
            if exit_['kind'] == 'split' and consumed and abs(
                    (parse_ts(consumed) - parse_ts(earliest))
                    .total_seconds()) > 1:
                ctx.log(f'  note: {identity["_id"]} consumed_at {consumed} '
                        f'!= first child {earliest}; exit.at follows I18')
            if identity.get('reserved'):
                raise MigrationAbort(f'identity {identity["_id"]} is '
                                     f'reserved but left circulation (I18)')
        else:
            kinds['in circulation'] += 1
        update: Dict[str, Any] = {'$set': {'exit': exit_}}
        if 'past_cycles' not in identity:
            update['$set']['past_cycles'] = []
        if 'consumed_at' in identity:
            update['$unset'] = {'consumed_at': ''}
        ops.append(UpdateOne({'_id': identity['_id']}, update))
    _write(ctx, IDENTITIES, ops)
    return dict(kinds)


# STEP 10b --- lineage inheritance --------------------------------------------
_LINEAGE_NEEDS = ('origin', 'original_function', 'material', 'trade_name')


def step_10b(ctx: Context) -> Report:
    identities = list(ctx.db[IDENTITIES].find({}))
    for identity in identities:
        missing = [f for f in _LINEAGE_NEEDS if f not in identity]
        if missing:
            raise MigrationAbort(f'identity {identity["_id"]} lacks '
                                 f'{missing} --- run steps 3, 10, 12 first')
    by_id = {i['_id']: i for i in identities}
    ops = []
    counts = {'roots': 0, 'children': 0}
    missing = object()
    for identity in lineage_order(identities):
        parents = [by_id[p] for p in identity.get('parent_identities') or []
                   if p in by_id]
        if not parents:
            counts['roots'] += 1
            update = {'inherited_fields': [], 'inherited_from': None}
        else:
            counts['children'] += 1
            update = inheritance_for(identity, parents)
        changed = any(identity.get(k, missing) != v
                      for k, v in update.items())
        identity.update(update)          # grandchildren compare with this
        if changed:
            ops.append(UpdateOne({'_id': identity['_id']},
                                 {'$set': update}))
    _write(ctx, IDENTITIES, ops)
    return counts


# STEP 6 --- attributes -> capture on v0 --------------------------------------
def step_6(ctx: Context) -> Report:
    query = {'$or': [{f'attributes.{k}': {'$exists': True}}
                     for k in ATTRIBUTE_KEYS]}
    grouped = _snapshots_by_identity(ctx)
    snap_ops, identity_ops = [], []
    for identity in ctx.db[IDENTITIES].find(query):
        v0 = _v0(grouped.get(identity['_id'], []))
        if v0 is None:
            raise MigrationAbort(f'identity {identity["_id"]} has no v0')
        capture = capture_from_attributes(identity, v0.get('capture'))
        if capture is not None:
            _check(Capture, capture, f'snapshot {v0["_id"]} capture')
            snap_ops.append(UpdateOne({'_id': v0['_id']},
                                      {'$set': {'capture': capture}}))
        identity_ops.append(UpdateOne({'_id': identity['_id']}, {
            '$set': {'attributes': remaining_attributes(identity)}}))
    return {'captures': _write(ctx, SNAPSHOTS, snap_ops),
            'identities': _write(ctx, IDENTITIES, identity_ops)}


# STEP 6c --- robot rig out of geometry (7.7) ---------------------------------
def _ply_bytes(mesh: dict) -> bytes:
    import trimesh
    shape = trimesh.Trimesh(vertices=mesh['vertices'], faces=mesh['faces'],
                            process=False)
    return shape.export(file_type='ply')


def _move_fixture(ctx: Context, snap: dict) -> str:
    """meshes/<sid>/1/{detailed,reduced}.ply -> capture/<sid>/fixtures/0.ply;
    returns what happened (for the report)."""
    if not ctx.files:
        return 'skipped (no files)'
    if ctx.meshes_dir is None or ctx.capture_dir is None:
        raise MigrationAbort('step 6c moves fixture files: pass the meshes '
                             'and capture directories, or --no-files')
    source_dir = ctx.meshes_dir / snap['_id'] / '1'
    target = ctx.capture_dir / snap['_id'] / 'fixtures' / '0.ply'
    candidates = [source_dir / 'detailed.ply', source_dir / 'reduced.ply']
    source = next((p for p in candidates if p.is_file()), None)
    if ctx.dry_run:
        return 'would move' if source else (
            'already moved' if target.is_file() else 'would export inline')
    target.parent.mkdir(parents=True, exist_ok=True)
    if source is not None:
        shutil.move(str(source), str(target))
        result = f'moved {source.name}'
    elif target.is_file():
        result = 'already moved'
    else:
        target.write_bytes(_ply_bytes(snap['geometry']['meshes'][1]))
        result = 'exported inline'
    if source_dir.is_dir():
        shutil.rmtree(source_dir)
    return result


def step_6c(ctx: Context) -> Report:
    coll = ctx.db[SNAPSHOTS]
    query = {'$or': [{'geometry.marker_points.0': {'$exists': True}},
                     {'geometry.meshes.1': {'$exists': True}}]}
    ops = []
    report: Dict[str, int] = defaultdict(int)
    for snap in coll.find(query):
        geometry = snap['geometry']
        meshes = geometry.get('meshes') or []
        if len(meshes) > 2:
            raise MigrationAbort(f'snapshot {snap["_id"]}: {len(meshes)} '
                                 f'meshes --- which are the component?')
        capture = dict(EMPTY_CAPTURE, **(snap.get('capture') or {}))
        capture['markers'] = split_markers(
            snap['_id'], geometry.get('marker_points') or [])
        capture['coordinate_system'] = dict(RIG_COORDINATE_SYSTEM)
        update: Dict[str, Any] = {}
        if len(meshes) == 2:
            assert_effector(snap['_id'], meshes[1]['vertices'])
            report[_move_fixture(ctx, snap)] += 1
            capture['fixtures'] = [{'label': 'end_effector',
                                    'file': fixture_file(snap['_id'])}]
            update['geometry.meshes'] = [meshes[0]]
            resolutions = dict(snap.get('mesh_ply_resolutions') or {})
            resolutions.pop('1', None)
            update['mesh_ply_resolutions'] = resolutions
        _check(Capture, capture, f'snapshot {snap["_id"]} capture')
        update['capture'] = capture
        report['snapshots'] += 1
        report['markers'] += len(capture['markers'])
        ops.append(UpdateOne({'_id': snap['_id']}, {
            '$set': update, '$unset': {'geometry.marker_points': ''}}))
    for snap in coll.find({'geometry.marker_points': {'$exists': True},
                           'geometry.marker_points.0': {'$exists': False}},
                          {'_id': 1}):
        ops.append(UpdateOne({'_id': snap['_id']},
                             {'$unset': {'geometry.marker_points': ''}}))
    _write(ctx, SNAPSHOTS, ops)
    return dict(report)


# STEP 6d --- reinforcements -> reinforcement_layout evidence (7.8) -----------
def step_6d(ctx: Context) -> Report:
    coll = ctx.db[SNAPSHOTS]
    evidence_ops, snap_ops = [], []
    for snap in coll.find({'geometry.reinforcements.0': {'$exists': True}}):
        record = reinforcement_evidence(snap)
        _check(Evidence, record, f'layout from snapshot {snap["_id"]}')
        evidence_ops.append(ReplaceOne({'_id': record['_id']}, record,
                                       upsert=True))
    for snap in coll.find({'geometry.reinforcements': {'$exists': True}},
                          {'_id': 1}):
        snap_ops.append(UpdateOne({'_id': snap['_id']}, {
            '$unset': {'geometry.reinforcements': ''}}))
    return {'layouts': _write(ctx, EVIDENCE, evidence_ops),
            'snapshots': _write(ctx, SNAPSHOTS, snap_ops)}


# STEP 6b --- condition -> visual_inspection evidence (7.9) -------------------
def step_6b(ctx: Context) -> Report:
    coll = ctx.db[SNAPSHOTS]
    datasets = _datasets_of(ctx)
    snaps = list(coll.find({'condition': {'$exists': True}}))
    table = varying_condition_datasets(
        (datasets.get(s['identity_id']), s.get('condition')) for s in snaps)
    if ctx.condition_datasets is not None:
        chosen = set(ctx.condition_datasets)
    else:
        chosen = {d for d, grades in table.items() if len(grades) > 1}
    for dataset in sorted(table, key=str):
        mark = 'migrate' if dataset in chosen else 'drop (batch default)'
        ctx.log(f'  {dataset}: {dict(sorted(table[dataset].items()))} '
                f'--> {mark}')
    evidence_ops, snap_ops = [], []
    for snap in snaps:
        if snap.get('condition') is not None \
                and datasets.get(snap['identity_id']) in chosen:
            record = condition_evidence(snap)
            _check(Evidence, record, f'grade of snapshot {snap["_id"]}')
            evidence_ops.append(ReplaceOne({'_id': record['_id']}, record,
                                           upsert=True))
        snap_ops.append(UpdateOne({'_id': snap['_id']},
                                  {'$unset': {'condition': ''}}))
    return {'inspections': _write(ctx, EVIDENCE, evidence_ops),
            'snapshots': _write(ctx, SNAPSHOTS, snap_ops)}


# STEP 4 --- extrusions -> authored prisms ------------------------------------
def step_4(ctx: Context) -> Report:
    coll = ctx.db[SNAPSHOTS]
    ops = []
    prisms = 0
    query = {'$or': [{'geometry.extrusions': {'$exists': True}},
                     {'geometry.proxies': {'$exists': False}}]}
    for snap in coll.find(query, {'geometry.extrusions': 1}):
        proxies = proxies_from_extrusions(snap)
        for i, proxy in enumerate(proxies):
            _check(Proxy, proxy, f'snapshot {snap["_id"]} proxy {i}')
        prisms += len(proxies)
        update: Dict[str, Any] = {'$set': {'geometry.proxies': proxies}}
        if 'extrusions' in (snap.get('geometry') or {}):
            update['$unset'] = {'geometry.extrusions': ''}
        ops.append(UpdateOne({'_id': snap['_id']}, update))
    return {'snapshots': _write(ctx, SNAPSHOTS, ops), 'prisms': prisms}


# STEP 9b --- complexity_source (6.15) ----------------------------------------
_AUTHORED_COMPLEXITY_DATASETS = ('beyond_debris',)


def step_9b(ctx: Context) -> Report:
    datasets = _datasets_of(ctx)
    ops = []
    counts: Dict[str, int] = defaultdict(int)
    for snap in ctx.db[SNAPSHOTS].find(
            {'complexity_source': {'$exists': False}},
            {'identity_id': 1, 'complexity': 1}):
        if snap.get('complexity') is None:
            source = None
        elif datasets.get(snap['identity_id']) \
                in _AUTHORED_COMPLEXITY_DATASETS:
            source = 'assigned'
        else:
            source = 'derived'
        counts[str(source)] += 1
        ops.append(UpdateOne({'_id': snap['_id']},
                             {'$set': {'complexity_source': source}}))
    _write(ctx, SNAPSHOTS, ops)
    return dict(counts)


# STEP 13 --- archive and drop designs (7.11) ---------------------------------
def step_13(ctx: Context) -> Report:
    from bson import json_util
    if 'designs' not in ctx.db.list_collection_names():
        return {'designs': 0}
    docs = list(ctx.db['designs'].find({}))
    if ctx.archive_dir is None:
        raise MigrationAbort(f'{len(docs)} designs: pass --archive-dir to '
                             f'export them before the drop')
    stamp = datetime.now(timezone.utc).strftime('%y%m%d')
    path = Path(ctx.archive_dir) / f'designs_archive_{stamp}.json'
    if not ctx.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_util.dumps(docs, indent=1), encoding='utf-8')
        reread = json_util.loads(path.read_text(encoding='utf-8'))
        if len(reread) != len(docs):
            raise MigrationAbort(f'archive {path} holds {len(reread)} of '
                                 f'{len(docs)} designs; collection kept')
        ctx.db['designs'].drop()
    return {'designs': len(docs), 'archive': str(path)}


# STEP 11b --- re-attribute the shared account's records (post cutover) -----
def step_11b(ctx: Context) -> Report:
    """
    Records the mapping covers move from the shared accounts to personal
    ones (with an ``attribution_corrected`` audit entry); the rest stay. The
    mapping's ``from`` lists the source accounts (default: the shared
    account); targets are user ids or usernames. Owners become contributors
    of their datasets, ``moderators`` moderate every dataset, ``members``
    adds roles per dataset, ``descriptions`` sets dataset descriptions
    (8.25, 8.26). The mapping names people, so it is never committed
    (template: ``reattribute_06.example.json``). No
    source account is
    disabled: ``ddu`` stays as the internal user-role test account
    (decisions 8.22, 8.24). Runs again for later mappings.
    """
    mapping = ctx.shared_mapping
    if not mapping:
        raise MigrationAbort('step 11b needs a mapping file (--mapping)')
    users = ctx.db[USERS]
    names = {u['_id']: u.get('username') for u in users.find({}, {
        'username': 1})}
    by_name = {name: user_id for user_id, name in names.items()}

    def resolve(value: str) -> str:
        if value in names:
            return value
        if value in by_name:
            return by_name[value]
        raise MigrationAbort(f'mapping names unknown user {value!r}')

    sources = [resolve(a)
               for a in mapping.get('from') or [ctx.shared_account]]
    moderators = [resolve(a) for a in mapping.get('moderators') or []]
    descriptions: Dict[str, str] = mapping.get('descriptions') or {}
    extra: Dict[str, Dict[str, List[str]]] = {}
    for dataset, grants in (mapping.get('members') or {}).items():
        for name, roles in grants.items():
            bad = [r for r in roles if r not in DATASET_ROLES]
            if bad:
                raise MigrationAbort(f'mapping: unknown dataset roles {bad}')
            extra.setdefault(dataset, {})[resolve(name)] = list(roles)
    mapping = {key: {k: resolve(v)
                     for k, v in (mapping.get(key) or {}).items()}
               for key in ('datasets', 'identities', 'snapshots')}
    datasets = _datasets_of(ctx)

    def audit(from_user_id: str) -> dict:
        return {'from_user_id': from_user_id, 'at': ctx.now,
                'by_user_id': ctx.operator_user_id}

    unmapped = {'snapshots': 0, 'identities': 0, 'evidence': 0}

    def target(kind: str, **keys) -> Optional[str]:
        user_id = attribution_target(mapping, **keys)
        if user_id is None:
            unmapped[kind] += 1
        return user_id

    authored: Dict[str, set] = defaultdict(set)
    snap_ops, identity_ops, evidence_ops = [], [], []
    for snap in ctx.db[SNAPSHOTS].find({'added_by_user_id': {'$in': sources}}):
        dataset = datasets.get(snap['identity_id'])
        user_id = target('snapshots', snapshot_id=snap['_id'],
                         identity_id=snap['identity_id'], dataset=dataset)
        if user_id is None:
            continue
        authored[dataset].add(user_id)
        snap_ops.append(UpdateOne({'_id': snap['_id']}, {'$set': {
            'added_by_user_id': user_id, 'added_by_username': names[user_id],
            'attribution_corrected': audit(snap['added_by_user_id'])}}))
    for identity in ctx.db[IDENTITIES].find(
            {'created_by_user_id': {'$in': sources}}):
        user_id = target('identities', identity_id=identity['_id'],
                         dataset=identity.get('dataset'))
        if user_id is None:
            continue
        identity_ops.append(UpdateOne({'_id': identity['_id']}, {'$set': {
            'created_by_user_id': user_id,
            'attribution_corrected': audit(identity['created_by_user_id'])}}))
    for record in ctx.db[EVIDENCE].find({'$or': [
            {'recorded_by_user_id': {'$in': sources}},
            {'performed_by.user_id': {'$in': sources}}]}):
        dataset = datasets.get(record['identity_id'])
        user_id = target('evidence', identity_id=record['identity_id'],
                         dataset=dataset)
        if user_id is None:
            continue
        performed = [dict(a, user_id=user_id)
                     if a.get('user_id') in sources else a
                     for a in record.get('performed_by') or []]
        source = record.get('recorded_by_user_id')
        update = {'performed_by': performed,
                  'attribution_corrected': audit(
                      source if source in sources else sources[0])}
        if source in sources:
            update['recorded_by_user_id'] = user_id
            update['recorded_by_username'] = names[user_id]
        evidence_ops.append(UpdateOne({'_id': record['_id']},
                                      {'$set': update}))
    # owners become contributors of the datasets they authored; the
    # mapping's moderators moderate every dataset, its members add roles per
    # dataset (8.25, 8.26); roles only grow
    member_ops = []
    for doc in ctx.db[DATASETS].find({}):
        wanted: Dict[str, List[str]] = defaultdict(list)
        for user_id in sorted(authored.get(doc['_id'], ())):
            wanted[user_id].append('contributor')
        for user_id in moderators:
            wanted[user_id].append('moderator')
        for user_id, roles in extra.get(doc['_id'], {}).items():
            wanted[user_id].extend(roles)
        update: Dict[str, Any] = {}
        description = descriptions.get(doc['_id'])
        if description is not None and doc.get('description') != description:
            update['description'] = description
        members = [dict(m) for m in doc.get('members') or []]
        index = {m['user_id']: m for m in members}
        changed = False
        for user_id, roles in wanted.items():
            member = index.get(user_id)
            if member is None:
                member = {'user_id': user_id, 'roles': [],
                          'added_by_user_id': ctx.operator_user_id,
                          'added_at': ctx.now}
                members.append(member)
                index[user_id] = member
            for role in roles:
                if role not in member['roles']:
                    member['roles'] = [*member['roles'], role]
                    changed = True
        if changed:
            update['members'] = members
        if update:
            update['lastmodified'] = ctx.now
            member_ops.append(UpdateOne({'_id': doc['_id']}, {'$set': update}))
    report = {'snapshots': _write(ctx, SNAPSHOTS, snap_ops),
              'identities': _write(ctx, IDENTITIES, identity_ops),
              'evidence': _write(ctx, EVIDENCE, evidence_ops),
              'datasets': _write(ctx, DATASETS, member_ops),
              'left unmapped': unmapped}
    return report


# REGISTRY (spec section 8.1, run order) --------------------------------------
STEPS: Tuple[Step, ...] = (
    Step('11a', 'rename dataset slugs (8.24)', (), 'db', step_11a),
    Step('1', 'effective_from by the 8.10 default', (), 'db', step_1),
    Step('1b', 'validated -> status', ('1',), 'db', step_1b),
    Step('1c', 'initialise new fields, normalise nulls', ('1b',), 'db',
         step_1c),
    Step('9', 'drop processes, assembly, virtual, iframe', (), 'db', step_9),
    Step('2', 'component_measurements -> component_evidence', (), 'db',
         step_2),
    Step('11', 'datasets collection', ('11a',), 'db', step_11),
    Step('12', 'materials collection, material / class / trade name', (),
         'db', step_12),
    Step('3', 'type -> original_function', (), 'db', step_3),
    Step('10', 'salvage -> origin', ('11a',), 'db', step_10),
    Step('10c', 'consumed_at -> exit', ('1',), 'db', step_10c),
    Step('10b', 'lineage inheritance', ('3', '10', '12'), 'db', step_10b),
    Step('6', 'attributes -> capture', ('1c',), 'db', step_6),
    Step('6c', 'robot rig -> capture markers / fixtures', ('6',), 'db',
         step_6c),
    Step('6d', 'reinforcements -> reinforcement_layout evidence', ('2',),
         'db', step_6d),
    Step('6b', 'condition -> visual_inspection evidence', ('2',), 'db',
         step_6b),
    Step('4', 'extrusions -> authored prism proxies', (), 'db', step_4),
    Step('9b', 'complexity_source', ('11a',), 'db', step_9b),
    Step('5', 'frame + shape class (main_geometry.py)', ('3', '4', '6c'),
         'runner'),
    Step('7', 'proxies, descriptors, complexity, previews '
         '(main_geometry.py)', ('5', '9b'), 'runner'),
    Step('8', 'shape class after tuning (main_geometry.py)', ('7',),
         'runner'),
    Step('13', 'archive and drop designs', (), 'db', step_13),
    Step('14', 'strip photo GPS (migrate_strip_photo_gps.py)', (), 'files'),
    Step('11b', 're-attribute the shared account\'s records (mapping)',
         ('cutover',), 'post', step_11b),
)
STEP_BY_ID: Dict[str, Step] = {s.id: s for s in STEPS}
CUTOVER_STEPS: Tuple[str, ...] = tuple(s.id for s in STEPS if s.kind == 'db')


def run(ctx: Context, step_ids: Sequence[str]) -> Dict[str, Report]:
    """Run the given steps in registry order; stops at the first abort."""
    unknown = [s for s in step_ids if s not in STEP_BY_ID]
    if unknown:
        raise MigrationAbort(f'unknown steps: {unknown}')
    reports: Dict[str, Report] = {}
    for step in STEPS:
        if step.id not in step_ids:
            continue
        if step.apply is None:
            raise MigrationAbort(f'step {step.id} is not run here: '
                                 f'{step.title}')
        ctx.log(f'step {step.id:3s} {step.title}'
                f'{"  (dry run)" if ctx.dry_run else ""}')
        reports[step.id] = step.apply(ctx)
        ctx.log(f'         {reports[step.id]}')
    return reports


def default_dirs() -> Dict[str, Optional[Path]]:
    """Storage directories from the backend's environment variables."""
    def env(name: str) -> Optional[Path]:
        value = os.getenv(name)
        return Path(value) if value else None
    return {'meshes_dir': env('SNAPSHOT_MESHES_DIR'),
            'capture_dir': env('SNAPSHOT_CAPTURE_DIR')}
