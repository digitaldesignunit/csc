"""Lineage inheritance, merges, cut rules and the derived split exit
(spec section 3.1.2, 3.1.3, I17, I18; decisions 8.8, 8.31--8.34)."""

from __future__ import annotations

import pytest

from apps.catalog.lineage import (
    KEEP,
    ChildFacts,
    changed_units,
    cut_refusal,
    derived_exit,
    detach_on_patch,
    expected_unit,
    inherit_on_create,
    propagate,
    reinherit,
)
from apps.catalog.vocab import INHERITABLE_FIELDS


def _origin(**over):
    base = {'kind': 'deinstallation', 'at': '2024-07-24T00:00:00Z',
            'at_precision': 'day', 'place': {'name': 'Lichtwiese'},
            'construction_work': {'name': 'Pavilion'},
            'performed_by': [{'kind': 'organization', 'organization': 'A'}],
            'notes': None}
    base.update(over)
    return base


def _piece(pid, number, **over):
    doc = {'_id': pid, 'catalog_number': number, 'origin': _origin(),
           'manufactured_at': '1968-01-01T00:00:00Z',
           'manufactured_precision': 'year', 'material': 'concrete',
           'material_class': '17 01 01', 'material_class_source': 'derived',
           'trade_name': None, 'manufacturer': None,
           'material_separability': None, 'original_function': 'IfcWall',
           'inherited_fields': [], 'inherited_from': None}
    doc.update(over)
    return doc


# CREATE ----------------------------------------------------------------------
def test_single_parent_child_inherits_every_unit_it_does_not_state():
    parent = _piece('p', 1, trade_name='Corian')
    result = inherit_on_create({'original_function': 'IfcBuildingElementPart'},
                               [parent])
    assert 'original_function' not in result.inherited_fields
    assert set(result.inherited_fields) == set(INHERITABLE_FIELDS) - {
        'original_function'}
    assert result.values['trade_name'] == 'Corian'
    assert result.values['manufactured_precision'] == 'year'
    assert result.inherited_from == 'p'
    assert result.missing == []


def test_stating_one_field_of_a_unit_makes_the_whole_unit_own():
    parent = _piece('p', 1)
    result = inherit_on_create({'material_class': '17 01 07'}, [parent])
    assert 'material' not in result.inherited_fields
    assert 'material' not in result.values


def test_material_travels_with_an_assigned_class():
    """8.32: a roof-tile parent keeps its assigned class on the child."""
    parent = _piece('p', 1, material='fired_clay', material_class='17 01 03',
                    material_class_source='assigned')
    result = inherit_on_create({}, [parent])
    assert result.values['material_class'] == '17 01 03'
    assert result.values['material_class_source'] == 'assigned'


def test_merge_agrees_on_origin_despite_notes_and_actors():
    """8.33: identifying keys equal --> first origin, actors united, notes
    joined with catalog numbers."""
    a = _piece('a', 1, origin=_origin(notes='north wall'))
    b = _piece('b', 2, origin=_origin(
        notes='south wall',
        performed_by=[{'kind': 'organization', 'organization': 'A'},
                      {'kind': 'organization', 'organization': 'B'}]))
    agree, values = expected_unit('origin', [a, b])
    assert agree
    origin = values['origin']
    assert [p['organization'] for p in origin['performed_by']] == ['A', 'B']
    assert origin['notes'] == 'CSC-000001: north wall\nCSC-000002: south wall'


def test_merge_disagreeing_origin_is_unset_and_not_inherited():
    a = _piece('a', 1)
    b = _piece('b', 2, origin=_origin(at='2023-01-01T00:00:00Z'))
    result = inherit_on_create({}, [a, b])
    assert 'origin' not in result.inherited_fields
    assert result.values['origin']['kind'] == 'unknown'


def test_merge_disagreeing_on_a_required_unit_needs_it_stated():
    a = _piece('a', 1)
    b = _piece('b', 2, material='steel', material_class='17 04 05')
    assert inherit_on_create({}, [a, b]).missing == ['material']
    stated = inherit_on_create({'material': 'concrete'}, [a, b])
    assert stated.missing == []


# PROPAGATE / DETACH / RE-INHERIT ---------------------------------------------
def test_three_generations_propagate_through_a_merge():
    """Grandparent change reaches a merged grandchild only while both of its
    parents agree; then the grandchild lets go (8.31, 8.33)."""
    gp = _piece('gp', 1)
    c1 = {**_piece('c1', 2), **inherit_on_create({}, [gp]).values,
          'inherited_fields': list(INHERITABLE_FIELDS), 'inherited_from': 'gp'}
    c2 = {**_piece('c2', 3), **inherit_on_create({}, [gp]).values,
          'inherited_fields': list(INHERITABLE_FIELDS), 'inherited_from': 'gp'}
    merged_values = inherit_on_create({}, [c1, c2])
    g = {**_piece('g', 4), **merged_values.values,
         'inherited_fields': merged_values.inherited_fields,
         'inherited_from': 'c1'}
    assert 'manufactured_at' in g['inherited_fields']

    # the grandparent's date is corrected: both children follow ...
    gp_after = {**gp, 'manufactured_at': '1970-01-01T00:00:00Z'}
    units = changed_units(gp, gp_after)
    assert units == ['manufactured_at']
    for child in (c1, c2):
        update = propagate(child, [gp_after], units)
        child.update(update.set_values)
    # ... and so does the merged grandchild, its parents still agreeing
    update = propagate(g, [c1, c2], units)
    assert update.set_values == {'manufactured_at': '1970-01-01T00:00:00Z'}

    # c2 makes the date its own and changes it: the parents now disagree
    c2['inherited_fields'] = [u for u in c2['inherited_fields']
                              if u not in detach_on_patch(
                                  c2, ['manufactured_at'])]
    c2['manufactured_at'] = '1980-01-01T00:00:00Z'
    update = propagate(g, [c1, c2], ['manufactured_at'])
    assert update.detached == ['manufactured_at']
    assert 'manufactured_at' not in update.inherited_fields
    assert update.set_values == {}


def test_reinherit_copies_back_and_refuses_disagreeing_merges():
    parent = _piece('p', 1, trade_name='Corian')
    child = _piece('c', 2, trade_name='Other', inherited_fields=[],
                   inherited_from=None)
    update = reinherit(child, [parent], ['trade_name'])
    assert update.set_values == {'trade_name': 'Corian'}
    assert update.inherited_fields == ['trade_name']
    a, b = _piece('a', 1, trade_name='X'), _piece('b', 2, trade_name='Y')
    with pytest.raises(ValueError):
        reinherit(child, [a, b], ['trade_name'])


# CUTS (8.34) -----------------------------------------------------------------
@pytest.mark.parametrize('exit_kind, allowed', [
    (None, True), ('split', True), ('merged', True), ('installed', False),
    ('returned', False), ('lost', False), ('recycled', False),
    ('disposed', False)])
def test_cut_needs_a_parent_in_circulation_or_already_cut(exit_kind, allowed):
    parent = _piece('p', 1, exit={'kind': exit_kind} if exit_kind else None)
    assert (cut_refusal(parent, ever_published=True) is None) == allowed


def test_cut_refused_from_withdrawn_or_unpublished_parents():
    parent = _piece('p', 1, withdrawn={'duplicate_of': 'q'})
    assert 'duplicates q' in cut_refusal(parent, ever_published=True)
    assert 'publish it first' in cut_refusal(_piece('p', 1),
                                             ever_published=False)


# DERIVED EXIT (8.8, 8.34) ----------------------------------------------------
def _child(cid, at, parents=1, withdrawn=False):
    return ChildFacts(child_id=cid, parent_count=parents, withdrawn=withdrawn,
                      first_published_at=at)


def test_first_published_child_ends_the_parent_at_the_earliest_date():
    parent = _piece('p', 1, exit=None)
    exit_ = derived_exit(parent, [_child('a', '2025-03-01T00:00:00Z'),
                                  _child('b', '2025-01-01T00:00:00Z'),
                                  _child('c', None)])
    assert exit_['kind'] == 'split' and exit_['at'] == '2025-01-01T00:00:00Z'
    assert exit_['recorded_by_user_id'] is None


def test_draft_rejected_and_withdrawn_children_do_not_count():
    parent = _piece('p', 1, exit=None)
    assert derived_exit(parent, [_child('a', None)]) is KEEP
    assert derived_exit(parent, [_child('a', '2025-01-01T00:00:00Z',
                                        withdrawn=True)]) is KEEP


def test_last_child_withdrawn_clears_a_server_set_exit():
    parent = _piece('p', 1, exit={'kind': 'split', 'at': '2025-01-01T00:00:00Z',
                                  'recorded_by_user_id': None})
    assert derived_exit(parent, [_child('a', '2025-01-01T00:00:00Z',
                                        withdrawn=True)]) is None


def test_merge_kind_when_every_child_has_several_parents():
    parent = _piece('p', 1, exit=None)
    assert derived_exit(parent, [_child('a', '2025-01-01T00:00:00Z',
                                        parents=2)])['kind'] == 'merged'


def test_authored_exit_is_never_overwritten():
    parent = _piece('p', 1, exit={'kind': 'installed',
                                  'at': '2025-01-01T00:00:00Z',
                                  'recorded_by_user_id': 'u'})
    assert derived_exit(parent, [_child('a', '2025-02-01T00:00:00Z')]) is KEEP


def test_hand_set_split_is_taken_over_and_falls_back():
    """8.34: the earlier of the hand-set date and the children's wins; the
    last child gone, the hand-set split returns with its author."""
    hand = {'kind': 'split', 'at': '2024-06-01T00:00:00Z',
            'at_precision': 'month', 'recorded_by_user_id': 'mod',
            'notes': 'cut on site'}
    parent = _piece('p', 1, exit=hand)
    taken = derived_exit(parent, [_child('a', '2025-01-01T00:00:00Z')])
    assert taken['recorded_by_user_id'] is None
    assert taken['at'] == '2024-06-01T00:00:00Z'
    assert taken['manual_by_user_id'] == 'mod'
    back = derived_exit({**parent, 'exit': taken},
                        [_child('a', '2025-01-01T00:00:00Z', withdrawn=True)])
    assert back['recorded_by_user_id'] == 'mod'
    assert back['at'] == '2024-06-01T00:00:00Z'
    assert back['at_precision'] == 'month'


# BATCHES (8.105) -------------------------------------------------------------
def _draw_of(cid, at, quantity, withdrawn=False):
    return ChildFacts(child_id=cid, parent_count=1, withdrawn=withdrawn,
                      first_published_at=at, quantity=quantity)


def test_a_batch_is_split_only_at_remaining_zero_at_the_latest_draw():
    batch = _piece('b', 1, exit=None)
    some = [_draw_of('a', '2025-01-01T00:00:00Z', 4)]
    assert derived_exit(batch, some, batch_size=10) is KEEP
    all_out = [*some, _draw_of('b', '2025-02-01T00:00:00Z', 6),
               _draw_of('c', '2025-03-01T00:00:00Z', 1, withdrawn=True)]
    exit_ = derived_exit(batch, all_out, batch_size=10)
    assert exit_['kind'] == 'split' and exit_['at'] == '2025-02-01T00:00:00Z'
    assert exit_['recorded_by_user_id'] is None


def test_a_withdrawn_draw_clears_the_batch_split_and_an_authored_exit_stays():
    split = {'kind': 'split', 'at': '2025-02-01T00:00:00Z',
             'recorded_by_user_id': None}
    batch = _piece('b', 1, exit=split)
    back = [_draw_of('a', '2025-01-01T00:00:00Z', 4),
            _draw_of('b', '2025-02-01T00:00:00Z', 6, withdrawn=True)]
    assert derived_exit(batch, back, batch_size=10) is None
    lost = _piece('b', 1, exit={'kind': 'lost', 'at': '2025-02-01T00:00:00Z',
                                'recorded_by_user_id': 'u'})
    assert derived_exit(lost, back, batch_size=10) is KEEP


def test_only_single_parent_children_are_draws():
    batch = _piece('b', 1, exit=None)
    merged = ChildFacts(child_id='m', parent_count=2, withdrawn=False,
                        first_published_at='2025-01-01T00:00:00Z', quantity=10)
    assert derived_exit(batch, [merged], batch_size=10) is KEEP
