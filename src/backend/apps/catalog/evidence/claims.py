#!/usr/bin/env python3.13
"""
The non-instrumental methods and the reinforcement layout (spec A.3, A.4;
decisions 7.4, 7.8, 7.9). Pure functions.

Archival documents, datasheets and era heuristics carry a claim the client
states as the summary. A visual inspection and a reinforcement layout derive
their summary from the payload.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Any, Dict, List

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import _check_result
from apps.catalog.evidence.payloads import (
    ReinforcementLayoutPayload,
    VisualInspectionPayload,
)
from apps.catalog.evidence.types import Prepared, Problem
from apps.catalog.vocab import (
    QUANTITY_BY_NAME,
    REINFORCEMENT_BASIS_TIER,
)

VISUAL_QUANTITIES = ('spalling', 'cracking', 'corrosion', 'condition_grade',
                     'crack_width')


def prepare_claim(model, ctx: Dict[str, Any]) -> Prepared:
    """Archival document, datasheet, era heuristic: the payload says where
    the claim comes from, the client's summary is the claim itself."""
    return Prepared(payload=model.model_dump(by_alias=True, mode='json'))


def prepare_visual(model: VisualInspectionPayload,
                   ctx: Dict[str, Any]) -> Prepared:
    """One record per observed quantity (atomic rule, A.3); the summary is
    the worst observation: the highest severity or width, the lowest
    grade."""
    payload = model.model_dump(by_alias=True, mode='json')
    problems: List[Problem] = []
    quantities = {o['quantity'] for o in payload['observations']}
    if len(quantities) > 1:
        problems.append(Problem(
            'payload.observations',
            f'one record per observed quantity (atomic rule); got '
            f'{sorted(quantities)}'))
        return Prepared(payload=payload, errors=problems)
    quantity = payload['observations'][0]['quantity']
    spec = QUANTITY_BY_NAME[quantity]
    values: List[Any] = []
    for i, observation in enumerate(payload['observations']):
        value = observation['value']
        if spec.kind == 'ordinal':
            if float(value) != int(value):
                problems.append(Problem(
                    f'payload.observations.{i}.value',
                    f'{quantity} is a whole number 0..3'))
                continue
            value = int(value)
            observation['value'] = value
        elif value < 0:
            problems.append(Problem(f'payload.observations.{i}.value',
                                    f'{quantity} is not negative'))
            continue
        else:
            value = float(value)
            observation['value'] = value
        try:
            _check_result(quantity, value, None, spec.unit)
        except ValueError as exc:
            problems.append(Problem(f'payload.observations.{i}.value',
                                    str(exc)))
        values.append(value)
    if problems:
        return Prepared(payload=payload, errors=problems)
    worst = min(values) if spec.ordinal_direction == 'grade' else max(values)
    summary = {'quantity': quantity, 'value': worst, 'range': None,
               'unit': spec.unit, 'unit_entered': None, 'kind': 'claimed',
               'uncertainty': None}
    return Prepared(payload=payload, summary=summary)


def layout_tier(payload: Dict[str, Any]):
    """The source tier of a reinforcement layout follows its basis (7.8)."""
    return REINFORCEMENT_BASIS_TIER.get((payload or {}).get('basis'))


def prepare_layout(model: ReinforcementLayoutPayload,
                   ctx: Dict[str, Any]) -> Prepared:
    """Summary: the diameter range over the bars; measured for a scan or an
    exposure, claimed for a drawing. A.4."""
    payload = model.model_dump(by_alias=True, mode='json')
    warnings: List[str] = []
    diameters = [bar['diameter_mm'] for bar in payload['bars']]
    summary = {'quantity': 'rebar_diameter', 'value': None,
               'range': [min(diameters), max(diameters)], 'unit': 'mm',
               'unit_entered': None,
               'kind': 'claimed' if payload['basis'] == 'drawing'
               else 'measured', 'uncertainty': None}
    if payload['basis'] == 'scan' and payload.get('instrument') is None:
        warnings.append('a scan names its instrument (prEN 12504-5)')
    if payload['basis'] == 'drawing' and payload.get('document') is None:
        warnings.append('a drawing layout names the drawing '
                        '(payload.document)')
    # I23: the bars' coordinates are in the stored coordinates of the
    # snapshot named by position.snapshot_id (checked by the registry)
    return Prepared(payload=payload, summary=summary, warnings=warnings,
                    source_tier=REINFORCEMENT_BASIS_TIER[payload['basis']])
