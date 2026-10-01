#!/usr/bin/env python3.13
"""
Pure mapping functions of the 0.5 -> 0.6 migration (spec section 8.1).

No database access: every function takes plain 0.5 documents (dicts) and
returns the 0.6 values, or raises ``MigrationAbort`` when a document does not
fit any known case --- the abort guards that catch drift between the rehearsed
dump (260916) and the cutover dump. ``steps.py`` applies them.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.vocab import INHERITABLE_FIELDS, MATERIAL_SEED_BY_ID


class MigrationAbort(Exception):
    """A document fits no known case; nothing of the step is written."""


# TIME ------------------------------------------------------------------------
def parse_ts(value: str) -> datetime:
    """ISO-8601 UTC string ('...Z', with or without fraction) -> datetime."""
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def to_ts(value: datetime) -> str:
    """datetime -> ISO-8601 UTC string ending in Z (seconds precision)."""
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def day_of(value: str) -> str:
    """The day of a timestamp, as midnight UTC (for ``day`` precision)."""
    return parse_ts(value).strftime('%Y-%m-%dT00:00:00Z')


# DETERMINISTIC IDS -----------------------------------------------------------
# documents a step creates get the same id on every run (idempotence)
_NAMESPACE = uuid.UUID('6f0b7c2e-1d5a-4c1e-9a52-0c0e5a1d0600')


def migration_id(step: str, source_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f'{step}:{source_id}'))


# STEP 3: type -> original_function -------------------------------------------
TYPE_TO_FUNCTION: Dict[str, str] = {
    'panel': 'IfcPlate',
    'beam': 'IfcBeam',
    'column': 'IfcColumn',
    'slab': 'IfcSlab',
    'brick': 'IfcBuildingElementPart',
    'pipe': 'IfcPipeSegment',
    'profile': 'IfcMember',
    'connector': 'IfcDiscreteAccessory',
    'rubble': 'CscDebris',
    'other': 'IfcBuildingElementProxy',
}


def original_function_for(identity: dict) -> str:
    type_ = identity.get('type')
    if type_ not in TYPE_TO_FUNCTION:
        raise MigrationAbort(f'identity {identity["_id"]}: unmapped type '
                             f'{type_!r}')
    return TYPE_TO_FUNCTION[type_]


# STEP 12: material -> materials FK + trade name ------------------------------
# 0.5 value -> (material id, trade name)
MATERIAL_MAP: Dict[str, Tuple[str, Optional[str]]] = {
    'corian': ('mineral_composite', 'Corian'),
    'concrete': ('concrete', None),
    'brick': ('fired_clay', None),
    'aerated-concrete': ('autoclaved_aerated_concrete', None),
    'asphalt': ('asphalt', None),
    'steel': ('steel', None),
    'wood': ('timber', None),
}


def material_for(identity: dict) -> Dict[str, Any]:
    """The four 0.6 material fields of one identity."""
    value = identity.get('material')
    if value in MATERIAL_SEED_BY_ID:          # already migrated
        material, trade = value, identity.get('trade_name')
    elif value in MATERIAL_MAP:
        material, trade = MATERIAL_MAP[value]
    else:
        raise MigrationAbort(f'identity {identity["_id"]}: unmapped material '
                             f'{value!r}')
    return {
        'material': material,
        'trade_name': trade,
        'material_class': MATERIAL_SEED_BY_ID[material].default_class,
        'material_class_source': 'derived',
    }


def material_documents() -> List[dict]:
    """The seeded ``materials`` collection (spec section 2.10)."""
    return [{'_id': m.id, 'label': m.label, 'group': m.group,
             'default_class': m.default_class, 'uniclass': m.uniclass,
             'notes': m.notes}
            for m in MATERIAL_SEED_BY_ID.values()]


# STEP 11a: dataset slugs renamed at cutover (decision 8.24) ------------------
# 0.5 slug -> 0.6 slug; 0.6 slugs are immutable (spec section 3.6)
DATASET_RENAMES: Dict[str, str] = {
    'sas_cita_scans': 'beyond_debris',
}


# STEP 11: datasets -----------------------------------------------------------
# slug -> (display name, visibility); a slug not listed gets the default
DATASETS: Dict[str, Tuple[str, str]] = {
    'mineral_composite_panels': ('Mineral composite panels', 'catalog'),
    'beyond_debris': ('Beyond Debris', 'catalog'),
    'ddu_build_with_debris': ('DDU Build with debris', 'catalog'),
    'ddu_aggregations': ('DDU aggregations', 'catalog'),
    'dbu_zirkus': ('ZirKuS', 'members'),
    'schoenes_neues_feld': ('Schönes neues Feld', 'members'),
    'spa_example_data': ('SPA example data', 'members'),
}


def dataset_document(slug: str, now: str) -> Tuple[dict, bool]:
    """A new ``datasets`` document; the flag says whether the slug is known
    (unknown slugs get ``members`` visibility and a warning)."""
    name, visibility = DATASETS.get(
        slug, (slug.replace('_', ' ').capitalize(), 'members'))
    return ({'_id': slug, 'name': name,
             'description': None,
             'visibility': visibility, 'members': [], 'created': now,
             'lastmodified': now}, slug in DATASETS)


# STEP 10: salvage_source / salvaged_at -> origin -----------------------------
_ROSSKOPF_PREFIX = 'Rosskopf + Partner AG'
_ROSSKOPF_ORIGIN = {
    'kind': 'offcut',
    'at': '2022-10-26T00:00:00Z', 'at_precision': 'day',
    'place': {'name': 'Rosskopf + Partner AG',
              'address': 'Bahnhofstraße 16, 09573 Augustusburg',
              'location': None},
    'construction_work': None,
    'method': None,
    'performed_by': [{'kind': 'organization', 'user_id': None,
                      'name': 'Rosskopf + Partner AG', 'organization': None,
                      'role': 'operator'}],
    'notes': None,
}
_ZIRKUS_ORIGIN = {
    'kind': 'deinstallation',
    'at': '2024-07-24T00:00:00Z', 'at_precision': 'day',
    'place': {'name': 'TU Darmstadt Lichtwiese Campus',
              'address': 'Günther-Behnisch-Straße, 64287 '
                         'Darmstadt, Germany',
              'location': None},
    'construction_work': {
        'name': 'Lichtwiese Campus Infrastructure — pedestrian bridge',
        'identifier': None, 'year_built': None,
        'use': 'pedestrian bridge'},
    'method': None,
    'performed_by': [],
    'notes': None,
}
_EXFELD_SOURCE = 'ExFeld Architektur, TU Darmstadt'
_BY_HAND_PREFIX = 'Measured by Hand'
# datasets whose identities carry no salvage data -> origin kind
_KIND_BY_DATASET: Dict[str, str] = {
    'beyond_debris': 'demolition',
    'ddu_build_with_debris': 'demolition',
    'spa_example_data': 'unknown',
}


def _bare(kind: str, at: Optional[str] = None, precision: str = 'unknown',
          **extra: Any) -> dict:
    origin = {'kind': kind, 'at': at, 'at_precision': precision,
              'place': None, 'construction_work': None, 'method': None,
              'performed_by': [], 'notes': None}
    origin.update(extra)
    return origin


def origin_for(identity: dict,
               parent_origins: Sequence[dict] = ()) -> dict:
    """The 0.6 ``origin`` of one 0.5 identity (spec section 8.1 step 10).
    A child without salvage data takes its parents' origin when they agree
    (step 10b then lists it as inherited)."""
    if isinstance(identity.get('origin'), dict):      # already migrated
        return identity['origin']
    source = identity.get('salvage_source')
    if not source and parent_origins \
            and all(o == parent_origins[0] for o in parent_origins):
        return copy.deepcopy(parent_origins[0])
    dataset = identity.get('dataset')
    at = identity.get('salvaged_at')
    if dataset == 'dbu_zirkus':
        return copy.deepcopy(_ZIRKUS_ORIGIN)
    if source and source.startswith(_ROSSKOPF_PREFIX):
        if at and day_of(at) != _ROSSKOPF_ORIGIN['at']:
            raise MigrationAbort(f'identity {identity["_id"]}: Rosskopf '
                                 f'offcut with an unexpected date {at}')
        return copy.deepcopy(_ROSSKOPF_ORIGIN)
    if source == _EXFELD_SOURCE:
        return _bare('unknown', day_of(at) if at else None,
                     'day' if at else 'unknown',
                     place={'name': 'ExFeld', 'address': 'TU Darmstadt',
                            'location': None})
    if source and source.startswith(_BY_HAND_PREFIX):
        return _bare('unknown', notes=source)
    if source:
        raise MigrationAbort(f'identity {identity["_id"]}: unmapped '
                             f'salvage_source {source!r}')
    if dataset in _KIND_BY_DATASET:
        return _bare(_KIND_BY_DATASET[dataset])
    if dataset == 'ddu_aggregations' and not identity.get('parent_identities'):
        return copy.deepcopy(_ROSSKOPF_ORIGIN)
    raise MigrationAbort(f'identity {identity["_id"]}: no salvage data and '
                         f'no rule for dataset {dataset!r}')


# STEP 1: effective_from (decision 8.10) --------------------------------------
def v0_effective_from(identity: dict, v0: dict) -> Tuple[str, str]:
    """(effective_from, precision) of an identity's first snapshot: the
    cut for a child, else ``origin.at``, else the capture time, else
    ``created``."""
    if identity.get('parent_identities'):
        return v0['created'], 'exact'
    origin = origin_for(identity)
    if origin.get('at'):
        return origin['at'], origin.get('at_precision') or 'exact'
    captured = captured_at(identity, v0)
    if captured:
        return captured, 'exact'
    return v0['created'], 'exact'


def effective_from_all(
        identity: dict,
        snapshots: Sequence[dict]) -> Dict[str, Tuple[str, str]]:
    """snapshot id -> (effective_from, precision) for every snapshot of one
    identity; aborts unless the values are monotonic in ``version`` (I3)."""
    ordered = sorted(snapshots, key=lambda s: s['version'])
    out: Dict[str, Tuple[str, str]] = {}
    previous: Optional[datetime] = None
    for snap in ordered:
        if snap.get('effective_from'):
            value = (snap['effective_from'],
                     snap.get('effective_from_precision') or 'exact')
        elif snap['version'] == ordered[0]['version']:
            value = v0_effective_from(identity, snap)
        else:
            value = (snap['created'], 'exact')
        when = parse_ts(value[0])
        if previous is not None and when < previous:
            raise MigrationAbort(
                f'identity {identity["_id"]}: effective_from not monotonic '
                f'in version at v{snap["version"]} (I3)')
        previous = when
        out[snap['_id']] = value
    return out


# STEP 6: attributes -> capture (decision 7.7) --------------------------------
def captured_at(identity: dict, v0: Optional[dict] = None) -> Optional[str]:
    """The robot scan's recording time, if the 0.5 identity kept it."""
    if v0 and isinstance(v0.get('capture'), dict) \
            and v0['capture'].get('captured_at'):
        return v0['capture']['captured_at']
    meta = (identity.get('attributes') or {}).get('3d_scan_metadata') or {}
    created = meta.get('created_utc')
    return to_ts(parse_ts(created)) if created else None


EMPTY_CAPTURE = {
    'method': None, 'device': None, 'software': None, 'captured_at': None,
    'notes': None, 'coordinate_system': None, 'markers': [], 'fixtures': [],
}
ATTRIBUTE_KEYS = ('primitive', 'scan', '3d_scan_metadata')


def capture_from_attributes(identity: dict,
                            capture: Optional[dict]) -> Optional[dict]:
    """The v0 ``capture`` block after folding in the identity's ad-hoc
    attributes; None when there is nothing to record."""
    attributes = identity.get('attributes') or {}
    out = dict(EMPTY_CAPTURE, **(capture or {}))
    changed = capture is not None
    if '3d_scan_metadata' in attributes:
        out['method'] = 'photogrammetry'
        out['captured_at'] = captured_at(identity)
        changed = True
    if attributes.get('scan') not in (None, ''):
        out['notes'] = f'scan {attributes["scan"]}'
        changed = True
    return out if changed else None


def remaining_attributes(identity: dict) -> dict:
    return {k: v for k, v in (identity.get('attributes') or {}).items()
            if k not in ATTRIBUTE_KEYS}


# STEP 6c: robot-scan capture context (decision 7.7) --------------------------
RIG_COORDINATE_SYSTEM = {'name': 'DDU robot gripper marker plane',
                         'description': None}
_RIG_MARKERS = 4
_RIG_Z_MAX = 50.0          # the gripper's marker plane is z ~ 0
_COMPONENT_Z_MIN = 100.0   # markers on the stone sit well above it
# the end effector was cut out of the scan with a cylinder, r 160 mm, h 300 mm
# (3d_scan_metadata step4.cylinder_split); 260916: r <= 160, z -244 ... 250
_FIXTURE_R_MAX = 170.0
_FIXTURE_Z = (-260.0, 310.0)


def split_markers(snapshot_id: str,
                  points: Sequence[Sequence[float]]) -> List[dict]:
    """0.5 ``marker_points`` -> labelled markers. The import wrote the four
    blue rig markers first, then the green ones on the stone (260916: all
    70 scans); both bands are asserted."""
    markers = []
    for i, point in enumerate(points):
        rig = i < _RIG_MARKERS
        z = point[2]
        if rig and abs(z) > _RIG_Z_MAX:
            raise MigrationAbort(f'snapshot {snapshot_id}: marker {i} should '
                                 f'be on the rig plane, z = {z:.1f}')
        if not rig and z < _COMPONENT_Z_MIN:
            raise MigrationAbort(f'snapshot {snapshot_id}: marker {i} should '
                                 f'be on the component, z = {z:.1f}')
        if rig:
            markers.append({'label': f'blue_{i + 1}', 'role': 'rig',
                            'point': list(point)})
        else:
            markers.append({'label': f'green_{i - _RIG_MARKERS + 1}',
                            'role': 'component', 'point': list(point)})
    return markers


def assert_effector(snapshot_id: str, vertices: Iterable[Sequence[float]]):
    """The second mesh of a robot scan must be the gripper, not a stone."""
    radius = max((v[0] ** 2 + v[1] ** 2) ** 0.5 for v in vertices)
    zs = [v[2] for v in vertices]
    if radius > _FIXTURE_R_MAX or min(zs) < _FIXTURE_Z[0] \
            or max(zs) > _FIXTURE_Z[1]:
        raise MigrationAbort(f'snapshot {snapshot_id}: meshes[1] is not the '
                             f'end effector (bbox outside the gripper)')


def fixture_file(snapshot_id: str, index: int = 0) -> str:
    return f'capture/{snapshot_id}/fixtures/{index}.ply'


# STEP 10c: consumed_at -> exit (decision 6.3, 8.8) ---------------------------
_INSTALLED_NOTE = ('modified by students during the workshop; resulting '
                   'pieces not catalogued')


def exit_for(identity: dict, children_first_effective_from: Optional[str]
             ) -> Optional[dict]:
    """The 0.6 ``exit`` of a consumed identity; None if not consumed.

    A parent with catalogued children is split at the earliest child's first
    ``effective_from`` (I18 --- equal to ``consumed_at`` in 260916). A
    consumed piece without children is ``installed`` (build with debris) or
    ``lost`` (aggregations); anything else aborts.
    """
    if isinstance(identity.get('exit'), dict):        # already migrated
        return identity['exit']
    consumed = identity.get('consumed_at')
    if not consumed:
        return None
    if children_first_effective_from:
        return {'kind': 'split', 'at': children_first_effective_from,
                'at_precision': 'exact', 'construction_work': None,
                'notes': None, 'recorded_by_user_id': None}
    dataset = identity.get('dataset')
    kinds = {'ddu_build_with_debris': 'installed', 'ddu_aggregations': 'lost'}
    if dataset not in kinds:
        raise MigrationAbort(f'identity {identity["_id"]}: consumed without '
                             f'children in dataset {dataset!r}')
    return {'kind': kinds[dataset], 'at': to_ts(parse_ts(consumed)),
            'at_precision': 'exact', 'construction_work': None,
            'notes': _INSTALLED_NOTE, 'recorded_by_user_id': None}


# STEP 10b: lineage inheritance (decision 6.2) --------------------------------
def _field_value(doc: dict, field: str) -> Any:
    if field == 'manufactured_at':
        return (doc.get('manufactured_at'),
                doc.get('manufactured_precision') or 'unknown')
    return doc.get(field)


def inheritance_for(child: dict, parents: Sequence[dict]) -> dict:
    """``$set`` for one child: every inheritable field equal across the
    parents and the child is listed; ``manufactured_at`` always comes from
    the parents (0.5 GH wrote the child's creation time into it)."""
    update: Dict[str, Any] = {}
    inherited: List[str] = []
    for field in INHERITABLE_FIELDS:
        values = [_field_value(p, field) for p in parents]
        unanimous = all(v == values[0] for v in values)
        if not unanimous:
            continue
        if field == 'manufactured_at':
            update['manufactured_at'], update['manufactured_precision'] = \
                values[0]
            inherited.append(field)
        elif _field_value(child, field) == values[0]:
            inherited.append(field)
    update['inherited_fields'] = inherited
    update['inherited_from'] = parents[0]['_id'] if inherited else None
    return update


def lineage_order(identities: Sequence[dict]) -> List[dict]:
    """Children after their parents (breadth-first from the roots)."""
    by_id = {i['_id']: i for i in identities}
    done: set = set()
    out: List[dict] = []
    pending = list(identities)
    while pending:
        rest = []
        for identity in pending:
            parents = identity.get('parent_identities') or []
            if all(p in done or p not in by_id for p in parents):
                out.append(identity)
                done.add(identity['_id'])
            else:
                rest.append(identity)
        if len(rest) == len(pending):
            raise MigrationAbort('lineage cycle among '
                                 f'{[i["_id"] for i in rest][:5]}')
        pending = rest
    return out


# STEP 4: extrusions -> authored prism proxies --------------------------------
_IDENTITY_PLACEMENT = {'o': [0.0, 0.0, 0.0], 'x': [1.0, 0.0, 0.0],
                       'y': [0.0, 1.0, 0.0], 'z': [0.0, 0.0, 1.0]}


def proxies_from_extrusions(snapshot: dict) -> List[dict]:
    """0.5 extrusions (profile in xy, centred on z = 0 from -h/2 to +h/2)
    -> authored prisms with the identity placement (App. B)."""
    proxies = []
    for i, ext in enumerate((snapshot.get('geometry') or {})
                            .get('extrusions') or []):
        profile = ext.get('profile') or []
        height = ext.get('height')
        if len(profile) < 3 or not height or height <= 0:
            raise MigrationAbort(f'snapshot {snapshot["_id"]}: extrusion {i} '
                                 f'has no usable profile / height')
        proxies.append({
            'primitive': 'prism',
            'role': 'primary' if i == 0 else 'part',
            'params': {'profile': [list(p) for p in profile],
                       'holes': ext.get('holes'), 'height': height},
            'placement': dict(_IDENTITY_PLACEMENT),
            'fit': {'method': 'authored'},
            'deviation_maps': None,
            'regions': [],
        })
    return proxies


# EVIDENCE BUILDERS (steps 6d, 6b) --------------------------------------------
def _evidence_envelope(step: str, snapshot: dict, *, method: str,
                       source_tier: str, summary: dict, payload: dict,
                       description: str,
                       performed_by: List[dict]) -> dict:
    observed = day_of(snapshot['created'])
    return {
        '_id': migration_id(step, snapshot['_id']),
        'identity_id': snapshot['identity_id'],
        'method': method,
        'method_version': 1,
        'source_tier': source_tier,
        'standard': None,
        'observed_at': observed,
        'observed_at_precision': 'day',
        'sampled_at': None,
        'sampled_at_precision': None,
        'performed_by': performed_by,
        'recorded_by_user_id': snapshot['added_by_user_id'],
        'recorded_by_username': snapshot.get('added_by_username'),
        'position': {'kind': 'none', 'snapshot_id': snapshot['_id'],
                     'point': None, 'description': description},
        'summary': summary,
        'derived': [],
        'payload': payload,
        'destructive': False,
        'attachments': [],
        'notes': None,
        'status': 'published',
        'status_changed_by_user_id': None,
        'status_changed_at': None,
        'status_history': [],
        'verification': {'state': 'unverified', 'by': None, 'at': None,
                         'note': None},
        'supersedes': None,
        'superseded_by': None,
        'etag': None,
        'created': snapshot['created'],
        'lastmodified': snapshot['created'],
    }


def reinforcement_evidence(snapshot: dict) -> dict:
    """Step 6d: the 0.5 bars -> one ``reinforcement_layout`` record (7.8);
    the ZirKuS bars were modelled after the original drawing (user)."""
    bars = [{'spec': b.get('spec'), 'diameter_mm': b.get('diameter'),
             'points': [list(p) for p in b.get('points') or []]}
            for b in snapshot['geometry']['reinforcements']]
    diameters = [b['diameter_mm'] for b in bars if b['diameter_mm']]
    if not diameters:
        raise MigrationAbort(f'snapshot {snapshot["_id"]}: reinforcement '
                             f'without diameters')
    return _evidence_envelope(
        '6d', snapshot, method='reinforcement_layout',
        source_tier='archival',
        summary={'quantity': 'rebar_diameter', 'value': None,
                 'range': [min(diameters), max(diameters)], 'unit': 'mm',
                 'unit_entered': None, 'kind': 'claimed',
                 'uncertainty': None},
        payload={'basis': 'drawing', 'document': None, 'bars': bars},
        description='bar centrelines, in this snapshot\'s stored '
                    'coordinates',
        performed_by=[])


def condition_evidence(snapshot: dict) -> dict:
    """Step 6b: one 0.5 condition grade -> one ``visual_inspection``."""
    grade = snapshot['condition']
    return _evidence_envelope(
        '6b', snapshot, method='visual_inspection', source_tier='visual',
        summary={'quantity': 'condition_grade', 'value': grade,
                 'range': None, 'unit': None, 'unit_entered': None,
                 'kind': 'claimed', 'uncertainty': None},
        payload={'observations': [{'quantity': 'condition_grade',
                                   'value': grade, 'note': None}]},
        description='whole component',
        performed_by=[{'kind': 'user',
                       'user_id': snapshot['added_by_user_id'],
                       'name': None, 'organization': None, 'role': None}])


def varying_condition_datasets(pairs: Iterable[Tuple[str, Any]]
                               ) -> Dict[str, Dict[Any, int]]:
    """dataset -> {grade: count} over non-null 0.5 grades (for the table
    step 6b prints and for choosing the datasets whose grades vary)."""
    table: Dict[str, Dict[Any, int]] = {}
    for dataset, grade in pairs:
        if grade is None:
            continue
        counts = table.setdefault(dataset, {})
        counts[grade] = counts.get(grade, 0) + 1
    return table


# STEP 11b: retire the shared account (decision 6.5) --------------------------
def attribution_target(mapping: dict, *, snapshot_id: Optional[str] = None,
                       identity_id: Optional[str] = None,
                       dataset: Optional[str] = None) -> Optional[str]:
    """The personal user a shared-account record is re-attributed to: an
    explicit snapshot entry wins over the identity, the identity over the
    dataset; None when the mapping does not cover it."""
    for key, value in (('snapshots', snapshot_id),
                       ('identities', identity_id),
                       ('datasets', dataset)):
        if value is not None and value in (mapping.get(key) or {}):
            return mapping[key][value]
    return None
