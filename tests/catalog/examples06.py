"""
Hand-written 0.6 documents (data model spec section 3), one valid example
of each.

Functions return fresh dicts so a test can mutate one field and expect a
validation error. Values follow the real data where one exists (the ZirKuS
bridge beam, the Corian offcuts, the DDU robot scans).
"""

from __future__ import annotations

import copy

IDENTITY_ID = '6f1c1d3e-2a4b-4c5d-8e9f-0a1b2c3d4e5f'
SNAPSHOT_ID = '7a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
EVIDENCE_ID = '8b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e'
USER_ID = '9c4d5e6f-7a8b-4c9d-0e1f-2a3b4c5d6e7f'
MODERATOR_ID = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d'
T0 = '2026-02-03T10:15:00Z'
T1 = '2026-02-27T14:30:00Z'

_ORIGIN = {
    'kind': 'deinstallation',
    'at': '2024-07-24T00:00:00Z',
    'at_precision': 'day',
    'place': {
        'name': 'TU Darmstadt Lichtwiese Campus',
        'address': 'Guenther-Behnisch-Strasse, 64287 Darmstadt, Germany',
        'location': None,
    },
    'construction_work': {
        'name': 'Lichtwiese Campus Infrastructure --- pedestrian bridge',
        'identifier': None,
        'year_built': None,
        'use': 'pedestrian bridge',
    },
    'method': 'lifted out by crane after saw cuts at the supports',
    'performed_by': [{'kind': 'organization', 'name': 'Rueckbau GmbH',
                      'role': 'operator'}],
    'notes': None,
}

_IDENTITY = {
    '_id': IDENTITY_ID,
    'catalog_number': 42,
    'original_function': 'IfcBeam',
    'material': 'concrete',
    'material_class': '17 01 01',
    'material_class_source': 'derived',
    'trade_name': None,
    'dataset': 'dbu_zirkus',
    'manufactured_at': '1974-01-01T00:00:00Z',
    'manufactured_precision': 'year',
    'origin': _ORIGIN,
    'parent_identities': None,
    'inherited_fields': [],
    'inherited_from': None,
    'exit': None,
    'past_cycles': [],
    'withdrawn': None,
    'reserved': '',
    'is_public': False,
    'current_snapshot_id': SNAPSHOT_ID,
    # the fold of the one published, accredited core record below (4.4):
    # 38.3 +- 1.2 (expanded), destructive 0.90 x factor 1.00
    'properties': {
        'compressive_strength': {
            'range': [37.1, 39.5], 'unit': 'MPa', 'confidence': 0.9,
            'source': 'destructive', 'n': 1, 'evidence_ids': [EVIDENCE_ID],
            'inherited_from': None, 'derived_at': T1,
        },
        'compressive_strength_in_situ': {
            'range': [38.3, 38.3], 'unit': 'MPa', 'confidence': 0.9,
            'source': 'destructive', 'n': 1, 'evidence_ids': [EVIDENCE_ID],
            'inherited_from': None, 'derived_at': T1,
        },
    },
    'properties_version': 1,
    'attributes': {},
    'created_by_user_id': USER_ID,
    'created': T0,
    'lastmodified': T1,
}

_SNAPSHOT = {
    '_id': SNAPSHOT_ID,
    'identity_id': IDENTITY_ID,
    'version': 0,
    'status': 'published',
    'status_changed_by_user_id': MODERATOR_ID,
    'status_changed_at': T0,
    'supersedes': None,
    'superseded_by': None,
    'name': 'ZirKuS beam B3',
    'effective_from': '2024-07-24T00:00:00Z',
    'effective_from_precision': 'day',
    'shape_class': 'linear',
    'shape_class_source': 'derived',
    'geometry': {
        'meshes': [{
            'vertices': [[0, 0, 0], [6000, 0, 0], [6000, 300, 0], [0, 300, 0]],
            'faces': [[0, 1, 2], [0, 2, 3]],
            'colors': [[128, 128, 128]] * 4,
        }],
        'point_clouds': [],
        'proxies': [{
            'primitive': 'box',
            'role': 'primary',
            'params': {'size': [6000, 300, 450]},
            'placement': {'o': [3000, 150, 225], 'x': [1, 0, 0],
                          'y': [0, 1, 0], 'z': [0, 0, 1]},
            'fit': {'method': 'obb',
                    'source': {'kind': 'meshes', 'index': 0,
                               'resolution': 'original'},
                    'n_points': 184220, 'rms_mm': 2.1, 'max_mm': 14.7,
                    'p95_mm': 6.3, 'spec_version': 1, 'computed_at': T1},
            'deviation_maps': None,
            'regions': [],
        }],
    },
    'capture': {
        'method': 'photogrammetry', 'device': 'iPhone 14 Pro Max',
        'software': 'Metashape', 'captured_at': T0, 'notes': None,
        'coordinate_system': None, 'markers': [], 'fixtures': [],
    },
    'descriptors': {'boxscore': 1.2, 'spherescore': 70.1,
                    'linescore': 12.0, 'planescore': 3.4},
    # no snapshot-scoped quantity has evidence: the core's are identity-scoped
    'properties': {},
    'properties_version': 1,
    'frame': {'o': [3000, 150, 225], 'x': [1, 0, 0], 'y': [0, 1, 0],
              'z': [0, 0, 1]},
    'bbx': [6000, 450, 300],
    'complexity': 1,
    'complexity_source': 'derived',
    'fragment': False,
    'color': [128, 128, 128],
    'location': {'lat': 49.86, 'lon': 8.68},
    'notes': None,
    'quantity': 1,
    'added_by_user_id': USER_ID,
    'added_by_username': 'alice',
    'photo_count': 2,
    'mesh_ply_resolutions': {'0': ['reduced', 'detailed']},
    'etag': 'abc',
    'created': T0,
    'lastmodified': T1,
}

_ROBOT_CAPTURE = {
    'method': 'photogrammetry', 'device': None, 'software': 'Metashape',
    'captured_at': None, 'notes': None,
    'coordinate_system': {'name': 'DDU robot gripper marker plane',
                          'description': None},
    'markers': [{'label': 'blue_1', 'role': 'rig', 'point': [120, 0.6, -0.6]},
                {'label': 'green_3', 'role': 'component',
                 'point': [-3.8, -99.9, 269.2]}],
    'fixtures': [{'label': 'end_effector',
                  'file': f'capture/{SNAPSHOT_ID}/fixtures/0.ply'}],
}

_EVIDENCE = {
    '_id': EVIDENCE_ID,
    'identity_id': IDENTITY_ID,
    'method': 'core_compression',
    'method_version': 1,
    'source_tier': 'destructive',
    'standard': {'code': 'EN 12504-1', 'year': 2019},
    'observed_at': T1,
    'observed_at_precision': 'exact',
    'sampled_at': '2026-02-20T11:00:00Z',
    'sampled_at_precision': 'exact',
    'performed_by': [{
        'kind': 'organization', 'name': None, 'organization': 'Pruefstelle',
        'role': 'laboratory',
        'accreditation': {'scheme': 'iso_17025', 'id': 'D-PL-12345-01-00',
                          'body': 'DAkkS', 'scope': ['EN 12504-1', 'EN 12390-3'],
                          'valid_until': None},
    }],
    'recorded_by_user_id': USER_ID,
    'recorded_by_username': 'alice',
    'position': {'kind': 'point', 'snapshot_id': SNAPSHOT_ID,
                 'point': [1500, 150, 450], 'description': 'north face, mid-span'},
    'summary': {'quantity': 'compressive_strength', 'value': 38.3, 'range': None,
                'unit': 'MPa', 'unit_entered': 'N/mm2', 'kind': 'measured',
                'uncertainty': {'type': 'expanded', 'value': 1.2, 'k': 2}},
    'derived': [{'quantity': 'compressive_strength_in_situ', 'value': 38.3,
                 'unit': 'MPa', 'kind': 'derived',
                 'model': {'kind': 'en_13791', 'reference': 'EN 13791:2019',
                           'note': None}}],
    'payload': {
        'sampling': {'cored_at': '2026-02-20T11:00:00Z',
                     'paired_rebound_id': None, 'drill_diameter_mm': 100,
                     'drilling_method': 'wet',
                     'orientation_vs_casting': None, 'operator': None,
                     'hole_repaired': False},
        'specimen': {'label': 'C-03', 'measured_diameter_mm': 99.6,
                     'length_as_drilled_mm': 215.0,
                     'length_prepared_mm': 199.2,
                     'end_preparation': 'ground',
                     'length_diameter_ratio': 2.0, 'ld_class': '2:1',
                     'mass_g': 3712.0, 'density_kg_m3': 2382.0,
                     'max_aggregate_size_mm': 16, 'storage': 'water',
                     'reinforcement': [], 'valid_for_strength': True,
                     'defects_note': None},
        'test': {'tested_at': T1, 'machine': None,
                 'loading_rate_mpa_s': 0.6, 'max_load_kn': 298.4,
                 'cross_section_area_mm2': 7791.0,
                 'failure_type': 'satisfactory', 'failure_type_code': None,
                 'age_at_test_days': 7},
        'result': {'fc_core_mpa': 38.3, 'ld_correction_applied': False,
                   'fc_is_cyl_mpa': 38.3, 'fc_is_cube_mpa': None,
                   'conversion_basis': 'EN 13791:2019 + DIN EN 13791/A20:'
                                       '2022-04'},
        'deviations': None,
    },
    'destructive': True,
    'attachments': [{
        'index': 0, 'name': 'Pruefbericht_2026-117.pdf',
        'media_type': 'application/pdf', 'size': 812345, 'sha256': 'a' * 64,
        'uploaded_by_user_id': USER_ID, 'uploaded_at': T1, 'removed': None,
    }],
    'notes': None,
    'status': 'published',
    'status_changed_by_user_id': MODERATOR_ID,
    'status_changed_at': T1,
    'verification': {
        'state': 'accredited',
        'by': {'kind': 'user', 'user_id': MODERATOR_ID, 'name': None,
               'organization': None, 'role': None},
        'at': T1,
        'note': 'D-PL-12345-01-00 scope checked in the DAkkS register',
    },
    'supersedes': None,
    'superseded_by': None,
    'etag': 'def',
    'created': T1,
    'lastmodified': T1,
}

_DATASET = {
    '_id': 'dbu_zirkus',
    'name': 'ZirKuS',
    'description': 'Pedestrian bridge elements, Lichtwiese campus',
    'visibility': 'members',
    'members': [
        {'user_id': USER_ID, 'roles': ['contributor'],
         'added_by_user_id': MODERATOR_ID, 'added_at': T0},
        {'user_id': MODERATOR_ID, 'roles': ['contributor', 'moderator'],
         'added_by_user_id': MODERATOR_ID, 'added_at': T0},
    ],
    'created': T0,
    'lastmodified': T0,
}

_MATERIAL = {'_id': 'mineral_composite',
             'label': 'Mineral composite (acrylic solid surface)',
             'group': 'polymer', 'default_class': '17 02 03',
             'uniclass': None, 'notes': None}

_PURGE_STUB = {'_id': IDENTITY_ID, 'purged_at': T1,
               'purged_by_user_id': MODERATOR_ID, 'reason': 'test data'}


def identity():
    return copy.deepcopy(_IDENTITY)


def snapshot():
    return copy.deepcopy(_SNAPSHOT)


def robot_capture():
    return copy.deepcopy(_ROBOT_CAPTURE)


def evidence():
    return copy.deepcopy(_EVIDENCE)


def dataset():
    return copy.deepcopy(_DATASET)


def material():
    return copy.deepcopy(_MATERIAL)


def purge_stub():
    return copy.deepcopy(_PURGE_STUB)
