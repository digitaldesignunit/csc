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

class ComponentModel(BaseModel):
    id: str = Field(default_factory=uuid.uuid4, alias='_id')
    componenttype: str = Field(alias='type')
    material: str = Field(...)
    materialthickness: float = Field(...)
    geometry: Dict = Field(...)
    color: Optional[List[float]]
    validated: bool = Field(...)
    bbx: Dict = Field(...)

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
                        [679.2203210442758, 516.7578056094549],
                        [678.6911271829246, 517.2869994708061],
                        [677.3681425295466, 565.443640853766],
                        [667.3134591638736, 989.3279237960838],
                        [667.8426530252249, 989.8571176574351],
                        [781.0901393543834, 992.7676838948668],
                        [796.9659551949196, 991.97389310284],
                        [800.6703122243781, 993.0322808255423],
                        [804.6392661845122, 993.2968777562179],
                        [813.3709648968071, 992.2384900335155],
                        [824.4840359851825, 993.8260716175691],
                        [939.848297759746, 996.4720409243251],
                        [940.6420885517728, 995.1490562709472],
                        [951.7551596401481, 523.1081319456694],
                        [934.8209560769094, 522.3143411536425],
                        [679.2203210442758, 516.7578056094549]
                    ],
                },
                'color': [200.0, 210.0, 255.0],
                'validated': True,
                'bbx': {
                    'xy': [
                        [-214.1436004638672, -95.405517578125],
                        [195.86329650878906, -129.63218688964844],
                        [214.6228485107422, 95.09168243408203],
                        [-195.384033203125, 129.31834411621094]
                    ],
                    'xyz': None
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

    class Config:
        extra = 'allow'
        schema_extra = {
            'example': {
                'componenttype': 'AnotherComponentType',
                'material': 'SuddenlyOtherMaterial',
                'materialthickness': 14.2,
                'geometry': {
                    'polyline': [
                        [796.9659551949196, 991.97389310284],
                        [800.6703122243781, 993.0322808255423],
                        [804.6392661845122, 993.2968777562179],
                        [813.3709648968071, 992.2384900335155],
                        [824.4840359851825, 993.8260716175691],
                        [939.848297759746, 996.4720409243251],
                        [940.6420885517728, 995.1490562709472],
                        [951.7551596401481, 523.1081319456694],
                        [934.8209560769094, 522.3143411536425],
                        [796.9659551949196, 991.97389310284]
                    ],
                },
                'color': [200.0, 210.0, 255.0],
                'validated': True,
                'bbx': {
                    'xy': [
                        [-214.1436004638672, -95.405517578125],
                        [195.86329650878906, -129.63218688964844],
                        [214.6228485107422, 95.09168243408203],
                        [-195.384033203125, 129.31834411621094]
                    ],
                    'xyz': None
                }
            }
        }
