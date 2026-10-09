"""Pure mapping functions of the 0.6 migration (spec section 8.1)."""

from __future__ import annotations

import pytest

from apps.catalog.documents import Capture, Evidence, Exit, Origin, Proxy
from apps.catalog.migration06 import mappings as m
from apps.catalog.migration06.mappings import MigrationAbort

ROSSKOPF = 'Rosskopf + Partner AG, Bahnhofstra\u00dfe 16, 09573 Augustusburg'


def _identity(**fields):
    doc = {'_id': 'i1', 'dataset': 'mineral_composite_panels', 'type': 'panel',
           'material': 'corian', 'salvage_source': None, 'salvaged_at': None,
           'parent_identities': None, 'consumed_at': None, 'attributes': {},
           'manufactured_at': None, 'manufactured_precision': 'unknown'}
    doc.update(fields)
    return doc


def _snapshot(**fields):
    doc = {'_id': 's1', 'identity_id': 'i1', 'version': 0,
           'created': '2026-05-19T14:56:28.570893Z', 'added_by_user_id': 'u1',
           'added_by_username': 'ddu', 'geometry': {}}
    doc.update(fields)
    return doc


# small maps ------------------------------------------------------------------
def test_type_and_material_maps():
    assert m.original_function_for(_identity(type='rubble')) == 'CscDebris'
    with pytest.raises(MigrationAbort):
        m.original_function_for(_identity(type='sculpture'))
    assert m.material_for(_identity()) == {
        'material': 'mineral_composite', 'trade_name': 'Corian',
        'material_class': '17 02 03', 'material_class_source': 'derived'}
    assert m.material_for(_identity(material='brick'))['material'] == 'fired_clay'
    migrated = _identity(material='concrete', trade_name=None)
    assert m.material_for(migrated)['material_class'] == '17 01 01'
    with pytest.raises(MigrationAbort):
        m.material_for(_identity(material='unobtainium'))
    assert len(m.material_documents()) == 32


def test_dataset_documents():
    doc, known = m.dataset_document('dbu_zirkus', '2026-09-30T00:00:00Z')
    assert known and doc['visibility'] == 'members' and doc['members'] == []
    doc, known = m.dataset_document('new_project', '2026-09-30T00:00:00Z')
    assert not known and doc['visibility'] == 'members'
    assert doc['name'] == 'New project'


# origin (step 10) ------------------------------------------------------------
def test_origin_rosskopf_zirkus_exfeld_by_hand():
    rosskopf = m.origin_for(_identity(salvage_source=ROSSKOPF,
                                      salvaged_at='2022-10-26T00:00:00.000000Z'))
    assert rosskopf['kind'] == 'offcut' and rosskopf['at_precision'] == 'day'
    zirkus = m.origin_for(_identity(dataset='dbu_zirkus'))
    assert zirkus['kind'] == 'deinstallation'
    assert zirkus['at'] == '2024-07-24T00:00:00Z'
    exfeld = m.origin_for(_identity(salvage_source='ExFeld Architektur, TU Darmstadt',
                                    salvaged_at='2026-05-19T00:00:00Z'))
    assert (exfeld['kind'], exfeld['at'], exfeld['place']['name']) == \
        ('unknown', '2026-05-19T00:00:00Z', 'ExFeld')
    by_hand = m.origin_for(_identity(salvage_source='Measured by Hand, Parent not '
                                                    'found (ID:69da)'))
    assert by_hand['kind'] == 'unknown' and by_hand['notes'].startswith('Measured')
    for origin in (rosskopf, zirkus, exfeld, by_hand):
        Origin.model_validate(origin)


def test_origin_rules_by_dataset_and_lineage():
    assert m.origin_for(_identity(dataset='beyond_debris'))['kind'] == 'demolition'
    assert m.origin_for(_identity(dataset='spa_example_data'))['kind'] == 'unknown'
    assert m.origin_for(_identity(dataset='ddu_aggregations'))['kind'] == 'offcut'
    child = _identity(dataset='ddu_aggregations', parent_identities=['p'])
    parent_origin = m.origin_for(_identity(salvage_source=ROSSKOPF))
    assert m.origin_for(child, [parent_origin]) == parent_origin
    with pytest.raises(MigrationAbort):              # no rule, no parent origin
        m.origin_for(child)


def test_origin_guards():
    with pytest.raises(MigrationAbort):
        m.origin_for(_identity(salvage_source='Somewhere else'))
    with pytest.raises(MigrationAbort):              # an offcut on another date
        m.origin_for(_identity(salvage_source=ROSSKOPF,
                               salvaged_at='2023-01-01T00:00:00Z'))
    with pytest.raises(MigrationAbort):
        m.origin_for(_identity(dataset='unknown_project'))


# effective_from (step 1, 8.10) -----------------------------------------------
def test_v0_effective_from_rules():
    snap = _snapshot()
    assert m.v0_effective_from(_identity(salvage_source=ROSSKOPF), snap) == \
        ('2022-10-26T00:00:00Z', 'day')
    child = _identity(salvage_source=ROSSKOPF, parent_identities=['p'])
    assert m.v0_effective_from(child, snap) == (snap['created'], 'exact')
    scan = _identity(dataset='ddu_build_with_debris', attributes={
        '3d_scan_metadata': {'created_utc': '2025-10-30T00:26:28.345536Z'}})
    assert m.v0_effective_from(scan, snap) == ('2025-10-30T00:26:28Z', 'exact')
    assert m.v0_effective_from(_identity(dataset='spa_example_data'), snap) == \
        (snap['created'], 'exact')


def test_effective_from_is_monotonic_or_aborts():
    identity = _identity(salvage_source=ROSSKOPF)
    v0 = _snapshot()
    v1 = _snapshot(_id='s2', version=1, created='2026-06-09T07:21:10Z')
    values = m.effective_from_all(identity, [v1, v0])
    assert values == {'s1': ('2022-10-26T00:00:00Z', 'day'),
                      's2': ('2026-06-09T07:21:10Z', 'exact')}
    early = _snapshot(_id='s2', version=1, created='2020-01-01T00:00:00Z')
    with pytest.raises(MigrationAbort, match='monotonic'):
        m.effective_from_all(identity, [v0, early])


# capture (steps 6, 6c) -------------------------------------------------------
def test_capture_from_attributes():
    scan = _identity(attributes={'3d_scan_metadata': {
        'created_utc': '2025-10-30T00:26:28.345536Z', 'run_dir': 'C:\\x'},
        'primitive': 'box', 'scan': '28'})
    capture = m.capture_from_attributes(scan, None)
    assert capture['method'] == 'photogrammetry'
    assert capture['captured_at'] == '2025-10-30T00:26:28Z'
    assert capture['notes'] == 'scan 28'
    Capture.model_validate(capture)
    assert m.remaining_attributes(dict(scan, attributes={**scan['attributes'],
                                                         'keep': 1})) == {'keep': 1}
    assert m.capture_from_attributes(_identity(), None) is None


def test_markers_split_by_order_and_height():
    points = [[-120, 0.6, -0.5], [120, 0.6, -0.5], [0, 120, 0.3], [0, -120, 0.1],
              [-54.8, 70.9, 619.1]]
    markers = m.split_markers('s1', points)
    assert [(x['label'], x['role']) for x in markers] == [
        ('blue_1', 'rig'), ('blue_2', 'rig'), ('blue_3', 'rig'), ('blue_4', 'rig'),
        ('green_1', 'component')]
    with pytest.raises(MigrationAbort):              # a rig marker off the plane
        m.split_markers('s1', [[0, 0, 300]] + points[1:4])
    with pytest.raises(MigrationAbort):              # a "stone" marker on the plane
        m.split_markers('s1', points[:4] + [[10, 10, 5]])


def test_effector_guard():
    m.assert_effector('s1', [[-140, 0, -68], [0, 145, 250], [100, 100, 0]])
    with pytest.raises(MigrationAbort):              # a stone, not the gripper
        m.assert_effector('s1', [[-300, 0, 0], [0, 0, 700], [10, 10, 10]])


# exit (step 10c) -------------------------------------------------------------
def test_exit_kinds():
    assert m.exit_for(_identity(), None) is None
    split = m.exit_for(_identity(consumed_at='2026-04-29T09:41:30.620849Z'),
                       '2026-04-29T09:41:30.620849Z')
    assert split['kind'] == 'split' and split['recorded_by_user_id'] is None
    installed = m.exit_for(_identity(dataset='ddu_build_with_debris',
                                     consumed_at='2026-01-01T10:00:00Z'), None)
    lost = m.exit_for(_identity(dataset='ddu_aggregations',
                                consumed_at='2026-01-01T10:00:00Z'), None)
    assert (installed['kind'], lost['kind']) == ('installed', 'lost')
    for block in (split, installed, lost):
        Exit.model_validate(block)
    with pytest.raises(MigrationAbort):
        m.exit_for(_identity(consumed_at='2026-01-01T10:00:00Z'), None)


# lineage (step 10b) ----------------------------------------------------------
def test_inheritance_lists_equal_fields_and_overwrites_manufacture():
    origin = m.origin_for(_identity(salvage_source=ROSSKOPF))
    parent = dict(_identity(_id='p', origin=origin, original_function='IfcPlate',
                            trade_name='Corian', material='mineral_composite'))
    child = dict(parent, _id='c', parent_identities=['p'],
                 manufactured_at='2026-04-29T09:41:30Z',
                 manufactured_precision='exact', original_function='IfcSlab')
    update = m.inheritance_for(child, [parent])
    assert update['inherited_fields'] == ['origin', 'manufactured_at', 'material',
                                          'trade_name', 'manufacturer',
                                          'material_separability']
    assert (update['manufactured_at'], update['manufactured_precision']) == \
        (None, 'unknown')
    assert update['inherited_from'] == 'p'


def test_merge_inherits_only_unanimous_fields():
    a = _identity(_id='a', material='concrete', trade_name=None)
    b = _identity(_id='b', material='fired_clay', trade_name=None)
    child = _identity(_id='c', material='concrete', trade_name=None,
                      parent_identities=['a', 'b'])
    update = m.inheritance_for(child, [a, b])
    assert 'material' not in update['inherited_fields']
    assert 'trade_name' in update['inherited_fields']


def test_lineage_order_and_cycle():
    root = _identity(_id='r')
    child = _identity(_id='c', parent_identities=['r'])
    grandchild = _identity(_id='g', parent_identities=['c'])
    order = [i['_id'] for i in m.lineage_order([grandchild, child, root])]
    assert order == ['r', 'c', 'g']
    with pytest.raises(MigrationAbort, match='cycle'):
        m.lineage_order([_identity(_id='x', parent_identities=['y']),
                         _identity(_id='y', parent_identities=['x'])])


# proxies (step 4) ------------------------------------------------------------
def test_extrusions_become_authored_prisms():
    snap = _snapshot(geometry={'extrusions': [
        {'profile': [[-200, -100], [200, -100], [200, 100], [-200, 100]],
         'height': 12},
        {'profile': [[0, 0], [10, 0], [10, 10]], 'height': 5}]})
    proxies = m.proxies_from_extrusions(snap)
    assert [p['role'] for p in proxies] == ['primary', 'part']
    for proxy in proxies:
        Proxy.model_validate(proxy)
        assert proxy['fit'] == {'method': 'authored'}
    assert m.proxies_from_extrusions(_snapshot(geometry={'extrusions': None})) == []
    with pytest.raises(MigrationAbort):
        m.proxies_from_extrusions(_snapshot(geometry={'extrusions': [
            {'profile': [[0, 0], [1, 0]], 'height': 1}]}))


# evidence (steps 6d, 6b) -----------------------------------------------------
def test_reinforcement_layout_record():
    snap = _snapshot(geometry={'reinforcements': [
        {'spec': 'BSt III', 'diameter': 8, 'points': [[0, 0, 0], [100, 0, 0]]},
        {'spec': 'BSt III', 'diameter': 12, 'points': [[0, 50, 0], [100, 50, 0]]}]})
    record = m.reinforcement_evidence(snap)
    Evidence.model_validate(record)
    assert record['source_tier'] == 'archival'
    assert record['summary']['range'] == [8, 12]
    assert record['position']['snapshot_id'] == 's1'
    assert record['observed_at'] == snap['created']
    assert record['observed_at_precision'] == 'day'
    assert record['_id'] == m.reinforcement_evidence(snap)['_id']   # stable id


def test_condition_grade_record():
    record = m.condition_evidence(_snapshot(condition=1))
    Evidence.model_validate(record)
    assert record['summary'] == {'quantity': 'condition_grade', 'value': 1,
                                 'range': None, 'unit': None, 'unit_entered': None,
                                 'kind': 'claimed', 'uncertainty': None}
    assert record['performed_by'][0]['user_id'] == 'u1'
    table = m.varying_condition_datasets([('a', 2), ('a', 2), ('b', 2), ('b', 1),
                                          ('b', None)])
    assert table == {'a': {2: 2}, 'b': {2: 1, 1: 1}}


# shared account (step 11b) ---------------------------------------------------
def test_attribution_target_precedence():
    mapping = {'datasets': {'d': 'u-dataset'}, 'identities': {'i': 'u-identity'},
               'snapshots': {'s': 'u-snapshot'}}
    assert m.attribution_target(mapping, snapshot_id='s', identity_id='i',
                                dataset='d') == 'u-snapshot'
    assert m.attribution_target(mapping, snapshot_id='x', identity_id='i',
                                dataset='d') == 'u-identity'
    assert m.attribution_target(mapping, identity_id='x', dataset='d') == 'u-dataset'
    assert m.attribution_target(mapping, dataset='other') is None


# prism profiles (decision 8.112 review) --------------------------------------
BOWTIE = [[0, 0], [10, 10], [10, 0], [0, 10]]            # self-intersecting
SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10]]


def test_a_repeated_closing_point_is_dropped_and_nothing_else_changes():
    assert m.without_closing_point(SQUARE + [SQUARE[0]]) == SQUARE
    assert m.without_closing_point(SQUARE) == SQUARE
    # a ring that is only 3 points long and equal at the ends stays
    assert m.without_closing_point([[0, 0], [1, 1], [0, 0]]) == [
        [0, 0], [1, 1], [0, 0]]
    proxies = m.proxies_from_extrusions(_snapshot(geometry={'extrusions': [
        {'profile': SQUARE + [SQUARE[0]], 'height': 4,
         'holes': [[[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]]}]}))
    assert proxies[0]['params']['profile'] == SQUARE
    assert proxies[0]['params']['holes'] == [[[2, 2], [4, 2], [4, 4], [2, 4]]]
    Proxy.model_validate(proxies[0])


def test_a_self_intersecting_profile_is_reported_and_kept_as_it_was():
    snap = _snapshot(geometry={'extrusions': [
        {'profile': SQUARE, 'height': 4}, {'profile': BOWTIE, 'height': 4}]})
    proxies = m.proxies_from_extrusions(snap)
    assert proxies[1]['params']['profile'] == BOWTIE          # not repaired
    Proxy.model_validate(proxies[1])             # a stored one still reads
    found = m.prism_problems(proxies)
    assert [i for i, _ in found] == [1]
    assert 'Self-intersection' in found[0][1]
    assert m.prism_problems(proxies[:1]) == []
