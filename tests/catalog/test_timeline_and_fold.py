"""
The snapshot timeline and the property fold (spec section 4.1, 4.4;
decisions 8.10, 8.12, 8.19): tier precedence, derived results, verification,
inheritance and merges, outranked evidence, the as-of sets of snapshots.
Pure functions, no database.
"""

from __future__ import annotations

import math

from apps.catalog.properties import (
    contexts_for,
    fold,
    foldable,
    keep_derived_at,
    quantities_of_scope,
    same_properties,
    snapshot_inputs,
    window,
)
from apps.catalog.timeline import (
    AFTER_EXIT,
    APPROXIMATE,
    BEFORE_FIRST,
    EXACT,
    build_timeline,
    resolve_snapshot_at,
)
from apps.catalog.vocab import QUANTITY_BY_NAME

NOW = '2026-10-02T12:00:00Z'


def snap(sid, version, start, precision='exact', status='published',
         superseded_by=None, supersedes=None):
    return {'_id': sid, 'version': version, 'effective_from': start,
            'effective_from_precision': precision, 'status': status,
            'superseded_by': superseded_by, 'supersedes': supersedes}


S0 = snap('s0', 0, '2024-07-24T00:00:00Z')
S1 = snap('s1', 1, '2026-02-01T00:00:00Z')
IDENTITY = {'_id': 'i1', 'exit': None, 'past_cycles': [],
            'origin': {'at': '2024-07-24T00:00:00Z'}}


# RESOLUTION -------------------------------------------------------------------
def test_resolution_picks_the_latest_started_live_snapshot():
    snaps = [S0, S1]
    assert resolve_snapshot_at(IDENTITY, snaps, '2025-01-01T00:00:00Z') \
        .snapshot_id == 's0'
    ctx = resolve_snapshot_at(IDENTITY, snaps, '2026-03-01T00:00:00Z')
    assert (ctx.snapshot_id, ctx.resolution) == ('s1', EXACT)
    # on the boundary the new state has begun
    assert resolve_snapshot_at(IDENTITY, snaps, '2026-02-01T00:00:00Z') \
        .snapshot_id == 's1'
    before = resolve_snapshot_at(IDENTITY, snaps, '2020-01-01T00:00:00Z')
    assert (before.snapshot_id, before.resolution) == (None, BEFORE_FIRST)


def test_corrected_withdrawn_and_unpublished_snapshots_do_not_resolve():
    corrected = snap('s1', 1, '2026-02-01T00:00:00Z', superseded_by='s2')
    fix = snap('s2', 2, '2026-02-01T00:00:00Z', supersedes='s1')
    got = resolve_snapshot_at(IDENTITY, [S0, corrected, fix],
                              '2026-03-01T00:00:00Z')
    assert got.snapshot_id == 's2'
    for status in ('withdrawn', 'draft', 'pending', 'rejected'):
        hidden = snap('s1', 1, '2026-02-01T00:00:00Z', status=status)
        assert resolve_snapshot_at(IDENTITY, [S0, hidden],
                                   '2026-03-01T00:00:00Z').snapshot_id == 's0'


def test_equal_start_goes_to_the_higher_version():
    a = snap('a', 1, '2026-02-01T00:00:00Z')
    b = snap('b', 2, '2026-02-01T00:00:00Z')
    assert resolve_snapshot_at(IDENTITY, [a, b],
                               '2026-02-02T00:00:00Z').snapshot_id == 'b'


def test_after_exit_feeds_no_snapshot():
    left = {**IDENTITY, 'exit': {'kind': 'installed',
                                 'at': '2026-05-01T00:00:00Z'}}
    inside = resolve_snapshot_at(left, [S0, S1], '2026-04-01T00:00:00Z')
    assert inside.snapshot_id == 's1'
    after = resolve_snapshot_at(left, [S0, S1], '2026-06-01T00:00:00Z')
    assert (after.snapshot_id, after.resolution) == (None, AFTER_EXIT)
    # even a non-terminal exit (installed, returned, lost) counts (8.10)
    for kind in ('returned', 'lost', 'recycled'):
        gone = {**IDENTITY, 'exit': {'kind': kind,
                                     'at': '2026-05-01T00:00:00Z'}}
        assert resolve_snapshot_at(gone, [S0], '2026-06-01T00:00:00Z') \
            .resolution == AFTER_EXIT


def test_an_archived_cycle_gap_is_after_exit_too_8_19():
    """Piece left in 2025-01, was installed elsewhere, re-entered 2026-01:
    an inspection in between resolves after_exit, not to the old snapshot."""
    again = {
        '_id': 'i1', 'exit': None,
        'past_cycles': [{'origin': {'at': '2024-07-24T00:00:00Z'},
                         'exit': {'kind': 'installed',
                                  'at': '2025-01-01T00:00:00Z'}}],
        'origin': {'at': '2026-01-01T00:00:00Z'}}
    snaps = [S0, snap('s1', 1, '2026-01-01T00:00:00Z')]
    gap = resolve_snapshot_at(again, snaps, '2025-06-01T00:00:00Z')
    assert (gap.snapshot_id, gap.resolution) == (None, AFTER_EXIT)
    assert resolve_snapshot_at(again, snaps, '2024-12-01T00:00:00Z') \
        .snapshot_id == 's0'
    assert resolve_snapshot_at(again, snaps, '2026-02-01T00:00:00Z') \
        .snapshot_id == 's1'
    # the boundaries themselves are not in the gap
    assert resolve_snapshot_at(again, snaps, '2025-01-01T00:00:00Z') \
        .resolution != AFTER_EXIT
    assert resolve_snapshot_at(again, snaps, '2026-01-01T00:00:00Z') \
        .resolution != AFTER_EXIT
    # a re-entry date that is unknown bounds nothing
    unknown = {**again, 'origin': {'at': None}}
    assert resolve_snapshot_at(unknown, snaps, '2025-06-01T00:00:00Z') \
        .resolution != AFTER_EXIT
    # two cycles: the second gap is found too
    twice = {
        '_id': 'i1', 'exit': None, 'origin': {'at': '2027-01-01T00:00:00Z'},
        'past_cycles': [
            {'origin': {'at': '2024-07-24T00:00:00Z'},
             'exit': {'kind': 'installed', 'at': '2025-01-01T00:00:00Z'}},
            {'origin': {'at': '2026-01-01T00:00:00Z'},
             'exit': {'kind': 'returned', 'at': '2026-06-01T00:00:00Z'}}]}
    assert resolve_snapshot_at(twice, snaps, '2026-09-01T00:00:00Z') \
        .resolution == AFTER_EXIT


def test_a_coarse_date_is_approximate():
    year = [S0, snap('s1', 1, '2026-01-01T00:00:00Z', precision='year')]
    inside = resolve_snapshot_at(IDENTITY, year, '2026-06-01T00:00:00Z')
    assert (inside.snapshot_id, inside.resolution) == ('s1', APPROXIMATE)
    after = resolve_snapshot_at(IDENTITY, year, '2027-06-01T00:00:00Z')
    assert after.resolution == EXACT
    day = [S0, snap('s1', 1, '2026-02-01T00:00:00Z', precision='day')]
    assert resolve_snapshot_at(IDENTITY, day, '2026-02-01T14:30:00Z') \
        .resolution == APPROXIMATE
    assert resolve_snapshot_at(IDENTITY, day, '2026-02-03T00:00:00Z') \
        .resolution == EXACT
    # the date's own span reaching the next start (an evidence year)
    soon = [S0, snap('s1', 1, '2026-02-01T00:00:00Z')]
    assert resolve_snapshot_at(IDENTITY, soon, '2026-01-15T00:00:00Z',
                               at_precision='month').resolution == \
        APPROXIMATE
    assert resolve_snapshot_at(IDENTITY, soon, '2026-01-15T00:00:00Z') \
        .resolution == EXACT


# FOLD -------------------------------------------------------------------------
def rec(rid, tier, quantity, value=None, rng=None, *, verification='unverified',
        status='published', superseded_by=None, observed='2026-02-27T00:00:00Z',
        uncertainty=None, derived=None, method='archival_document',
        payload=None, unit=None):
    spec = QUANTITY_BY_NAME[quantity]
    return {
        '_id': rid, 'identity_id': 'i1', 'method': method,
        'source_tier': tier, 'status': status,
        'superseded_by': superseded_by, 'observed_at': observed,
        'observed_at_precision': 'exact',
        'verification': {'state': verification},
        'summary': {'quantity': quantity, 'value': value, 'range': rng,
                    'unit': unit if unit is not None else spec.unit,
                    'kind': 'claimed', 'uncertainty': uncertainty},
        'derived': derived or [], 'payload': payload or {}}


def identity_fold(records, **kw):
    return fold(quantities_of_scope('identity'), records, now=NOW, **kw)


def test_the_highest_tier_wins_outright_and_the_rest_is_outranked():
    core = rec('core', 'destructive', 'compressive_strength', 38.3)
    old = rec('old', 'archival', 'compressive_strength', rng=[18, 28])
    guess = rec('guess', 'heuristic', 'compressive_strength', rng=[10, 40])
    result = identity_fold([old, guess, core])
    prop = result.properties['compressive_strength']
    assert prop['source'] == 'destructive' and prop['range'] == [38.3, 38.3]
    assert prop['n'] == 1 and prop['evidence_ids'] == ['core']
    assert prop['unit'] == 'MPa' and prop['inherited_from'] is None
    assert set(result.outranked['compressive_strength']) == {'old', 'guess'}
    # without the core the archival claim wins over the heuristic
    prop = identity_fold([old, guess]).properties['compressive_strength']
    assert prop['source'] == 'archival' and prop['range'] == [18, 28]


def test_ranking_differs_per_quantity():
    """concrete_class ranks archival above ndt (spec 2.6)."""
    claim = rec('claim', 'archival', 'concrete_class', rng=['B225'])
    derived = rec('reb', 'ndt', 'rebound_number', 43, method='rebound_hammer',
                  derived=[{'quantity': 'concrete_class', 'value': 'C16/20',
                            'range': None, 'unit': None, 'kind': 'derived',
                            'model': {'kind': 'din_en_13791_a20_na6'}}])
    prop = identity_fold([claim, derived]).properties['concrete_class']
    assert prop['source'] == 'archival' and prop['range'] == ['B225']
    only = identity_fold([derived]).properties['concrete_class']
    assert only['source'] == 'ndt' and only['range'] == ['C16/20']
    # rebound_number is ndt-only: an archival claim of it is never folded
    assert 'rebound_number' in identity_fold([derived]).properties


def test_derived_results_enter_with_the_records_tier():
    core = rec('core', 'destructive', 'compressive_strength', 38.3,
               method='core_compression',
               derived=[{'quantity': 'compressive_strength_in_situ',
                         'value': 31.4, 'range': None, 'unit': 'MPa',
                         'kind': 'derived',
                         'model': {'kind': 'en_13791'}}])
    rebound = rec('reb', 'ndt', 'rebound_number', 43,
                  method='rebound_hammer',
                  derived=[{'quantity': 'compressive_strength_in_situ',
                            'value': 28.0, 'range': None, 'unit': 'MPa',
                            'kind': 'derived',
                            'model': {'kind': 'en_13791_correlation'}}])
    result = identity_fold([core, rebound]).properties
    prop = result['compressive_strength_in_situ']
    # a strength estimated from a rebound set is outranked by a core's
    assert prop['source'] == 'destructive' and prop['range'] == [31.4, 31.4]
    assert prop['evidence_ids'] == ['core']
    only = identity_fold([rebound]).properties[
        'compressive_strength_in_situ']
    assert only['source'] == 'ndt' and only['range'] == [28.0, 28.0]
    # the measured quantity of the core is a separate property
    assert result['compressive_strength']['range'] == [38.3, 38.3]
    assert identity_fold([core, rebound]).outranked == {
        'compressive_strength_in_situ': ['reb']}


def test_range_uses_values_ranges_and_expanded_uncertainty():
    a = rec('a', 'destructive', 'compressive_strength', 38.3,
            uncertainty={'type': 'expanded', 'value': 1.2, 'k': 2})
    b = rec('b', 'destructive', 'compressive_strength', 36.0)
    c = rec('c', 'destructive', 'compressive_strength', rng=[40.0, 41.5])
    prop = identity_fold([a, b, c]).properties['compressive_strength']
    assert prop['range'] == [36.0, 41.5] and prop['n'] == 3
    only = identity_fold([a]).properties['compressive_strength']
    assert only['range'] == [37.1, 39.5]            # 38.3 -/+ 1.2
    # only an expanded uncertainty widens; a standard deviation does not
    sd = rec('sd', 'destructive', 'compressive_strength', 38.3,
             uncertainty={'type': 'stddev', 'value': 3.0})
    assert identity_fold([sd]).properties['compressive_strength'][
        'range'] == [38.3, 38.3]


def test_confidence_formula_count_and_verification_factor():
    def confidence(records):
        return identity_fold(records).properties[
            'compressive_strength']['confidence']
    one = rec('1', 'destructive', 'compressive_strength', 38.0)
    # (1 - (1 - 0.90) * n^-0.5) * v, v = 0.70 for unverified
    assert confidence([one]) == round((1 - 0.10) * 0.70, 4)
    four = [rec(str(i), 'destructive', 'compressive_strength', 38.0)
            for i in range(4)]
    assert confidence(four) == round((1 - 0.10 * 4 ** -0.5) * 0.70, 4)
    reviewed = [{**r, 'verification': {'state': 'reviewed'}} for r in four]
    assert confidence(reviewed) == round(1 - 0.10 * 4 ** -0.5, 4)
    mixed = [{**four[0], 'verification': {'state': 'accredited'}}, four[1],
             {**four[2], 'verification': {'state': 'self_attested'}},
             four[3]]
    factor = (1.0 + 0.70 + 0.85 + 0.70) / 4
    assert confidence(mixed) == round((1 - 0.10 * 4 ** -0.5) * factor, 4)
    # the cap
    many = [{**rec(str(i), 'destructive', 'compressive_strength', 38.0),
             'verification': {'state': 'accredited'}} for i in range(400)]
    assert confidence(many) == 0.99
    base = {t: 1 - (1 - b) for t, b in (('ndt', 0.60), ('archival', 0.40),
                                        ('visual', 0.30),
                                        ('heuristic', 0.20))}
    for tier, b in base.items():
        rec1 = rec('x', tier, 'compressive_strength', 20.0)
        got = identity_fold([rec1]).properties['compressive_strength'][
            'confidence']
        assert math.isclose(got, round(b * 0.70, 4))


def test_unpublished_corrected_and_excluded_records_are_not_folded():
    good = rec('good', 'destructive', 'compressive_strength', 38.3)
    drafts = [rec(s, 'destructive', 'compressive_strength', 99.0, status=s)
              for s in ('draft', 'pending', 'rejected', 'withdrawn')]
    corrected = rec('old', 'destructive', 'compressive_strength', 12.0,
                    superseded_by='good')
    bar = rec('bar', 'destructive', 'compressive_strength', 70.0,
              method='core_compression',
              payload={'specimen': {'valid_for_strength': False}})
    discarded = rec('disc', 'ndt', 'rebound_number', 80,
                    method='rebound_hammer', payload={'set_discarded': True})
    result = identity_fold([good, corrected, bar, discarded, *drafts])
    assert result.properties['compressive_strength']['evidence_ids'] == [
        'good']
    assert 'rebound_number' not in result.properties
    assert foldable([bar, discarded, corrected, good, *drafts]) == [good]
    assert identity_fold([]).properties == {}


def test_categorical_and_ordinal_ranges():
    a = rec('a', 'archival', 'exposure_class', rng=['XC4', 'XF1'])
    b = rec('b', 'archival', 'exposure_class', 'XC3')
    prop = identity_fold([a, b]).properties['exposure_class']
    assert prop['range'] == ['XC3', 'XC4', 'XF1'] and prop['unit'] is None
    snap_q = quantities_of_scope('snapshot')
    findings = [rec('s1', 'visual', 'spalling', 1, method='visual_inspection'),
                rec('s2', 'visual', 'spalling', 3, method='visual_inspection'),
                rec('g', 'visual', 'condition_grade', 2,
                    method='visual_inspection'),
                rec('w', 'visual', 'crack_width', 0.3,
                    method='visual_inspection')]
    result = fold(snap_q, findings, now=NOW).properties
    assert result['spalling']['range'] == [1, 3] and result['spalling'][
        'n'] == 2
    assert result['crack_width']['unit'] == 'mm'
    assert 'compressive_strength' not in result      # identity scope only


# INHERITANCE ------------------------------------------------------------------
def parent(pid, strength=None, conf=0.9, rng=None):
    props = {}
    if strength is not None:
        props['compressive_strength'] = {
            'range': rng or [strength, strength], 'unit': 'MPa',
            'confidence': conf, 'source': 'destructive', 'n': 2,
            'evidence_ids': ['x'], 'inherited_from': None,
            'derived_at': NOW}
    return {'_id': pid, 'properties': props}


def test_a_child_inherits_from_one_parent_with_reduced_confidence():
    p = parent('p1', 38.0, conf=0.9)
    got = identity_fold([], parents_of=lambda: [p]).properties[
        'compressive_strength']
    assert got['source'] == 'inherited' and got['range'] == [38.0, 38.0]
    assert got['confidence'] == round(0.9 * 0.8, 4)
    assert got['inherited_from'] == ['p1'] and got['n'] == 0
    assert got['evidence_ids'] == [] and got['unit'] == 'MPa'


def test_a_merge_takes_the_union_and_the_weakest_confidence():
    p1 = parent('p1', 38.0, conf=0.9, rng=[36.0, 40.0])
    p2 = parent('p2', 30.0, conf=0.5, rng=[28.0, 32.0])
    p3 = parent('p3')                                 # knows nothing
    got = identity_fold([], parents_of=lambda: [p1, p2, p3]).properties[
        'compressive_strength']
    assert got['range'] == [28.0, 40.0]
    assert got['confidence'] == round(0.5 * 0.8, 4)
    assert got['inherited_from'] == ['p1', 'p2']
    cat = {'_id': 'p', 'properties': {'concrete_class': {
        'range': ['B225'], 'unit': None, 'confidence': 0.4,
        'source': 'archival', 'n': 1, 'evidence_ids': [],
        'inherited_from': None, 'derived_at': NOW}}}
    cat2 = {'_id': 'q', 'properties': {'concrete_class': {
        'range': ['C20/25'], 'unit': None, 'confidence': 0.6,
        'source': 'archival', 'n': 1, 'evidence_ids': [],
        'inherited_from': None, 'derived_at': NOW}}}
    merged = identity_fold([], parents_of=lambda: [cat, cat2]).properties
    assert merged['concrete_class']['range'] == ['B225', 'C20/25']


def test_own_evidence_beats_inheritance_per_quantity():
    own = rec('own', 'archival', 'compressive_strength', rng=[20, 22])
    p = parent('p1', 38.0)
    calls = []

    def parents():
        calls.append(1)
        return [p]
    got = identity_fold([own], parents_of=parents).properties
    assert got['compressive_strength']['source'] == 'archival'
    assert calls == [1]            # asked once, for the other quantities
    # the snapshot target never inherits
    assert fold(quantities_of_scope('snapshot'), [], now=NOW).properties == {}


def test_a_grandchild_inherits_through_the_chain():
    grand = identity_fold([], parents_of=lambda: [parent('p1', 38.0, 0.9)])
    child = {'_id': 'c', 'properties': grand.properties}
    got = identity_fold([], parents_of=lambda: [child]).properties[
        'compressive_strength']
    assert got['confidence'] == round(0.9 * 0.8 * 0.8, 4)
    assert got['inherited_from'] == ['c']


# AS-OF SETS AND WINDOWS -------------------------------------------------------
def test_snapshot_inputs_follow_the_resolved_context():
    snaps = [S0, S1]
    r0 = rec('r0', 'visual', 'spalling', 1, observed='2025-01-01T00:00:00Z',
             method='visual_inspection')
    r1 = rec('r1', 'visual', 'spalling', 2, observed='2026-03-01T00:00:00Z',
             method='visual_inspection')
    early = rec('early', 'visual', 'spalling', 3,
                observed='2020-01-01T00:00:00Z', method='visual_inspection')
    core = rec('core', 'destructive', 'mass', 80.0, method='core_compression',
               observed='2026-03-05T00:00:00Z')
    core['sampled_at'] = '2025-06-01T00:00:00Z'      # sampled in v0's time
    core['sampled_at_precision'] = 'exact'
    left = {**IDENTITY, 'exit': {'kind': 'installed',
                                 'at': '2026-04-01T00:00:00Z'}}
    late = rec('late', 'visual', 'spalling', 3, observed='2026-09-01T00:00:00Z',
               method='visual_inspection')
    records = [r0, r1, early, core, late]
    contexts = contexts_for(left, snaps, records)
    assert contexts['r0'].snapshot_id == 's0'
    assert contexts['r1'].snapshot_id == 's1'
    assert contexts['early'].resolution == BEFORE_FIRST
    assert contexts['late'].resolution == AFTER_EXIT
    # a core resolves at sampled_at, not at the later test date
    assert contexts['core'].snapshot_id == 's0'
    assert [r['_id'] for r in snapshot_inputs(records, contexts, 's0')] == [
        'r0', 'core']
    assert [r['_id'] for r in snapshot_inputs(records, contexts, 's1')] == [
        'r1']
    result = fold(quantities_of_scope('snapshot'),
                  snapshot_inputs(records, contexts, 's1'), now=NOW)
    assert result.properties['spalling']['range'] == [2, 2]
    # before_first / after_exit records enter no snapshot but do enter the
    # identity-scoped fold
    ident = [rec('a', 'archival', 'density', 1700.0, observed='2020-01-01T'
                 '00:00:00Z')]
    assert identity_fold(ident).properties['density']['source'] == 'archival'


def test_window_for_the_as_of_view():
    a = rec('a', 'destructive', 'compressive_strength', 30.0,
            observed='2025-01-01T00:00:00Z')
    b = rec('b', 'destructive', 'compressive_strength', 40.0,
            observed='2026-01-01T00:00:00Z')
    assert [r['_id'] for r in window([a, b], '2025-06-01T00:00:00Z')] == ['a']
    got = identity_fold(window([a, b], '2025-06-01T00:00:00Z')).properties
    assert got['compressive_strength']['range'] == [30.0, 30.0]


def test_a_recompute_that_changes_nothing_is_recognised():
    records = [rec('a', 'destructive', 'compressive_strength', 30.0)]
    first = identity_fold(records).properties
    later = fold(quantities_of_scope('identity'), records,
                 now='2027-01-01T00:00:00Z').properties
    assert first != later and same_properties(first, later)
    kept = keep_derived_at(first, later)
    assert kept == first
    changed = fold(quantities_of_scope('identity'),
                   [rec('a', 'destructive', 'compressive_strength', 31.0)],
                   now='2027-01-01T00:00:00Z').properties
    assert not same_properties(first, changed)
    assert keep_derived_at(first, changed) == changed


# MERGED TIMELINE --------------------------------------------------------------
def test_the_merged_timeline():
    identity = {
        '_id': 'i1', 'origin': {'kind': 'deinstallation',
                                'at': '2024-07-24T00:00:00Z',
                                'at_precision': 'day'},
        'exit': {'kind': 'installed', 'at': '2026-05-01T00:00:00Z',
                 'at_precision': 'exact'},
        'past_cycles': []}
    snaps = [S0, snap('s1', 1, '2026-02-01T00:00:00Z', superseded_by='s2'),
             snap('s2', 2, '2026-02-01T00:00:00Z', supersedes='s1')]
    early = rec('early', 'visual', 'condition_grade', 2,
                observed='2020-01-01T00:00:00Z', method='visual_inspection')
    mid = rec('mid', 'destructive', 'compressive_strength', 38.3,
              observed='2026-03-01T00:00:00Z', method='core_compression')
    old = rec('old', 'visual', 'spalling', 1, observed='2026-03-02T00:00:00Z',
              method='visual_inspection', superseded_by='mid')
    late = rec('late', 'visual', 'spalling', 2, observed='2026-09-01T00:00:00Z',
               method='visual_inspection')
    records = [early, mid, old, late]
    contexts = contexts_for(identity, snaps, records)
    changes = [{'at': '2026-02-10T00:00:00Z', 'cause': 'patch',
                'changes': [{'path': 'trade_name', 'old': 'a', 'new': 'b'}]}]
    events = build_timeline(identity, snaps, records, contexts, changes)
    kinds = [(e['kind'], e.get('record_id') or e.get('detail'))
             for e in events]
    assert kinds == [
        ('evidence', 'early'), ('origin', 'deinstallation'),
        ('snapshot', 's0'), ('snapshot', 's1'), ('snapshot', 's2'),
        ('metadata_changed', None), ('evidence', 'mid'),
        ('evidence', 'old'), ('exit', 'installed'), ('evidence', 'late')]
    by_id = {e.get('record_id'): e for e in events if e.get('record_id')}
    assert by_id['early']['section'] == 'before_cataloguing'
    assert by_id['late']['section'] == 'after_leaving_circulation'
    assert by_id['mid']['section'] == 'history'
    assert by_id['s1']['corrected'] is True
    assert by_id['s2']['corrects'] == 's1'
    assert by_id['old']['corrected'] is True
    assert by_id['mid']['snapshot_id'] == 's2'
    # a viewer outside the dataset sees only that metadata changed
    outside = build_timeline(identity, snaps, records, contexts, changes,
                             members=False)
    changed = [e for e in outside if e['kind'] == 'metadata_changed'][0]
    assert 'paths' not in changed and changed['at'] == '2026-02-10T00:00:00Z'
