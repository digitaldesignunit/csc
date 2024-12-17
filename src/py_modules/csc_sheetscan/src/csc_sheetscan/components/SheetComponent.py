# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Dict, List

# LOCAL MODULE IMPORTS --------------------------------------------------------
from csc_sheetscan.components import BaseComponent


# CLASS DEFINITIONS -----------------------------------------------------------

class SheetComponent(BaseComponent):

    def __init__(self,
                 _id: str,
                 material: str,
                 profile: List[List[float]],
                 complexity: int,
                 fragment: bool,
                 color: List[int],
                 bbx: List[List[float]],
                 location: Dict = None,
                 descriptors: Dict = None,
                 indicators: Dict = None,
                 validated: bool = False) -> None:
        if location is None:
            location = {}
        if descriptors is None:
            descriptors = {}
        if indicators is None:
            indicators = {}
        # process inputs
        geometry = {
            'extrusion': {
                'profile': profile
            }
        }
        # create BaseComponent
        super().__init__(
            _id=_id,
            componenttype='sheet',
            material=material,
            geometry=geometry,
            complexity=complexity,
            fragment=fragment,
            assembly=False,
            color=color,
            bbx=bbx,
            location=location,
            descriptors=descriptors,
            indicators=indicators,
            validated=validated
        )
