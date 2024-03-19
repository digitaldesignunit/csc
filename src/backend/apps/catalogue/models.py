import uuid
from typing import Optional, List

from pydantic import BaseModel, Field


class ComponentModel(BaseModel):
    id: str = Field(default_factory=uuid.uuid4, alias='_id')
    componenttype: str = Field(alias='type')
    material: str = Field(...)
    geometry: List[List[float]] = Field(...)
    # boundingbox: Tuple[float, float, float] = Field(...)

    class Config:
        populate_by_name = True
        schema_extra = {
            'example': {
                'id': 'bd5432e7-c332-4b1b-a898-b3e4296071e0',
                'componenttype': 'sheet',
                'material': 'corian',
                'geometry': [
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
                    ]
            }
        }


class UpdateComponentModel(BaseModel):
    componenttype: Optional[str]
    material: Optional[str]
    geometry: Optional[List[List[float]]]

    class Config:
        schema_extra = {
            'example': {
                'componenttype': 'AnotherComponentType',
                'material': 'SuddenlyOtherMaterial',
                'geometry': [
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
                    ]
            }
        }
