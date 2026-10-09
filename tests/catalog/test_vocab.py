"""Controlled vocabularies (data model spec section 2)."""

from __future__ import annotations

import re

from apps.catalog import vocab


def test_labels_cover_every_value():
    assert set(vocab.ORIGINAL_FUNCTION_LABELS) == set(vocab.ORIGINAL_FUNCTIONS)
    assert set(vocab.SHAPE_CLASS_LABELS) == set(vocab.SHAPE_CLASSES)
    assert set(vocab.ORIGIN_KIND_LABELS) == set(vocab.ORIGIN_KINDS)
    assert set(vocab.EXIT_KIND_LABELS) == set(vocab.EXIT_KINDS)
    assert set(vocab.CONDITION_GRADE_LABELS) == set(range(0, 4))


def test_composite_is_never_derived():
    assert 'composite' in vocab.SHAPE_CLASSES
    assert 'composite' not in vocab.DERIVABLE_SHAPE_CLASSES


def test_every_method_has_a_tier_rule():
    assert set(vocab.METHOD_TIER) == set(vocab.EVIDENCE_METHODS)
    for method, tier in vocab.METHOD_TIER.items():
        if method == 'reinforcement_layout':
            assert tier is None          # follows the payload's basis (7.8)
        else:
            assert tier in vocab.SOURCE_TIERS
    tiers = set(vocab.REINFORCEMENT_BASIS_TIER.values())
    assert tiers <= set(vocab.SOURCE_TIERS)


def test_policy_constants():
    assert set(vocab.TIER_BASE_CONFIDENCE) == set(vocab.SOURCE_TIERS)
    assert vocab.TIER_BASE_CONFIDENCE['destructive'] == 0.90
    assert set(vocab.VERIFICATION_FACTOR) == set(vocab.VERIFICATION_STATES)
    assert vocab.INHERIT_K == 0.80


def test_quantities_are_consistent():
    names = [q.name for q in vocab.QUANTITIES]
    assert len(names) == len(set(names))
    for q in vocab.QUANTITIES:
        assert q.kind in ('scalar', 'categorical', 'ordinal')
        assert q.scope in ('identity', 'snapshot')
        assert q.ranking and set(q.ranking) <= set(vocab.SOURCE_TIERS)
        assert (q.unit is None) == (q.kind != 'scalar')
        assert (q.ordinal_direction is not None) == (q.kind == 'ordinal')
        if q.applies_to is not None:
            assert set(q.applies_to) <= set(vocab.MATERIAL_GROUPS)
    # decisions 6.13 and 7.9
    assert vocab.QUANTITY_BY_NAME['mass'].scope == 'snapshot'
    assert vocab.QUANTITY_BY_NAME['density'].scope == 'identity'
    grade = vocab.QUANTITY_BY_NAME['condition_grade']
    assert grade.ordinal_direction == 'grade'
    assert grade.applies_to is None
    assert vocab.QUANTITY_BY_NAME['spalling'].ordinal_direction == 'severity'


def test_material_seed():
    ids = [m.id for m in vocab.MATERIAL_SEED]
    assert len(ids) == len(set(ids)) == 32
    # never a hazardous (*) default
    code = re.compile(r'^17 \d{2} \d{2}$')
    for m in vocab.MATERIAL_SEED:
        assert m.group in vocab.MATERIAL_GROUPS
        assert code.match(m.default_class), m.id
    # the 0.5 materials all have a target (spec section 8.1 step 12)
    for target in ('mineral_composite', 'concrete', 'fired_clay',
                   'autoclaved_aerated_concrete', 'asphalt', 'steel',
                   'timber'):
        assert target in vocab.MATERIAL_SEED_BY_ID


def test_exit_kinds():
    assert set(vocab.TERMINAL_EXIT_KINDS) <= set(vocab.EXIT_KINDS)
    assert set(vocab.SERVER_SET_EXIT_KINDS) <= set(vocab.TERMINAL_EXIT_KINDS)
    terminal = set(vocab.TERMINAL_EXIT_KINDS)
    assert not {'installed', 'returned', 'lost'} & terminal


def test_evidence_labels_cover_their_vocabularies():
    assert set(vocab.EVIDENCE_METHOD_LABELS) == set(vocab.EVIDENCE_METHODS)
    assert set(vocab.SOURCE_TIER_LABELS) == set(vocab.SOURCE_TIERS) | {
        'inherited'}
    assert set(vocab.VERIFICATION_STATE_LABELS) == set(
        vocab.VERIFICATION_STATES)
    assert set(vocab.QUANTITY_LABELS) == set(vocab.QUANTITY_BY_NAME)


def test_decision_8_44_rows_and_mapping_columns():
    for name in ('exposure_class', 'chloride_content', 'elastic_modulus',
                 'crack_width'):
        assert name in vocab.QUANTITY_BY_NAME
    assert vocab.QUANTITY_BY_NAME['exposure_class'].values == \
        vocab.EXPOSURE_CLASSES and len(vocab.EXPOSURE_CLASSES) == 18
    assert vocab.QUANTITY_BY_NAME['chloride_content'].unit == '%'
    assert vocab.QUANTITY_BY_NAME['elastic_modulus'].unit == 'GPa'
    crack = vocab.QUANTITY_BY_NAME['crack_width']
    assert (crack.unit, crack.scope) == ('mm', 'snapshot')
    assert crack.ranking == ('visual', 'ndt')
    # mapping columns exist where one counterpart is known; a QUDT unit is
    # named for every scalar
    for q in vocab.QUANTITIES:
        if q.kind == 'scalar':
            assert q.qudt_unit and q.qudt_unit.startswith('unit:'), q.name
    assert vocab.QUANTITY_BY_NAME['elastic_modulus'].cero == 'youngModulus'
    assert vocab.ORIGINAL_FUNCTION_IFC_CLASS['IfcBeam'] == 'IfcBeam'
    assert vocab.ORIGINAL_FUNCTION_IFC_CLASS['CscDebris'] is None
    assert vocab.EVIDENCE_METHOD_SOSA_TYPE['core_compression'] == \
        'sosa:Sample'
    assert vocab.EVIDENCE_METHOD_SOSA_TYPE['rebound_hammer'] == \
        'sosa:Observation'


def test_decision_8_70_g_ifc_names_for_exposure_class_and_cover():
    """Checked against the IFC documentation (Pset_ConcreteElementGeneral
    has ExposureClass, IfcLabel, and ConcreteCover, IfcPositiveLengthMeasure)."""
    exposure = vocab.QUANTITY_BY_NAME['exposure_class']
    cover = vocab.QUANTITY_BY_NAME['cover_depth']
    assert exposure.ifc_property == 'Pset_ConcreteElementGeneral.ExposureClass'
    assert cover.ifc_property == 'Pset_ConcreteElementGeneral.ConcreteCover'
    assert (exposure.bsdd, cover.bsdd) == ('ExposureClass', 'ConcreteCover')
