# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Dict, List

# LOCAL MODULE IMPORTS --------------------------------------------------------
from csc_sheetscan.components import BaseComponent


# CLASS DEFINITIONS -----------------------------------------------------------

class SheetComponent(BaseComponent):

    def __init__(self,
                 _id: str,
                 material: str,
                 materialthickness: float,
                 polyline: List[List[float]],
                 complexity: int,
                 fragment: bool,
                 color: List[int],
                 bbx_xy: List[List[float]],
                 descriptors: Dict = {},
                 indicators: Dict = {},
                 validated: bool = False) -> None:
        # process inputs
        geometry = {
            'polyline': polyline
        }
        bbx = {
            'xy': bbx_xy,
            'xyz': None
        }
        # create BaseComponent
        super().__init__(
            _id=_id,
            componenttype='sheet',
            material=material,
            materialthickness=materialthickness,
            geometry=geometry,
            complexity=complexity,
            fragment=fragment,
            assembly=False,
            color=color,
            bbx=bbx,
            descriptors=descriptors,
            indicators=indicators,
            validated=validated
        )
