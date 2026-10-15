"""Hand-written rows in the shape parse.py produces: one invented donor building with a wall, a
hollow-core slab and their reinforcement. Names, places and numbers are made up; nothing here comes from
the Zenodo files."""

from __future__ import annotations

import struct
from pathlib import Path

WALL_FILE = 'Wall Data - Dutch.xlsx'
HCS_FILE = 'HCS Data - Finnish.xlsx'


def building(pilot='Dutch', year=1987, building_id='B_TEST_1'):
    return {
        '_pilot': pilot, 'wings': [],
        'BUILDING DATA / Building ID': building_id,
        'BUILDING DATA / Name': 'Sample Hall',
        'BUILDING DATA / Building Type': 'office',
        'BUILDING DATA / City': 'Sampletown',
        'BUILDING DATA / Country': 'NL',
        'BUILDING DATA / Latitude': 52.0,
        'BUILDING DATA / Longitude': 5.9,
        'BUILDING DATA / Construction Year': year,
        'BUILDING DATA / Deconstruction Year': 2023,
        'BUILDING DATA / Deconstruction Company': 'Demolition Example Ltd',
        'BUILDING DATA / Exposure Class': 'XC1',
    }


def wall_element(eid='W1', product='P_WALL', reinf='R_WALL', **extra):
    rec = {'_row': 5, 'Wall ID': eid, 'Building ID': 'B_TEST_1', 'Product ID': product,
           'Reinf ID': reinf, 'Wall Type': 'FACADE_WALL', 'Wing': 'A', 'Floor Num': 1,
           'Orientation': 'N', 'Grid Position': 'G1', 'Status': 'Active', 'Has Tests': False,
           'Has Damage': False, 'Intervention Class': 'None', 'Storage Lat': 50.1,
           'Storage Long': 8.1, 'Notes': 'stored in the yard'}
    rec.update(extra)
    return rec


def wall_product(product='P_WALL', reinf='R_WALL', cls='NL_B52.5', notes=None, **extra):
    rec = {'_row': 4, 'Product ID': product, 'Reinf ID': reinf, 'Concrete Strength Class': cls}
    if notes is not None:
        rec['Notes'] = notes
    rec.update(extra)
    return rec


def layer_row(plane='XZ', h1=100, h2=2900, v1=200, v2=200, position=30, count=3, spacing=45,
              diameter=12, grade='NL_FeB500', reinf='R_WALL', cover=(20, 25, 15), **extra):
    """One longitudinal layer, headers as in the pilot files (``h1`` / ``v1``)."""
    rec = {'_row': 6, 'Reinf ID': reinf, 'ELEMENT ZONING / Zone ID': 'Z1', 'ELEMENT ZONING / Layer ID': 'L1',
           'ELEMENT ZONING / Zone Plane': plane,
           'FRONT CROSS-SECTION / Layer Coord [Start] h1': h1,
           'FRONT CROSS-SECTION / Layer Coord [End] h2': h2,
           'FRONT CROSS-SECTION / Layer Coord [Start] v1': v1,
           'FRONT CROSS-SECTION / Layer Coord [End] v2': v2,
           'BAR PROPERTIES / Layer Position [Start]': position,
           'BAR PROPERTIES / Num. Bars': count, 'BAR PROPERTIES / Bar Spacing (mm)': spacing,
           'BAR PROPERTIES / Bar Diameter (mm)': diameter, 'BAR PROPERTIES / Steel Grade': grade,
           'CONCRETE COVER / X': cover[0], 'CONCRETE COVER / Z': cover[1], 'CONCRETE COVER / Y': cover[2],
           'CONCRETE COVER / Confidence (+- mm)': 5}
    rec.update(extra)
    return rec


def stirrup_row(shape=((20, 20), (2980, 20), (2980, 2480), (20, 2480)), plane='XZ', axis='y',
                start=30, end=150, spacing=40, description='Closed stirrup', diameter=8,
                grade='NL_FeB500', reinf='R_WALL'):
    """A transverse record in the grouped form of parse.py: scalars from the first row, the shape as
    column lists."""
    a, b = plane[0], plane[1]
    return {'_row': 7, 'Reinf ID': reinf, 'Zone ID': 'Z2', 'Description': description,
            'Diameter (mm)': diameter, 'Spacing (mm)': spacing, 'Bent Plane': plane,
            f'Define Shape [list] / {a.upper()} []': [p[0] for p in shape],
            f'Define Shape [list] / {b.upper()} []': [p[1] for p in shape],
            'Reinforced Span / Axis': axis, 'Reinforced Span / Start': start,
            'Reinforced Span / End': end, 'Steel Grade': grade}


def strand_row(y=100, z=40, diameter=12.5, grade='FI_FeP1860', reinf='R_HCS'):
    return {'_row': 8, 'Reinf ID': reinf, 'Strand ID': 'S1', 'Coordinates / x': y,
            'Coordinates / y': z, 'Num Wires': 7, 'Strand Diameter (mm)': diameter, 'Steel Grade': grade}


def mesh_entry(file, product, bbox=(3000.0, 150.0, 2500.0), origin=(0.0, 0.0, 0.0), notes=None):
    return {'file': file, 'pilot': 'Dutch', 'type': 'Wall', 'product': product,
            'ply': f'meshes/Dutch/Wall/{product}.ply', 'watertight': True, 'volume_m3': 1.0,
            'faces': 12, 'bbox_mm': list(bbox), 'origin_mm': list(origin), 'notes': notes or []}


def wall_file(elements, products, longs=(), transv=()):
    return {'file': WALL_FILE, 'type': 'Wall', 'pilot': 'Dutch', 'sheets': {
        'elements': {'records': list(elements)}, 'Geometry': {'records': list(products)},
        'Long Reinf': {'records': list(longs)}, 'Transv Reinf': {'records': list(transv)}}}


def parsed_and_geometry(elements=None, products=None, longs=None, transv=None, bbox=(3000.0, 150.0, 2500.0)):
    """A parsed.json / geometry.json pair for one wall file, as plan.Planner takes them."""
    products = products if products is not None else [wall_product()]
    parsed = {'buildings': [building()], 'element_files': [wall_file(
        elements if elements is not None else [wall_element()], products,
        longs if longs is not None else [layer_row()],
        transv if transv is not None else [stirrup_row()])]}
    geometry = {'products': [mesh_entry(WALL_FILE, p['Product ID'], bbox) for p in products]}
    return parsed, geometry


def write_ply(path: Path, vertices, faces) -> None:
    """A binary little-endian PLY in the layout trimesh writes (float vertices, ``uchar int`` faces)."""
    header = ('ply\nformat binary_little_endian 1.0\n'
              f'element vertex {len(vertices)}\nproperty float x\nproperty float y\nproperty float z\n'
              f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
    body = b''.join(struct.pack('<3f', *v) for v in vertices)
    body += b''.join(struct.pack('<B3i', 3, *f) for f in faces)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header.encode('ascii') + body)


def write_box(path: Path, size=(3000.0, 150.0, 2500.0)) -> None:
    x, y, z = size
    vertices = [(0, 0, 0), (x, 0, 0), (x, y, 0), (0, y, 0), (0, 0, z), (x, 0, z), (x, y, z), (0, y, z)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    write_ply(path, vertices, faces)
