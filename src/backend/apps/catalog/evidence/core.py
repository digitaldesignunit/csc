#!/usr/bin/env python3.13
"""
The drilled core in compression (spec A.2, EN 12504-1:2019, EN 12390-3:2019,
EN 13791:2019 with DIN EN 13791/A20:2022-04; decisions 8.40 - 8.42): F / A,
the length-to-diameter class, validity for strength, the in-situ conversion,
and the pairing to a rebound record. Pure functions.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import math
from typing import Any, Dict, List, Optional

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.timeutil import parse_ts
from apps.catalog.evidence.payloads import CoreCompressionPayload
from apps.catalog.evidence.types import (
    DerivedModelKind,
    PairingFacts,
    Prepared,
    Problem,
)

AREA_TOLERANCE = 0.01               # cross-section area against pi d^2 / 4
STRENGTH_TOLERANCE = 0.01           # fc_core against F / A, "within 1 %"
LOAD_RATE_RANGE = (0.4, 0.8)        # warn outside (0.6 +- 0.2 MPa/s)
SMALL_CORE_MM = 75.0                # EN 13791: below only if impractical
MIN_CORE_MM = 50.0
CUBE_DIAMETERS_MM = (50.0, 150.0)   # German annex NA.7
LD_LIMITS = (('2:1', 1.95, 2.05), ('1:1', 0.90, 1.10))
LENGTH_FACTOR_1_TO_1 = 0.82         # EN 13791:2019, normal concrete
AGGREGATE_RATIO_MIN = 3.0
CONVERSION_BASIS = 'EN 13791:2019 + DIN EN 13791/A20:2022-04'

DERIVED_KINDS = (
    DerivedModelKind(
        'en_13791', 'compressive_strength_in_situ',
        'EN 13791:2019 in-situ strength of a core',
        'f_c,is of the core: a 2:1 core is f_c,is, a 1:1 core is multiplied '
        'by the core length factor 0.82. Built by the server.',
        server_built=True),
)


def round_tenth(value: float) -> float:
    return math.floor(value * 10 + 0.5) / 10


def ld_class(ratio: float) -> str:
    for name, low, high in LD_LIMITS:
        if low <= ratio <= high:
            return name
    return 'other'


def prepare(model: CoreCompressionPayload, ctx: Dict[str, Any]) -> Prepared:
    """Recompute A, F / A, the l/d ratio and class, validity for strength
    and the in-situ conversions; cross-check what the client sent."""
    payload = model.model_dump(by_alias=True, mode='json')
    problems: List[Problem] = []
    warnings: List[str] = []
    specimen, test, result = (payload['specimen'], payload['test'],
                              payload['result'])
    sampling = payload['sampling']
    diameter = specimen['measured_diameter_mm']

    # cross-section area, A_c from the mean diameter
    area_calc = math.pi * diameter ** 2 / 4.0
    area = test.get('cross_section_area_mm2')
    if area is None:
        area = round(area_calc, 1)
    elif abs(area - area_calc) / area_calc > AREA_TOLERANCE:
        problems.append(Problem(
            'payload.test.cross_section_area_mm2',
            f'differs from pi d^2 / 4 = {area_calc:.1f} mm2 by more than '
            f'1 %'))
    test['cross_section_area_mm2'] = area

    # f_c = F / A_c to 0.1 MPa
    fc_calc = test['max_load_kn'] * 1000.0 / area
    fc = result.get('fc_core_mpa')
    if fc is None:
        fc = round_tenth(fc_calc)
    elif abs(fc - fc_calc) / fc_calc > STRENGTH_TOLERANCE:
        problems.append(Problem(
            'payload.result.fc_core_mpa',
            f'F / A is {fc_calc:.1f} MPa; the value differs by more than '
            f'1 % (check the transcription of F and the diameter)'))
    result['fc_core_mpa'] = fc

    # length-to-diameter ratio and class
    length = specimen.get('length_prepared_mm') \
        or specimen.get('length_as_drilled_mm')
    ratio_class: Optional[str] = None
    if length is None:
        problems.append(Problem(
            'payload.specimen.length_prepared_mm',
            'give the prepared length (or the length as drilled): the '
            'length-to-diameter class needs it'))
    else:
        ratio = length / diameter
        ratio_class = ld_class(ratio)
        for field, server in (('length_diameter_ratio', round(ratio, 3)),
                              ('ld_class', ratio_class)):
            sent = specimen.get(field)
            if sent is not None and (
                    abs(sent - server) > 0.01 if field.endswith('ratio')
                    else sent != server):
                problems.append(Problem(
                    f'payload.specimen.{field}',
                    f'the server computes {server!r}; got {sent!r}'))
        specimen['length_diameter_ratio'] = round(ratio, 3)
        specimen['ld_class'] = ratio_class

    # a longitudinal bar makes the core invalid for strength
    valid = not any(bar['orientation'] == 'longitudinal'
                    for bar in specimen['reinforcement'])
    sent = specimen.get('valid_for_strength')
    if sent is not None and sent != valid:
        problems.append(Problem('payload.specimen.valid_for_strength',
                                f'the server computes {valid!r} from the '
                                f'reinforcement; got {sent!r}'))
    specimen['valid_for_strength'] = valid

    # in-situ strength (EN 13791) and the German cube equivalence (NA.7)
    cyl: Optional[float] = None
    cube: Optional[float] = None
    if valid and ratio_class is not None and diameter >= MIN_CORE_MM:
        if ratio_class == '2:1':
            cyl = fc
        elif ratio_class == '1:1':
            cyl = round_tenth(fc * LENGTH_FACTOR_1_TO_1)
            if CUBE_DIAMETERS_MM[0] <= diameter <= CUBE_DIAMETERS_MM[1]:
                cube = fc
    for field, server in (('fc_is_cyl_mpa', cyl), ('fc_is_cube_mpa', cube)):
        sent = result.get(field)
        if sent is not None and (server is None
                                 or abs(sent - server) > 0.05):
            problems.append(Problem(
                f'payload.result.{field}',
                f'the server computes {server!r}; got {sent!r}'))
        result[field] = server
    basis = CONVERSION_BASIS if (cyl is not None or cube is not None) \
        else None
    if result.get('conversion_basis') not in (None, basis):
        problems.append(Problem('payload.result.conversion_basis',
                                f'the server sets {basis!r}'))
    result['conversion_basis'] = basis

    derived: List[Dict[str, Any]] = []
    if cyl is not None:
        note = ('2:1 core: f_c,is equals the core strength'
                if ratio_class == '2:1'
                else '1:1 core multiplied by the core length factor 0.82')
        derived.append({
            'quantity': 'compressive_strength_in_situ', 'value': cyl,
            'range': None, 'unit': 'MPa', 'kind': 'derived',
            'model': {'kind': 'en_13791', 'reference': CONVERSION_BASIS,
                      'note': note}})

    # warnings
    if diameter < SMALL_CORE_MM:
        warnings.append(
            f'diameter {diameter:g} mm is below 75 mm: EN 13791 accepts it '
            f'only when larger cores are impractical, then as 1:1 cores and '
            f'three per location')
    rate = test.get('loading_rate_mpa_s')
    if rate is not None and not LOAD_RATE_RANGE[0] <= rate <= LOAD_RATE_RANGE[1]:
        warnings.append(f'loading rate {rate:g} MPa/s is outside '
                        f'{LOAD_RATE_RANGE[0]} - {LOAD_RATE_RANGE[1]} '
                        f'(0.6 +- 0.2, EN 12390-3)')
    dmax = specimen.get('max_aggregate_size_mm')
    if dmax and diameter / dmax < AGGREGATE_RATIO_MIN:
        warnings.append('the diameter is under 3 times the maximum '
                        'aggregate size: the result is biased')
    if ratio_class == 'other':
        warnings.append('the length-to-diameter ratio is neither 2:1 '
                        '(1.95 - 2.05) nor 1:1 (0.90 - 1.10): no in-situ '
                        'strength is derived')
    if not valid:
        warnings.append('a longitudinal bar: the core is invalid for '
                        'strength; the record stays and does not count in '
                        'the property fold (redrill)')
    if diameter < MIN_CORE_MM:
        warnings.append('under 50 mm: no in-situ strength is derived')

    summary = {'quantity': 'compressive_strength', 'value': fc,
               'range': None, 'unit': 'MPa', 'unit_entered': None,
               'kind': 'measured', 'uncertainty': None}
    return Prepared(
        payload=payload, summary=summary, derived=derived,
        sampled_at=sampling['cored_at'], observed_at=test['tested_at'],
        errors=problems, warnings=warnings, excluded_from_fold=not valid)


# PAIRING (decision 8.42) -----------------------------------------------------
def pairing_problems(payload: Dict[str, Any], facts: PairingFacts,
                     where: str = 'payload.sampling.paired_rebound_id'
                     ) -> List[Problem]:
    """The checks of ``paired_rebound_id`` against the stored rebound
    record: same component, rebound method, taken no later than the coring,
    not discarded, one core per rebound record."""
    rebound = facts.rebound
    pid = payload['sampling'].get('paired_rebound_id')
    if pid is None:
        return []
    if rebound is None:
        return [Problem(where, f'no record {pid}')]
    problems: List[Problem] = []
    if rebound.get('identity_id') != facts.identity_id:
        problems.append(Problem(where, 'the rebound record belongs to '
                                       'another component'))
    if rebound.get('method') != 'rebound_hammer':
        problems.append(Problem(where, 'the paired record is not a rebound '
                                       'hammer record'))
        return problems
    if rebound.get('status') in ('rejected', 'withdrawn') \
            or rebound.get('superseded_by'):
        problems.append(Problem(
            where, 'pair with a current record: this one is rejected, '
                   'withdrawn or corrected'))
    if (rebound.get('payload') or {}).get('set_discarded'):
        problems.append(Problem(where, 'the rebound set was discarded; a '
                                       'discarded set cannot be paired'))
    cored = payload['sampling']['cored_at']
    if rebound.get('observed_at') and \
            parse_ts(rebound['observed_at']) > parse_ts(cored):
        problems.append(Problem(
            where, 'the rebound record is later than the coring: the spot '
                   'is tested before it is drilled'))
    if facts.other_pairs:
        problems.append(Problem(
            where, 'one core per rebound record: already paired with '
                   + ', '.join(facts.other_pairs)))
    return problems
