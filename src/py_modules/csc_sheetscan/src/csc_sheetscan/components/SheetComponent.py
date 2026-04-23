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
                 processes: Dict = None,
                 validated: bool = False) -> None:
        if location is None:
            location = {}
        if descriptors is None:
            descriptors = {}
        if processes is None:
            processes = {}
        # process inputs
        geometry = {
            'extrusion': {
                'profile': profile
            }
        }
        # create BaseComponent
        # NOTE: the `csc_sheetscan` pipeline still produces sheet-shaped
        # components (extruded 2D profile), but the canonical type name
        # changed from `sheet` to `panel` in Phase 1 of the v0.5 roadmap
        # (see IMPLEMENTATION_PLAN.md, ADR-002).
        super().__init__(
            _id=_id,
            componenttype='panel',
            material=material,
            geometry=geometry,
            complexity=complexity,
            fragment=fragment,
            assembly=False,
            color=color,
            bbx=bbx,
            location=location,
            descriptors=descriptors,
            processes=processes,
            validated=validated
        )
