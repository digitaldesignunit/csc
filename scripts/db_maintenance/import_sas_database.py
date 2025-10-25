# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os
import json
import shutil

COMPLEXITY_MAP = {
    'low': 1,
    'medium': 2,
    'high': 3
}

SOURCE_DIR = r'C:\Users\EFESTWIN\Documents\07_tu_darmstadt_ddu\05_Promotion\07_Source\240404_SAS_Debris_Files' # NOQA
GEOMETRY_TARGET_DIR = r'C:\Users\EFESTWIN\Documents\07_tu_darmstadt_ddu\05_Promotion\07_Source\241212_MES_Geometry_Repo' # NOQA
JSON_TARGET_DIR = r'C:\Users\EFESTWIN\Documents\07_tu_darmstadt_ddu\05_Promotion\07_Source\241212_MES_JSON_Repo' # NOQA

if not os.path.exists(JSON_TARGET_DIR):
    os.makedirs(JSON_TARGET_DIR)
if not os.path.exists(GEOMETRY_TARGET_DIR):
    os.makedirs(GEOMETRY_TARGET_DIR)

# get all rubble objects by folder
rubble_ids = os.listdir(SOURCE_DIR)
for i, rubble_id in enumerate(rubble_ids):
    size = len(rubble_ids)
    print(f'Processing {rubble_id} - ({i + 1}/{size})...')
    # get all files in rubble folder
    rubble_metadata = os.path.join(SOURCE_DIR, rubble_id, 'metadata.json')
    rubble_vectors = os.path.join(SOURCE_DIR, rubble_id, 'vectors.json')
    mesh_primitive = os.path.join(SOURCE_DIR, rubble_id, 'mesh_primitive.json')

    # get rubble directory
    source_obj_dir = os.path.join(SOURCE_DIR, rubble_id, 'obj')

    # create target directory
    target_obj_dir = os.path.join(GEOMETRY_TARGET_DIR, rubble_id)
    if not os.path.exists(target_obj_dir):
        os.makedirs(target_obj_dir)

    # copy all files to target directory
    print('Copying geometry files...')
    for filename in os.listdir(source_obj_dir):
        source_obj_file = os.path.join(source_obj_dir, filename)
        target_obj_file = os.path.join(target_obj_dir, filename)
        shutil.copyfile(source_obj_file, target_obj_file)

    # read metadata json file in source folder
    print('Converting json metadata...')
    with open(rubble_metadata, 'r') as f:
        metadata = json.load(f)
        # create new json data based on csc pydantic component model
        component_data = {
            'id': metadata['name'],
            'name': f'SAS Rubble {str(i + 1).zfill(3)}',
            'created': '241212-000001',
            'lastmodified': '241212-000001',
            'type': 'rubble',
            'material': metadata['material'],
            'materialthickness': None,
            'geometry': {},
            'complexity': COMPLEXITY_MAP[metadata['complexity']],
            'fragment': metadata['fragment'],
            'assembly': False,
            'color': [100, 100, 100],  # COMPUTE!!
            'bbx': {
                'xy': None,
                'xyz': None
            },
            'location': {
                'lat': 55.682107,
                'lon': 12.603487
            },
            'descriptors': {},
            'processes': {},
            'validated': False,
            'iframe': {
                'o': [0, 0, 0],
                'x': [1, 0, 0],
                'y': [0, 1, 0],
                'z': [0, 0, 1]
            },
            'attributes': {
                'primitive': metadata['primitive'],
                'scan': metadata['scan'],
            }
        }

    # add geometry data to json dict
    print('Injecting primitive mesh data...')
    with open(mesh_primitive, 'r') as f:
        json_data = json.load(f)
        component_data['geometry'] = {'mesh': json_data['mesh']}
        component_data['bbx'].update(json_data['bbxdata'])
        component_data['materialthickness'] = json_data['materialthickness']

    # add vector data to json dict
    print('Injecting descriptor data...')
    with open(rubble_vectors, 'r') as f:
        vector_data = json.load(f)
        component_data['descriptors'] = {'sas_vectors': vector_data}

    # write json data to target directory
    print('Saving JSON file...')
    target_json_file = os.path.join(JSON_TARGET_DIR, f'{rubble_id}.json')
    with open(target_json_file, 'w') as json_file:
        json_file.write(json.dumps(component_data, indent=4))
