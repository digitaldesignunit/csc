#!/usr/bin/env python3.13
"""
The invariants of data model spec section 5 as code.

Every id I1..I26 is registered once. Four kinds:

* ``document`` --- one document can break it; checked by validating each
  stored document against its model in ``documents.py`` (the validator
  message names the id, e.g. "(I4)").
* ``corpus``   --- spans documents (a snapshot and its identity, parents and
  children); a function over the whole corpus.
* ``route``    --- a rule about *changes* (immutability, allowed
  transitions); stored data cannot show a violation, the routes enforce it
  (plan P3 / P6).
* ``dropped``  --- kept as a tombstone so ids stay stable (I12).

Checks take a ``Corpus`` of plain dicts so they run without a database
(unit tests, the migration rehearsal);
``scripts/db_maintenance/check_invariants.py`` loads a corpus from MongoDB
and prints the report.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Type

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import BaseModel, ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import (
    ComponentIdentity,
    ComponentSnapshot,
    Dataset,
    Evidence,
    Material,
)
from apps.catalog.vocab import EVER_PUBLISHED_STATUSES, OPEN_STATUSES

IDENTITIES = 'component_identities'
SNAPSHOTS = 'component_snapshots'
EVIDENCE = 'component_evidence'


@dataclass
class Corpus:
    """One database's documents, as stored (dicts with ``_id``)."""
    identities: List[dict] = field(default_factory=list)
    snapshots: List[dict] = field(default_factory=list)
    evidence: List[dict] = field(default_factory=list)
    datasets: List[dict] = field(default_factory=list)
    materials: List[dict] = field(default_factory=list)
    users: List[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Violation:
    invariant: str      # 'I4', or 'schema' for a model error without an id
    collection: str
    doc_id: str
    message: str
    severity: str = 'error'     # 'error' | 'warning'


@dataclass(frozen=True)
class Invariant:
    id: str
    summary: str
    kind: str           # 'document' | 'corpus' | 'route' | 'dropped'
    check: Optional[Callable[['Corpus'], Iterable[Violation]]] = None


def _v(invariant: str, collection: str, doc: dict, message: str,
       severity: str = 'error') -> Violation:
    return Violation(invariant, collection, str(doc.get('_id')), message,
                     severity)


# DOCUMENT CHECKS -------------------------------------------------------------
_ID_IN_MESSAGE = re.compile(r'\((I\d+b?)\)')
_MODELS: Tuple[Tuple[str, str, Type[BaseModel]], ...] = (
    ('identities', IDENTITIES, ComponentIdentity),
    ('snapshots', SNAPSHOTS, ComponentSnapshot),
    ('evidence', EVIDENCE, Evidence),
    ('datasets', 'datasets', Dataset),
    ('materials', 'materials', Material),
)


def check_documents(corpus: Corpus) -> List[Violation]:
    """Validate every document; a model error violates the id it names."""
    out: List[Violation] = []
    for attr, collection, model in _MODELS:
        for doc in getattr(corpus, attr):
            try:
                model.model_validate(doc)
            except ValidationError as exc:
                for error in exc.errors():
                    match = _ID_IN_MESSAGE.search(error['msg'])
                    where = '.'.join(str(p) for p in error['loc'])
                    out.append(_v(match.group(1) if match else 'schema',
                                  collection, doc,
                                  f'{where}: {error["msg"]}'))
    return out


# CORPUS CHECKS ---------------------------------------------------------------
def _when(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] if value.endswith('Z')
                                  else value)


def _by_identity(corpus: Corpus) -> Dict[str, List[dict]]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for snap in corpus.snapshots:
        grouped[snap.get('identity_id')].append(snap)
    return grouped


def _ever_published(snaps: List[dict]) -> bool:
    return any(s.get('status') in EVER_PUBLISHED_STATUSES for s in snaps)


def check_i3(corpus: Corpus) -> Iterable[Violation]:
    """effective_from monotonic in version over an identity's snapshots."""
    for snaps in _by_identity(corpus).values():
        live = sorted(
            (s for s in snaps if s.get('status') == 'published'
             and not s.get('superseded_by') and s.get('effective_from')),
            key=lambda s: s.get('version', 0))
        for earlier, later in zip(live, live[1:]):
            if _when(later['effective_from']) \
                    < _when(earlier['effective_from']):
                yield _v('I3', SNAPSHOTS, later, 'effective_from before '
                         f'v{earlier.get("version")}')


def check_i3b(corpus: Corpus) -> Iterable[Violation]:
    """One open (draft / pending) snapshot per identity; current published."""
    by_id = {s['_id']: s for s in corpus.snapshots}
    for identity_id, snaps in _by_identity(corpus).items():
        open_ = [s for s in snaps if s.get('status') in OPEN_STATUSES]
        if len(open_) > 1:
            yield _v('I3b', IDENTITIES, {'_id': identity_id},
                     f'{len(open_)} draft / pending snapshots')
    for identity in corpus.identities:
        current = identity.get('current_snapshot_id')
        if current is None:
            continue
        snap = by_id.get(current)
        if snap is None or snap.get('status') != 'published' \
                or snap.get('identity_id') != identity['_id']:
            yield _v('I3b', IDENTITIES, identity,
                     'current_snapshot_id is not a published snapshot of it')


def check_i9(corpus: Corpus) -> Iterable[Violation]:
    """position.snapshot_id belongs to the record's identity."""
    owner = {s['_id']: s.get('identity_id') for s in corpus.snapshots}
    for record in corpus.evidence:
        sid = (record.get('position') or {}).get('snapshot_id')
        if sid is not None and owner.get(sid) != record.get('identity_id'):
            yield _v('I9', EVIDENCE, record, 'position.snapshot_id is not '
                     'a snapshot of this identity')


def _check_supersession(records: List[dict], collection: str,
                        same_method: bool,
                        invariant: str) -> Iterable[Violation]:
    by_id = {r['_id']: r for r in records}
    targets: Dict[str, str] = {}
    for record in records:
        old_id = record.get('supersedes')
        if old_id is None:
            continue
        old = by_id.get(old_id)
        if old is None or old.get('identity_id') != record.get('identity_id'):
            yield _v(invariant, collection, record,
                     'supersedes a record of another identity (or none)')
            continue
        if same_method and old.get('method') != record.get('method'):
            yield _v(invariant, collection, record,
                     'supersedes a record of another method')
        if old.get('status') not in EVER_PUBLISHED_STATUSES:
            yield _v(invariant, collection, record,
                     'supersedes an unpublished record')
        if old_id in targets and record.get('status') == 'published' \
                and by_id[targets[old_id]].get('status') == 'published':
            yield _v(invariant, collection, record,
                     'a record is superseded at most once (no forks)')
        targets.setdefault(old_id, record['_id'])


def check_i14(corpus: Corpus) -> Iterable[Violation]:
    """Evidence supersession: same identity and method, published target."""
    return _check_supersession(corpus.evidence, EVIDENCE, True, 'I14')


def check_i21(corpus: Corpus) -> Iterable[Violation]:
    """Snapshot supersession: same identity, published target, no forks."""
    return _check_supersession(corpus.snapshots, SNAPSHOTS, False, 'I21')


def check_i17(corpus: Corpus) -> Iterable[Violation]:
    """An inherited field equals the parent's (the server propagates)."""
    by_id = {i['_id']: i for i in corpus.identities}
    for child in corpus.identities:
        parent = by_id.get(child.get('inherited_from'))
        if child.get('inherited_fields') and parent is None:
            yield _v('I17', IDENTITIES, child,
                     'inherited_from names an unknown identity')
            continue
        for name in child.get('inherited_fields') or []:
            fields = (name,)
            if name == 'manufactured_at':
                fields = (name, 'manufactured_precision')
            for f in fields:
                if child.get(f) != parent.get(f):
                    yield _v('I17', IDENTITIES, child,
                             f'inherited {f} differs from the parent')


def check_i18(corpus: Corpus) -> Iterable[Violation]:
    """A server-set split / merged exit exists iff a published child does,
    at the earliest child effective_from (8.8)."""
    grouped = _by_identity(corpus)
    children: Dict[str, List[dict]] = defaultdict(list)
    for identity in corpus.identities:
        for parent_id in identity.get('parent_identities') or []:
            children[parent_id].append(identity)

    def first_published(child: dict) -> Optional[datetime]:
        times = [_when(s['effective_from'])
                 for s in grouped.get(child['_id'], [])
                 if s.get('status') in EVER_PUBLISHED_STATUSES
                 and s.get('effective_from')]
        return min(times) if times else None

    for identity in corpus.identities:
        live = [c for c in children.get(identity['_id'], [])
                if not c.get('withdrawn') and first_published(c) is not None]
        exit_ = identity.get('exit') or {}
        server_set = exit_.get('kind') in ('split', 'merged') \
            and exit_.get('recorded_by_user_id') is None
        if live and not exit_:
            yield _v('I18', IDENTITIES, identity,
                     'has published children but no split / merged exit')
        elif server_set and not live:
            yield _v('I18', IDENTITIES, identity, 'server-set split / '
                     'merged exit without a published child')
        elif server_set:
            earliest = min(first_published(c) for c in live)
            if _when(exit_['at']) != earliest:
                yield _v('I18', IDENTITIES, identity,
                         'exit.at is not the earliest child effective_from')


def check_i19(corpus: Corpus) -> Iterable[Violation]:
    """duplicate_of names an existing, non-withdrawn identity (no chains)."""
    by_id = {i['_id']: i for i in corpus.identities}
    for identity in corpus.identities:
        target_id = (identity.get('withdrawn') or {}).get('duplicate_of')
        if target_id is None:
            continue
        target = by_id.get(target_id)
        if target is None or target.get('withdrawn'):
            yield _v('I19', IDENTITIES, identity, 'duplicate_of must name '
                     'a live identity (re-point to the terminal)')


def check_i20(corpus: Corpus) -> Iterable[Violation]:
    """Dataset FK; one enabled admin; datasets without moderator warned."""
    known = {d['_id'] for d in corpus.datasets}
    for identity in corpus.identities:
        if identity.get('dataset') not in known:
            yield _v('I20', IDENTITIES, identity,
                     f'unknown dataset {identity.get("dataset")!r}')
    admins = [u for u in corpus.users
              if u.get('role') == 'admin' and not u.get('disabled')]
    if corpus.users and not admins:
        yield _v('I20', 'users', {'_id': '-'}, 'no enabled admin')
    for dataset in corpus.datasets:
        members = dataset.get('members') or []
        if not any('moderator' in (m.get('roles') or []) for m in members):
            yield _v('I20', 'datasets', dataset,
                     'no moderator: administered by admins only', 'warning')


def check_i25(corpus: Corpus) -> Iterable[Violation]:
    """Material FK; a derived material_class equals the default class."""
    materials = {m['_id']: m for m in corpus.materials}
    for identity in corpus.identities:
        material = materials.get(identity.get('material'))
        derived = identity.get('material_class_source', 'derived') \
            == 'derived'
        if material is None:
            yield _v('I25', IDENTITIES, identity,
                     f'unknown material {identity.get("material")!r}')
        elif derived and identity.get('material_class') \
                != material.get('default_class'):
            yield _v('I25', IDENTITIES, identity, 'derived material_class '
                     'differs from the default class')


def check_i26(corpus: Corpus) -> Iterable[Violation]:
    """No published evidence on an unpublished identity (8.9)."""
    grouped = _by_identity(corpus)
    for record in corpus.evidence:
        snaps = grouped.get(record.get('identity_id'), [])
        if record.get('status') in EVER_PUBLISHED_STATUSES \
                and not _ever_published(snaps):
            yield _v('I26', EVIDENCE, record,
                     'published evidence on an unpublished identity')


# REGISTRY (spec section 5) ---------------------------------------------------
INVARIANTS: Tuple[Invariant, ...] = (
    Invariant('I1', 'geometry: a mesh, a point cloud or an authored proxy',
              'document'),
    Invariant('I2', 'exactly one primary proxy once proxies exist',
              'document'),
    Invariant('I3', 'effective_from set and monotonic per identity',
              'corpus', check_i3),
    Invariant('I3b', 'one open snapshot per identity; current published',
              'corpus', check_i3b),
    Invariant('I4', 'composite is assigned, never derived', 'document'),
    Invariant('I5', 'evidence identity_id is immutable', 'route'),
    Invariant('I6', 'summary has value or range fitting its quantity',
              'document'),
    Invariant('I7', 'one result per quantity per record', 'document'),
    Invariant('I8', 'payload validates against its method (P6)', 'route'),
    Invariant('I9', 'position.snapshot_id belongs to the identity',
              'corpus', check_i9),
    Invariant('I10', 'observed_at >= sampled_at', 'document'),
    Invariant('I11', 'properties never accepted from a client', 'route'),
    Invariant('I12', 'dropped (6.13)', 'dropped'),
    Invariant('I13', 'frozen evidence fields change only by supersession',
              'route'),
    Invariant('I14', 'evidence supersession: same identity and method, '
              'no forks', 'corpus', check_i14),
    Invariant('I15', 'status transitions', 'route'),
    Invariant('I16', 'origin.construction_work only for deinstallation / '
              'demolition', 'document'),
    Invariant('I17', 'inherited fields server-maintained, equal to the '
              'parent', 'corpus', check_i17),
    Invariant('I18', 'exit rules; server-set split / merged from '
              'published children', 'corpus', check_i18),
    Invariant('I19', 'hard delete only if never published; duplicate_of '
              'live', 'corpus', check_i19),
    Invariant('I20', 'dataset FK; an enabled admin exists; datasets have '
              'moderators', 'corpus', check_i20),
    Invariant('I21', 'published snapshots frozen; snapshot supersession',
              'corpus', check_i21),
    Invariant('I22', 'accredited needs a covering accreditation',
              'document'),
    Invariant('I23', 'markers / fixtures never geometry; layouts name '
              'their snapshot', 'document'),
    Invariant('I24', 'published attachments add-only, removal leaves a '
              'tombstone', 'route'),
    Invariant('I25', 'material FK; derived material_class = default '
              'class', 'corpus', check_i25),
    Invariant('I26', 'no published evidence on an unpublished identity',
              'corpus', check_i26),
)
INVARIANT_BY_ID: Dict[str, Invariant] = {inv.id: inv for inv in INVARIANTS}


def check_all(corpus: Corpus) -> List[Violation]:
    """Every data check: document validation plus each corpus invariant."""
    violations = check_documents(corpus)
    for inv in INVARIANTS:
        if inv.check is not None:
            violations.extend(inv.check(corpus))
    return violations
