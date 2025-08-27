#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Optional, List, Dict, Union, Literal
import uuid

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import BaseModel, Field, EmailStr

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
    "color",
    "created",
    "lastmodified",
]


ALLOWED_COMPLEXITY_LEVELS = [0, 1, 2, 3]


class ComponentCount(BaseModel):
    count: int


class ComponentDescriptors(BaseModel):
    id: str = Field(alias="_id")
    descriptors: Optional[Dict] = None

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
        None,
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
    complexity: Optional[int] = Field(
        None,
        description="Complexity level (0-3, where 0 is simplest)"
    )
    fragment: bool = Field(
        description="Whether this component is a fragment"
    )
    assembly: bool = Field(
        description="Whether this component is an assembly"
    )
    # geometry & data
    geometry: Dict = Field(
        description="Component geometry data (mesh, extrusion, etc.)"
    )
    color: Optional[List[int]] = Field(
        None,
        description="RGB color values as [R, G, B] integers (0-255)"
    )
    bbx: List[float] = Field(
        description=("Bounding box maximum extents as [X, Y, Z] float values "
                     "(dimensions of the component)")
    )
    location: Optional[Dict] = Field(
        None,
        description="Geographic location data (lat/lon coordinates)"
    )
    descriptors: Optional[Dict] = Field(
        None,
        description="Component descriptors and metadata"
    )
    processes: Optional[Dict] = Field(
        None,
        description="Manufacturing or processing information"
    )
    iframe: Optional[Dict] = Field(
        None,
        description="Insertion Frame / Transformation matrix data"
    )
    pca_frame: Optional[Dict] = Field(
        None,
        description=("PCA Frame / Principal Component Analysis transformation "
                     "matrix data")
    )
    reserved: Optional[str] = Field(
        None,
        description=("UUID of user who has reserved this component "
                     "(empty if not reserved)")
    )
    attributes: Optional[Dict] = Field(
        None,
        description="Additional component attributes"
    )
    validated: bool = Field(
        description="Whether this component has been validated"
    )

    class Config:
        extra = "allow"
        populate_by_name = True
        schema_extra = {
            "example": {
                "_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Concrete Slab A",
                "created": "2024-01-15T10:30:00Z",
                "lastmodified": "2024-01-15T10:30:00Z",
                "type": "slab",
                "material": "concrete",
                "complexity": 2,
                "fragment": False,
                "assembly": False,
                "geometry": {
                    "mesh": {
                        "v": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                        "f": [[0, 1, 2], [0, 2, 3]],
                        "c": [[128, 128, 128], [128, 128, 128]]
                    }
                },
                "color": [128, 128, 128],
                "bbx": [1.0, 1.0, 0.2],
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
                "validated": True
            }
        }


class UpdateComponentModel(BaseModel):
    componenttype: Optional[str]
    lastmodified: str
    material: Optional[str]
    geometry: Optional[Dict]
    complexity: Optional[float]
    fragment: Optional[bool]
    assembly: Optional[bool]
    color: Optional[List[int]]
    validated: Optional[bool]
    bbx: Optional[Dict]
    iframe: Optional[Dict]
    pca_frame: Optional[Dict]
    reserved: Optional[str]

    class Config:
        extra = "allow"
        populate_by_name = True


# DESIGNS ---------------------------------------------------------------------

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
    # components and respetive insertion frames
    components: List[Dict] = Field(
        description="List of components and their insertion frames"
    )

    class Config:
        extra = "allow"
        populate_by_name = True
        schema_extra = {
            "example": {
                "_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Design A",
                "description": "One of many beautiful designs",
                "created": "2024-01-15T10:30:00Z",
                "lastmodified": "2024-01-15T10:30:00Z",
                "components": [
                    {
                        "component": "550e8400-e29b-41d4-a716-446655440000",
                        "iframe": {
                            "x": 0,
                            "y": 0,
                            "z": 0
                        }
                    },
                    {
                        "component": "550e8400-e29b-41d4-a716-446655440001",
                        "iframe": {
                            "x": 0,
                            "y": 0,
                            "z": 0
                        }
                    }
                ]
            }
        }
