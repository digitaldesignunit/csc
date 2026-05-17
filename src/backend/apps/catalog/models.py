#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Optional, List, Dict, Union, Literal
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


class TokenData(BaseModel):
    sub: Union[str, None] = None  # subject (we use user _id / GUID)
    role: Role = "user"


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
    verification_token: Optional[str] = None
    verification_token_expires: Optional[datetime] = None

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


class RegisterPayload(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    # max_length=72 matches bcrypt's hard truncation limit, also prevents DoS
    password: str = Field(min_length=8, max_length=72)


class ChangePasswordPayload(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


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


ALLOWED_COMPONENT_SORTKEYS = [
    "_id",
    "name",
    "type",
    "material",
    "dataset",
    "color",
    "bbx.0",
    "bbx.1",
    "bbx.2",
    "created",
    "lastmodified",
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


class ComponentPolylinePoints(RootModel[List[List[float]]]):
    """Polyline points as array of [x, y] coordinates"""
    root: List[List[float]] = Field(
        description="Array of [x, y] coordinate pairs"
    )

    def __init__(self, root: List[List[float]]):
        if not all(
            isinstance(point, list) and len(point) == 2
            and all(isinstance(coord, (int, float)) for coord in point)
            for point in root
        ):
            raise ValueError(
                'All polyline points must be [x, y] coordinate pairs'
            )
        super().__init__(root=root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root)


class ComponentMeshVertices(RootModel[List[List[float]]]):
    """Mesh vertices as array of [x, y, z] coordinates"""
    root: List[List[float]] = Field(
        description="Array of [x, y, z] vertex coordinates"
    )

    def __init__(self, root: List[List[float]]):
        if not all(
            isinstance(vertex, list) and len(vertex) == 3
            and all(isinstance(coord, (int, float)) for coord in vertex)
            for vertex in root
        ):
            raise ValueError(
                'All mesh vertices must be [x, y, z] coordinate triplets'
            )
        super().__init__(root=root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root)


class ComponentMeshFaces(RootModel[List[List[int]]]):
    """Mesh faces as array of vertex indices"""
    root: List[List[int]] = Field(
        description="Array of face vertex indices"
    )

    def __init__(self, root: List[List[int]]):
        if not all(
            isinstance(face, list) and len(face) >= 3
            and all(isinstance(idx, int) for idx in face)
            for face in root
        ):
            raise ValueError(
                'All mesh faces must be arrays of integer vertex indices'
            )
        super().__init__(root=root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root)


class ComponentMeshColors(RootModel[List[List[int]]]):
    """Mesh vertex colors as array of [r, g, b] values"""
    root: List[List[int]] = Field(
        description="Array of [r, g, b] color values (0-255)"
    )

    def __init__(self, root: List[List[int]]):
        if not all(
            isinstance(color, list) and len(color) == 3
            and all(isinstance(c, int) and 0 <= c <= 255 for c in color)
            for color in root
        ):
            raise ValueError(
                'All mesh colors must be [r, g, b] values (0-255)'
            )
        super().__init__(root=root)

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]

    def __len__(self):
        return len(self.root)


class ComponentMesh(BaseModel):
    v: ComponentMeshVertices = Field(description="Mesh vertices")
    f: ComponentMeshFaces = Field(description="Mesh faces")
    c: Optional[ComponentMeshColors] = Field(
        None, description="Mesh vertex colors"
    )


class ComponentExtrusion(BaseModel):
    profile: ComponentPolylinePoints = Field(
        description="Extrusion profile points"
    )
    height: float = Field(description="Extrusion height")


class ComponentGeometry(BaseModel):
    meshes: Optional[List[ComponentMesh]] = Field(
        None, description="Array of mesh geometries"
    )
    extrusion: Optional[ComponentExtrusion] = Field(
        None, description="Extrusion geometry"
    )


class ComponentFrame(BaseModel):
    o: List[float] = Field(description="Origin point [x, y, z]")
    x: List[float] = Field(description="X axis vector [x, y, z]")
    y: List[float] = Field(description="Y axis vector [x, y, z]")
    z: List[float] = Field(description="Z axis vector [x, y, z]")


class ComponentCount(BaseModel):
    count: int


class ComponentDescriptors(BaseModel):
    id: str = Field(alias="_id")
    descriptors: Dict = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class ComponentModel(BaseModel):
    # globally unique ID (GUID stored in Mongo as _id)
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="Globally unique component identifier (GUID)"
    )
    # human readable name (optional)
    name: Optional[str] = Field(
        'Unnamed Component',
        description="Human readable component name (optional)"
    )
    # timestamps
    created: str = Field(
        description="ISO timestamp when component was created"
    )
    lastmodified: str = Field(
        description="ISO timestamp when component was last modified"
    )
    # base attributes
    componenttype: str = Field(
        alias="type",
        description=(
            "Type of component. Must be one of ALLOWED_COMPONENT_TYPES "
            "(panel, beam, column, slab, rubble, brick, pipe, profile, "
            "connector, other)."
        )
    )
    material: str = Field(
        description="Material type of the component"
    )
    dataset: str = Field(
        description="Dataset name that this component belongs to"
    )
    complexity: int = Field(
        description="Complexity level (0-3, where 0 is simplest)"
    )
    fragment: bool = Field(
        description="Whether this component is a fragment"
    )
    assembly: bool = Field(
        description="Whether this component is an assembly"
    )
    # geometry & data
    geometry: ComponentGeometry = Field(
        description="Component geometry data (meshes or extrusion)"
    )
    color: Optional[List[int]] = Field(
        [110, 110, 110],
        description="RGB color values as [R, G, B] integers (0-255)"
    )
    bbx: ComponentBoundingBox = Field(
        description=("Bounding box maximum extents as [X, Y, Z] float values "
                     "(dimensions of the component)")
    )
    bbx_origin: List[float] = Field(
        description=("Bounding box center/origin as [X, Y, Z] float values "
                     "(vector from world origin to bbx center in PCA space)")
    )
    location: Optional[ComponentLocation] = Field(
        {
            'lat': 0.0,
            'lon': 0.0
        },
        description="Geographic location data (lat/lon coordinates)"
    )
    descriptors: Optional[Dict] = Field(
        {},
        description="Component descriptors and metadata"
    )
    processes: Optional[Dict] = Field(
        {},
        description="Manufacturing or processing information"
    )
    iframe: ComponentFrame = Field(
        {
            'o': [0.0, 0.0, 0.0],
            'x': [1.0, 0.0, 0.0],
            'y': [0.0, 1.0, 0.0],
            'z': [0.0, 0.0, 1.0]
        },
        description="Insertion Frame / Transformation matrix data"
    )
    pca_frame: ComponentFrame = Field(
        {
            'o': [0.0, 0.0, 0.0],
            'x': [1.0, 0.0, 0.0],
            'y': [0.0, 1.0, 0.0],
            'z': [0.0, 0.0, 1.0]
        },
        description=("PCA Frame / Principal Component Analysis transformation "
                     "matrix data")
    )
    reserved: str = Field(
        '',
        description=("UUID of user who has reserved this component "
                     "(empty if not reserved)")
    )
    attributes: Optional[Dict] = Field(
        {},
        description="Additional component attributes"
    )
    marker_points: Optional[List[List[float]]] = Field(
        [],
        description="Marker points as array of [x, y, z] coordinate triplets"
    )
    validated: bool = Field(
        description="Whether this component has been validated"
    )
    etag: Optional[str] = Field(
        '',
        description=("ETag for cache validation (auto-generated from "
                     "lastmodified and key fields)")
    )
    # Lineage + provenance fields --------------------------------------------
    condition: Optional[int] = Field(
        None,
        description=(
            "Condition grade. 0 = destroyed/retired, 1 = poor, "
            "2 = average, 3 = good. `None` = unknown / unassessed."
        )
    )
    manufactured_at: Optional[str] = Field(
        None,
        description=(
            "ISO-8601 timestamp (UTC) describing when the component was "
            "originally manufactured, to the precision indicated by "
            "`manufactured_precision`. Optional."
        )
    )
    manufactured_precision: Optional[str] = Field(
        None,
        description=(
            "Precision qualifier for `manufactured_at`. Must be one of "
            "ALLOWED_MANUFACTURED_PRECISIONS (exact, month, year, unknown)."
        )
    )
    salvage_source: Optional[str] = Field(
        None,
        description=(
            "Short free-text description of where the component was "
            "salvaged from (e.g. building name, demolition site)."
        )
    )
    salvaged_at: Optional[str] = Field(
        None,
        description=(
            "ISO-8601 timestamp (UTC) describing when the component was "
            "salvaged. Optional. Paired with `salvage_source`."
        )
    )
    parent_component: Optional[str] = Field(
        None,
        description=(
            "Optional UUID of the parent component this component was "
            "derived from (e.g. when a piece is split into smaller pieces "
            "and reintroduced into the catalog)."
        )
    )

    @field_validator('componenttype')
    @classmethod
    def _validate_componenttype(cls, v: str) -> str:
        if v not in ALLOWED_COMPONENT_TYPES:
            raise ValueError(
                f'type must be one of {ALLOWED_COMPONENT_TYPES}'
            )
        return v

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
    def _normalize_salvage_source(
        cls, v: Optional[str]
    ) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        # An empty string after trimming collapses to "not provided".
        return v or None

    @field_validator('parent_component')
    @classmethod
    def _validate_parent_component(
        cls, v: Optional[str]
    ) -> Optional[str]:
        if v is None or v == '':
            return None
        try:
            uuid.UUID(str(v))
        except (ValueError, AttributeError, TypeError):
            raise ValueError(
                'parent_component must be a valid UUID string'
            )
        return str(v)

    class Config:
        extra = "ignore"
        populate_by_name = True
        schema_extra = {
            "example": {
                "_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Concrete Slab A",
                "created": "2024-01-15T10:30:00Z",
                "lastmodified": "2024-01-15T10:30:00Z",
                "type": "slab",
                "material": "concrete",
                "dataset": "sas_cita_scans",
                "complexity": 2,
                "fragment": False,
                "assembly": False,
                "geometry": {
                    "meshes": [
                        {
                            "v": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                            "f": [[0, 1, 2], [0, 2, 3]],
                            "c": [[128, 128, 128], [128, 128, 128],
                                  [128, 128, 128], [128, 128, 128]]
                        },
                        {
                            "v": [[0, 0, 0.1], [1, 0, 0.1],
                                  [1, 1, 0.1], [0, 1, 0.1]],
                            "f": [[0, 1, 2], [0, 2, 3]],
                            "c": [[200, 200, 200], [200, 200, 200],
                                  [200, 200, 200], [200, 200, 200]]
                        }
                    ]
                },
                "color": [128, 128, 128],
                "bbx": [1.0, 1.0, 0.2],
                "bbx_origin": [0.5, 0.5, 0.1],
                "location": {
                    "lat": 37.81627937,
                    "lon": 144.95373531},
                "descriptors": {"roundness": 0.1},
                "processes": {"manufacturing": "cast"},
                "iframe": {
                    "o": [0, 0, 0],
                    "x": [1, 0, 0],
                    "y": [0, 1, 0],
                    "z": [0, 0, 1]
                    },
                "pca_frame": {
                    "o": [0, 0, 0],
                    "x": [1, 0, 0],
                    "y": [0, 1, 0],
                    "z": [0, 0, 1]
                    },
                "reserved": "550e8400-e29b-41d4-a716-446655440000",
                "attributes": {"strength": "C30"},
                "marker_points": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                "validated": True,
                "etag": "abc123def456",
                "condition": 2,
                "manufactured_at": "1998-06-01T00:00:00Z",
                "manufactured_precision": "year",
                "salvage_source": "Demolition site, Berlin-Wedding",
                "salvaged_at": "2026-02-14T00:00:00Z",
                "parent_component": (
                    "550e8400-e29b-41d4-a716-446655440111"
                )
            }
        }


class UpdateComponentModel(BaseModel):
    componenttype: Optional[str] = None
    lastmodified: str
    material: Optional[str] = None
    dataset: Optional[str] = None
    geometry: Optional[ComponentGeometry] = None
    complexity: Optional[float] = None
    fragment: Optional[bool] = None
    assembly: Optional[bool] = None
    color: Optional[List[int]] = None
    validated: Optional[bool] = None
    bbx: Optional[ComponentBoundingBox] = None
    bbx_origin: Optional[List[float]] = None
    iframe: Optional[ComponentFrame] = None
    pca_frame: Optional[ComponentFrame] = None
    reserved: Optional[str] = None
    condition: Optional[int] = None
    manufactured_at: Optional[str] = None
    manufactured_precision: Optional[str] = None
    salvage_source: Optional[str] = None
    salvaged_at: Optional[str] = None
    parent_component: Optional[str] = None

    @field_validator('componenttype')
    @classmethod
    def _validate_componenttype(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in ALLOWED_COMPONENT_TYPES:
            raise ValueError(
                f'type must be one of {ALLOWED_COMPONENT_TYPES}'
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

    @field_validator('parent_component')
    @classmethod
    def _validate_parent_component(
        cls, v: Optional[str]
    ) -> Optional[str]:
        if v is None or v == '':
            return None
        try:
            uuid.UUID(str(v))
        except (ValueError, AttributeError, TypeError):
            raise ValueError(
                'parent_component must be a valid UUID string'
            )
        return str(v)

    class Config:
        extra = "ignore"
        populate_by_name = True


# COMPONENTS - IDENTITY / SNAPSHOT MODEL ---------------------------------


class SnapshotMesh(BaseModel):
    """Inline mesh primitive on a snapshot.

    Full-fidelity binary PLY companion lives at
    ``meshes/<snapshot_id>/<index>.ply``, where ``<index>`` is the 0-based
    position in the snapshot's ``geometry.meshes`` array.
    """
    vertices: List[List[float]] = Field(
        description="Mesh vertices as array of [x, y, z] coordinates"
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


class SnapshotGeometry(BaseModel):
    """Multi-representation geometry block for one snapshot.

    A single snapshot may hold simultaneous representations (multiple
    meshes + multiple point clouds + multiple extrusions) of the same
    physical state. Marker points are shared across all representations
    within the snapshot (same coordinate frame).
    """
    meshes: Optional[List[SnapshotMesh]] = Field(
        None,
        description="Array of mesh primitives (each backed by a PLY file)"
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
            "(meshes, point clouds, extrusions, marker_points). At least one "
            "of meshes / point_clouds / extrusions must be non-empty."
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


class ComposeIdentityResponse(BaseModel):
    """Compose response: an identity plus its current snapshot.

    Returned by `GET /identities/{identity_id}/compose` - the primary read
    path for the new data model.
    """
    identity: ComponentIdentity
    snapshot: ComponentSnapshot


class UpdateComponentIdentityModel(BaseModel):
    """PATCH payload for identity-side metadata (admin only).

    Snapshot fields (name, geometry, validated, color, etc.) belong on
    ``PATCH /identities/{id}/current-snapshot`` or a new snapshot version.
    """
    componenttype: Optional[str] = Field(
        default=None,
        alias='type',
        description='Component type (one of ALLOWED_COMPONENT_TYPES)',
    )
    material: Optional[str] = Field(default=None, max_length=100)
    dataset: Optional[str] = Field(default=None, max_length=200)
    manufactured_at: Optional[str] = Field(default=None, max_length=40)
    manufactured_precision: Optional[str] = Field(default=None)
    salvage_source: Optional[str] = Field(default=None, max_length=500)
    salvaged_at: Optional[str] = Field(default=None, max_length=40)
    reserved: Optional[str] = Field(
        default=None,
        description='User UUID who reserved this identity; empty string clears',
    )
    attributes: Optional[Dict] = Field(default=None)
    parent_identities: Optional[List[str]] = Field(
        default=None,
        description=(
            'Parent identity UUIDs. Empty list or null clears lineage.'
        ),
    )
    consumed_at: Optional[str] = Field(
        default=None,
        max_length=40,
        description='ISO timestamp when consumed; null clears for active',
    )

    @field_validator('componenttype')
    @classmethod
    def _validate_componenttype(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
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

    @field_validator('material', 'dataset')
    @classmethod
    def _strip_non_empty_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v == '':
            raise ValueError('value must not be empty')
        return v

    class Config:
        extra = 'ignore'
        populate_by_name = True


class CreateComponentRequest(BaseModel):
    """Create a new identity plus its version-0 snapshot (ADR-014 #2)."""

    id: Optional[str] = Field(
        default=None,
        alias='_id',
        description='Optional identity UUID; server generates if omitted',
    )
    name: Optional[str] = 'Unnamed Component'
    componenttype: str = Field(alias='type')
    material: str
    dataset: str
    complexity: int
    fragment: bool
    assembly: bool
    geometry: SnapshotGeometry
    color: Optional[List[int]] = Field(default=[110, 110, 110])
    bbx: ComponentBoundingBox
    bbx_origin: List[float]
    location: Optional[ComponentLocation] = Field(
        default_factory=lambda: ComponentLocation(lat=0.0, lon=0.0)
    )
    descriptors: Optional[Dict] = Field(default_factory=dict)
    processes: Optional[Dict] = Field(default_factory=dict)
    iframe: ComponentFrame
    pca_frame: ComponentFrame
    validated: bool = False
    condition: Optional[int] = None
    manufactured_at: Optional[str] = None
    manufactured_precision: Optional[str] = None
    salvage_source: Optional[str] = None
    salvaged_at: Optional[str] = None
    reserved: str = ''
    attributes: Optional[Dict] = Field(default_factory=dict)
    parent_identities: Optional[List[str]] = None
    marker_points: Optional[List[List[float]]] = Field(
        default=None,
        description=(
            'Optional marker points merged into geometry.marker_points '
            'when not already set on geometry'
        ),
    )

    @field_validator('componenttype')
    @classmethod
    def _validate_componenttype(cls, v: str) -> str:
        if v not in ALLOWED_COMPONENT_TYPES:
            raise ValueError(
                f'type must be one of {ALLOWED_COMPONENT_TYPES}'
            )
        return v

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
        extra = 'ignore'
        populate_by_name = True


class UpdateComponentSnapshotModel(BaseModel):
    """PATCH payload for the current snapshot of an identity.

    Per ADR-015 write granularity: only metadata fields can be updated in
    place on the current snapshot. Geometry and any field derived from
    geometry (`bbx`, `bbx_origin`, `complexity`, `iframe`, `pca_frame`)
    MUST instead drive a new snapshot version, so those fields are
    intentionally absent from this model.

    Server-managed fields (`id`, `identity_id`, `version`, `virtual`,
    `created`, `lastmodified`, `etag`) are not exposed here either.

    Only fields explicitly present in the request payload are applied
    (`exclude_unset=True` semantics on the consumer side).
    """
    name: Optional[str] = None
    descriptors: Optional[Dict] = None
    fragment: Optional[bool] = None
    assembly: Optional[bool] = None
    condition: Optional[int] = None
    color: Optional[List[int]] = None
    location: Optional[ComponentLocation] = None
    processes: Optional[Dict] = None
    validated: Optional[bool] = None

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


# DESIGNS ---------------------------------------------------------------------

class DesignInsertionFrame(BaseModel):
    """Insertion frame defining component orientation in design space."""
    o: List[float] = Field(
        description="Origin point as [x, y, z] coordinates"
    )
    x: List[float] = Field(
        description="X-axis vector as [x, y, z] coordinates"
    )
    y: List[float] = Field(
        description="Y-axis vector as [x, y, z] coordinates"
    )
    z: List[float] = Field(
        description="Z-axis vector as [x, y, z] coordinates"
    )


class DesignComponent(BaseModel):
    """Component reference with its insertion frame in the design."""
    component: str = Field(
        description="Component ID (GUID) reference"
    )
    iframe: DesignInsertionFrame = Field(
        description="Insertion frame defining component orientation"
    )


class DesignAdditionalGeometry(BaseModel):
    """Design-scoped additional geometry item (static meshes)."""
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description=(
            "Globally unique identifier for this additional geometry item"
        )
    )
    name: Optional[str] = Field(
        None, description="Optional human-readable name"
    )
    iframe: DesignInsertionFrame = Field(
        description="Insertion frame defining geometry orientation"
    )
    geometry: ComponentGeometry = Field(
        description="Geometry data with one or more meshes."
    )


class DesignModel(BaseModel):
    # globally unique ID (GUID stored in Mongo as _id)
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="Globally unique design identifier (GUID)"
    )
    # name and description
    name: Optional[str] = Field(
        None,
        description="Human readable design name (optional)"
    )
    description: Optional[str] = Field(
        None,
        description="Design description (optional)"
    )
    # creator
    creator: str = Field(
        description="UUID of user who created this design"
    )
    # timestamps
    created: str = Field(
        description="ISO timestamp when design was created"
    )
    lastmodified: str = Field(
        description="ISO timestamp when design was last modified"
    )
    # components and respective insertion frames
    components: List[DesignComponent] = Field(
        description="List of components and their insertion frames"
    )
    # additional geometry (design-scoped)
    additional_geometry: List[DesignAdditionalGeometry] = Field(
        default_factory=list,
        description=(
            "List of additional static meshes embedded in the design. "
            "Always present; may be empty."
        )
    )

    class Config:
        extra = "ignore"
        populate_by_name = True
        schema_extra = {
            "example": {
                "_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Design A",
                "description": "One of many beautiful designs",
                "creator": "550e8400-e29b-41d4-a716-446655440002",
                "created": "2024-01-15T10:30:00Z",
                "lastmodified": "2024-01-15T10:30:00Z",
                "components": [
                    {
                        "component": "550e8400-e29b-41d4-a716-446655440000",
                        "iframe": {
                            "o": [0.0, 0.0, 0.0],
                            "x": [1.0, 0.0, 0.0],
                            "y": [0.0, 1.0, 0.0],
                            "z": [0.0, 0.0, 1.0]
                        }
                    },
                    {
                        "component": "550e8400-e29b-41d4-a716-446655440001",
                        "iframe": {
                            "o": [100.0, 0.0, 0.0],
                            "x": [1.0, 0.0, 0.0],
                            "y": [0.0, 1.0, 0.0],
                            "z": [0.0, 0.0, 1.0]
                        }
                    }
                ],
                "additional_geometry": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440099",
                        "name": "connector A",
                        "iframe": {
                            "o": [0.0, 0.0, 0.0],
                            "x": [1.0, 0.0, 0.0],
                            "y": [0.0, 1.0, 0.0],
                            "z": [0.0, 0.0, 1.0]
                        },
                        "geometry": {
                            "meshes": [
                                {
                                    "v": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                                    "f": [[0, 1, 2]]
                                }
                            ]
                        }
                    }
                ]
            }
        }


class CreateDesignRequest(BaseModel):
    """Request model for creating a new design."""
    id: str = Field(
        alias="_id",
        description="Design ID (UUID provided by client)"
    )
    name: Optional[str] = Field(
        None,
        description="Human readable design name (optional)"
    )
    description: Optional[str] = Field(
        None,
        description="Design description (optional)"
    )
    components: List[DesignComponent] = Field(
        description="List of components and their insertion frames"
    )
    additional_geometry: List[DesignAdditionalGeometry] = Field(
        default_factory=list,
        description=(
            "List of additional static meshes embedded in the design. "
            "Always present; may be empty."
        )
    )


class UpdateDesignModel(BaseModel):
    """Model for updating an existing design."""
    name: Optional[str] = Field(
        None,
        description="Human readable design name (optional)"
    )
    description: Optional[str] = Field(
        None,
        description="Design description (optional)"
    )
    components: Optional[List[DesignComponent]] = Field(
        None,
        description="List of components and their insertion frames"
    )
    additional_geometry: Optional[List[DesignAdditionalGeometry]] = Field(
        None,
        description=(
            "List of additional static meshes embedded in the design"
        )
    )

    class Config:
        extra = "ignore"
        populate_by_name = True
