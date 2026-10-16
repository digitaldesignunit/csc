"""parse.py: the sheets as published, read by header text (decision 8.145). Workbooks are built in memory
from hand-written rows."""

from __future__ import annotations

import pytest

openpyxl = pytest.importorskip('openpyxl')


def sheet(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    return ws


def test_header_keys_run_across_three_rows_and_sections_carry_to_the_right(parse_module):
    ws = sheet([
        ['Product ID', 'GENERAL', None, 'Mirrored'],            # section (merged over two columns)
        [None, 'FRONT CROSS-SECTION [list]', None, None],       # field, carried over its sub-columns
        [None, 'X', 'Z', None],                                 # sub-field
        ['P_1', 100, 200, True],
    ])
    keys, rows = parse_module.table(ws)
    assert keys == ['Product ID', 'GENERAL / FRONT CROSS-SECTION [list] / X',
                    'GENERAL / FRONT CROSS-SECTION [list] / Z', 'Mirrored']
    assert [r for _, r in rows] == [['P_1', 100, 200, True]]


def test_a_section_does_not_leak_into_the_next_one(parse_module):
    ws = sheet([
        ['Reinf ID', 'CONCRETE COVER', None, 'BAR PROPERTIES', None],
        [None, 'X', 'Z', 'Num. Bars', 'Bar Diameter (mm)'],
        ['R_1', 20, 25, 4, 12],
    ])
    keys, _ = parse_module.table(ws)
    assert keys == ['Reinf ID', 'CONCRETE COVER / X', 'CONCRETE COVER / Z',
                    'BAR PROPERTIES / Num. Bars', 'BAR PROPERTIES / Bar Diameter (mm)']


def test_special_characters_of_the_headers_are_written_plain(parse_module):
    plus_minus, theta, c_cedilla = chr(0xB1), chr(0x3B8), chr(0xE7)
    assert parse_module.norm(f'Confidence ({plus_minus} mm)') == 'Confidence (+- mm)'
    assert parse_module.norm(f'Bent Angle, {theta} (deg)') == 'Bent Angle, theta (deg)'
    assert parse_module.norm(f'Fa{c_cedilla}ade   Layer\n') == 'Facade Layer'


def test_a_grouped_record_has_its_scalars_and_one_list_per_column(parse_module):
    ws = sheet([
        ['Product ID', 'Height (mm)', 'X', 'Z'],
        ['P_01', 150, 0, 0],
        [None, None, 4000, 0],
        [None, None, 4000, 2500],
        ['P_02', 160, 0, 0],
        [None, None, 1000, 0],
    ])
    keys, records = parse_module.grouped(ws, 'Product ID')
    assert len(records) == 2
    first, second = records
    assert first['Product ID'] == 'P_01' and first['Height (mm)'] == 150
    assert first['X'] == 0 and first['X []'] == [0, 4000, 4000]
    assert first['Z []'] == [0, 0, 2500]
    assert 'Height (mm) []' not in first                         # a scalar stays a scalar
    assert second['Product ID'] == 'P_02' and second['X []'] == [0, 1000]


def test_a_flat_record_skips_empty_cells_and_remembers_its_row(parse_module):
    ws = sheet([
        ['Wall ID', 'Building ID', 'Notes'],
        ['W_1', 'B_1', None],
        [None, None, None],                                      # an empty row is not a record
        ['W_2', 'B_1', 'a note'],
    ])
    keys, records = parse_module.records(ws)
    assert [r['Wall ID'] for r in records] == ['W_1', 'W_2']
    assert 'Notes' not in records[0] and records[1]['Notes'] == 'a note'
    assert [r['_row'] for r in records] == [2, 4]


def test_booleans_dates_and_blanks_are_read_as_values(parse_module):
    import datetime
    assert parse_module.value('TRUE') is True and parse_module.value(' false ') is False
    assert parse_module.value('  ') is None and parse_module.value(' text ') == 'text'
    assert parse_module.value(datetime.date(2023, 5, 1)) == '2023-05-01'
    assert parse_module.value(3.5) == 3.5


def test_the_alias_headers_of_the_pilot_files_stay_what_they_are(parse_module):
    """The parser does not rename: `Reinf_ID` and `Reinf ID`, `Radius (mm)` and `Radius/ Bevel (mm)`,
    `Storgage Lat` stay as written; the planner and the geometry accept every spelling."""
    ws = sheet([
        ['Reinf_ID', 'Storgage Lat', 'GENERAL', None],
        [None, None, 'Radius/ Bevel (mm)', 'Radius (mm)'],
        ['R_1', 50.1, 0, 0],
    ])
    keys, records = parse_module.records(ws)
    assert keys == ['Reinf_ID', 'Storgage Lat', 'GENERAL / Radius/ Bevel (mm)', 'GENERAL / Radius (mm)']
    assert records[0]['Reinf_ID'] == 'R_1' and records[0]['Storgage Lat'] == 50.1


def test_site_rows_below_a_building_are_its_wings(parse_module):
    ws = sheet([
        ['BUILDING DATA', None, 'STRUCTURAL FRAME', None],
        ['Building ID', 'Name', 'Wing ID', 'Storeys'],
        ['B_1', 'Sample Hall', 'A', 3],
        [None, None, 'B', 5],
        ['B_2', 'Other Hall', 'A', 2],
    ])
    keys, buildings = parse_module.site(ws)
    assert [b['BUILDING DATA / Building ID'] for b in buildings] == ['B_1', 'B_2']
    assert buildings[0]['wings'] == [{'Wing ID': 'A', 'Storeys': 3}, {'Wing ID': 'B', 'Storeys': 5}]
    assert buildings[1]['wings'] == [{'Wing ID': 'A', 'Storeys': 2}]
