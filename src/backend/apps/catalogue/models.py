#!/usr/bin/env python3.9

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import uuid
from typing import Optional, List, Dict, Union


# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------

from pydantic import BaseModel, Field


# AUTH ------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Union[str, None] = None


class User(BaseModel):
    _id: str
    username: str
    email: Union[str, None] = None
    full_name: Union[str, None] = None
    disabled: Union[bool, None] = None


class UserInDB(User):
    hashed_password: str


# COMPONENTS ------------------------------------------------------------------

ALLOWED_COMPONENT_TYPES = [
    'sheet',
    'beam',
    'slab',
    'rubble',
    'column'
]

ALLOWED_COMPONENT_SORTKEYS = [
    '_id',
    'type',
    'material'
]


class ComponentModel(BaseModel):
    id: str = Field(default_factory=uuid.uuid4, alias='_id')
    componenttype: str = Field(alias='type')
    material: str = Field(...)
    materialthickness: float = Field(...)
    geometry: Dict = Field(...)
    color: Optional[List[float]]
    validated: bool = Field(...)
    bbx: Dict = Field(...)
    iframe = Optional[Dict]

    class Config:
        extra = 'allow'
        populate_by_name = True
        schema_extra = {
            'example': {
                'id': 'bd5432e7-c332-4b1b-a898-b3e4296071e0',
                'componenttype': 'sheet',
                'material': 'corian',
                'materialthickness': 12.0,
                'geometry': {
                    'polyline': [
                        [601.8, 439.8],
                        [583.9, -9.8],
                        [276.0, -153.2],
                        [317.9, -237.6],
                        [305.6, -353.6],
                        [214.8, -439.8],
                        [85.3, -309.5],
                        [-601.8, -439.8],
                        [-165.9, 111.5],
                        [-203.0, 283.6],
                        [-187.6, 361.3],
                        [-58.1, 361.8],
                        [601.8, 439.8]
                    ],
                    'mesh': {
                        'v': [
                            [796.96, 991.97, 10.0],
                            [800.67, 993.03, 20.0],
                            [804.63, 993.29, 15.0],
                        ],
                        'f': [
                            [0, 1, 2],
                            [1, 2, 0],
                            [2, 1, 0]
                        ]
                    }
                },
                'color': [200.0, 210.0, 255.0],
                'validated': True,
                'bbx': {
                    'xy': [
                        [-601.8, -439.8],
                        [601.8, -439.8],
                        [601.8, 439.8],
                        [-601.8, 439.8]
                    ],
                    'xyz': [
                        [-177.1, -112.0, -56.2],
                        [181.8, -112.0, -56.2],
                        [181.8, 156.1, -56.2],
                        [-177.1, 156.1, -56.2],
                        [-177.1, -112.0, 80.6],
                        [181.8, -112.0, 80.6],
                        [181.8, 156.1, 80.6],
                        [-177.1, 156.1, 80.6]
                    ]
                },
                'iframe': {
                    'o': [0.0, 0.0, 0.0],
                    'x': [1.0, 0.0, 0.0],
                    'y': [0.0, 1.0, 0.0],
                    'z': [0.0, 0.0, 1.0]
                }
            }
        }


class UpdateComponentModel(BaseModel):
    componenttype: Optional[str]
    material: Optional[str]
    geometry: Optional[Dict]
    materialthickness: Optional[float]
    color: Optional[List[float]]
    validated: Optional[bool]
    bbx: Optional[Dict]
    iframe = Optional[Dict]

    class Config:
        extra = 'allow'
        schema_extra = {
            'example': {
                'componenttype': 'AnotherComponentType',
                'material': 'SuddenlyOtherMaterial',
                'materialthickness': 14.2,
                'geometry': {
                    'polyline': [
                        [601.8, 439.8],
                        [583.9, -9.8],
                        [276.0, -153.2],
                        [317.9, -237.6],
                        [305.6, -353.6],
                        [214.8, -439.8],
                        [85.3, -309.5],
                        [-601.8, -439.8],
                        [-165.9, 111.5],
                        [-203.0, 283.6],
                        [-187.6, 361.3],
                        [-58.1, 361.8],
                        [601.8, 439.8]
                    ],
                    'mesh': {
                        'v': [
                            [796.96, 991.97, 10.0],
                            [800.67, 993.03, 20.0],
                            [804.63, 993.29, 15.0],
                        ],
                        'f': [
                            [0, 1, 2],
                            [1, 2, 0],
                            [2, 1, 0]
                        ]
                    }
                },
                'color': [200.0, 210.0, 255.0],
                'validated': True,
                'bbx': {
                    'xy': [
                        [-601.8, -439.8],
                        [601.8, -439.8],
                        [601.8, 439.8],
                        [-601.8, 439.8]
                    ],
                    'xyz': [
                        [-177.1, -112.0, -56.2],
                        [181.8, -112.0, -56.2],
                        [181.8, 156.1, -56.2],
                        [-177.1, 156.1, -56.2],
                        [-177.1, -112.0, 80.6],
                        [181.8, -112.0, 80.6],
                        [181.8, 156.1, 80.6],
                        [-177.1, 156.1, 80.6]
                    ]
                },
                'iframe': {
                    'o': [0.0, 0.0, 0.0],
                    'x': [1.0, 0.0, 0.0],
                    'y': [0.0, 1.0, 0.0],
                    'z': [0.0, 0.0, 1.0]
                }
            }
        }
