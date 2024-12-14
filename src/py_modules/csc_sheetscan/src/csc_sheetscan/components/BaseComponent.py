# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
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
                 complexity: int,
                 fragment: bool,
                 assembly: bool,
                 geometry: Dict,
                 color: List[int],
                 bbx: Dict,
                 name: str = '',
                 location: Dict = {},
                 descriptors: Dict = {},
                 processes: Dict = {},
                 attributes: Dict = {},
                 validated: bool = False) -> None:
        self.__COMPONENT_DATA = {}
        # CREATE TIMESTAMP AND SET
        timestamp = create_timestamp_str()
        # SYNTHESIZE NAME IF NOT PRESENT
        if not name or name == '':
            name = (f'{componenttype.capitalize()} Component '
                    f'made from {material.capitalize()}, '
                    f'created {timestamp}')
        # SET DATA TO DICT
        self.__COMPONENT_DATA['_id'] = _id
        self.__COMPONENT_DATA['name'] = name  # add default name generation
        self.__COMPONENT_DATA['created'] = timestamp
        self.__COMPONENT_DATA['lastmodified'] = timestamp
        self.__COMPONENT_DATA['type'] = componenttype
        self.__COMPONENT_DATA['material'] = material
        self.__COMPONENT_DATA['materialthickness'] = materialthickness
        self.__COMPONENT_DATA['complexity'] = complexity
        self.__COMPONENT_DATA['fragment'] = fragment
        self.__COMPONENT_DATA['assembly'] = assembly
        self.__COMPONENT_DATA['geometry'] = geometry
        self.__COMPONENT_DATA['color'] = color
        self.__COMPONENT_DATA['bbx'] = bbx
        self.__COMPONENT_DATA['location'] = location
        self.__COMPONENT_DATA['descriptors'] = descriptors
        self.__COMPONENT_DATA['processes'] = processes
        self.__COMPONENT_DATA['attributes'] = attributes
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

    # GEOMETRY PROP
    def get_geometry(self):
        return self.__COMPONENT_DATA['geometry']

    geometry = property(get_geometry)

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

    # LOCATION PROP
    def get_location(self):
        return self.__COMPONENT_DATA['location']

    def set_location(self, location: Dict):
        if not location.has_key('lat'):
            raise ValueError('Input location has no "lat" key! Dict should '
                             'be like: {"lat": 49.861444, "lon": 8.676556}')
        if not location.has_key('lon'):
            raise ValueError('Input location has no "lon" key! Dict should '
                             'be like: {"lat": 49.861444, "lon": 8.676556}')
        self.__COMPONENT_DATA['location'] = location
        self.__update_lastmodified()

    location = property(get_location, set_location)

    # DESCRIPTORS PROP
    def get_descriptors(self):
        return self.__COMPONENT_DATA['descriptors']

    descriptors = property(get_descriptors)

    # PROCESSES PROP
    def get_processes(self):
        return self.__COMPONENT_DATA['processes']

    processes = property(get_processes)

    # IFRAME PROP
    def get_iframe(self):
        return self.__COMPONENT_DATA['iframe']

    def set_iframe(self, iframe: Dict):
        self.__COMPONENT_DATA['iframe'] = iframe
        self.__update_lastmodified()

    iframe = property(get_iframe, set_iframe)

    # ATTRIBUTES PROP
    def get_attributes(self):
        return self.__COMPONENT_DATA['attributes']

    def set_attributes(self, attributes: Dict):
        self.__COMPONENT_DATA['attributes'] = attributes
        self.__update_lastmodified()

    attributes = property(get_attributes)

    # VALIDATED PROP
    def get_validated(self):
        return self.__COMPONENT_DATA['validated']

    def set_validated(self, validated: bool):
        self.__COMPONENT_DATA['validated'] = validated
        self.__update_lastmodified()

    validated = property(get_validated, set_validated)

    def access_dict(self):
        """
        Returns the dictionary of this component.

        ATTENTION: If you modify the dictionary, the component will be
        modified!
        """
        return self.__COMPONENT_DATA

    def to_shallow_dict(self):
        """
        Returns a shallow copy of the dictionary of this component.
        """
        return self.__COMPONENT_DATA.copy()

    def to_deep_dict(self):
        """
        Returns a deep copy of the dictionary of this component.
        """
        return copy.deepcopy(self.__COMPONENT_DATA)

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
