#!/usr/bin/env python3.13
"""
Document models of the 0.6 data model (data model spec section 3).

One model per stored document --- identity, snapshot, evidence, dataset,
material, purge stub --- plus the blocks they are built from. Top-level
documents ignore unknown keys (envelopes); nested blocks forbid them, so a
misspelt field fails instead of being dropped silently.

Invariants that one document can check on its own are validators here; each
error message names its invariant id, e.g. "(I4)" (spec section 5).
Invariants that span documents are checked by ``invariants.py`` and by the
routes.

Evidence ``payload`` stays an untyped dict until the method registry lands
(spec section 4.5, plan P6).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import re
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, Union

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.vocab import (
    DESTRUCTIVE_METHODS,
    INHERITABLE_FIELDS,
    METHOD_TIER,
    ORDINAL_RANGE,
    ORIGIN_KINDS_WITH_CONSTRUCTION_WORK,
    QUANTITY_BY_NAME,
    REINFORCEMENT_BASIS_TIER,
    AccreditationScheme,
    ActorKind,
    ActorRole,
    CaptureMethod,
    DatasetRole,
    EvidenceMethod,
    ExitKind,
    FitMethod,
    FitSourceKind,
    FitSourceResolution,
    MarkerRole,
    MaterialGroup,
    OriginalFunction,
    OriginKind,
    PositionKind,
    Precision,
    Primitive,
    PropertySource,
    ProxyRole,
    RegionReason,
    ResolutionHint,
    ShapeClass,
    SourceTier,
    Status,
    SummaryKind,
    UncertaintyType,
    ValueSource,
    VerificationState,
    Visibility,
)


# SHARED TYPES ----------------------------------------------------------------
def _iso_utc(value: str) -> str:
    """ISO-8601 UTC timestamp string ending in 'Z' (spec section 3)."""
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ValueError(
            'timestamp must be an ISO-8601 UTC string ending in Z')
    try:
        datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ValueError(f'not an ISO-8601 timestamp: {value!r}') from exc
    return value


_LOW_CODE = re.compile(r'^17 \d{2} \d{2}\*?$')


def _low_code(value: str) -> str:
    """EU List of Waste chapter 17 code, e.g. '17 01 01' (hazardous: '*')."""
    if not _LOW_CODE.match(value):
        raise ValueError(f'not a List of Waste chapter 17 code: {value!r}')
    return value


def _slug(value: str) -> str:
    if not re.match(r'^[a-z0-9][a-z0-9_]{1,62}$', value):
        raise ValueError('slug: lower-case letters, digits and underscores')
    return value


Timestamp = Annotated[str, AfterValidator(_iso_utc)]
LowCode = Annotated[str, AfterValidator(_low_code)]
Slug = Annotated[str, AfterValidator(_slug)]
Vec3 = Annotated[List[float], Field(min_length=3, max_length=3)]
Vec2 = Annotated[List[float], Field(min_length=2, max_length=2)]
Rgb = Annotated[List[Annotated[int, Field(ge=0, le=255)]],
                Field(min_length=3, max_length=3)]
Grade = Annotated[int, Field(ge=0, le=3)]


class _Block(BaseModel):
    """Nested block: unknown keys are errors."""
    model_config = ConfigDict(extra='forbid', populate_by_name=True)


class _Document(BaseModel):
    """Stored top-level document: unknown keys are ignored (envelope)."""
    model_config = ConfigDict(extra='ignore', populate_by_name=True)


def _later_or_equal(a: str, b: str) -> bool:
    """True when ISO-UTC timestamp ``a`` is not before ``b``."""
    return datetime.fromisoformat(a[:-1]) >= datetime.fromisoformat(b[:-1])


# ACTOR (section 3.3.1) -------------------------------------------------------
class Accreditation(_Block):
    scheme: AccreditationScheme = Field(
        description='iso_17025 = laboratory accreditation (e.g. DAkkS); '
                    'notified_body = CPR notified body (Art 52 number)')
    id: str = Field(description='Accreditation or notified-body number')
    body: str = Field(description='Accrediting or notifying authority')
    scope: List[str] = Field(
        min_length=1, description='Standards the accreditation covers')
    valid_until: Optional[Timestamp] = None


class Actor(_Block):
    """A person or organization credited with an act."""
    kind: ActorKind
    user_id: Optional[str] = None
    name: Optional[str] = None
    organization: Optional[str] = None
    organization_ror: Optional[str] = None
    orcid: Optional[str] = None
    email: Optional[str] = None
    role: Optional[ActorRole] = None
    accreditation: Optional[Accreditation] = None
    redacted_at: Optional[Timestamp] = None

    @model_validator(mode='after')
    def _named(self) -> 'Actor':
        if self.kind == 'user' and not self.user_id:
            raise ValueError('actor kind "user" needs user_id')
        if self.kind in ('person', 'organization') \
                and self.redacted_at is None \
                and not (self.name or self.organization):
            raise ValueError('actor needs a name or an organization')
        return self


# IDENTITY BLOCKS (section 3.1) -----------------------------------------------
class GeoLocation(_Block):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Place(_Block):
    name: Optional[str] = None
    address: Optional[str] = None
    location: Optional[GeoLocation] = None


class ConstructionWork(_Block):
    """The works a piece left or went into --- never the company."""
    name: str
    identifier: Optional[str] = None
    year_built: Optional[int] = None
    use: Optional[str] = None


class Origin(_Block):
    """How the piece entered circulation (section 3.1.1)."""
    kind: OriginKind
    at: Optional[Timestamp] = None
    at_precision: Precision = 'unknown'
    place: Optional[Place] = None
    construction_work: Optional[ConstructionWork] = None
    method: Optional[str] = None
    performed_by: List[Actor] = Field(default_factory=list)
    notes: Optional[str] = None

    @model_validator(mode='after')
    def _construction_work_kind(self) -> 'Origin':
        if self.construction_work is not None \
                and self.kind not in ORIGIN_KINDS_WITH_CONSTRUCTION_WORK:
            raise ValueError('origin.construction_work only for '
                             'deinstallation / demolition (I16)')
        return self


class Exit(_Block):
    """How the piece left circulation (section 3.1.3)."""
    kind: ExitKind
    at: Timestamp
    at_precision: Precision = 'exact'
    construction_work: Optional[ConstructionWork] = None
    notes: Optional[str] = None
    recorded_by_user_id: Optional[str] = None

    @model_validator(mode='after')
    def _construction_work_kind(self) -> 'Exit':
        if self.construction_work is not None and self.kind != 'installed':
            raise ValueError(
                'exit.construction_work only for kind installed (I18)')
        return self


class PastCycle(_Block):
    origin: Optional[Origin] = None
    exit: Exit


class StatusChange(_Block):
    """One status transition of a snapshot or evidence record (8.30):
    append-only, so the timeline and the audit keep every moderation act."""
    from_: Status = Field(alias='from')
    to: Status
    at: Timestamp
    by_user_id: str
    reason: Optional[str] = None


class Withdrawn(_Block):
    """Record-level tombstone (section 3.1.4)."""
    at: Timestamp
    by_user_id: str
    reason: str = Field(min_length=1)
    duplicate_of: Optional[str] = None


class PropertyValue(_Block):
    """One derived property (section 4.4): never authored."""
    range: List[Union[float, str]] = Field(min_length=1)
    unit: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    source: PropertySource
    n: int = Field(ge=0)
    evidence_ids: List[str] = Field(default_factory=list)
    inherited_from: Optional[List[str]] = None
    derived_at: Timestamp


class ComponentIdentity(_Document):
    """``component_identities``: the permanent record of one component."""
    id: str = Field(alias='_id')
    catalog_number: int = Field(ge=1)
    original_function: OriginalFunction
    material: str = Field(description='FK -> materials._id (I25)')
    material_class: LowCode
    material_class_source: ValueSource = 'derived'
    trade_name: Optional[str] = None
    dataset: str = Field(description='FK -> datasets._id (I20)')
    manufactured_at: Optional[Timestamp] = None
    manufactured_precision: Precision = 'unknown'
    origin: Optional[Origin] = None
    parent_identities: Optional[List[str]] = None
    inherited_fields: List[str] = Field(default_factory=list)
    inherited_from: Optional[str] = None
    exit: Optional[Exit] = None
    past_cycles: List[PastCycle] = Field(default_factory=list)
    withdrawn: Optional[Withdrawn] = None
    reserved: str = ''
    is_public: bool = False
    current_snapshot_id: Optional[str] = None
    properties: Dict[str, PropertyValue] = Field(default_factory=dict)
    properties_version: int = 1
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: str
    created: Timestamp
    lastmodified: Timestamp

    @field_validator('inherited_fields')
    @classmethod
    def _inheritable(cls, value: List[str]) -> List[str]:
        unknown = set(value) - set(INHERITABLE_FIELDS)
        if unknown:
            raise ValueError(f'not inheritable: {sorted(unknown)} (I17)')
        if len(set(value)) != len(value):
            raise ValueError('inherited_fields repeats a field (I17)')
        return value

    @model_validator(mode='after')
    def _consistency(self) -> 'ComponentIdentity':
        if self.inherited_fields and (
                not self.parent_identities
                or self.inherited_from not in self.parent_identities):
            raise ValueError(
                'inherited_from must be one of parent_identities (I17)')
        if self.reserved and self.exit is not None:
            raise ValueError(
                'a piece out of circulation cannot be reserved (I18)')
        if self.withdrawn and self.withdrawn.duplicate_of == self.id:
            raise ValueError(
                'an identity cannot be a duplicate of itself (I19)')
        if self.parent_identities and self.id in self.parent_identities:
            raise ValueError('an identity cannot be its own parent')
        return self


# SNAPSHOT BLOCKS (section 3.2) -----------------------------------------------
class Frame(_Block):
    """Origin + three axes: the canonical frame or a proxy's placement."""
    o: Vec3
    x: Vec3
    y: Vec3
    z: Vec3


class Mesh(_Block):
    vertices: List[Vec3]
    faces: List[List[int]]
    colors: Optional[List[Rgb]] = None

    @model_validator(mode='after')
    def _indices(self) -> 'Mesh':
        count = len(self.vertices)
        for face in self.faces:
            if len(face) < 3 or any(i < 0 or i >= count for i in face):
                raise ValueError(
                    'mesh face with fewer than 3 or out-of-range indices')
        if self.colors is not None and len(self.colors) != count:
            raise ValueError('mesh colors must parallel vertices')
        return self


class PointCloud(_Block):
    points: List[Vec3]
    colors: Optional[List[Rgb]] = None

    @model_validator(mode='after')
    def _parallel(self) -> 'PointCloud':
        if self.colors is not None and len(self.colors) != len(self.points):
            raise ValueError('point cloud colors must parallel points')
        return self


class BoxParams(_Block):
    size: Vec3


class PrismParams(_Block):
    profile: List[Vec2] = Field(min_length=3)
    holes: Optional[List[List[Vec2]]] = None
    height: float = Field(gt=0)


class CylinderParams(_Block):
    radius: float = Field(gt=0)
    height: float = Field(gt=0)


class HullParams(_Block):
    vertices: List[Vec3] = Field(min_length=4)
    faces: List[List[int]] = Field(min_length=4)


PRIMITIVE_PARAMS = {
    'box': BoxParams,
    'prism': PrismParams,
    'cylinder': CylinderParams,
    'hull': HullParams,
}


class FitSource(_Block):
    kind: FitSourceKind
    index: int = Field(ge=0)
    resolution: FitSourceResolution


class Fit(_Block):
    method: FitMethod
    source: Optional[FitSource] = None
    n_points: Optional[int] = Field(None, ge=0)
    inlier_ratio: Optional[float] = Field(None, ge=0.0, le=1.0)
    rms_mm: Optional[float] = Field(None, ge=0.0)
    max_mm: Optional[float] = Field(None, ge=0.0)
    p95_mm: Optional[float] = Field(None, ge=0.0)
    spec_version: Optional[int] = None
    computed_at: Optional[Timestamp] = None

    @model_validator(mode='after')
    def _authored(self) -> 'Fit':
        """An authored proxy has no source and no residuals (3.2.1)."""
        residuals = (self.n_points, self.inlier_ratio, self.rms_mm,
                     self.max_mm, self.p95_mm)
        if self.method == 'authored':
            if self.source is not None \
                    or any(r is not None for r in residuals):
                raise ValueError(
                    'an authored fit has no source and no residuals')
        elif self.source is None:
            raise ValueError('a fitted proxy names its source geometry')
        return self


class MapScale(_Block):
    scale_mm: float
    offset_mm: float


class DeviationMapFace(_Block):
    file: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    distance: MapScale


class DeviationMaps(_Block):
    resolution_mm: float = Field(gt=0)
    channels: List[str]
    faces: Dict[str, DeviationMapFace]


class Bounds(_Block):
    min: Vec3
    max: Vec3


class Region(_Block):
    """Local resolution relevance --- a schema slot only in 0.6 (3.6)."""
    label: str
    bounds: Bounds
    resolution_hint: ResolutionHint
    reason: RegionReason
    source: ValueSource


class Proxy(_Block):
    """A primitive standing in for the snapshot's shape (3.2.1, App. B)."""
    primitive: Primitive
    role: ProxyRole
    params: Dict[str, Any]
    placement: Frame
    fit: Fit
    deviation_maps: Optional[DeviationMaps] = None
    regions: List[Region] = Field(default_factory=list)

    @model_validator(mode='after')
    def _params_and_fit(self) -> 'Proxy':
        PRIMITIVE_PARAMS[self.primitive].model_validate(self.params)
        if self.fit.method == 'authored' and self.deviation_maps is not None:
            raise ValueError('an authored proxy has no deviation maps')
        return self


class Geometry(_Block):
    meshes: List[Mesh] = Field(default_factory=list)
    point_clouds: List[PointCloud] = Field(default_factory=list)
    proxies: List[Proxy] = Field(default_factory=list)

    @model_validator(mode='after')
    def _representation(self) -> 'Geometry':
        authored = any(p.fit.method == 'authored' for p in self.proxies)
        if not (self.meshes or self.point_clouds or authored):
            raise ValueError('geometry needs a mesh, a point cloud or an '
                             'authored proxy (I1)')
        if self.proxies \
                and sum(p.role == 'primary' for p in self.proxies) != 1:
            raise ValueError('exactly one proxy has role primary (I2)')
        return self


class CoordinateSystem(_Block):
    name: str
    description: Optional[str] = None


class Marker(_Block):
    label: str
    role: MarkerRole
    point: Vec3


class Fixture(_Block):
    label: str
    file: str


class Capture(_Block):
    """How this snapshot's geometry was recorded (section 3.2.3)."""
    method: Optional[CaptureMethod] = None
    device: Optional[str] = None
    software: Optional[str] = None
    captured_at: Optional[Timestamp] = None
    notes: Optional[str] = None
    coordinate_system: Optional[CoordinateSystem] = None
    markers: List[Marker] = Field(default_factory=list)
    fixtures: List[Fixture] = Field(default_factory=list)


class ComponentSnapshot(_Document):
    """``component_snapshots``: one recorded state of a component."""
    id: str = Field(alias='_id')
    identity_id: str
    version: int = Field(ge=0)
    status: Status
    status_changed_by_user_id: Optional[str] = None
    status_changed_at: Optional[Timestamp] = None
    status_history: List[StatusChange] = Field(default_factory=list)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    name: Optional[str] = None
    effective_from: Timestamp
    effective_from_precision: Precision = 'exact'
    shape_class: Optional[ShapeClass] = None
    shape_class_source: Optional[ValueSource] = None
    geometry: Geometry
    capture: Optional[Capture] = None
    descriptors: Dict[str, Any] = Field(default_factory=dict)
    properties: Dict[str, PropertyValue] = Field(default_factory=dict)
    properties_version: int = 1
    frame: Optional[Frame] = None
    bbx: Optional[Vec3] = None
    complexity: Optional[Grade] = None
    complexity_source: Optional[ValueSource] = None
    fragment: bool = False
    color: Optional[Rgb] = None
    location: Optional[GeoLocation] = None
    notes: Optional[str] = None
    quantity: int = Field(1, ge=1)
    added_by_user_id: str
    added_by_username: Optional[str] = None
    photo_count: int = Field(0, ge=0)
    mesh_ply_resolutions: Dict[str, List[str]] = Field(default_factory=dict)
    etag: Optional[str] = None
    created: Timestamp
    lastmodified: Timestamp

    @model_validator(mode='after')
    def _consistency(self) -> 'ComponentSnapshot':
        if (self.shape_class is None) != (self.shape_class_source is None):
            raise ValueError('shape_class and shape_class_source come '
                             'together')
        if self.shape_class == 'composite' \
                and self.shape_class_source != 'assigned':
            raise ValueError(
                'composite is always assigned, never derived (I4)')
        if (self.complexity is None) != (self.complexity_source is None):
            raise ValueError('complexity and complexity_source come '
                             'together')
        if self.supersedes is not None and self.supersedes == self.id:
            raise ValueError('a snapshot cannot supersede itself')
        return self


# EVIDENCE BLOCKS (section 3.3) -----------------------------------------------
class Standard(_Block):
    code: str
    year: Optional[int] = None


class Position(_Block):
    """Where on the piece (3.3.2); kind none + description always works."""
    kind: PositionKind = 'none'
    snapshot_id: Optional[str] = None
    point: Optional[Vec3] = None
    description: Optional[str] = None

    @model_validator(mode='after')
    def _point(self) -> 'Position':
        if self.point is not None and self.snapshot_id is None:
            raise ValueError('a position point needs the snapshot whose '
                             'coordinates it uses')
        if self.kind == 'point' and self.point is None:
            raise ValueError('position kind point needs a point')
        if self.kind == 'none' and not self.description:
            raise ValueError('position kind none needs a description')
        return self


class Uncertainty(_Block):
    type: UncertaintyType
    value: Optional[float] = Field(None, ge=0.0)
    k: Optional[float] = Field(None, gt=0.0)


def _check_result(quantity: str, value: Any, range_: Any,
                  unit: Optional[str]) -> None:
    """I6: a value or a range, fitting the quantity's kind and unit."""
    spec = QUANTITY_BY_NAME.get(quantity)
    if spec is None:
        raise ValueError(f'unknown quantity: {quantity!r}')
    if value is None and not range_:
        raise ValueError(f'{quantity}: needs a value or a range (I6)')
    if spec.unit is not None and unit != spec.unit:
        raise ValueError(f'{quantity}: unit must be {spec.unit!r} '
                         f'(canonical), got {unit!r} (I6)')
    items = ([value] if value is not None else []) + list(range_ or [])
    if spec.kind == 'categorical':
        if not all(isinstance(v, str) for v in items):
            raise ValueError(
                f'{quantity}: categorical values are strings (I6)')
    elif spec.kind == 'ordinal':
        low, high = ORDINAL_RANGE
        if not all(isinstance(v, int) and not isinstance(v, bool)
                   and low <= v <= high for v in items):
            raise ValueError(f'{quantity}: ordinal values are integers '
                             f'{low}..{high} (I6)')
    elif not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                 for v in items):
        raise ValueError(f'{quantity}: scalar values are numbers (I6)')
    if spec.kind != 'categorical' and range_:
        if len(range_) != 2 or range_[0] > range_[1]:
            raise ValueError(f'{quantity}: range is [low, high] (I6)')


class Summary(_Block):
    """The record's one headline result --- the fold input (3.3)."""
    quantity: str
    value: Optional[Union[float, int, str]] = None
    range: Optional[List[Union[float, int, str]]] = None
    unit: Optional[str] = None
    unit_entered: Optional[str] = None
    kind: SummaryKind
    uncertainty: Optional[Uncertainty] = None

    @model_validator(mode='after')
    def _fits_quantity(self) -> 'Summary':
        _check_result(self.quantity, self.value, self.range, self.unit)
        return self


class DerivationModel(_Block):
    kind: str
    reference: Optional[str] = None
    note: Optional[str] = None


class DerivedResult(_Block):
    """A value derived from the record's result by a named model."""
    quantity: str
    value: Optional[Union[float, int, str]] = None
    range: Optional[List[Union[float, int, str]]] = None
    unit: Optional[str] = None
    kind: str = 'derived'
    model: DerivationModel

    @model_validator(mode='after')
    def _fits_quantity(self) -> 'DerivedResult':
        if self.kind != 'derived':
            raise ValueError('a derived result has kind "derived"')
        _check_result(self.quantity, self.value, self.range, self.unit)
        return self


class AttachmentRemoval(_Block):
    at: Timestamp
    by_user_id: str
    reason: str = Field(min_length=1)


class Attachment(_Block):
    """One file of an evidence record (7.3); removal leaves a tombstone."""
    index: int = Field(ge=0)
    name: str
    media_type: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    uploaded_by_user_id: str
    uploaded_at: Timestamp
    removed: Optional[AttachmentRemoval] = None


class Verification(_Block):
    state: VerificationState = 'unverified'
    by: Optional[Actor] = None
    at: Optional[Timestamp] = None
    note: Optional[str] = None


class Evidence(_Document):
    """``component_evidence``: one observation or claim about a component."""
    id: str = Field(alias='_id')
    identity_id: str
    method: EvidenceMethod
    method_version: int = Field(1, ge=1)
    source_tier: SourceTier
    standard: Optional[Standard] = None
    observed_at: Timestamp
    observed_at_precision: Precision = 'exact'
    sampled_at: Optional[Timestamp] = None
    sampled_at_precision: Optional[Precision] = None
    performed_by: List[Actor] = Field(default_factory=list)
    recorded_by_user_id: str
    recorded_by_username: Optional[str] = None
    position: Position
    summary: Summary
    derived: List[DerivedResult] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)
    destructive: bool = False
    attachments: List[Attachment] = Field(default_factory=list)
    notes: Optional[str] = None
    status: Status
    status_changed_by_user_id: Optional[str] = None
    status_changed_at: Optional[Timestamp] = None
    status_history: List[StatusChange] = Field(default_factory=list)
    verification: Verification = Field(default_factory=Verification)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    etag: Optional[str] = None
    created: Timestamp
    lastmodified: Timestamp

    @model_validator(mode='after')
    def _consistency(self) -> 'Evidence':
        quantities = [self.summary.quantity] + \
            [d.quantity for d in self.derived]
        if len(set(quantities)) != len(quantities):
            raise ValueError('one result per quantity per record (I7)')
        if self.sampled_at is not None and \
                not _later_or_equal(self.observed_at, self.sampled_at):
            raise ValueError('observed_at must not be before sampled_at '
                             '(I10)')
        expected_tier = METHOD_TIER[self.method]
        if self.method == 'reinforcement_layout':
            expected_tier = REINFORCEMENT_BASIS_TIER.get(
                self.payload.get('basis'))
            if self.position.snapshot_id is None:
                raise ValueError(
                    'a reinforcement layout names its snapshot (I23)')
        if expected_tier is not None and self.source_tier != expected_tier:
            raise ValueError(f'method {self.method} has tier '
                             f'{expected_tier}')
        if self.destructive != (self.method in DESTRUCTIVE_METHODS):
            raise ValueError('destructive follows the method')
        if self.verification.state == 'accredited':
            self._check_accreditation()
        self._check_verifier()
        indices = [a.index for a in self.attachments]
        if indices != sorted(set(indices)):
            raise ValueError('attachment indices are unique and ascending')
        if self.supersedes is not None and self.supersedes == self.id:
            raise ValueError('a record cannot supersede itself')
        return self

    def _check_verifier(self) -> None:
        """I27: who may hold which verification state (decision 8.12)."""
        state = self.verification.state
        performers = {a.user_id for a in self.performed_by if a.user_id}
        if (state == 'self_attested'
                and self.recorded_by_user_id not in performers):
            raise ValueError('self_attested needs the recorder among '
                             'performed_by (I27)')
        if state not in ('reviewed', 'accredited'):
            return
        by = self.verification.by
        if by is None or not by.user_id:
            raise ValueError(f'{state} names its reviewer (I27)')
        if by.user_id == self.recorded_by_user_id or by.user_id in performers:
            raise ValueError('the reviewer is neither the recorder nor a '
                             'performer (I27)')
        if state == 'accredited' and not (self.verification.note or
                                          '').strip():
            raise ValueError('accredited needs a note on what was checked '
                             '(I27)')

    def _check_accreditation(self) -> None:
        """I22: an accredited performer whose scope covers the standard."""
        if self.standard is None:
            raise ValueError('accredited evidence names its standard (I22)')
        for actor in self.performed_by:
            acc = actor.accreditation
            if acc is None or self.standard.code not in acc.scope:
                continue
            if acc.valid_until is None or \
                    _later_or_equal(acc.valid_until, self.observed_at):
                return
        raise ValueError('accredited needs a performer accredited for the '
                         'standard at observation time (I22)')


# DATASETS, MATERIALS, PURGE STUBS (sections 3.6, 2.10, 3.1.4) ----------------
class DatasetMember(_Block):
    user_id: str
    roles: List[DatasetRole] = Field(min_length=1)
    added_by_user_id: Optional[str] = None
    added_at: Optional[Timestamp] = None

    @field_validator('roles')
    @classmethod
    def _set(cls, value: List[str]) -> List[str]:
        if len(set(value)) != len(value):
            raise ValueError('roles form a set')
        return value


class Dataset(_Document):
    """``datasets``: a project --- membership, permission, visibility."""
    id: Slug = Field(alias='_id')
    name: str = Field(min_length=1)
    description: Optional[str] = None
    visibility: Visibility = 'members'
    members: List[DatasetMember] = Field(default_factory=list)
    created: Timestamp
    lastmodified: Timestamp

    @model_validator(mode='after')
    def _unique_members(self) -> 'Dataset':
        ids = [m.user_id for m in self.members]
        if len(set(ids)) != len(ids):
            raise ValueError('a user is a member once')
        return self

    def roles_of(self, user_id: str) -> frozenset:
        for member in self.members:
            if member.user_id == user_id:
                return frozenset(member.roles)
        return frozenset()


class Material(_Document):
    """``materials``: generic material with its List of Waste default."""
    id: Slug = Field(alias='_id')
    label: str = Field(min_length=1)
    group: MaterialGroup
    default_class: LowCode
    uniclass: Optional[str] = None
    notes: Optional[str] = None

    @field_validator('default_class')
    @classmethod
    def _not_hazardous(cls, value: str) -> str:
        """Hazardous classes are never derived from a material (2.10)."""
        if value.endswith('*'):
            raise ValueError(
                'a default class is never a hazardous (*) entry')
        return value


class Invitation(_Document):
    """``invitations``: one email-bound, single-use registration code
    (section 3.7, decision 8.14); only the code's sha256 is stored."""
    id: str = Field(alias='_id')
    email: str
    code_sha256: str
    dataset: Optional[str] = None
    roles: List[DatasetRole] = Field(default_factory=list)
    created_by_user_id: str
    created: Timestamp
    expires_at: Timestamp
    used_at: Optional[Timestamp] = None
    used_by_user_id: Optional[str] = None
    revoked_at: Optional[Timestamp] = None
    revoked_by_user_id: Optional[str] = None

    @model_validator(mode='after')
    def _roles_need_a_dataset(self) -> 'Invitation':
        if self.roles and not self.dataset:
            raise ValueError('roles are granted in a dataset')
        return self


class PurgeStub(_Document):
    """``purged_records``: what remains of a hard-deleted id -> 410 Gone."""
    id: str = Field(alias='_id')
    purged_at: Timestamp
    purged_by_user_id: str
    reason: str = Field(min_length=1)
