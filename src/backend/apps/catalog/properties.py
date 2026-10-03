#!/usr/bin/env python3.13
"""
The property fold (data model spec section 4.4; decisions 6.13, 8.10, 8.12).

One pure function with two call sites that differ only in the input and the
target: ``identity.properties`` (every published, non-superseded record, the
quantities of scope ``identity``, with inheritance from the parents) and
``snapshot.properties`` (the records whose resolved context is that
snapshot, the quantities of scope ``snapshot``). The routes load the
documents and write the result; nothing here touches a database.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.evidence.registry import SPEC_BY_NAME, is_excluded_from_fold
from apps.catalog.timeline import Context, context_time, resolve_snapshot_at
from apps.catalog.timeutil import parse_ts
from apps.catalog.vocab import (
    CONFIDENCE_CAP,
    FOLD_ALPHA,
    INHERIT_K,
    QUANTITIES,
    TIER_BASE_CONFIDENCE,
    VERIFICATION_FACTOR,
    Quantity,
)

PROPERTIES_VERSION = 1            # a rule change bumps it (--recompute)


@dataclass
class FoldResult:
    properties: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # quantity -> ids of records a higher tier outranked (not superseded)
    outranked: Dict[str, List[str]] = field(default_factory=dict)


def quantities_of_scope(scope: str) -> Tuple[Quantity, ...]:
    return tuple(q for q in QUANTITIES if q.scope == scope)


def foldable(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Published and not corrected, minus real observations that must not
    count (a discarded rebound set, a core invalid for strength)."""
    return [r for r in records
            if r.get('status') == 'published'
            and not r.get('superseded_by')
            and not is_excluded_from_fold(r)]


def _uncertainty(result: Dict[str, Any]) -> float:
    """The expanded uncertainty of a result, else 0 (a derived result
    carries none)."""
    uncertainty = result.get('uncertainty') or {}
    if uncertainty.get('type') == 'expanded' \
            and uncertainty.get('value') is not None:
        return float(uncertainty['value'])
    return 0.0


def _bounds(quantity: Quantity, results: Sequence[Dict[str, Any]]
            ) -> List[Any]:
    """The range a set of results spans: the distinct values of a
    categorical quantity, min..max of an ordinal one, and lo..hi of a
    scalar one (a result's own range, else value -/+ its uncertainty)."""
    if quantity.kind == 'categorical':
        values = set()
        for r in results:
            if r.get('value') is not None:
                values.add(r['value'])
            values.update(r.get('range') or [])
        return sorted(values)
    lows, highs = [], []
    for r in results:
        rng = r.get('range')
        if rng:
            lows.append(rng[0])
            highs.append(rng[1])
        else:
            u = _uncertainty(r) if quantity.kind == 'scalar' else 0.0
            lows.append(r['value'] - u)
            highs.append(r['value'] + u)
    low, high = min(lows), max(highs)
    if quantity.kind == 'scalar':
        low, high = round(low, 6), round(high, 6)
    return [low, high]


def _union(quantity: Quantity, ranges: Sequence[Sequence[Any]]) -> List[Any]:
    if quantity.kind == 'categorical':
        return sorted({v for rng in ranges for v in rng})
    return [min(rng[0] for rng in ranges), max(rng[-1] for rng in ranges)]


def fold(quantities: Iterable[Quantity], evidence: Sequence[Dict[str, Any]],
         *, parents_of: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
         now: str) -> FoldResult:
    """
    ``evidence`` is already filtered to the target (the caller applies the
    as-of context); this keeps the published, non-superseded, usable
    records. For each quantity the highest tier present wins outright; the
    range spans its results, ``n`` counts records, the confidence grows
    with ``n`` toward the tier's base and is scaled by the mean
    verification factor. A quantity without evidence is inherited from the
    parents (identity target only): the union of their ranges, the weakest
    confidence times ``INHERIT_K``.

    ``parents_of`` returns the parents as ``{'_id', 'properties'}``
    documents; it is only called when a quantity needs it.
    """
    records = foldable(evidence)
    out = FoldResult()
    parents: Optional[Sequence[Dict[str, Any]]] = None
    for quantity in quantities:
        rq = [(e, r) for e in records
              for r in [e['summary'], *(e.get('derived') or [])]
              if r.get('quantity') == quantity.name
              and e.get('source_tier') in quantity.ranking]
        if rq:
            top = next(t for t in quantity.ranking
                       if any(e['source_tier'] == t for e, _ in rq))
            top_results = [(e, r) for e, r in rq if e['source_tier'] == top]
            n = len(top_results)
            factor = sum(VERIFICATION_FACTOR[
                (e.get('verification') or {}).get('state') or 'unverified']
                for e, _ in top_results) / n
            base = TIER_BASE_CONFIDENCE[top]
            confidence = min(
                CONFIDENCE_CAP,
                (1 - (1 - base) * n ** -FOLD_ALPHA) * factor)
            ids = sorted({e['_id'] for e, _ in top_results},
                         key=lambda i: (next(
                             e['observed_at'] for e, _ in top_results
                             if e['_id'] == i), i))
            out.properties[quantity.name] = {
                'range': _bounds(quantity, [r for _, r in top_results]),
                'unit': quantity.unit, 'confidence': round(confidence, 4),
                'source': top, 'n': n, 'evidence_ids': ids,
                'inherited_from': None, 'derived_at': now}
            outranked = [e['_id'] for e, _ in rq
                         if e['source_tier'] != top]
            if outranked:
                out.outranked[quantity.name] = list(dict.fromkeys(outranked))
        elif parents_of is not None:
            if parents is None:
                parents = list(parents_of())
            have = [p for p in parents
                    if (p.get('properties') or {}).get(quantity.name)]
            if have:
                values = [p['properties'][quantity.name] for p in have]
                out.properties[quantity.name] = {
                    'range': _union(quantity, [v['range'] for v in values]),
                    'unit': quantity.unit,
                    'confidence': round(
                        min(v['confidence'] for v in values) * INHERIT_K, 4),
                    'source': 'inherited', 'n': 0, 'evidence_ids': [],
                    'inherited_from': [p['_id'] for p in have],
                    'derived_at': now}
    return out


# CONTEXTS --------------------------------------------------------------------
def contexts_for(identity: Dict[str, Any],
                 snapshots: Sequence[Dict[str, Any]],
                 records: Iterable[Dict[str, Any]]) -> Dict[str, Context]:
    """Evidence id -> the state of the piece it belongs to (spec 4.1): a
    core resolves at ``sampled_at``, everything else at ``observed_at``."""
    out: Dict[str, Context] = {}
    for record in records:
        spec = SPEC_BY_NAME.get(record.get('method'))
        at, precision = context_time(
            record, spec.context_time if spec else 'observed_at')
        out[record['_id']] = resolve_snapshot_at(
            identity, snapshots, at, at_precision=precision)
    return out


def snapshot_inputs(records: Iterable[Dict[str, Any]],
                    contexts: Dict[str, Context],
                    snapshot_id: str) -> List[Dict[str, Any]]:
    """The as-of set of one snapshot: records whose context is it;
    ``before_first`` and ``after_exit`` records enter none (8.10)."""
    return [r for r in records
            if contexts.get(r['_id']) is not None
            and contexts[r['_id']].snapshot_id == snapshot_id]


def same_properties(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Whether two property sets say the same, ``derived_at`` aside, so a
    recompute that changes nothing writes nothing and propagates nothing."""
    def bare(props: Dict[str, Any]):
        return {q: {k: v for k, v in value.items() if k != 'derived_at'}
                for q, value in (props or {}).items()}
    return bare(a) == bare(b)


def keep_derived_at(old: Dict[str, Any], new: Dict[str, Any]
                    ) -> Dict[str, Any]:
    """``new`` with the old ``derived_at`` of every property that did not
    change."""
    out = {}
    for name, value in new.items():
        before = (old or {}).get(name)
        same = before is not None and {
            k: v for k, v in before.items() if k != 'derived_at'} == {
            k: v for k, v in value.items() if k != 'derived_at'}
        out[name] = {**value, 'derived_at': before['derived_at']} \
            if same else value
    return out


def window(records: Iterable[Dict[str, Any]], as_of: str
           ) -> List[Dict[str, Any]]:
    """Records observed up to ``as_of`` (``GET .../properties?as_of=``:
    identity-scoped quantities over a time window, computed not stored)."""
    limit = parse_ts(as_of)
    return [r for r in records
            if r.get('observed_at') and parse_ts(r['observed_at']) <= limit]
