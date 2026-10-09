#!/usr/bin/env python3.13
"""
The evidence method registry (data model spec section 4.5): turns what a
client sends into the record that is stored, or refuses it with every
problem found.

``prepare_record`` is pure: it validates the payload against the method's
model, lets the method recompute and cross-check its server fields, derives
the headline result where the method can, converts units to the canonical
ones (section 2.6), checks the derived results against their models'
conditions (decision 8.41) and the quantity's tier ranking, and returns the
fields of the record. The routes add what needs the database (identity,
snapshot, pairing, exit rules) and the lifecycle.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import ValidationError

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import DerivedResult, Position, Standard, Summary
from apps.catalog.evidence import core, rebound
from apps.catalog.evidence.specs import ALL_EVIDENCE_SPECS
from apps.catalog.evidence.types import (
    EvidenceInvalid,
    EvidenceMethodSpec,
    PairingFacts,
    Problem,
)
from apps.catalog.timeutil import parse_ts
from apps.catalog.units import accepted_units, convert, factor
from apps.catalog.vocab import QUANTITY_BY_NAME, QUANTITY_LABELS

SPEC_BY_NAME: Dict[str, EvidenceMethodSpec] = {
    spec.name: spec for spec in ALL_EVIDENCE_SPECS}
# the instrumental methods and the layout say where on the piece; a claim
# without a position is about the whole component
POSITION_REQUIRED = ('rebound_hammer', 'core_compression',
                     'reinforcement_layout')
WHOLE_COMPONENT = {'kind': 'none', 'description': 'whole component'}
RESULT_FIELDS = (
    'method', 'method_version', 'source_tier', 'standard', 'observed_at',
    'observed_at_precision', 'sampled_at', 'sampled_at_precision',
    'position', 'summary', 'derived', 'payload', 'destructive')


@dataclass
class PreparedRecord:
    """The fields ``prepare_record`` computed, and what it noticed."""
    fields: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    excluded_from_fold: bool = False


def method_spec(name: str) -> EvidenceMethodSpec:
    spec = SPEC_BY_NAME.get(name)
    if spec is None:
        raise EvidenceInvalid([Problem(
            'method', f'unknown method {name!r}; one of '
                      f'{sorted(SPEC_BY_NAME)}')])
    return spec


def _validation_problems(exc: ValidationError, prefix: str) -> List[Problem]:
    out = []
    for error in exc.errors():
        where = '.'.join([prefix] + [str(p) for p in error.get('loc', ())])
        out.append(Problem(where, error['msg']))
    return out


# RESULTS ---------------------------------------------------------------------
def _normalized_result(result: Dict[str, Any], where: str,
                       problems: List[Problem], *, entered: bool
                       ) -> Optional[Dict[str, Any]]:
    """A result with its values converted to the quantity's canonical unit;
    ``unit`` is the unit the values are in (a canonical one needs no
    conversion), ``unit_entered`` remembers what was typed."""
    quantity = QUANTITY_BY_NAME.get(result.get('quantity'))
    if quantity is None:
        problems.append(Problem(f'{where}.quantity', 'unknown quantity '
                                f'{result.get("quantity")!r}'))
        return None
    out = dict(result)
    typed = result.get('unit')
    if quantity.unit is None:
        if typed not in (None, ''):
            problems.append(Problem(f'{where}.unit',
                                    f'{quantity.name} has no unit'))
            return None
        out['unit'] = None
        return out
    try:
        scale = factor(typed or None, quantity.unit)
    except ValueError as exc:
        problems.append(Problem(f'{where}.unit', str(exc)))
        return None
    if scale != 1.0:
        numbers = ([out['value']] if out.get('value') is not None else []) \
            + list(out.get('range') or []) \
            + ([out['uncertainty']['value']] if (
                out.get('uncertainty') or {}).get('value') is not None
               else [])
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in numbers):
            problems.append(Problem(
                f'{where}.unit',
                f'{quantity.name} is a number: a value in {typed!r} cannot '
                f'be converted from text'))
            return None
        if out.get('value') is not None:
            out['value'] = convert(out['value'], typed, quantity.unit)
        if out.get('range'):
            out['range'] = [convert(v, typed, quantity.unit)
                            for v in out['range']]
        uncertainty = out.get('uncertainty')
        if uncertainty and uncertainty.get('value') is not None:
            out['uncertainty'] = {**uncertainty, 'value': convert(
                uncertainty['value'], typed, quantity.unit)}
    out['unit'] = quantity.unit
    if entered and typed not in (None, quantity.unit):
        out['unit_entered'] = typed
    return out


def _same_result(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Server-derived against client-sent headline results."""
    def close(x, y):
        if x is None or y is None:
            return x is y
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-9)
        return x == y
    if a['quantity'] != b['quantity'] or a.get('kind') != b.get('kind'):
        return False
    if not close(a.get('value'), b.get('value')):
        return False
    ra, rb = a.get('range'), b.get('range')
    if bool(ra) != bool(rb):
        return False
    return not ra or all(close(x, y) for x, y in zip(ra, rb))


def _check_ranking(result: Dict[str, Any], tier: str, where: str,
                   problems: List[Problem]) -> None:
    quantity = QUANTITY_BY_NAME[result['quantity']]
    if tier not in quantity.ranking:
        problems.append(Problem(
            f'{where}.quantity',
            f'{quantity.name} is not folded from {tier} evidence (it takes '
            f'{list(quantity.ranking)})'))


# THE RECORD ------------------------------------------------------------------
def prepare_record(data: Dict[str, Any], *,
                   pairing: Optional[PairingFacts] = None) -> PreparedRecord:
    """Validate and complete one record; raises ``EvidenceInvalid`` listing
    every problem. ``data`` holds the client's fields: ``method``,
    ``payload``, and any of ``standard``, ``observed_at``(+``_precision``),
    ``sampled_at``(+``_precision``), ``position``, ``summary``,
    ``derived``."""
    spec = method_spec(data.get('method'))
    try:
        model = spec.payload_model.model_validate(data.get('payload') or {})
    except ValidationError as exc:
        raise EvidenceInvalid(_validation_problems(exc, 'payload')) from exc
    prepared = spec.prepare(model, data)
    problems: List[Problem] = list(prepared.errors)
    warnings = list(prepared.warnings)

    # source tier (7.8: a layout's follows its basis)
    tier = spec.source_tier or prepared.source_tier
    if tier is None and spec.tier_of is not None:
        tier = spec.tier_of(prepared.payload)
    if tier is None:
        problems.append(Problem('payload', 'the source tier cannot be '
                                           'derived'))
        raise EvidenceInvalid(problems)

    # times: the payload decides them where it carries them (a core)
    times: Dict[str, Optional[str]] = {}
    for name, from_payload in (('observed_at', prepared.observed_at),
                               ('sampled_at', prepared.sampled_at)):
        sent = data.get(name)
        if from_payload is not None:
            if sent is not None and parse_ts(sent) != parse_ts(from_payload):
                problems.append(Problem(
                    name, f'must equal the date in the payload '
                          f'({from_payload}); leave it out and the server '
                          f'takes it'))
            times[name] = from_payload
        else:
            times[name] = sent
    if times['observed_at'] is None:
        problems.append(Problem('observed_at', 'when the result was '
                                               'produced'))
    observed_precision = data.get('observed_at_precision') or 'exact'
    sampled_precision = (data.get('sampled_at_precision') or 'exact') \
        if times['sampled_at'] else None
    if times['observed_at'] and times['sampled_at'] and \
            parse_ts(times['observed_at']) < parse_ts(times['sampled_at']):
        problems.append(Problem('observed_at', 'must not be before '
                                               'sampled_at (I10)'))

    # standard
    standard = data.get('standard') or spec.default_standard
    if standard is not None:
        try:
            standard = Standard.model_validate(standard).model_dump()
        except ValidationError as exc:
            problems.extend(_validation_problems(exc, 'standard'))

    # position: a grid dictates a region on the picked snapshot (8.43)
    position = data.get('position')
    if position is None and spec.name not in POSITION_REQUIRED:
        position = dict(WHOLE_COMPONENT)
    if position is None:
        problems.append(Problem(
            'position', 'say where on the piece: kind none with a '
                        'description is always enough'))
    else:
        position = dict(position)
        if prepared.position is not None:
            if position.get('kind') not in (None, 'region'):
                problems.append(Problem('position.kind',
                                        'a grid test area is a region'))
            centre = prepared.position['point']
            sent = position.get('point')
            if sent is not None and max(abs(a - b) for a, b in
                                        zip(sent, centre)) \
                    > rebound.POINT_TOLERANCE_MM:
                problems.append(Problem(
                    'position.point',
                    f'the server sets it to the grid centre {centre}'))
            position.update(prepared.position)
            if position.get('snapshot_id') is None:
                problems.append(Problem(
                    'position.snapshot_id',
                    'a grid is laid on a snapshot: name the snapshot whose '
                    'coordinates it uses'))
        if spec.name == 'reinforcement_layout' \
                and position.get('snapshot_id') is None:
            problems.append(Problem(
                'position.snapshot_id',
                'a reinforcement layout names its snapshot: the bar '
                'coordinates are in its stored coordinates (I23)'))
        try:
            position = Position.model_validate(position).model_dump()
        except ValidationError as exc:
            problems.extend(_validation_problems(exc, 'position'))

    # headline result
    summary = _headline(spec, prepared, data.get('summary'), tier, problems)

    # derived results
    derived = _derived(spec, prepared, data.get('derived') or [], tier,
                       problems)
    if summary is not None and any(
            d['quantity'] == summary['quantity'] for d in derived):
        problems.append(Problem(
            'derived', 'a derived result never shadows the measured one: '
                       'one result per quantity per record (I7)'))

    if spec.name == 'core_compression' and pairing is not None:
        problems.extend(core.pairing_problems(prepared.payload, pairing))
    if problems:
        raise EvidenceInvalid(problems)

    fields = {
        'method': spec.name, 'method_version': spec.version,
        'source_tier': tier, 'standard': standard,
        'observed_at': times['observed_at'],
        'observed_at_precision': observed_precision,
        'sampled_at': times['sampled_at'],
        'sampled_at_precision': sampled_precision,
        'position': position, 'summary': summary, 'derived': derived,
        'payload': prepared.payload, 'destructive': spec.destructive,
    }
    return PreparedRecord(fields=fields, warnings=warnings,
                          excluded_from_fold=prepared.excluded_from_fold)


def _headline(spec: EvidenceMethodSpec, prepared, sent: Optional[dict],
              tier: str, problems: List[Problem]) -> Optional[dict]:
    where = 'summary'
    sent_norm = None
    if sent is not None:
        sent_norm = _normalized_result(sent, where, problems, entered=True)
    if prepared.summary is None and not spec.summary_from_client:
        return None                           # derivation failed: reported
    if prepared.summary is None:              # a claim: the client's
        if sent is None and spec.summary_optional                 and not (prepared.payload or {}).get('claim'):
            return None                       # a document (8.106)
        if sent is None:
            problems.append(Problem(where, 'the claim: a quantity and a '
                                           'value or a range'))
            return None
        result = sent_norm
        if result is None:
            return None
        kind = spec.summary_kind
        if result.get('kind') != kind:
            problems.append(Problem(f'{where}.kind',
                                    f'a {spec.name} result is {kind}'))
    else:                                     # the server derives it
        result = dict(prepared.summary)
        if sent_norm is not None:
            if not _same_result(prepared.summary, sent_norm):
                mine = prepared.summary
                shown = mine.get('range') if mine.get('value') is None \
                    else mine['value']
                problems.append(Problem(
                    where, f'the server derives {mine["quantity"]} = '
                           f'{shown} from the payload; got a different '
                           f'result'))
            if sent_norm.get('uncertainty') is not None:
                result['uncertainty'] = sent_norm['uncertainty']
            if sent_norm.get('unit_entered'):
                result['unit_entered'] = sent_norm['unit_entered']
    if result is None:
        return None
    if result['quantity'] not in spec.summary_quantities:
        problems.append(Problem(
            f'{where}.quantity',
            f'{spec.name} records are about '
            f'{list(spec.summary_quantities)}; got {result["quantity"]}'))
        return None
    _check_ranking(result, tier, where, problems)
    try:
        Summary.model_validate(result)
    except ValidationError as exc:
        problems.extend(_validation_problems(exc, where))
        return None
    return result


def _derived(spec: EvidenceMethodSpec, prepared, incoming: List[dict],
             tier: str, problems: List[Problem]) -> List[dict]:
    out: List[dict] = []
    server_kinds = spec.server_derived_kinds
    allowed = {k.kind: k for k in spec.derived_kinds}
    for i, entry in enumerate(incoming):
        where = f'derived.{i}'
        kind = ((entry or {}).get('model') or {}).get('kind')
        if kind in server_kinds:
            continue                           # the server builds it
        if kind not in allowed:
            problems.append(Problem(
                f'{where}.model.kind',
                f'{spec.name} has no derived model {kind!r}; '
                f'{sorted(allowed) or "none"} are known'))
            continue
        norm = _normalized_result(entry, where, problems, entered=False)
        if norm is None:
            continue
        spec_kind = allowed[kind]
        if norm['quantity'] != spec_kind.quantity:
            problems.append(Problem(
                f'{where}.quantity', f'{kind} yields {spec_kind.quantity}'))
            continue
        try:
            DerivedResult.model_validate(norm)
        except ValidationError as exc:
            problems.extend(_validation_problems(exc, where))
            continue
        if spec.name == 'rebound_hammer':
            problems.extend(rebound.check_derived(norm, prepared.payload,
                                                  where))
        _check_ranking(norm, tier, where, problems)
        out.append(norm)
    out.extend(prepared.derived)
    return out


# STORED RECORDS --------------------------------------------------------------
def is_excluded_from_fold(record: Dict[str, Any]) -> bool:
    """A discarded rebound set or a core with a longitudinal bar is a real
    observation that must not count (A.1, A.2): read from the stored
    payload, where the server wrote the verdict."""
    payload = record.get('payload') or {}
    method = record.get('method')
    if method == 'rebound_hammer':
        return bool(payload.get('set_discarded'))
    if method == 'core_compression':
        return (payload.get('specimen') or {}).get(
            'valid_for_strength') is False
    return False


def record_warnings(record: Dict[str, Any]) -> List[str]:
    """The warnings of a stored record, computed from it (they are never
    stored, so a rule change shows at once)."""
    try:
        return prepare_record({k: record.get(k) for k in RESULT_FIELDS}
                              ).warnings
    except EvidenceInvalid:
        return []


# INTROSPECTION ---------------------------------------------------------------
def describe_method(spec: EvidenceMethodSpec) -> Dict[str, Any]:
    """One method as ``GET /evidence/methods`` serves it; the field
    descriptions of the payload schema are the help texts of the form."""
    return {
        'name': spec.name, 'label': spec.label,
        'description': spec.description,
        'source_tier': spec.source_tier,
        'tier_from_payload': spec.source_tier is None,
        'destructive': spec.destructive,
        'default_standard': spec.default_standard,
        'summary_quantities': list(spec.summary_quantities),
        'summary_from_client': spec.summary_from_client,
        'summary_optional': spec.summary_optional,
        'summary_kind': spec.summary_kind,
        'context_time': spec.context_time,
        'position_required': spec.name in POSITION_REQUIRED,
        'version': spec.version,
        'derived_models': [{
            'kind': k.kind, 'quantity': k.quantity, 'label': k.label,
            'description': k.description, 'server_built': k.server_built,
            'needs_note': k.needs_note, 'needs_reference': k.needs_reference,
        } for k in spec.derived_kinds],
        'payload_schema': spec.payload_model.model_json_schema(
            by_alias=True),
    }


def describe_quantities() -> List[Dict[str, Any]]:
    """The quantity vocabulary with units, scope, ranking and the mapping
    columns of spec 7.8 (the form's quantity pickers and unit lists)."""
    return [{
        'name': q.name, 'label': QUANTITY_LABELS.get(q.name, q.name),
        'unit': q.unit, 'kind': q.kind, 'scope': q.scope,
        'ranking': list(q.ranking), 'ordinal_direction': q.ordinal_direction,
        'applies_to': list(q.applies_to) if q.applies_to else None,
        'values': list(q.values) if q.values else None,
        'accepted_units': list(accepted_units(q.unit)) if q.unit else None,
        'mapping': {'qudt_unit': q.qudt_unit, 'cero': q.cero,
                    'ifc_property': q.ifc_property, 'bsdd': q.bsdd},
    } for q in QUANTITY_BY_NAME.values()]


def paired_rebound_id(data: Dict[str, Any]) -> Optional[str]:
    """The rebound record a core names, from the client's raw data (the
    route loads it for the pairing checks)."""
    if data.get('method') != 'core_compression':
        return None
    sampling = (data.get('payload') or {}).get('sampling') or {}
    value = sampling.get('paired_rebound_id')
    return value if isinstance(value, str) else None


def tier_ranking_has(quantity: str, tier: str) -> bool:
    return tier in QUANTITY_BY_NAME[quantity].ranking


ALL_METHOD_NAMES: Tuple[str, ...] = tuple(SPEC_BY_NAME)
