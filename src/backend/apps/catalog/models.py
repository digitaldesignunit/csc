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
    "type",
    "material",
    "dataset",
    "color",
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
