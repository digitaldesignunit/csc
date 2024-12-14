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
    'material',
    'color',
    'created',
    'lastmodified',
]

ALLOWED_COMPLEXITY_LEVELS = [
    0,  # very low -> e.g. polygon, line
    1,  # low -> e.g. extrusion, sheet
    2,  # medium
    3,  # high
]


class ComponentModel(BaseModel):
    # globally unique ID
    id: str = Field(default_factory=uuid.uuid4, alias='_id')
    # human readable name (optional)
    name: Optional[str]
    # timestamp fields
    created: str = Field(...)
    lastmodified: str = Field(...)
    # base attributes
    componenttype: str = Field(alias='type')
    material: str = Field(...)
    materialthickness: float = Field(...)
    complexity: Optional[int]
    fragment: bool = Field(...)
    assembly: bool = Field(...)
    # geometry data is a dict storing the geometric representation
    geometry: Dict = Field(...)
    color: Optional[List[int]]
    bbx: List[float] = Field(...)
    # location
    location: Optional[Dict]
    # attached geometric descriptors, i.e. feature vectors
    descriptors: Optional[Dict]
    # reference to attached processes
    processes: Optional[Dict]
    # insertion frame
    iframe: Optional[Dict]
    # additional attributes (optional)
    attributes: Optional[Dict]
    # validation
    validated: bool = Field(...)

    class Config:
        extra = 'allow'
        populate_by_name = True
        json_schema_extra = {
            'examples': [
                {
                    '_id': '0026b86f-2b7c-4441-a42b-c135401601f9',
                    'name': 'Sheet 1',
                    'created': '240522-000248',
                    'lastmodified': '240522-000248',
                    'type': 'sheet',
                    'material': 'corian',
                    'materialthickness': 12,
                    'geometry': {
                        'extrusion': {
                            'height': 12.0,
                            'profile': [
                                [-236.5281668056187, 135.9138446188233],
                                [-235.98666438856054, 136.43043673849218],
                                [-187.81222509575286, 136.619636378187],
                                [236.19128468854456, 136.69496037267368],
                                [236.7078768082133, 136.15345795561552],
                                [236.95223496355607, 22.86883920802336],
                                [235.7850096001714, 7.0161038801627456],
                                [236.75591809603554, 3.2878627042294966],
                                [236.92702811500726, -0.6862193828435466],
                                [235.66342362481873, -9.390589013450608],
                                [236.98900730732123, -20.537947095166373],
                                [236.91902123370357, -135.93252734186524],
                                [235.57772033975323, -136.69496037267368],
                                [-236.59400116300475, -136.69496037267356],
                                [-236.98900730732095, -119.74676506200217],
                                [-236.5281668056187, 135.9138446188233]
                            ]
                        }
                    },
                    'complexity': 1,
                    'fragment': True,
                    'assembly': False,
                    'color': [209, 208, 205],
                    'bbx': [
                        [-236.98900730732106, -136.69496037267368, -6.0],
                        [236.98900730732112, 136.69496037267368, 6.0]
                    ],
                    'location': {
                        'lat': 49.86144,
                        'lon': 8.676556
                    },
                    'descriptors': {},
                    'processes': {},
                    'validated': True,
                    'iframe': {
                        'o': [0, 0, 0],
                        'x': [1, 0, 0],
                        'y': [0, 1, 0],
                        'z': [0, 0, 1]
                    },
                    'attributes': {}
                },
                {
                    '_id': 'a99b2619-0d97-495f-98c4-a6b02db206a3',
                    'name': 'Beam 1',
                    'created': '240522-083157',
                    'lastmodified': '240522-083157',
                    'type': 'beam',
                    'material': 'timber',
                    'materialthickness': 53.0,
                    'geometry': {
                        'mesh': {
                            'v': [
                                [510, 33.5, 26.5],
                                [510, -33.5, 26.5],
                                [-510, 33.5, 26.5],
                                [-510, -33.5, 26.5],
                                [-510, -33.5, 26.5],
                                [-510, 33.5, 26.5],
                                [-510, 36.5, 23.5],
                                [-510, 36.5, -23.5],
                                [-510, 33.5, -26.5],
                                [-510, -33.5, -26.5],
                                [-510, -36.5, -23.5],
                                [-510, -36.5, 23.5],
                                [-510, 33.5, -26.5],
                                [-510, -33.5, -26.5],
                                [510, 33.5, -26.5],
                                [510, -33.5, -26.5],
                                [510, 33.5, 26.5],
                                [510, -33.5, 26.5],
                                [510, -33.5, -26.5],
                                [510, 33.5, -26.5],
                                [510, 36.5, -23.5],
                                [510, 36.5, 23.5],
                                [510, -36.5, 23.5],
                                [510, -36.5, -23.5],
                                [510, 36.5, 23.5],
                                [-510, 36.5, -23.5],
                                [-510, 36.5, 23.5],
                                [510, 36.5, -23.5],
                                [510, -36.5, 23.5],
                                [510, -36.5, -23.5],
                                [-510, -36.5, 23.5],
                                [-510, -36.5, -23.5],
                                [510, 33.5, 26.5],
                                [-510, 33.5, 26.5],
                                [-510, 36.5, 23.5],
                                [510, 36.5, 23.5],
                                [510, -33.5, 26.5],
                                [-510, -33.5, 26.5],
                                [-510, -36.5, 23.5],
                                [510, -36.5, 23.5],
                                [-510, 33.5, -26.5],
                                [510, 33.5, -26.5],
                                [510, 36.5, -23.5],
                                [-510, 36.5, -23.5],
                                [-510, -33.5, -26.5],
                                [510, -33.5, -26.5],
                                [510, -36.5, -23.5],
                                [-510, -36.5, -23.5]
                            ],
                            'f': [
                                [1, 0, 2],
                                [6, 11, 4],
                                [11, 6, 7],
                                [10, 7, 8],
                                [13, 12, 14],
                                [18, 19, 20],
                                [23, 20, 21],
                                [22, 21, 16],
                                [27, 25, 26],
                                [29, 28, 30],
                                [35, 34, 33],
                                [39, 36, 37],
                                [43, 42, 41],
                                [47, 44, 45],
                                [1, 2, 3],
                                [6, 4, 5],
                                [11, 7, 10],
                                [10, 8, 9],
                                [13, 14, 15],
                                [18, 20, 23],
                                [23, 21, 22],
                                [22, 16, 17],
                                [27, 26, 24],
                                [29, 30, 31],
                                [35, 33, 32],
                                [39, 37, 38],
                                [43, 41, 40],
                                [47, 45, 46]
                            ],
                            'c': [
                                [29, 28, 30],
                                [35, 33, 32],
                                [39, 37, 38],
                                [43, 41, 40],
                                [47, 45, 46],
                                [35, 34, 33],
                                [39, 36, 37],
                                [43, 42, 41],
                                [47, 44, 45],
                                [1, 0, 2],
                                [6, 11, 4],
                                [11, 6, 7],
                                [10, 7, 8],
                                [13, 12, 14],
                                [18, 19, 20],
                                [23, 20, 21],
                                [22, 21, 16],
                                [27, 25, 26],
                                [1, 2, 3],
                                [6, 4, 5],
                                [11, 7, 10],
                                [10, 8, 9],
                                [13, 14, 15],
                                [18, 20, 23],
                                [23, 21, 22],
                                [22, 16, 17],
                                [27, 26, 24],
                                [29, 30, 31]
                            ]
                        }
                    },
                    'complexity': 1,
                    'fragment': True,
                    'assembly': False,
                    'color': [207, 194, 126],
                    'bbx': [
                        [-510, -36.500000, -26.500000],
                        [510, 36.500000, 26.500000]
                    ],
                    'location': {
                        'lat': 49.86144,
                        'lon': 8.676556
                    },
                    'descriptors': {},
                    'processes': {},
                    'validated': True,
                    'iframe': {
                        'o': [0, 0, 0],
                        'x': [1, 0, 0],
                        'y': [0, 1, 0],
                        'z': [0, 0, 1]
                    },
                    'attributes': {}
                }
            ]
        }


class UpdateComponentModel(BaseModel):
    componenttype: Optional[str]
    lastmodified: str = Field(...)
    material: Optional[str]
    geometry: Optional[Dict]
    materialthickness: Optional[float]
    complexity: Optional[float]
    fragment: Optional[bool]
    assembly: Optional[bool]
    color: Optional[List[int]]
    validated: Optional[bool]
    bbx: Optional[Dict]
    iframe: Optional[Dict]

    class Config:
        extra = 'allow'
        populate_by_name = True
        json_schema_extra = {
            'examples': [
                {
                    '_id': '0026b86f-2b7c-4441-a42b-c135401601f9',
                    'name': 'Sheet 1',
                    'created': '240522-000248',
                    'lastmodified': '240522-000248',
                    'type': 'sheet',
                    'material': 'corian',
                    'materialthickness': 12,
                    'geometry': {
                        'extrusion': {
                            'height': 12.0,
                            'profile': [
                                [-236.5281668056187, 135.9138446188233],
                                [-235.98666438856054, 136.43043673849218],
                                [-187.81222509575286, 136.619636378187],
                                [236.19128468854456, 136.69496037267368],
                                [236.7078768082133, 136.15345795561552],
                                [236.95223496355607, 22.86883920802336],
                                [235.7850096001714, 7.0161038801627456],
                                [236.75591809603554, 3.2878627042294966],
                                [236.92702811500726, -0.6862193828435466],
                                [235.66342362481873, -9.390589013450608],
                                [236.98900730732123, -20.537947095166373],
                                [236.91902123370357, -135.93252734186524],
                                [235.57772033975323, -136.69496037267368],
                                [-236.59400116300475, -136.69496037267356],
                                [-236.98900730732095, -119.74676506200217],
                                [-236.5281668056187, 135.9138446188233]
                            ]
                        }
                    },
                    'complexity': 1,
                    'fragment': True,
                    'assembly': False,
                    'color': [209, 208, 205],
                    'bbx': [
                        [-236.98900730732106, -136.69496037267368, -6.0],
                        [236.98900730732112, 136.69496037267368, 6.0]
                    ],
                    'location': {
                        'lat': 49.86144,
                        'lon': 8.676556
                    },
                    'descriptors': {},
                    'processes': {},
                    'validated': True,
                    'iframe': {
                        'o': [0, 0, 0],
                        'x': [1, 0, 0],
                        'y': [0, 1, 0],
                        'z': [0, 0, 1]
                    },
                    'attributes': {}
                },
                {
                    '_id': 'a99b2619-0d97-495f-98c4-a6b02db206a3',
                    'name': 'Beam 1',
                    'created': '240522-083157',
                    'lastmodified': '240522-083157',
                    'type': 'beam',
                    'material': 'timber',
                    'materialthickness': 53.0,
                    'geometry': {
                        'mesh': {
                            'v': [
                                [510, 33.5, 26.5],
                                [510, -33.5, 26.5],
                                [-510, 33.5, 26.5],
                                [-510, -33.5, 26.5],
                                [-510, -33.5, 26.5],
                                [-510, 33.5, 26.5],
                                [-510, 36.5, 23.5],
                                [-510, 36.5, -23.5],
                                [-510, 33.5, -26.5],
                                [-510, -33.5, -26.5],
                                [-510, -36.5, -23.5],
                                [-510, -36.5, 23.5],
                                [-510, 33.5, -26.5],
                                [-510, -33.5, -26.5],
                                [510, 33.5, -26.5],
                                [510, -33.5, -26.5],
                                [510, 33.5, 26.5],
                                [510, -33.5, 26.5],
                                [510, -33.5, -26.5],
                                [510, 33.5, -26.5],
                                [510, 36.5, -23.5],
                                [510, 36.5, 23.5],
                                [510, -36.5, 23.5],
                                [510, -36.5, -23.5],
                                [510, 36.5, 23.5],
                                [-510, 36.5, -23.5],
                                [-510, 36.5, 23.5],
                                [510, 36.5, -23.5],
                                [510, -36.5, 23.5],
                                [510, -36.5, -23.5],
                                [-510, -36.5, 23.5],
                                [-510, -36.5, -23.5],
                                [510, 33.5, 26.5],
                                [-510, 33.5, 26.5],
                                [-510, 36.5, 23.5],
                                [510, 36.5, 23.5],
                                [510, -33.5, 26.5],
                                [-510, -33.5, 26.5],
                                [-510, -36.5, 23.5],
                                [510, -36.5, 23.5],
                                [-510, 33.5, -26.5],
                                [510, 33.5, -26.5],
                                [510, 36.5, -23.5],
                                [-510, 36.5, -23.5],
                                [-510, -33.5, -26.5],
                                [510, -33.5, -26.5],
                                [510, -36.5, -23.5],
                                [-510, -36.5, -23.5]
                            ],
                            'f': [
                                [1, 0, 2],
                                [6, 11, 4],
                                [11, 6, 7],
                                [10, 7, 8],
                                [13, 12, 14],
                                [18, 19, 20],
                                [23, 20, 21],
                                [22, 21, 16],
                                [27, 25, 26],
                                [29, 28, 30],
                                [35, 34, 33],
                                [39, 36, 37],
                                [43, 42, 41],
                                [47, 44, 45],
                                [1, 2, 3],
                                [6, 4, 5],
                                [11, 7, 10],
                                [10, 8, 9],
                                [13, 14, 15],
                                [18, 20, 23],
                                [23, 21, 22],
                                [22, 16, 17],
                                [27, 26, 24],
                                [29, 30, 31],
                                [35, 33, 32],
                                [39, 37, 38],
                                [43, 41, 40],
                                [47, 45, 46]
                            ],
                            'c': [
                                [29, 28, 30],
                                [35, 33, 32],
                                [39, 37, 38],
                                [43, 41, 40],
                                [47, 45, 46],
                                [35, 34, 33],
                                [39, 36, 37],
                                [43, 42, 41],
                                [47, 44, 45],
                                [1, 0, 2],
                                [6, 11, 4],
                                [11, 6, 7],
                                [10, 7, 8],
                                [13, 12, 14],
                                [18, 19, 20],
                                [23, 20, 21],
                                [22, 21, 16],
                                [27, 25, 26],
                                [1, 2, 3],
                                [6, 4, 5],
                                [11, 7, 10],
                                [10, 8, 9],
                                [13, 14, 15],
                                [18, 20, 23],
                                [23, 21, 22],
                                [22, 16, 17],
                                [27, 26, 24],
                                [29, 30, 31]
                            ]
                        }
                    },
                    'complexity': 1,
                    'fragment': True,
                    'assembly': False,
                    'color': [207, 194, 126],
                    'bbx': [
                        [-510, -36.500000000000014, -26.500000000000004],
                        [510, 36.500000000000014, 26.500000000000004]
                    ],
                    'location': {
                        'lat': 49.86144,
                        'lon': 8.676556
                    },
                    'descriptors': {},
                    'processes': {},
                    'validated': True,
                    'iframe': {
                        'o': [0, 0, 0],
                        'x': [1, 0, 0],
                        'y': [0, 1, 0],
                        'z': [0, 0, 1]
                    },
                    'attributes': {}
                }
            ]
        }


class DesignModel(BaseModel):
    id: str = Field(default_factory=uuid.uuid4, alias='_id')
    created: str = Field(...)
    lastmodified: str = Field(...)
    title: str = Field(...)
    description: Optional[str]
    components: List[str] = Field(...)


class ProcessModel(BaseModel):
    # globally unique ID
    id: str = Field(default_factory=uuid.uuid4, alias='_id')
    # timestamp fields
    created: str = Field(...)
    lastmodified: str = Field(...)
    # base attributes
    processtype: str = Field(alias='type')
    # indicator and descriptor data
    descriptors: Optional[Dict]
    indicators: Optional[Dict]
    # validation
    validated: bool = Field(...)
    # reference
    machines: Optional[Dict]
