#!/usr/bin/env python3.9
from typing import Optional, List, Dict, Union, Literal
import uuid
from pydantic import BaseModel, Field, EmailStr

# ---------------------- AUTH ----------------------

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


# ---------------------- COMPONENTS ----------------------

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


class ComponentModel(BaseModel):
    # globally unique ID (GUID stored in Mongo as _id)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    # human readable name (optional)
    name: Optional[str]
    # timestamps
    created: str
    lastmodified: str
    # base attributes
    componenttype: str = Field(alias="type")
    material: str
    complexity: Optional[int]
    fragment: bool
    assembly: bool
    # geometry & data
    geometry: Dict
    color: Optional[List[int]]
    bbx: List[float]
    location: Optional[Dict]
    descriptors: Optional[Dict]
    processes: Optional[Dict]
    iframe: Optional[Dict]
    attributes: Optional[Dict]
    validated: bool

    class Config:
        extra = "allow"
        populate_by_name = True


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

    class Config:
        extra = "allow"
        populate_by_name = True
