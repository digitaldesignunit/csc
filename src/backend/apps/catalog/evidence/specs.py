#!/usr/bin/env python3.13
"""
The evidence methods, one ``EvidenceMethodSpec`` each (data model spec
section 2.5, 4.5, Appendix A). ``ALL_EVIDENCE_SPECS`` drives the validation,
``GET /evidence/methods``, the JSON Schemas and the web form: adding a
method is adding one spec here.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from typing import Tuple

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.evidence import claims, core, rebound
from apps.catalog.evidence.payloads import (
    ArchivalDocumentPayload,
    CoreCompressionPayload,
    EraHeuristicPayload,
    ManufacturerDatasheetPayload,
    ReboundHammerPayload,
    ReinforcementLayoutPayload,
    VisualInspectionPayload,
)
from apps.catalog.evidence.types import EvidenceMethodSpec
from apps.catalog.vocab import METHOD_TIER, QUANTITIES


def _claimable(tier: str) -> Tuple[str, ...]:
    """Quantities a claim of ``tier`` can be about: those whose ranking
    contains the tier (otherwise the fold would never use it)."""
    return tuple(q.name for q in QUANTITIES if tier in q.ranking)


REBOUND_HAMMER = EvidenceMethodSpec(
    name='rebound_hammer',
    label='Rebound hammer (EN 12504-2)',
    description=(
        'A test location: at least 9 readings with a rebound hammer. The '
        'result is the median as a whole number, a rebound number R or a '
        'Q-value, never a strength. A strength class read from the German '
        'annex, or a strength from a site correlation, is a derived result '
        'with its model named.'),
    payload_model=ReboundHammerPayload,
    source_tier=METHOD_TIER['rebound_hammer'], destructive=False,
    default_standard={'code': 'EN 12504-2', 'year': 2021},
    summary_quantities=('rebound_number', 'q_value'), summary_kind='measured',
    context_time='observed_at', prepare=rebound.prepare,
    derived_kinds=rebound.DERIVED_KINDS)

CORE_COMPRESSION = EvidenceMethodSpec(
    name='core_compression',
    label='Drilled core in compression (EN 12504-1, EN 12390-3)',
    description=(
        'A core drilled from the piece, prepared and crushed. The record '
        'carries both dates: sampled_at (the piece was drilled) decides the '
        'state of the piece it belongs to, observed_at is the test. The '
        'server recomputes F / A and the length-to-diameter class and '
        'derives the in-situ strength (EN 13791).'),
    payload_model=CoreCompressionPayload,
    source_tier=METHOD_TIER['core_compression'], destructive=True,
    default_standard={'code': 'EN 12504-1', 'year': 2019},
    summary_quantities=('compressive_strength',), summary_kind='measured',
    context_time='sampled_at', prepare=core.prepare,
    derived_kinds=core.DERIVED_KINDS)

ARCHIVAL_DOCUMENT = EvidenceMethodSpec(
    name='archival_document',
    label='Archival document',
    description=(
        'A claim from a drawing, specification, report, photo, marking, '
        'type plate or declaration of performance. The claim is the '
        'summary: a value or a range, or a class.'),
    payload_model=ArchivalDocumentPayload,
    source_tier=METHOD_TIER['archival_document'], destructive=False,
    default_standard=None, summary_quantities=_claimable('archival'),
    summary_kind='claimed', context_time='observed_at',
    prepare=claims.prepare_claim, summary_from_client=True)

VISUAL_INSPECTION = EvidenceMethodSpec(
    name='visual_inspection',
    label='Visual inspection',
    description=(
        'What an inspector saw: a finding (spalling, cracking, corrosion) '
        'as a severity 0 none to 3 severe, the overall condition grade '
        '(3 good to 0 unusable as is), or the widest crack in mm. One '
        'record per observed quantity; the photos of the finding are the '
        'record\'s attachments.'),
    payload_model=VisualInspectionPayload,
    source_tier=METHOD_TIER['visual_inspection'], destructive=False,
    default_standard=None, summary_quantities=claims.VISUAL_QUANTITIES,
    summary_kind='claimed', context_time='observed_at',
    prepare=claims.prepare_visual)

ERA_HEURISTIC = EvidenceMethodSpec(
    name='era_heuristic',
    label='Rule of thumb by era, region or typology',
    description=(
        'An estimate from the construction year, regional practice or the '
        'typology of the piece. The estimate is the summary.'),
    payload_model=EraHeuristicPayload,
    source_tier=METHOD_TIER['era_heuristic'], destructive=False,
    default_standard=None, summary_quantities=_claimable('heuristic'),
    summary_kind='claimed', context_time='observed_at',
    prepare=claims.prepare_claim, summary_from_client=True)

MANUFACTURER_DATASHEET = EvidenceMethodSpec(
    name='manufacturer_datasheet',
    label='Manufacturer datasheet',
    description=(
        'A figure from the manufacturer\'s datasheet for the product. The '
        'figure is the summary.'),
    payload_model=ManufacturerDatasheetPayload,
    source_tier=METHOD_TIER['manufacturer_datasheet'], destructive=False,
    default_standard=None, summary_quantities=_claimable('archival'),
    summary_kind='claimed', context_time='observed_at',
    prepare=claims.prepare_claim, summary_from_client=True)

REINFORCEMENT_LAYOUT = EvidenceMethodSpec(
    name='reinforcement_layout',
    label='Reinforcement layout',
    description=(
        'The bars of the piece from one source: a drawing (archival), a '
        'cover-meter or radar scan (non-destructive) or exposed bars '
        '(visual). The bar centrelines are in the stored coordinates of '
        'the snapshot named by position.snapshot_id, which is required. '
        'The summary is the diameter range over the bars.'),
    payload_model=ReinforcementLayoutPayload,
    source_tier=None, destructive=False, default_standard=None,
    summary_quantities=('rebar_diameter',), summary_kind=None,
    context_time='observed_at', prepare=claims.prepare_layout,
    tier_of=claims.layout_tier)

ALL_EVIDENCE_SPECS: Tuple[EvidenceMethodSpec, ...] = (
    REBOUND_HAMMER, CORE_COMPRESSION, ARCHIVAL_DOCUMENT, VISUAL_INSPECTION,
    ERA_HEURISTIC, MANUFACTURER_DATASHEET, REINFORCEMENT_LAYOUT,
)
