#!/usr/bin/env python3.13

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Optional, List, Dict, Literal
import uuid
from datetime import datetime

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

# AUTH ------------------------------------------------------------------------
Role = Literal["user", "admin"]


class Token(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class User(BaseModel):
    """
    Full user representation used internally, including sensitive data.
    """
    id: str = Field(alias="_id")
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    role: Role = "user"
    email_verified: bool = False
    verification_token: Optional[str] = None       # tokens before 0.6.1.1
    verification_token_sha256: Optional[str] = None
    verification_token_expires: Optional[datetime] = None
    # a token issued before this moment is refused (8.124 a)
    password_changed_at: Optional[datetime] = None
    # the personal profile (8.133): copied into the actors of records
    organization: Optional[str] = None
    organization_ror: Optional[str] = None
    orcid: Optional[str] = None
    default_role: Optional[str] = None

    class Config:
        populate_by_name = True


class UserPublic(BaseModel):
    """
    Safe user representation returned to clients - no tokens or credentials.
    """
    id: str = Field(alias="_id")
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    role: Role = "user"
    email_verified: bool = False

    class Config:
        populate_by_name = True


BCRYPT_MAX_PASSWORD_BYTES = 72


def _check_password_bytes(v: str) -> str:
    """bcrypt reads at most 72 bytes; non-ASCII characters take several."""
    if len(v.encode('utf-8')) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f'password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes '
            'in UTF-8 (fewer characters if it contains umlauts or symbols)'
        )
    return v


# the character set of a new username (decision 8.161): lowercase letters and
# digits, then dots, underscores and hyphens; 3 to 32 characters. Names that
# exist stay as they are; the rule is checked where a name is set.
USERNAME_PATTERN = r'^[a-z0-9][a-z0-9._-]{2,31}$'


def normalize_username(value: str) -> str:
    """Usernames are stored lowercase and unique; every lookup by
    username goes through this, so login ignores case (decision 8.28)."""
    return value.strip().lower()


class RegisterPayload(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # max_length=72 matches bcrypt's hard truncation limit, also prevents DoS
    password: str = Field(min_length=8, max_length=72)
    # an invitation code (8.14): required outside the open domains
    code: Optional[str] = Field(None, max_length=64)

    @field_validator('username', mode='before')
    @classmethod
    def _lowercase(cls, v):
        # lowercased before the pattern is checked, so "Sample.User" is fine
        return normalize_username(v) if isinstance(v, str) else v

    @field_validator('password')
    @classmethod
    def _password_fits_bcrypt(cls, v: str) -> str:
        return _check_password_bytes(v)


class ChangePasswordPayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator('new_password')
    @classmethod
    def _new_password_fits_bcrypt(cls, v: str) -> str:
        return _check_password_bytes(v)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class ResendVerificationRequest(BaseModel):
    """The address to send the verification mail to again (S10, 8.144)."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """The single-use token of the mail and the new password (the same
    rules as registration and change-password, 8.124 a)."""
    token: str = Field(min_length=16, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator('new_password')
    @classmethod
    def _new_password_fits_bcrypt(cls, v: str) -> str:
        return _check_password_bytes(v)


class AdminUserUpdate(BaseModel):
    """Fields an admin may change on another user account."""

    role: Optional[Role] = None
    disabled: Optional[bool] = None
    full_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100
    )


class UserInDB(User):
    hashed_password: str


# COMPONENTS ------------------------------------------------------------------
ALLOWED_COMPONENT_TYPES = [
    "panel",
    "beam",
    "column",
    "slab",
    "rubble",
    "brick",
    "pipe",
    "profile",
    "connector",
    "other",
]


ALLOWED_COMPLEXITY_LEVELS = [0, 1, 2, 3]


# Condition semantics:
#   0 = destroyed / retired (red)
#   1 = poor                (orange)
#   2 = average             (yellow)
#   3 = good                (green)
# A missing `condition` means "unknown / unassessed" and is distinct from 0.
ALLOWED_CONDITION_VALUES = [0, 1, 2, 3]


# Precision of `manufactured_at`. The stored timestamp is always ISO-8601;
# this field records how precisely the timestamp is known so downstream
# consumers do not over-interpret the value.
ALLOWED_MANUFACTURED_PRECISIONS = ["exact", "month", "year", "unknown"]


# COMPONENT SPECIFIC TYPES ----------------------------------------------------


class ComponentLocation(BaseModel):
    lat: float = Field(description="Latitude coordinate")
    lon: float = Field(description="Longitude coordinate")


# Type aliases (keep existing array formats)


class ComponentBoundingBox(RootModel[List[float]]):
    """Bounding box as [X, Y, Z] array format"""
    root: List[float] = Field(
        description="Bounding box maximum extents as [X, Y, Z] float values"
    )

    def __init__(self, root: List[float]):
        if len(root) != 3:
            raise ValueError(
                'Bounding box must have exactly 3 elements [X, Y, Z]'
            )
        if not all(isinstance(x, (int, float)) for x in root):
            raise ValueError('All bounding box elements must be numbers')
        super().__init__(root=root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root)


class ComponentFrame(BaseModel):
    o: List[float] = Field(description="Origin point [x, y, z]")
    x: List[float] = Field(description="X axis vector [x, y, z]")
    y: List[float] = Field(description="Y axis vector [x, y, z]")
    z: List[float] = Field(description="Z axis vector [x, y, z]")


class ComponentCount(BaseModel):
    count: int


# COMPONENTS - IDENTITY / SNAPSHOT MODEL ---------------------------------


class SnapshotMesh(BaseModel):
    """Inline mesh primitive on a snapshot.

    Vertices are in **Rhino Z-up** (CSC canonical). File companions use the
    same primitive **index** as this entry in ``geometry.meshes[i]``, with
    **resolution** as the filename (not a second index):

        ``meshes/<snapshot_id>/<i>/reduced.ply``  (catalog default)
        ``meshes/<snapshot_id>/<i>/detailed.ply`` (optional higher fidelity)

    Multiple distinct mesh bodies use ``i = 0, 1, ...``; dual-resolution pairs
    share the same ``i`` and differ only by ``reduced`` vs ``detailed``. Legacy
    on-disk OBJ may hold several ``o`` objects in one file; object order maps
    to ``i`` (not separate OBJ files per primitive).
    """
    vertices: List[List[float]] = Field(
        description=(
            "Mesh vertices as [x, y, z] in Rhino Z-up (CSC canonical frame)"
        )
    )
    faces: List[List[int]] = Field(
        description=(
            "Mesh faces as array of vertex index lists (triangles or polygons)"
        )
    )
    colors: Optional[List[List[int]]] = Field(
        None,
        description=(
            "Optional per-vertex RGB colors as [r, g, b] integers (0-255); "
            "parallel to vertices when present"
        )
    )


class SnapshotPointCloud(BaseModel):
    """Inline point cloud primitive on a snapshot.

    Low-resolution preview lives inline; the full-fidelity binary PLY
    companion lives at ``point_clouds/<snapshot_id>/<index>.ply``, where
    ``<index>`` is the 0-based position in the snapshot's
    ``geometry.point_clouds`` array.
    """
    points: List[List[float]] = Field(
        description="Point cloud points as array of [x, y, z] coordinates"
    )
    colors: Optional[List[List[int]]] = Field(
        None,
        description=(
            "Optional per-point RGB colors as [r, g, b] integers (0-255); "
            "parallel to points when present"
        )
    )


class SnapshotExtrusion(BaseModel):
    """Inline extrusion primitive on a snapshot.

    Profile + height, fully encoded on the snapshot document (no file
    companion). A snapshot may hold multiple extrusions in
    ``geometry.extrusions``.
    """
    profile: List[List[float]] = Field(
        description=(
            "2D profile polyline as array of [x, y] coordinate pairs "
            "(centered in XY)"
        )
    )
    height: float = Field(description="Extrusion length along Z")


class SnapshotReinforcement(BaseModel):
    """Inline reinforcement bar centerline on a snapshot.

    Fully encoded on the snapshot document (no file companion). A snapshot
    may hold multiple bars in ``geometry.reinforcements``. Does not satisfy
    the primary geometry representation requirement on its own.
    """
    spec: str = Field(
        description="Reinforcement steel specification (e.g. B500B)"
    )
    diameter: float = Field(
        gt=0,
        description="Bar diameter in mm",
    )
    points: List[List[float]] = Field(
        min_length=2,
        description=(
            "Open centerline polyline as [x, y, z] coordinate triplets; "
            "same coordinate frame as meshes/extrusions/marker_points"
        ),
    )

    @field_validator('spec')
    @classmethod
    def _strip_spec(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('spec must be non-empty')
        return v

    @field_validator('points')
    @classmethod
    def _validate_points(cls, v: List[List[float]]) -> List[List[float]]:
        for pt in v:
            if len(pt) != 3:
                raise ValueError('each point must be [x, y, z]')
        return v


class SnapshotGeometry(BaseModel):
    """Multi-representation geometry block for one snapshot.

    A single snapshot may hold simultaneous representations (multiple
    meshes + multiple point clouds + multiple extrusions) of the same
    physical state. Marker points are shared across all representations
    within the snapshot (same coordinate frame).
    """
    meshes: Optional[List[SnapshotMesh]] = Field(
        None,
        description=(
            'Mesh primitives; optional PLY files under '
            '``meshes/<snapshot_id>/<i>/{reduced,detailed}.ply``'
        )
    )
    point_clouds: Optional[List[SnapshotPointCloud]] = Field(
        None,
        description=(
            "Array of point cloud primitives (each backed by a PLY file)"
        )
    )
    extrusions: Optional[List[SnapshotExtrusion]] = Field(
        None,
        description=(
            "Array of extrusion primitives (profile + height; fully inline)"
        )
    )
    marker_points: Optional[List[List[float]]] = Field(
        None,
        description=(
            "Shared marker points as array of [x, y, z] coordinate triplets; "
            "same coordinate frame as the meshes/point_clouds/extrusions"
        )
    )
    reinforcements: Optional[List[SnapshotReinforcement]] = Field(
        None,
        description=(
            "Inline reinforcement bar centerlines (spec + diameter + open "
            "polyline); ancillary to primary mesh/point_cloud/extrusion "
            "representations"
        )
    )

    @model_validator(mode='after')
    def _require_at_least_one_representation(self) -> 'SnapshotGeometry':
        has_mesh = bool(self.meshes)
        has_point_cloud = bool(self.point_clouds)
        has_extrusion = bool(self.extrusions)
        if not (has_mesh or has_point_cloud or has_extrusion):
            raise ValueError(
                'geometry must include at least one of: meshes, '
                'point_clouds, extrusions (marker_points alone is not '
                'a valid geometry representation)'
            )
        return self


class ComponentIdentity(BaseModel):
    """Stable physical-object reference. One per legacy row after M3."""
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="Globally unique identity identifier (GUID)"
    )
    catalog_number: int = Field(
        description=(
            "Monotonic human-facing catalog number; never recycled. "
            "Display as 'CSC-' + six-digit zero-padded decimal."
        )
    )
    componenttype: str = Field(
        alias="type",
        description=(
            "Type of component. Must be one of ALLOWED_COMPONENT_TYPES."
        )
    )
    material: str = Field(description="Material type of the component")
    dataset: str = Field(
        description="Dataset name that this component belongs to"
    )
    manufactured_at: Optional[str] = Field(
        None,
        description=(
            "ISO-8601 timestamp (UTC) describing when the component was "
            "originally manufactured, to the precision indicated by "
            "`manufactured_precision`."
        )
    )
    manufactured_precision: Optional[str] = Field(
        None,
        description=(
            "Precision qualifier for `manufactured_at`. Must be one of "
            "ALLOWED_MANUFACTURED_PRECISIONS."
        )
    )
    salvage_source: Optional[str] = Field(
        None,
        description=(
            "Short free-text description of where the component was salvaged "
            "from (e.g. building name, demolition site)."
        )
    )
    salvaged_at: Optional[str] = Field(
        None,
        description=(
            "ISO-8601 timestamp (UTC) describing when the component was "
            "salvaged. Paired with `salvage_source`."
        )
    )
    reserved: str = Field(
        '',
        description=(
            "UUID of user who has reserved this component "
            "(empty if not reserved)"
        )
    )
    attributes: Optional[Dict] = Field(
        default_factory=dict,
        description="Additional static metadata about the physical piece"
    )
    parent_identities: Optional[List[str]] = Field(
        None,
        description=(
            "UUIDs of immediate parent identities. Single-element for 1:1 "
            "splits; multi-element for N:1 merges. `None` if no known parent."
        )
    )
    consumed_at: Optional[str] = Field(
        None,
        description=(
            "ISO-8601 timestamp when the physical piece ceased to exist as "
            "a discrete object (split, demolished, returned). `None` = active."
        )
    )
    is_public: bool = Field(
        False,
        description=(
            "When true, anonymous users may view all snapshots on "
            "the public component detail page (viewer + read-only metadata)."
        ),
    )
    current_snapshot_id: str = Field(
        description=(
            "UUID of the snapshot in `component_snapshots` that represents "
            "the current state of this identity."
        )
    )
    created: str = Field(
        description="ISO timestamp when this identity was first recorded"
    )
    lastmodified: str = Field(
        description="ISO timestamp when this identity was last modified"
    )

    @field_validator('componenttype')
    @classmethod
    def _validate_componenttype(cls, v: str) -> str:
        if v not in ALLOWED_COMPONENT_TYPES:
            raise ValueError(
                f'type must be one of {ALLOWED_COMPONENT_TYPES}'
            )
        return v

    @field_validator('manufactured_precision')
    @classmethod
    def _validate_manufactured_precision(
        cls, v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return v
        if v not in ALLOWED_MANUFACTURED_PRECISIONS:
            raise ValueError(
                'manufactured_precision must be one of '
                f'{ALLOWED_MANUFACTURED_PRECISIONS}'
            )
        return v

    @field_validator('salvage_source')
    @classmethod
    def _normalize_salvage_source(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None

    @field_validator('parent_identities')
    @classmethod
    def _validate_parent_identities(
        cls, v: Optional[List[str]]
    ) -> Optional[List[str]]:
        if v is None:
            return None
        if len(v) == 0:
            return None
        for item in v:
            try:
                uuid.UUID(str(item))
            except (ValueError, AttributeError, TypeError):
                raise ValueError(
                    'parent_identities entries must be valid UUID strings'
                )
        return [str(item) for item in v]

    class Config:
        extra = "ignore"
        populate_by_name = True


class ComponentSnapshot(BaseModel):
    """State of one identity at one point in time. Version 0 created at M3."""
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="Globally unique snapshot identifier (GUID)"
    )
    identity_id: str = Field(
        description="UUID of the ComponentIdentity this snapshot belongs to"
    )
    version: int = Field(
        description=(
            "Per-identity monotonic version, zero-based. First snapshot for "
            "an identity is `0`. Unique on (identity_id, version). "
            "Server-assigned: never accept this field from client payloads; "
            "the backend computes it (`0` on initial create, "
            "`max(existing)+1` on snapshot evolution)."
        )
    )
    virtual: bool = Field(
        default=False,
        description=(
            "True when this snapshot represents a hypothetical / proposal "
            "(not yet realized on the physical piece). Migrated snapshots "
            "from legacy are `False`."
        )
    )
    name: Optional[str] = Field(
        'Unnamed Component',
        description=(
            "Human readable name for this state (can change across "
            "snapshots, e.g. on remanufacturing)."
        )
    )
    geometry: SnapshotGeometry = Field(
        description=(
            "Multi-representation geometry block for this snapshot "
            "(meshes, point clouds, extrusions, marker_points, "
            "reinforcements). At least one of meshes / point_clouds / "
            "extrusions must be non-empty."
        )
    )
    descriptors: Optional[Dict] = Field(
        default_factory=dict,
        description="Descriptors computed from this snapshot's geometry"
    )
    bbx: ComponentBoundingBox = Field(
        description="Bounding box [X, Y, Z] for this snapshot's geometry"
    )
    bbx_origin: List[float] = Field(
        description="Bounding box origin [X, Y, Z] in PCA space"
    )
    complexity: int = Field(
        description="Complexity level (0-3); derived from geometry"
    )
    fragment: bool = Field(
        description="Whether this snapshot's state is a fragment"
    )
    assembly: bool = Field(
        description="Whether this snapshot's state is an assembly"
    )
    condition: Optional[int] = Field(
        None,
        description=(
            "Condition grade for this state. 0 = destroyed/retired, "
            "1 = poor, 2 = average, 3 = good. `None` = unknown."
        )
    )
    color: Optional[List[int]] = Field(
        [110, 110, 110],
        description="RGB rendering color as [R, G, B] integers (0-255)"
    )
    location: Optional[ComponentLocation] = Field(
        {'lat': 0.0, 'lon': 0.0},
        description=(
            "Geographic location of the piece at the time of this snapshot. "
            "PATCH-able on the current snapshot without creating a new one."
        )
    )
    processes: Optional[Dict] = Field(
        default_factory=dict,
        description="Manufacturing or processing information for this state"
    )
    iframe: ComponentFrame = Field(
        description=(
            "Insertion frame / transformation matrix for this state"
        )
    )
    pca_frame: ComponentFrame = Field(
        description=(
            "PCA frame / principal-component transformation for this state"
        )
    )
    validated: bool = Field(
        description="Whether this snapshot's state has been validated"
    )
    etag: Optional[str] = Field(
        '',
        description=(
            "ETag for cache validation; recomputed from snapshot content."
        )
    )
    photo_count: Optional[int] = Field(
        None,
        description=(
            "Number of user-uploaded photos on disk for this snapshot; "
            "optional cache for list UI"
        ),
    )
    added_by_user_id: Optional[str] = Field(
        None,
        description=(
            "User id of whoever created this snapshot (set on v0 create; "
            "records who added the identity to the catalog)"
        ),
    )
    added_by_username: Optional[str] = Field(
        None,
        description=(
            "Username at create time "
            "(display cache for added_by_user_id)"
        ),
    )
    notes: Optional[str] = Field(
        None,
        max_length=5000,
        description="Free-text notes for this snapshot state",
    )
    quantity: int = Field(
        default=1,
        ge=1,
        le=999_999,
        description=(
            "Number of identical physical items represented by this "
            "catalog entry (e.g. a batch of matching fixtures)"
        ),
    )
    mesh_ply_resolutions: Optional[Dict[str, List[str]]] = Field(
        None,
        description=(
            "Which resolution files exist on disk per mesh primitive index "
            "(string keys '0', '1', ... matching ``geometry.meshes``). "
            "Values list role names: "
            "typically 'reduced', optionally 'detailed'. "
            "Paths: ``meshes/<snapshot_id>/<i>/reduced.ply`` and "
            "``.../detailed.ply``. Example: {'0': ['reduced', 'detailed']}."
        ),
    )
    point_cloud_files: Optional[List[int]] = Field(
        None,
        description=(
            "Indices of ``geometry.point_clouds`` whose full cloud is stored "
            "as a file (``point_clouds/<snapshot_id>/<i>.ply``); set by the "
            "upload route. Absent on versions uploaded before the marker "
            "existed. Example: [0]."
        ),
    )
    created: str = Field(
        description="ISO timestamp when this snapshot was created"
    )
    lastmodified: str = Field(
        description="ISO timestamp when this snapshot was last modified"
    )

    @field_validator('version')
    @classmethod
    def _validate_version(cls, v: int) -> int:
        if v < 0:
            raise ValueError('version must be >= 0')
        return v

    @field_validator('identity_id')
    @classmethod
    def _validate_identity_id(cls, v: str) -> str:
        try:
            uuid.UUID(str(v))
        except (ValueError, AttributeError, TypeError):
            raise ValueError('identity_id must be a valid UUID string')
        return str(v)

    @field_validator('complexity')
    @classmethod
    def _validate_complexity(cls, v: int) -> int:
        if v not in ALLOWED_COMPLEXITY_LEVELS:
            raise ValueError(
                f'complexity must be one of {ALLOWED_COMPLEXITY_LEVELS}'
            )
        return v

    @field_validator('condition')
    @classmethod
    def _validate_condition(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v not in ALLOWED_CONDITION_VALUES:
            raise ValueError(
                f'condition must be one of {ALLOWED_CONDITION_VALUES}'
            )
        return v

    class Config:
        extra = "ignore"
        populate_by_name = True

