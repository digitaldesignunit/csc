"""Evidence create bodies shared by the evidence route tests (spec A.1 - A.4)."""

from __future__ import annotations

import copy

T = '2026-02-27T14:30:00Z'
LAB = {'kind': 'organization', 'organization': 'Pruefstelle Muster GmbH',
       'role': 'laboratory',
       'accreditation': {'scheme': 'iso_17025', 'id': 'D-PL-12345-01-00',
                         'body': 'DAkkS',
                         'scope': ['EN 12504-1', 'EN 12390-3'],
                         'valid_until': None}}


def person(user_id, role='operator'):
    return {'kind': 'user', 'user_id': user_id, 'role': role}


def rebound(readings=None, **over):
    payload = {
        'instrument': {'hammer_type': 'N', 'manufacturer': 'Proceq'},
        'test_area': {'label': 'TA-1', 'surface_preparation': 'ground',
                      'surface_condition': 'dry'},
        'impact_direction': 'horizontal',
        'readings': readings or [44, 42, 41, 45, 43, 42, 40, 44, 43],
        'reading_unit': '1',
    }
    payload.update(over)
    return payload


def rebound_body(observed_at=T, readings=None, **over):
    body = {'method': 'rebound_hammer', 'observed_at': observed_at,
            'position': {'kind': 'none', 'description': 'north face'},
            'payload': rebound(readings)}
    body.update(over)
    return body


def core(cored_at='2026-02-20T11:00:00Z', tested_at=T, paired=None, **over):
    payload = {
        'sampling': {'cored_at': cored_at, 'drill_diameter_mm': 100,
                     'drilling_method': 'wet',
                     'paired_rebound_id': paired},
        'specimen': {'label': 'C-03', 'measured_diameter_mm': 99.6,
                     'length_prepared_mm': 199.2,
                     'end_preparation': 'ground', 'storage': 'water'},
        'test': {'tested_at': tested_at, 'max_load_kn': 298.4,
                 'failure_type': 'satisfactory'},
    }
    payload.update(over)
    return payload


def core_body(paired=None, performed_by=None, cored_at='2026-02-20T11:00:00Z',
              tested_at=T, **over):
    body = {'method': 'core_compression',
            'position': {'kind': 'none', 'description': 'drill spot 3'},
            'performed_by': performed_by if performed_by is not None
            else [LAB],
            'payload': core(cored_at=cored_at, tested_at=tested_at,
                            paired=paired)}
    body.update(over)
    return body


def claim_body(quantity='compressive_strength', rng=(18, 28), unit='MPa',
               observed_at='2026-03-01T00:00:00Z', **over):
    body = {'method': 'archival_document', 'observed_at': observed_at,
            'payload': {'document': {'title': 'Statik 1968',
                                     'date': '1968-03', 'kind': 'spec'},
                        'claim': {'text': 'B225'}},
            'summary': {'quantity': quantity, 'range': list(rng),
                        'unit': unit, 'kind': 'claimed'}}
    body.update(over)
    return body


def visual_body(quantity='spalling', value=2, observed_at=T, **over):
    body = {'method': 'visual_inspection', 'observed_at': observed_at,
            'payload': {'observations': [
                {'quantity': quantity, 'value': value, 'note': 'north'}]}}
    body.update(over)
    return body


def layout_body(snapshot_id, observed_at=T, **over):
    body = {'method': 'reinforcement_layout', 'observed_at': observed_at,
            'position': {'kind': 'none', 'snapshot_id': snapshot_id,
                         'description': 'bar centrelines'},
            'payload': {'basis': 'scan',
                        'instrument': {'kind': 'covermeter'},
                        'bars': [{'spec': 'BSt III', 'diameter_mm': 12,
                                  'points': [[0, 0, 20], [6000, 0, 20]]}]}}
    body.update(over)
    return body


def clone(body, **over):
    out = copy.deepcopy(body)
    out.update(over)
    return out


# files ------------------------------------------------------------------------
PDF = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n'


def png_bytes(size=(64, 48)):
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', size, (200, 30, 30)).save(buffer, format='PNG')
    return buffer.getvalue()
