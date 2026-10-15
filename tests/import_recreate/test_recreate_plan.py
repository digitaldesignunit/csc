"""plan.py: the records the import writes, from hand-written rows (decision 8.145)."""

from __future__ import annotations

import re
import uuid

import pytest

import recreate_samples as s


def planner(plan_module, **kw):
    parsed, geometry = s.parsed_and_geometry(**kw)
    p = plan_module.Planner(parsed, geometry)
    p.run()
    return p


def evidence(item, method=None, what=None):
    out = [r for r in item['evidence'] if method is None or r['method'] == method]
    if what:
        out = [r for r in out if r['payload']['document']['reference'].endswith(':' + what)]
    return out


# BARS -------------------------------------------------------------------------
def test_layer_bars_are_spaced_along_the_third_axis(plan_module):
    """XZ plane: the first bar runs in x and z, the others follow along y at the bar spacing."""
    skips = []
    bars = plan_module.long_bars([s.layer_row()], skips)
    assert skips == []
    assert [b['points'] for b in bars] == [
        [[100.0, 30.0, 200.0], [2900.0, 30.0, 200.0]],
        [[100.0, 75.0, 200.0], [2900.0, 75.0, 200.0]],
        [[100.0, 120.0, 200.0], [2900.0, 120.0, 200.0]]]
    assert {b['diameter_mm'] for b in bars} == {12.0}
    assert {b['spec'] for b in bars} == {'FeB500'}          # the pilot prefix of the grade is dropped


def test_the_zone_plane_decides_which_axis_is_the_third(plan_module):
    yz = plan_module.long_bars([s.layer_row(plane='YZ', h1=10, h2=90, v1=300, v2=300, position=500,
                                            count=2, spacing=100)], [])
    assert yz[0]['points'] == [[500.0, 10.0, 300.0], [500.0, 90.0, 300.0]]       # third axis: x
    assert yz[1]['points'][0][0] == 600.0
    xy = plan_module.long_bars([s.layer_row(plane='XY', h1=0, h2=1000, v1=50, v2=50, position=700,
                                            count=1, spacing=0)], [])
    assert xy[0]['points'] == [[0.0, 50.0, 700.0], [1000.0, 50.0, 700.0]]        # third axis: z


def test_an_incomplete_layer_row_is_skipped_and_said(plan_module):
    skips = []
    bars = plan_module.long_bars([s.layer_row(h1=None)], skips)
    assert bars == [] and len(skips) == 1 and 'incomplete row' in skips[0]


def test_a_closed_stirrup_is_closed_and_repeated_along_its_span(plan_module):
    bars = plan_module.transverse_bars([s.stirrup_row()], [])
    assert [b['points'][0][1] for b in bars] == [30.0, 70.0, 110.0, 150.0]       # along y, start to end
    first = bars[0]['points']
    assert first[0] == first[-1] and len(first) == 5                             # closed
    assert all(p[1] == 30.0 for p in first)                                      # in the plane y = 30
    assert [p[0] for p in first][:4] == [20.0, 2980.0, 2980.0, 20.0]             # shape x
    assert [p[2] for p in first][:4] == [20.0, 20.0, 2480.0, 2480.0]             # shape z
    open_one = plan_module.transverse_bars([s.stirrup_row(description='Open link')], [])
    assert len(open_one[0]['points']) == 4                                       # not closed


def test_strands_run_along_x_at_their_section_coordinates(plan_module):
    bars = plan_module.strand_bars([s.strand_row(y=100, z=40), s.strand_row(y=220, z=40)], 6000.0)
    assert [b['points'] for b in bars] == [[[0.0, 100.0, 40.0], [6000.0, 100.0, 40.0]],
                                           [[0.0, 220.0, 40.0], [6000.0, 220.0, 40.0]]]
    assert bars[0]['diameter_mm'] == 12.5 and bars[0]['spec'] == 'FeP1860'


def test_mirrored_bars_are_reflected_about_the_middle_of_the_length(plan_module):
    bars = plan_module.long_bars([s.layer_row(count=1)], [])
    plan_module.mirror(bars, 0.0, 3000.0)
    assert bars[0]['points'] == [[2900.0, 30.0, 200.0], [100.0, 30.0, 200.0]]


def test_a_mirrored_product_mirrors_its_bars_with_the_mesh(plan_module):
    p = planner(plan_module, products=[s.wall_product(**{'Mirrored': True})],
                longs=[s.layer_row(count=1)], transv=[])
    layout = evidence(p.items[0], 'reinforcement_layout')[0]
    assert layout['payload']['bars'][0]['points'] == [[2900.0, 30.0, 200.0], [100.0, 30.0, 200.0]]
    assert 'Mirrored with the element' in layout['payload']['accuracy_note']
    assert p.items[0]['identity']['attributes']['recreate']['mirrored'] is True


def test_bars_outside_the_element_are_dropped_and_counted_in_the_accuracy_note(plan_module):
    # the layer lies at z = 200; a second one at z = 4000 is above the 2500 mm element
    p = planner(plan_module, longs=[s.layer_row(count=2), s.layer_row(v1=4000, v2=4000, count=2)],
                transv=[])
    layout = evidence(p.items[0], 'reinforcement_layout')[0]
    assert len(layout['payload']['bars']) == 2
    note = layout['payload']['accuracy_note']
    assert '2 bar(s) of the published type lie outside this element' in note
    assert 'Hooks, hairpins' in note and '+-5 mm' in note
    assert p.layout_checks['bars'] == 4 and p.layout_checks['dropped'] == 2
    assert 'dropped in P_WALL' in p.layout_checks
    # the internal helper fields never reach the record
    assert all(not k.startswith('_') for b in layout['payload']['bars'] for k in b)


def test_an_element_without_reinforcement_rows_gets_no_layout(plan_module):
    p = planner(plan_module, longs=[], transv=[])
    assert evidence(p.items[0], 'reinforcement_layout') == []


# ARCHIVAL VALUES ----------------------------------------------------------------
def test_a_concrete_class_keeps_its_own_name_without_an_invented_equivalent(plan_module):
    p = planner(plan_module, products=[s.wall_product(cls='NL_B52.5')])
    record = evidence(p.items[0], what='concrete_class')[0]
    assert record['summary']['value'] == 'B52.5'
    assert 'interpretation' not in record['payload']['claim']
    assert record['payload']['claim']['text'] == 'Concrete Strength Class: NL_B52.5'


def test_k30_becomes_c25_30_only_through_the_note_of_the_dataset(plan_module):
    note = 'K30 is equivalent to EN 206-1 class C25/30 (approximately).'
    with_note = planner(plan_module, products=[s.wall_product(cls='FI_K30', notes=note)]).items[0]
    record = evidence(with_note, what='concrete_class')[0]
    assert record['summary']['value'] == 'C25/30'
    assert 'equivalent to EN 206-1 C25/30 (note of the dataset)' in \
        record['payload']['claim']['interpretation']
    without = planner(plan_module, products=[s.wall_product(cls='FI_K30', notes='no equivalence given')]
                      ).items[0]
    assert evidence(without, what='concrete_class')[0]['summary']['value'] == 'K30'


@pytest.mark.parametrize('note, value', [
    ('Mean compression strength = 23,5 N/mm2 (exterior walls).', 23.5),
    ('Mean compression strength = 40.8 N/mm2.', 40.8),
    ('Cores were drilled. The average compressive strength of the slabs was 80,6 MPa (std 4,8).', 80.6),
])
def test_the_mean_strength_is_read_from_the_note(plan_module, note, value):
    p = planner(plan_module, products=[s.wall_product(notes=note)])
    record = evidence(p.items[0], what='compressive_strength_in_situ')[0]
    assert record['summary']['value'] == value and record['summary']['unit'] == 'MPa'
    claim = record['payload']['claim']
    assert re.search(r'23,5|40\.8|80,6', claim['text'])           # the sentence of the dataset, quoted
    assert 'mean of the tests' in claim['interpretation']


def test_a_note_without_a_mean_gives_no_strength_record(plan_module):
    p = planner(plan_module, products=[s.wall_product(notes='Some other remark about 12 mm cores.')])
    assert evidence(p.items[0], what='compressive_strength_in_situ') == []


def test_rebar_exposure_and_cover_records(plan_module):
    item = planner(plan_module).items[0]
    assert evidence(item, what='rebar_spec')[0]['summary']['value'] == 'FeB500'
    assert evidence(item, what='exposure_class')[0]['summary']['value'] == 'XC1'
    cover = evidence(item, what='cover_depth')[0]
    assert cover['summary']['value'] == 15 and cover['summary']['unit'] == 'mm'   # the smallest layer cover
    # every archival record cites the dataset itself
    for record in evidence(item, 'archival_document'):
        doc = record['payload']['document']
        assert doc['url'] == 'https://doi.org/10.5281/zenodo.16809738' and doc['kind'] == 'report'
        assert doc['retrieved_at'] == '2026-10-15'


# IDENTITY ------------------------------------------------------------------------
def test_ids_are_uuid5_of_the_element_and_stable(plan_module):
    a = planner(plan_module).items[0]
    b = planner(plan_module).items[0]
    expected = str(uuid.uuid5(plan_module.NAMESPACE, 'csc-import/recreate:NL:W1'))
    assert a['identity']['id'] == b['identity']['id'] == expected == plan_module.uid('recreate:NL:W1')
    assert a['key'] == 'recreate:NL:W1'
    # pinned: a change of the namespace or the key would orphan every imported component
    assert plan_module.uid('recreate:NL:W1') == '0aed26ee-e75d-5857-80d0-3f6c59430649'
    assert plan_module.uid('recreate:NL:W2') != plan_module.uid('recreate:DE:W1')


def test_the_storage_location_reads_the_misspelt_header_of_the_dutch_hcs_sheet(plan_module):
    el = s.wall_element()
    el['Storgage Lat'] = el.pop('Storage Lat')
    snapshot = planner(plan_module, elements=[el]).items[0]['snapshot']
    assert snapshot['location'] == {'lat': 50.1, 'lon': 8.1}


def test_the_reinforcement_id_is_found_under_both_spellings(plan_module):
    row = s.layer_row()
    row['Reinf_ID'] = row.pop('Reinf ID')
    assert plan_module.get(row, 'Reinf ID', 'Reinf_ID') == 'R_WALL'
    p = planner(plan_module, longs=[row], transv=[])
    assert len(evidence(p.items[0], 'reinforcement_layout')[0]['payload']['bars']) == 3


def test_the_origin_is_a_deinstallation_of_the_donor_building(plan_module):
    item = planner(plan_module).items[0]
    origin = item['identity']['origin']
    assert origin['kind'] == 'deinstallation' and origin['at'] == '2023-01-01T00:00:00Z'
    assert origin['at_precision'] == 'year'
    work = origin['construction_work']
    assert work['identifier'] == 'B_TEST_1' and work['year_built'] == 1987
    assert work['construction_method'] == 'prefabricated' and work['use'] == 'office'
    assert origin['place']['location'] == {'lat': 52.0, 'lon': 5.9}
    assert origin['position_in_work'] == 'wing A, floor 1, grid G1, facing N'
    assert origin['performed_by'] == [{'kind': 'organization', 'organization': 'Demolition Example Ltd'}]
    assert item['identity']['is_public'] is False and item['dataset'] == 'recreate_nl'
    assert item['snapshot']['effective_from'] == '2023-01-01T00:00:00Z'
    assert item['snapshot']['capture']['method'] == 'manual'


def test_an_element_without_a_mesh_is_skipped_and_said(plan_module):
    p = planner(plan_module, elements=[s.wall_element(product='P_MISSING')])
    assert p.items == [] and 'has no geometry' in p.skips[0]['reason']


def test_the_attribution_is_in_every_dataset_description(plan_module):
    parsed, geometry = s.parsed_and_geometry()
    entries = plan_module.Planner(parsed, geometry).dataset_entries()
    assert [e['id'] for e in entries] == ['recreate_nl']
    text = entries[0]['description']
    for part in ('958200', 'zenodo.16809738', 'CC BY 4.0', 'not the present state'):
        assert part in text


def test_the_plan_is_ascii_only(plan_module):
    item = planner(plan_module, elements=[s.wall_element(**{'Notes': 'Sto' + chr(0xDF) + ' ' + chr(0xE7)})]
                   ).items[0]
    assert item['snapshot']['notes'].startswith('Sto')            # the data's own note is kept verbatim
    assert plan_module.ascii_text('Gr' + chr(0xFC) + chr(0xDF) + 'e ' + chr(0xE7)) == 'Gruesse c'


# THE BODIES THE BACKEND TAKES ----------------------------------------------------
def test_one_item_validates_against_the_backend_models(plan_module, script_loader, tmp_path):
    """As ``run.py --dry-run`` does: the identity body, the draft snapshot body and every evidence record."""
    pytest.importorskip('numpy')
    pytest.importorskip('requests')
    run = script_loader('run')
    item = planner(plan_module).items[0]
    s.write_box(tmp_path / item['mesh_ply'])
    assert run.validate(tmp_path, [item]) == []
    # and the check does refuse a body the models refuse
    bad = {**item, 'identity': {**item['identity'], 'original_function': 'IfcNotAThing'}}
    problems = run.validate(tmp_path, [bad])
    assert problems and problems[0][0] == item['key']
