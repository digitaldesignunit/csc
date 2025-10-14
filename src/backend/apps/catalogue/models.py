#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Optional, List, Dict, Union, Literal
import uuid

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import BaseModel, Field, EmailStr, RootModel, model_validator

# AUTH ------------------------------------------------------------------------
Role = Literal["user", "admin"]


class Token(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class TokenData(BaseModel):
    sub: Union[str, None] = None  # subject (we use user _id / GUID)
    role: Role = "user"


class User(BaseModel):
    id: str = Field(alias="_id")
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    role: Role = "user"

    class Config:
        populate_by_name = True


class UserInDB(User):
    hashed_password: str


# COMPONENTS ------------------------------------------------------------------
ALLOWED_COMPONENT_TYPES = ["sheet", "beam", "slab", "rubble", "column"]


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
    mesh: Optional[ComponentMesh] = Field(
        None, description="Mesh geometry (single mesh - backward compat)"
    )
    meshes: Optional[List[ComponentMesh]] = Field(
        None, description="Array of mesh geometries (multiple meshes)"
    )
    extrusion: Optional[ComponentExtrusion] = Field(
        None, description="Extrusion geometry"
    )

    @model_validator(mode='after')
    def validate_mesh_fields(self):
        """Validate that mesh and meshes fields are not both present."""
        if self.mesh is not None and self.meshes is not None:
            raise ValueError(
                "Cannot have both 'mesh' and 'meshes' fields present. "
                "Use 'mesh' for single mesh (backward compatibility) or "
                "'meshes' for multiple meshes."
            )
        return self

    class Config:
        exclude_none = True


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
        description="Type of component (sheet, beam, slab, rubble, column)"
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
        description="Component geometry data (mesh, extrusion, etc.)"
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

    class Config:
        extra = "allow"
        populate_by_name = True
        exclude_none = True
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
                "etag": "abc123def456"
            }
        }


class UpdateComponentModel(BaseModel):
    componenttype: Optional[str]
    lastmodified: str
    material: Optional[str]
    dataset: Optional[str]
    geometry: Optional[ComponentGeometry]
    complexity: Optional[float]
    fragment: Optional[bool]
    assembly: Optional[bool]
    color: Optional[List[int]]
    validated: Optional[bool]
    bbx: Optional[ComponentBoundingBox]
    bbx_origin: Optional[List[float]]
    iframe: Optional[ComponentFrame]
    pca_frame: Optional[ComponentFrame]
    reserved: Optional[str]

    class Config:
        extra = "allow"
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
        description=(
            "Geometry data. Use 'meshes' array; if single mesh, provide array "
            "with one entry."
        )
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
        extra = "allow"
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
        extra = "allow"
        populate_by_name = True
