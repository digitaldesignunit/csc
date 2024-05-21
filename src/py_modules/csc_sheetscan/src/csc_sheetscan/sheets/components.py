# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import json
import os
from typing import Dict, List, Sequence


# ADDITIONAL MODULE IMPORTS ---------------------------------------------------


# LOCAL MODULE IMPORTS --------------------------------------------------------
from csc_sheetscan.utilities import (
    create_timestamp_str,
    sanitize_path
)


# CLASS DEFINITIONS -----------------------------------------------------------

class BaseComponent():

    __COMPONENT_DATA: Dict

    def __init__(self,
                 _id: str,
                 componenttype: str,
                 material: str,
                 materialthickness: float,
                 geometry: Dict,
                 complexity: int,
                 fragment: bool,
                 assembly: bool,
                 color: List[int],
                 bbx: Dict,
                 descriptors: Dict = {},
                 indicators: Dict = {},
                 validated: bool = False) -> None:
        self.__COMPONENT_DATA = {}
        # CREATE TIMESTAMP AND SET
        timestamp = create_timestamp_str()
        # SET DATA TO DICT
        self.__COMPONENT_DATA['_id'] = _id
        self.__COMPONENT_DATA['created'] = timestamp
        self.__COMPONENT_DATA['lastmodified'] = timestamp
        self.__COMPONENT_DATA['type'] = componenttype
        self.__COMPONENT_DATA['material'] = material
        self.__COMPONENT_DATA['materialthickness'] = materialthickness
        self.__COMPONENT_DATA['geometry'] = geometry
        self.__COMPONENT_DATA['complexity'] = complexity
        self.__COMPONENT_DATA['fragment'] = fragment
        self.__COMPONENT_DATA['assembly'] = assembly
        self.__COMPONENT_DATA['color'] = color
        self.__COMPONENT_DATA['bbx'] = bbx
        self.__COMPONENT_DATA['descriptors'] = descriptors
        self.__COMPONENT_DATA['indicators'] = indicators
        self.__COMPONENT_DATA['validated'] = validated
        self.__COMPONENT_DATA['iframe'] = {
            'o': [0.0, 0.0, 0.0],
            'x': [1.0, 0.0, 0.0],
            'y': [0.0, 1.0, 0.0],
            'z': [0.0, 0.0, 1.0]
        }

    # UUID PROP
    def get_component_id(self):
        return self.__COMPONENT_DATA['_id']

    id: str = property(get_component_id)

    # CREATED PROP
    def get_created(self):
        return self.__COMPONENT_DATA['created']

    created: str = property(get_created)

    # LAST MODIFIED PROP
    def get_lastmodified(self):
        return self.__COMPONENT_DATA['lastmodified']

    def __update_lastmodified(self):
        self.__COMPONENT_DATA['lastmodified'] = create_timestamp_str()

    lastmodified = property(get_lastmodified)

    # TYPE PROP
    def get_componenttype(self):
        return self.__COMPONENT_DATA['type']

    def set_componenttype(self, componenttype: str):
        self.__COMPONENT_DATA['type'] = componenttype
        self.__update_lastmodified()

    componenttype = property(get_componenttype, set_componenttype)

    # MATERIAL PROP
    def get_material(self):
        return self.__COMPONENT_DATA['material']

    def set_material(self, material: str):
        self.__COMPONENT_DATA['material'] = material
        self.__update_lastmodified()

    material = property(get_material, set_material)

    # MATERIALTHICKNESS PROP
    def get_materialthickness(self):
        return self.__COMPONENT_DATA['materialthickness']

    def set_materialthickness(self, materialthickness: float):
        self.__COMPONENT_DATA['materialthickness'] = materialthickness
        self.__update_lastmodified()

    materialthickness = property(get_materialthickness, set_materialthickness)

    # GEOMETRY PROP
    def get_geometry(self):
        return self.__COMPONENT_DATA['geometry']

    geometry = property(get_geometry)

    # COMPLEXITY PROP
    def get_complexity(self):
        return self.__COMPONENT_DATA['complexity']

    def set_complexity(self, complexity: int):
        self.__COMPONENT_DATA['complexity'] = complexity
        self.__update_lastmodified()

    complexity = property(get_complexity, set_complexity)

    # FRAGMENT PROP
    def get_fragment(self):
        return self.__COMPONENT_DATA['fragment']

    def set_fragment(self, fragment: bool):
        self.__COMPONENT_DATA['fragment'] = fragment
        self.__update_lastmodified()

    fragment = property(get_fragment, set_fragment)

    # ASSEMBLY PROP
    def get_assembly(self):
        return self.__COMPONENT_DATA['assembly']

    def set_assembly(self, assembly: bool):
        self.__COMPONENT_DATA['assembly'] = assembly
        self.__update_lastmodified()

    assembly = property(get_assembly, set_assembly)

    # COLOR PROP
    def get_color(self):
        return self.__COMPONENT_DATA['color']

    def set_color(self, color: Sequence[int]):
        if len(color) != 3:
            raise ValueError('Input is not a valid [R, G, B] value list!')
        self.__COMPONENT_DATA['color'] = color
        self.__update_lastmodified()

    color = property(get_color, set_color)

    # BBX PROP
    def get_bbx(self):
        return self.__COMPONENT_DATA['bbx']

    bbx = property(get_bbx)

    # DESCRIPTORS PROP
    def get_descriptors(self):
        return self.__COMPONENT_DATA['descriptors']

    descriptors = property(get_descriptors)

    # INDICATORS PROP
    def get_indicators(self):
        return self.__COMPONENT_DATA['indicators']

    indicators = property(get_indicators)

    # IFRAME PROP
    def get_iframe(self):
        return self.__COMPONENT_DATA['iframe']

    def set_iframe(self, iframe: Dict):
        self.__COMPONENT_DATA['iframe'] = iframe
        self.__update_lastmodified()

    iframe = property(get_iframe, set_iframe)

    # VALIDATED PROP
    def get_validated(self):
        return self.__COMPONENT_DATA['validated']

    def set_validated(self, validated: bool):
        self.__COMPONENT_DATA['validated'] = validated
        self.__update_lastmodified()

    validated = property(get_validated, set_validated)

    def to_json(self):
        """
        Returns a JSON string of this component.
        """
        return json.dumps(self.__COMPONENT_DATA, indent=4)

    def save_to_json(self, dirpath: str):
        """
        Saves the component to a .JSON file.
        """
        filename = self.id + '.json'
        print(filename)
        filepath = sanitize_path(os.path.join(dirpath, filename))
        with open(filepath, 'w') as jsonfile:
            jsonfile.write(self.to_json())
        return True

    @classmethod
    def create_from_json(cls, json_string: str):
        raise NotImplementedError(
            'Method create_from_json is not implemented yet'
        )


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
