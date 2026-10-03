"""
The evidence method registry (spec section 4.5, Appendix A; decisions 8.40
- 8.43): server recomputation, cross-checks, warnings against errors, the
derived models and the pairing checks. Pure functions, no database.
"""

from __future__ import annotations

import copy

import pytest

from apps.catalog.evidence.core import pairing_problems
from apps.catalog.evidence.registry import (
    ALL_METHOD_NAMES,
    SPEC_BY_NAME,
    describe_method,
    describe_quantities,
    is_excluded_from_fold,
    prepare_record,
    record_warnings,
)
from apps.catalog.evidence.types import EvidenceInvalid, PairingFacts
from apps.catalog.vocab import EVIDENCE_METHODS

SNAP = '7a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
T = '2026-02-27T14:30:00Z'


def rebound(**over):
    payload = {
        'instrument': {'hammer_type': 'N', 'manufacturer': 'Proceq',
                       'last_calibration_at': '2026-01-15',
                       'anvil_check': {
                           'expected': 80,
                           'before': {'readings': [80, 81, 79, 80, 80]},
                           'after': {'readings': [80, 80, 79, 81, 80]}}},
        'test_area': {'label': 'TA-1', 'surface_preparation': 'ground',
                      'surface_condition': 'dry', 'member_thickness_mm': 180,
                      'support': 'fixed_in_structure'},
        'impact_direction': 'horizontal',
        'readings': [44, 42, 41, 45, 43, 42, 40, 44, 43],
        'reading_unit': '1',
    }
    payload.update(over)
    return payload


def rebound_record(payload=None, **env):
    data = {'method': 'rebound_hammer', 'observed_at': T,
            'position': {'kind': 'none', 'description': 'north face'},
            'payload': payload or rebound()}
    data.update(env)
    return data


def core(**over):
    payload = {
        'sampling': {'cored_at': '2026-02-20T11:00:00Z',
                     'drill_diameter_mm': 100, 'drilling_method': 'wet'},
        'specimen': {'label': 'C-03', 'measured_diameter_mm': 99.6,
                     'length_prepared_mm': 199.2,
                     'end_preparation': 'ground', 'storage': 'water'},
        'test': {'tested_at': T, 'loading_rate_mpa_s': 0.6,
                 'max_load_kn': 298.4, 'failure_type': 'satisfactory'},
    }
    for key, value in over.items():
        section, _, name = key.partition('__')
        if name:
            payload[section] = {**payload[section], name: value}
        else:
            payload[key] = value
    return payload


def core_record(payload=None, **env):
    data = {'method': 'core_compression',
            'position': {'kind': 'point', 'snapshot_id': SNAP,
                         'point': [1500, 150, 450]},
            'payload': payload or core()}
    data.update(env)
    return data


def problems(data, **kw):
    with pytest.raises(EvidenceInvalid) as info:
        prepare_record(data, **kw)
    return [(p.path, p.message) for p in info.value.problems]


def paths(data, **kw):
    return [p for p, _ in problems(data, **kw)]


# REGISTRY ---------------------------------------------------------------------
def test_every_vocab_method_has_one_spec():
    assert set(SPEC_BY_NAME) == set(EVIDENCE_METHODS) == set(
        ALL_METHOD_NAMES)


def test_methods_are_described_with_field_texts():
    """The "?" popovers: every payload field carries a description."""
    for spec in SPEC_BY_NAME.values():
        description = describe_method(spec)
        schema = description['payload_schema']
        missing = []

        def walk(node, trail):
            for name, prop in (node.get('properties') or {}).items():
                if not (prop.get('description')
                        or prop.get('$ref') or prop.get('anyOf')
                        or prop.get('allOf')):
                    missing.append('.'.join(trail + [name]))
        walk(schema, [spec.name])
        for def_name, node in (schema.get('$defs') or {}).items():
            walk(node, [spec.name, def_name])
        assert missing == [], missing
    schema = describe_method(SPEC_BY_NAME['rebound_hammer'])['payload_schema']
    median = schema['properties']['median']
    assert median['server_computed'] is True


def test_quantity_table_carries_units_and_mappings():
    rows = {q['name']: q for q in describe_quantities()}
    assert rows['compressive_strength']['mapping']['qudt_unit'] == \
        'unit:MegaPA'
    assert 'N/mm2' in rows['compressive_strength']['accepted_units']
    for new in ('exposure_class', 'chloride_content', 'elastic_modulus',
                'crack_width'):
        assert new in rows
    assert rows['exposure_class']['values'][:2] == ['X0', 'XC1']
    assert rows['crack_width']['scope'] == 'snapshot'
    assert rows['chloride_content']['unit'] == '%'


# REBOUND ----------------------------------------------------------------------
def test_rebound_spec_example_gets_its_median_and_summary():
    result = prepare_record(rebound_record())
    f = result.fields
    assert f['payload']['median'] == 43 and f['payload']['n_valid'] == 9
    assert f['payload']['set_discarded'] is False
    assert f['summary'] == {
        'quantity': 'rebound_number', 'value': 43, 'range': None,
        'unit': '1', 'unit_entered': None, 'kind': 'measured',
        'uncertainty': None}
    assert f['source_tier'] == 'ndt' and f['destructive'] is False
    assert f['standard'] == {'code': 'EN 12504-2', 'year': 2021}
    assert result.warnings == [] and not result.excluded_from_fold


def test_median_is_a_whole_number_halves_up():
    payload = rebound(readings=[40, 40, 41, 41, 42, 42, 43, 43, 44, 44])
    assert prepare_record(rebound_record(payload)).fields['payload'][
        'median'] == 42                      # (42 + 42) / 2
    payload = rebound(readings=[40, 40, 41, 41, 42, 43, 43, 43, 44, 44])
    assert prepare_record(rebound_record(payload)).fields['payload'][
        'median'] == 43                      # (42 + 43) / 2 = 42.5 -> 43


def test_fewer_than_nine_readings_is_an_error():
    found = problems(rebound_record(rebound(readings=[44] * 8)))
    assert found[0][0] == 'payload.readings' and '9' in found[0][1]


def test_the_discard_rule_flags_the_set_and_the_fold_skips_it():
    # median 40; 3 of 10 (30 %) deviate by more than 25 %
    readings = [40, 40, 40, 40, 40, 40, 40, 60, 62, 20]
    result = prepare_record(rebound_record(rebound(readings=readings)))
    payload = result.fields['payload']
    assert payload['set_discarded'] is True and payload['median'] == 40
    assert result.excluded_from_fold
    assert any('discarded' in w for w in result.warnings)
    assert is_excluded_from_fold({'method': 'rebound_hammer',
                                  'payload': payload})
    # one deviating reading in ten (10 %) does not discard
    ok = prepare_record(rebound_record(rebound(
        readings=[40] * 9 + [60]))).fields['payload']
    assert ok['set_discarded'] is False
    # outlier_policy none never discards
    none = prepare_record(rebound_record(rebound(
        readings=readings, outlier_policy='none'))).fields['payload']
    assert none['set_discarded'] is False


def test_rejected_readings_are_flagged_not_deleted():
    payload = rebound(readings=[44, 42, 41, 45, 43, 42, 40, 44, 43, 90],
                      rejected_reading_indices=[9])
    result = prepare_record(rebound_record(payload))
    stored = result.fields['payload']
    assert len(stored['readings']) == 10 and stored['n_valid'] == 9
    assert stored['median'] == 43 and not stored['set_discarded']
    assert 'payload.rejected_reading_indices' in paths(rebound_record(
        rebound(rejected_reading_indices=[0, 0])))
    assert 'payload.rejected_reading_indices' in paths(rebound_record(
        rebound(rejected_reading_indices=[99])))
    every = rebound(rejected_reading_indices=list(range(9)))
    assert 'payload.rejected_reading_indices' in paths(rebound_record(every))
    few = rebound(rejected_reading_indices=[0, 1])
    assert any('only 7 valid' in w for w in prepare_record(
        rebound_record(few)).warnings)


def test_a_wrong_median_is_refused_a_right_one_accepted():
    sent = rebound(median=44)
    found = problems(rebound_record(sent))
    assert found[0][0] == 'payload.median' and '43' in found[0][1]
    prepare_record(rebound_record(rebound(median=43, n_valid=9,
                                          set_discarded=False)))
    assert 'payload.set_discarded' in paths(rebound_record(
        rebound(set_discarded=True)))


def test_q_value_hammers_and_the_quantity():
    q = rebound(instrument={'hammer_type': 'Q_N'}, reading_unit='Q')
    assert prepare_record(rebound_record(q)).fields['summary'][
        'quantity'] == 'q_value'
    assert 'payload.reading_unit' in paths(rebound_record(
        rebound(reading_unit='Q')))
    assert 'payload.reading_unit' in paths(rebound_record(
        rebound(instrument={'hammer_type': 'Q_L'})))
    # R and Q never mix: a summary naming the other quantity is refused
    wrong = rebound_record(summary={
        'quantity': 'q_value', 'value': 43, 'unit': '1',
        'kind': 'measured'})
    assert 'summary' in paths(wrong)


def test_a_rebound_number_is_never_a_strength():
    wrong = rebound_record(summary={
        'quantity': 'compressive_strength', 'value': 30, 'unit': 'MPa',
        'kind': 'measured'})
    assert 'summary' in paths(wrong)


def test_warnings_not_errors():
    bad_anvil = rebound(instrument={
        'hammer_type': 'N', 'anvil_check': {
            'expected': 80, 'before': {'readings': [80, 85, 79, 80, 80]}}})
    result = prepare_record(rebound_record(bad_anvil))
    assert any('reading 85' in w for w in result.warnings)
    loose = rebound(test_area={
        'surface_preparation': 'ground', 'surface_condition': 'dry',
        'member_thickness_mm': 80, 'support': 'loose'})
    assert any('loose' in w for w in prepare_record(
        rebound_record(loose)).warnings)
    # the same record warns when it is read back (warnings are not stored)
    stored = prepare_record(rebound_record(loose)).fields
    assert any('loose' in w for w in record_warnings(stored))


GRID = {'origin': [100, 100, 0], 'u': [1, 0, 0], 'v': [0, 1, 0],
        'rows': 3, 'cols': 3, 'spacing_mm': 30}


def _grid_record(grid=None, **area):
    test_area = {'surface_preparation': 'ground', 'surface_condition': 'dry',
                 'grid': grid or dict(GRID), **area}
    return rebound_record(rebound(test_area=test_area),
                          position={'snapshot_id': SNAP})


def test_the_grid_gives_points_and_a_region():
    result = prepare_record(_grid_record())
    grid = result.fields['payload']['test_area']['grid']
    assert len(grid['points']) == 9
    assert grid['points'][0] == [100, 100, 0]
    assert grid['points'][1] == [130, 100, 0]          # next in the row
    assert grid['points'][3] == [100, 130, 0]          # next row
    assert grid['points'][8] == [160, 160, 0]
    position = result.fields['position']
    assert position['kind'] == 'region' and position['snapshot_id'] == SNAP
    assert position['point'] == [130, 130, 0]          # the grid centre


def test_grid_rules():
    assert 'payload.test_area.grid' in paths(_grid_record(
        {**GRID, 'rows': 2}))                          # 6 points, 9 readings
    assert 'payload.test_area.grid.spacing_mm' in paths(_grid_record(
        {**GRID, 'spacing_mm': 20}))                   # < min_spacing 25
    assert 'payload.test_area.grid.u' in paths(_grid_record(
        {**GRID, 'u': [2, 0, 0]}))
    assert 'payload.test_area.grid' in paths(_grid_record(
        {**GRID, 'v': [1, 0, 0]}))                     # not orthogonal
    no_snapshot = rebound_record(rebound(test_area={
        'surface_preparation': 'ground', 'surface_condition': 'dry',
        'grid': GRID}), position={'kind': 'none', 'description': 'x'})
    assert 'position.kind' in paths(no_snapshot)
    # the client never sends the points: a grid with points is its own error
    # only when they differ from the server's
    assert 'position.point' in paths(rebound_record(
        rebound(test_area={'surface_preparation': 'ground',
                           'surface_condition': 'dry', 'grid': GRID}),
        position={'snapshot_id': SNAP, 'kind': 'region',
                  'point': [0, 0, 0]}))


def test_rebound_derived_strength_class_conditions():
    def derived(kind, value='C16/20', note='Table NA.6, row 40'):
        return [{'quantity': 'concrete_class', 'value': value,
                 'kind': 'derived',
                 'model': {'kind': kind, 'note': note, 'reference': None}}]
    ok = prepare_record(rebound_record(
        derived=derived('din_en_13791_a20_na6')))
    assert ok.fields['derived'][0]['value'] == 'C16/20'
    assert 'derived.0.model.note' in paths(rebound_record(
        derived=derived('din_en_13791_a20_na6', note='')))
    # N-type hammer only for NA.6; Q_N only for NA.7
    assert 'derived.0' in paths(rebound_record(
        derived=derived('din_en_13791_a20_na7')))
    ql = rebound(instrument={'hammer_type': 'L'})
    assert 'derived.0' in paths(rebound_record(
        ql, derived=derived('din_en_13791_a20_na6')))
    q = rebound(instrument={'hammer_type': 'Q_N'}, reading_unit='Q')
    assert prepare_record(rebound_record(
        q, derived=derived('din_en_13791_a20_na7'))).fields['derived']
    # carbonation up to 5 mm, or a ground surface
    carbonated = rebound(test_area={
        'surface_preparation': 'as_found', 'surface_condition': 'dry',
        'carbonation_depth_mm': 8})
    assert 'derived.0' in paths(rebound_record(
        carbonated, derived=derived('din_en_13791_a20_na6')))
    unknown = rebound(test_area={
        'surface_preparation': 'as_found', 'surface_condition': 'dry'})
    assert 'derived.0' in paths(rebound_record(
        unknown, derived=derived('din_en_13791_a20_na6')))
    fine = rebound(test_area={
        'surface_preparation': 'as_found', 'surface_condition': 'dry',
        'carbonation_depth_mm': 4.5})
    assert prepare_record(rebound_record(
        fine, derived=derived('din_en_13791_a20_na6')))
    # a discarded set derives nothing
    discarded = rebound(readings=[40, 40, 40, 40, 40, 40, 40, 60, 62, 20])
    assert 'derived.0' in paths(rebound_record(
        discarded, derived=derived('din_en_13791_a20_na6')))
    # the class is a categorical result of the right quantity
    wrong_quantity = [{'quantity': 'compressive_strength', 'value': 30,
                       'unit': 'MPa', 'kind': 'derived',
                       'model': {'kind': 'din_en_13791_a20_na6',
                                 'note': 'x'}}]
    assert 'derived.0.quantity' in paths(rebound_record(
        derived=wrong_quantity))


def test_rebound_correlation_result():
    entry = {'quantity': 'compressive_strength_in_situ', 'value': 31.5,
             'unit': 'N/mm2', 'kind': 'derived',
             'model': {'kind': 'en_13791_correlation',
                       'reference': 'Site correlation 2026-117'}}
    result = prepare_record(rebound_record(derived=[entry]))
    stored = result.fields['derived'][0]
    assert stored['unit'] == 'MPa' and stored['value'] == 31.5
    no_reference = copy.deepcopy(entry)
    no_reference['model']['reference'] = None
    assert 'derived.0.model.reference' in paths(rebound_record(
        derived=[no_reference]))
    unknown = copy.deepcopy(entry)
    unknown['model']['kind'] = 'astm_c805'
    assert 'derived.0.model.kind' in paths(rebound_record(derived=[unknown]))


# CORE -------------------------------------------------------------------------
def test_core_spec_example():
    result = prepare_record(core_record())
    f = result.fields
    payload = f['payload']
    assert payload['test']['cross_section_area_mm2'] == 7791.3
    assert payload['result']['fc_core_mpa'] == 38.3
    assert payload['specimen']['length_diameter_ratio'] == 2.0
    assert payload['specimen']['ld_class'] == '2:1'
    assert payload['specimen']['valid_for_strength'] is True
    assert payload['result']['fc_is_cyl_mpa'] == 38.3
    assert payload['result']['fc_is_cube_mpa'] is None
    assert payload['result']['conversion_basis'] == \
        'EN 13791:2019 + DIN EN 13791/A20:2022-04'
    assert f['summary']['quantity'] == 'compressive_strength'
    assert f['summary']['value'] == 38.3 and f['summary']['unit'] == 'MPa'
    # one derived in-situ result, the model named (I7: not the measured one)
    assert [d['quantity'] for d in f['derived']] == [
        'compressive_strength_in_situ']
    assert f['derived'][0]['model']['kind'] == 'en_13791'
    # both dates come from the payload; the tier and flags from the method
    assert f['sampled_at'] == '2026-02-20T11:00:00Z'
    assert f['observed_at'] == T
    assert f['source_tier'] == 'destructive' and f['destructive'] is True
    assert f['standard'] == {'code': 'EN 12504-1', 'year': 2019}
    assert result.warnings == []


def test_core_dates_must_agree_with_the_payload():
    assert 'sampled_at' in paths(core_record(
        sampled_at='2026-02-21T11:00:00Z'))
    assert 'observed_at' in paths(core_record(
        observed_at='2026-03-01T00:00:00Z'))
    ok = core_record(sampled_at='2026-02-20T11:00:00.000000Z',
                     observed_at=T)
    assert prepare_record(ok).fields['sampled_at'] == '2026-02-20T11:00:00Z'
    early = core(test__tested_at='2026-02-01T00:00:00Z')
    assert 'observed_at' in paths(core_record(early))        # I10


def test_f_over_a_is_cross_checked_within_one_percent():
    assert prepare_record(core_record(core(result={
        'fc_core_mpa': 38.5}))).fields['payload']['result'][
        'fc_core_mpa'] == 38.5                    # 0.5 % off, kept
    found = problems(core_record(core(result={'fc_core_mpa': 41.0})))
    assert found[0][0] == 'payload.result.fc_core_mpa'
    assert 'payload.test.cross_section_area_mm2' in paths(core_record(
        core(test__cross_section_area_mm2=8500)))
    ok_area = core(test__cross_section_area_mm2=7791.0)
    assert prepare_record(core_record(ok_area))


def test_ld_classes_and_the_one_to_one_core():
    one = core(specimen__length_prepared_mm=99.6)         # l/d 1.0
    f = prepare_record(core_record(one)).fields
    assert f['payload']['specimen']['ld_class'] == '1:1'
    assert f['payload']['result']['fc_is_cyl_mpa'] == 31.4   # 38.3 x 0.82
    assert f['payload']['result']['fc_is_cube_mpa'] == 38.3  # NA.7
    assert f['derived'][0]['value'] == 31.4
    for length, klass in ((194.0, 'other'), (194.3, '2:1'),
                          (204.0, '2:1'), (205.0, 'other'),
                          (89.5, 'other'), (89.7, '1:1'),
                          (109.5, '1:1'), (110.0, 'other')):
        got = prepare_record(core_record(core(
            specimen__length_prepared_mm=length))).fields['payload'][
            'specimen']['ld_class']
        assert got == klass, (length, got)
    other = prepare_record(core_record(core(
        specimen__length_prepared_mm=150.0)))
    assert other.fields['derived'] == []
    assert any('no in-situ strength' in w for w in other.warnings)
    # a wrong class sent by the client is refused
    assert 'payload.specimen.ld_class' in paths(core_record(core(
        specimen__ld_class='1:1')))
    # the drilled length stands in for a missing prepared one
    drilled = core(specimen__length_prepared_mm=None,
                   specimen__length_as_drilled_mm=199.2)
    assert prepare_record(core_record(drilled)).fields['payload'][
        'specimen']['ld_class'] == '2:1'
    nothing = core(specimen__length_prepared_mm=None)
    assert 'payload.specimen.length_prepared_mm' in paths(
        core_record(nothing))


def test_cube_equivalence_only_between_50_and_150_mm():
    big = core(specimen__measured_diameter_mm=160.0,
               specimen__length_prepared_mm=160.0, test__max_load_kn=800.0)
    f = prepare_record(core_record(big)).fields['payload']['result']
    assert f['fc_is_cube_mpa'] is None and f['fc_is_cyl_mpa'] is not None


def test_a_longitudinal_bar_invalidates_the_core_but_keeps_the_record():
    bars = core(specimen__reinforcement=[
        {'orientation': 'longitudinal', 'diameter_mm': 12,
         'position_mm': 40}])
    result = prepare_record(core_record(bars))
    payload = result.fields['payload']
    assert payload['specimen']['valid_for_strength'] is False
    assert payload['result']['fc_is_cyl_mpa'] is None
    assert result.fields['derived'] == []
    assert result.excluded_from_fold
    assert is_excluded_from_fold({'method': 'core_compression',
                                  'payload': payload})
    assert any('longitudinal' in w for w in result.warnings)
    transverse = core(specimen__reinforcement=[
        {'orientation': 'transverse', 'diameter_mm': 10,
         'position_mm': 45}])
    kept = prepare_record(core_record(transverse))
    assert kept.fields['payload']['specimen']['valid_for_strength'] is True
    assert not kept.excluded_from_fold
    assert 'payload.specimen.valid_for_strength' in paths(core_record(
        core(specimen__valid_for_strength=True,
             specimen__reinforcement=bars['specimen']['reinforcement'])))


def test_core_warnings():
    small = core(specimen__measured_diameter_mm=60.0,
                 specimen__length_prepared_mm=120.0, test__max_load_kn=100.0)
    assert any('75 mm' in w for w in prepare_record(
        core_record(small)).warnings)
    fast = core(test__loading_rate_mpa_s=1.2)
    assert any('loading rate' in w for w in prepare_record(
        core_record(fast)).warnings)
    coarse = core(specimen__max_aggregate_size_mm=40)
    assert any('aggregate' in w for w in prepare_record(
        core_record(coarse)).warnings)


def test_core_derived_en_13791_is_the_servers():
    """A client entry of the server-built kind is replaced, so a stored
    record can be re-prepared unchanged (an edit, a supersede)."""
    first = prepare_record(core_record())
    again = prepare_record(core_record(
        derived=first.fields['derived'],
        summary=first.fields['summary'],
        position=first.fields['position']))
    assert again.fields['derived'] == first.fields['derived']
    assert again.fields['payload'] == first.fields['payload']
    assert 'derived.0.model.kind' in paths(core_record(derived=[{
        'quantity': 'concrete_class', 'value': 'C20/25', 'kind': 'derived',
        'model': {'kind': 'din_en_13791_a20_na6', 'note': 'x'}}]))


def facts(**over):
    rebound_doc = {'_id': 'r1', 'identity_id': 'i1',
                   'method': 'rebound_hammer', 'status': 'published',
                   'superseded_by': None, 'observed_at': '2026-02-19T09:00:00Z',
                   'payload': {'set_discarded': False}}
    rebound_doc.update(over.pop('rebound', {}))
    return PairingFacts(identity_id=over.pop('identity_id', 'i1'),
                        rebound=over.pop('rebound_doc', rebound_doc),
                        other_pairs=over.pop('other_pairs', []))


def test_pairing_checks():
    payload = {'sampling': {'cored_at': '2026-02-20T11:00:00Z',
                            'paired_rebound_id': 'r1'}}
    assert pairing_problems(payload, facts()) == []
    assert pairing_problems({'sampling': {'cored_at': 'x'}}, facts()) == []
    text = lambda f: ' '.join(p.message for p in pairing_problems(  # noqa
        payload, f))
    assert 'no record' in text(facts(rebound_doc=None))
    assert 'another component' in text(facts(identity_id='other'))
    assert 'not a rebound' in text(facts(rebound={'method': 'core_compression'}))
    assert 'discarded' in text(facts(rebound={
        'payload': {'set_discarded': True}}))
    assert 'later than the coring' in text(facts(rebound={
        'observed_at': '2026-02-21T09:00:00Z'}))
    assert 'one core per rebound' in text(facts(other_pairs=['c9']))
    assert 'current record' in text(facts(rebound={'status': 'rejected'}))
    assert 'current record' in text(facts(rebound={'superseded_by': 'x'}))
    # the same day, earlier hour passes; fractional seconds compare right
    assert pairing_problems(payload, facts(rebound={
        'observed_at': '2026-02-20T11:00:00.000000Z'})) == []


# CLAIMS -----------------------------------------------------------------------
def archival(**over):
    data = {'method': 'archival_document',
            'observed_at': '2026-03-01T00:00:00Z',
            'payload': {'document': {'title': 'Statik 1968', 'date': '1968-03',
                                     'kind': 'spec'},
                        'claim': {'text': 'B225'}},
            'summary': {'quantity': 'concrete_class', 'range': ['B225'],
                        'kind': 'claimed'}}
    data.update(over)
    return data


def test_a_claim_is_the_clients_summary():
    result = prepare_record(archival())
    assert result.fields['summary']['range'] == ['B225']
    assert result.fields['source_tier'] == 'archival'
    assert result.fields['position'] == {
        'kind': 'none', 'snapshot_id': None, 'point': None,
        'description': 'whole component'}
    assert 'summary' in paths(archival(summary=None))
    assert 'summary.kind' in paths(archival(summary={
        'quantity': 'concrete_class', 'range': ['B225'],
        'kind': 'measured'}))


def test_units_are_converted_to_the_canonical_ones():
    claim = archival(summary={
        'quantity': 'compressive_strength', 'range': [18, 28],
        'unit': 'N/mm2', 'kind': 'claimed'})
    summary = prepare_record(claim).fields['summary']
    assert summary['unit'] == 'MPa' and summary['unit_entered'] == 'N/mm2'
    assert summary['range'] == [18, 28]
    kpa = archival(summary={
        'quantity': 'compressive_strength', 'value': 25000, 'unit': 'kPa',
        'kind': 'claimed'})
    assert prepare_record(kpa).fields['summary']['value'] == 25
    modulus = archival(summary={
        'quantity': 'elastic_modulus', 'value': 30000, 'unit': 'MPa',
        'kind': 'claimed'})
    assert prepare_record(modulus).fields['summary']['value'] == 30
    assert 'summary.unit' in paths(archival(summary={
        'quantity': 'compressive_strength', 'value': 1, 'unit': 'psi',
        'kind': 'claimed'}))
    assert 'summary.unit' in paths(archival(summary={
        'quantity': 'concrete_class', 'value': 'B225', 'unit': 'MPa',
        'kind': 'claimed'}))
    # stored form comes back through unchanged (canonical unit, kept text)
    stored = prepare_record(claim).fields
    again = prepare_record(archival(summary=stored['summary']))
    assert again.fields['summary'] == stored['summary']


def test_quantity_must_fit_method_and_tier():
    assert 'summary.quantity' in paths(archival(summary={
        'quantity': 'spalling', 'value': 1, 'kind': 'claimed'}))
    era = {'method': 'era_heuristic', 'observed_at': T,
           'payload': {'basis': 'construction_year', 'year': 1968},
           'summary': {'quantity': 'compressive_strength',
                       'range': [18, 28], 'unit': 'MPa', 'kind': 'claimed'}}
    assert prepare_record(era).fields['source_tier'] == 'heuristic'
    # cover_depth has no heuristic tier: it would never be folded
    era['summary'] = {'quantity': 'cover_depth', 'value': 30, 'unit': 'mm',
                      'kind': 'claimed'}
    assert 'summary.quantity' in paths(era)
    # the four decision-8.44 quantities
    exposure = archival(summary={'quantity': 'exposure_class',
                                 'range': ['XC4', 'XF1'], 'kind': 'claimed'})
    assert prepare_record(exposure)
    assert 'summary' in [p.split('.')[0] for p in paths(archival(summary={
        'quantity': 'exposure_class', 'value': 'XC9', 'kind': 'claimed'}))]
    chloride = archival(summary={'quantity': 'chloride_content',
                                 'value': 0.2, 'unit': '%',
                                 'kind': 'claimed'})
    assert prepare_record(chloride).fields['summary']['unit'] == '%'
    # a datasheet is archival too; a datasheet needs its manufacturer
    sheet = {'method': 'manufacturer_datasheet', 'observed_at': T,
             'payload': {'manufacturer': 'Rosskopf', 'product': 'Corian'},
             'summary': {'quantity': 'density', 'value': 1.7,
                         'unit': 'g/cm3', 'kind': 'claimed'}}
    assert prepare_record(sheet).fields['summary']['value'] == 1700
    sheet['payload'] = {'product': 'Corian'}
    assert 'payload.manufacturer' in paths(sheet)


def visual(observations, **over):
    data = {'method': 'visual_inspection', 'observed_at': T,
            'payload': {'observations': observations}}
    data.update(over)
    return data


def test_visual_inspection_one_quantity_per_record():
    result = prepare_record(visual([
        {'quantity': 'spalling', 'value': 1, 'note': 'north'},
        {'quantity': 'spalling', 'value': 2}]))
    assert result.fields['summary'] == {
        'quantity': 'spalling', 'value': 2, 'range': None, 'unit': None,
        'unit_entered': None, 'kind': 'claimed', 'uncertainty': None}
    grade = prepare_record(visual([
        {'quantity': 'condition_grade', 'value': 3},
        {'quantity': 'condition_grade', 'value': 1}]))
    assert grade.fields['summary']['value'] == 1        # the worst: lowest
    width = prepare_record(visual([{'quantity': 'crack_width',
                                    'value': 0.3}]))
    assert width.fields['summary']['value'] == 0.3
    assert width.fields['summary']['unit'] == 'mm'
    assert 'payload.observations' in paths(visual([
        {'quantity': 'spalling', 'value': 1},
        {'quantity': 'cracking', 'value': 1}]))
    assert 'payload.observations.0.value' in paths(visual([
        {'quantity': 'spalling', 'value': 4}]))
    assert 'payload.observations.0.value' in paths(visual([
        {'quantity': 'spalling', 'value': 1.5}]))
    assert 'payload.observations.0.value' in paths(visual([
        {'quantity': 'crack_width', 'value': -1}]))
    # a stored visual record re-prepares unchanged (migration 6b shape)
    migrated = {'method': 'visual_inspection', 'observed_at': T,
                'observed_at_precision': 'day',
                'position': {'kind': 'none', 'snapshot_id': SNAP,
                             'description': 'whole component'},
                'summary': {'quantity': 'condition_grade', 'value': 1,
                            'range': None, 'unit': None, 'unit_entered': None,
                            'kind': 'claimed', 'uncertainty': None},
                'payload': {'observations': [
                    {'quantity': 'condition_grade', 'value': 1,
                     'note': None}]}}
    assert prepare_record(migrated).fields['summary']['value'] == 1


def layout(basis='drawing', **over):
    data = {'method': 'reinforcement_layout', 'observed_at': T,
            'position': {'kind': 'none', 'snapshot_id': SNAP,
                         'description': 'bar centrelines'},
            'payload': {'basis': basis, 'bars': [
                {'spec': 'BSt III', 'diameter_mm': 8,
                 'points': [[0, 0, 20], [6000, 0, 20]]},
                {'spec': 'BSt III', 'diameter_mm': 12,
                 'points': [[0, 50, 20], [6000, 50, 20]]}]}}
    data.update(over)
    return data


def test_reinforcement_layout_tier_follows_the_basis():
    for basis, tier, kind in (('drawing', 'archival', 'claimed'),
                              ('scan', 'ndt', 'measured'),
                              ('exposed', 'visual', 'measured')):
        f = prepare_record(layout(basis)).fields
        assert f['source_tier'] == tier
        assert f['summary']['kind'] == kind
        assert f['summary']['range'] == [8, 12]
        assert f['summary']['quantity'] == 'rebar_diameter'
    # the bars' coordinates need the snapshot they are in (I23)
    assert 'position.snapshot_id' in paths(layout(position={
        'kind': 'none', 'description': 'x'}))
    assert 'position' in paths(layout(position=None))
    scan = prepare_record(layout('scan'))
    assert any('instrument' in w for w in scan.warnings)
    one_bar = layout()
    one_bar['payload']['bars'] = [one_bar['payload']['bars'][0]]
    assert prepare_record(one_bar).fields['summary']['range'] == [8, 8]
    # the migration 6d shape validates against the real model
    migrated = layout()
    migrated['payload'] = {'basis': 'drawing', 'document': None, 'bars': [
        {'spec': None, 'diameter_mm': 8,
         'points': [[0, 0, 20], [6000, 0, 20]]}]}
    assert prepare_record(migrated)


def test_unknown_method_and_bad_payload():
    assert paths({'method': 'astm_c805', 'payload': {}}) == ['method']
    found = problems(rebound_record(rebound(surprise=1)))
    assert found[0][0] == 'payload.surprise'
    assert 'payload.instrument.hammer_type' in paths(rebound_record(
        rebound(instrument={'hammer_type': 'X'})))
    assert 'observed_at' in paths({
        'method': 'visual_inspection',
        'payload': {'observations': [{'quantity': 'spalling', 'value': 1}]}})
