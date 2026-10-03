#!/usr/bin/env python3.13
"""
What the read routes serve: the 0.6 documents (``documents.py``) plus the
few row shapes that are not a stored document (plan P2, read-only
catch-up).

The 0.5 response models in ``models.py`` stay with the 0.5 write routes
until their phase rebuilds them (P3 / P4 / P7).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, List, Literal, Optional

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import BaseModel, ConfigDict, Field

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import (
    ComponentIdentity,
    ComponentSnapshot,
    Exit,
    Frame,
    GeoLocation,
    Geometry,
    Origin,
)
from apps.catalog.vocab import Precision, ShapeClass, Status


# PASSPORT --------------------------------------------------------------------
class ComponentPassport(BaseModel):
    """``GET /identities/{id}/compose``: one identity and its snapshots."""
    identity: ComponentIdentity
    snapshots: List[ComponentSnapshot]
    # only with ?include=evidence (spec 7.2): the published evidence, as the
    # caller sees it (the shape of GET /evidence/{id})
    evidence: Optional[List[Dict[str, Any]]] = None


def identity_body(doc: Dict[str, Any]) -> Dict[str, Any]:
    return ComponentIdentity.model_validate(doc).model_dump(
        by_alias=True, mode='json')


def snapshot_body(doc: Dict[str, Any]) -> Dict[str, Any]:
    body = ComponentSnapshot.model_validate(doc) \
        .model_dump(by_alias=True, mode='json')
    # a stage error is operational: the stored text stays on the document
    # (and in the runner's log); readers only see that a stage failed
    stamps = {stage: stamp
              for stage, stamp in (body.get('derivation') or {}).items()
              if stamp}
    for stamp in stamps.values():
        if stamp.get('error'):
            stamp['error'] = 'failed'
    body['derivation'] = stamps
    return body


def passport_body(identity_doc: Dict[str, Any],
                  snapshot_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {'identity': identity_body(identity_doc),
            'snapshots': [snapshot_body(doc) for doc in snapshot_docs]}


# CATALOG ROW (GET /identities?expand=shallow) --------------------------------
class CatalogRow(BaseModel):
    """
    One catalog list row: identity core + current-snapshot metadata. Not a
    stored document; the list, map and children routes serve it.
    """
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias='_id')
    catalog_number: int
    original_function: str
    material: str
    material_class: str
    trade_name: Optional[str] = None
    dataset: str
    origin: Optional[Origin] = None
    exit: Optional[Exit] = None
    reserved: str = ''
    reserved_by_username: Optional[str] = None
    is_public: bool = False
    current_snapshot_id: Optional[str] = None
    # current snapshot
    identity_id: str
    version: int
    status: Status
    name: Optional[str] = None
    effective_from: Optional[str] = None
    effective_from_precision: Optional[Precision] = None
    shape_class: Optional[ShapeClass] = None
    complexity: Optional[int] = None
    fragment: bool = False
    quantity: int = 1
    color: Optional[List[int]] = None
    location: Optional[GeoLocation] = None
    bbx: Optional[List[float]] = None
    frame: Optional[Frame] = None
    etag: Optional[str] = None
    created: str
    lastmodified: str


def catalog_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    """An aggregation row (identity + ``current_snapshot``) -> CatalogRow."""
    snap = doc.get('current_snapshot') or {}
    row = {
        '_id': doc['_id'],
        'catalog_number': doc.get('catalog_number'),
        'original_function': doc.get('original_function'),
        'material': doc.get('material'),
        'material_class': doc.get('material_class'),
        'trade_name': doc.get('trade_name'),
        'dataset': doc.get('dataset'),
        'origin': doc.get('origin'),
        'exit': doc.get('exit'),
        'reserved': doc.get('reserved') or '',
        'reserved_by_username': doc.get('reserved_by_username'),
        'is_public': bool(doc.get('is_public')),
        'current_snapshot_id': doc.get('current_snapshot_id'),
        **{key: snap.get(key) for key in (
            'identity_id', 'version', 'status', 'name', 'effective_from',
            'effective_from_precision', 'shape_class', 'complexity',
            'color', 'location', 'bbx', 'frame', 'etag', 'created',
            'lastmodified')},
        'fragment': bool(snap.get('fragment')),
        'quantity': snap.get('quantity') or 1,
    }
    return CatalogRow.model_validate(row).model_dump(by_alias=True,
                                                     mode='json')


# SNAPSHOT ROWS ---------------------------------------------------------------
class SnapshotSummaryItem(BaseModel):
    """Row for ``GET /identities/{id}/snapshots``."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias='_id')
    identity_id: str
    version: int
    status: Status
    is_current: bool
    name: Optional[str] = None
    effective_from: str
    effective_from_precision: Precision = 'exact'
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    added_by_user_id: Optional[str] = None
    added_by_username: Optional[str] = None
    status_changed_at: Optional[str] = None
    geometry_failed: bool = False
    created: str
    lastmodified: str


GEOMETRY_STAGES = ('frame', 'shape_class', 'proxies')


def geometry_failed(doc: Dict[str, Any]) -> bool:
    """True when frame, class or proxy could not be derived: the frame, size,
    class and proxies the snapshot shows are those of an earlier geometry
    (decision 8.60). The text of the error is never part of this."""
    derivation = doc.get('derivation') or {}
    return any((derivation.get(stage) or {}).get('error')
               for stage in GEOMETRY_STAGES)


class PendingSnapshotItem(BaseModel):
    """Row for the moderation queue ``GET /snapshots/pending``."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias='_id')
    identity_id: str
    version: int
    status: Status
    is_current: bool
    name: Optional[str] = None
    created: str
    catalog_number: Optional[int] = None
    original_function: Optional[str] = None
    material: Optional[str] = None
    dataset: Optional[str] = None
    live_version: Optional[int] = Field(
        default=None,
        description='Version of the identity\'s current snapshot, if any')
    supersedes: Optional[str] = Field(
        default=None, description='set when this corrects a published one')
    added_by_username: Optional[str] = None


class Tombstone(BaseModel):
    """A withdrawn record seen from outside its dataset (8.17): 200 with
    this body instead of the record."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias='_id')
    kind: Literal['identity', 'snapshot', 'evidence']
    status: Literal['withdrawn']
    withdrawn_at: Optional[str] = None
    version: Optional[int] = None
    catalog_number: Optional[int] = None
    identity_id: Optional[str] = None
    current_snapshot_id: Optional[str] = None
    duplicate_of: Optional[str] = None


class CatalogSharedTypesEnvelope(BaseModel):
    """Codegen-only: the shared value types (``/schema/catalog-shared``)."""
    frame: Frame
    location: GeoLocation
    geometry: Geometry
