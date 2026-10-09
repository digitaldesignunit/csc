#!/usr/bin/env python3.13
"""
Evidence payload models, one per method (data model spec Appendix A).

``extra = "forbid"``: a misspelt field fails instead of being dropped. Every
field carries a description; ``GET /evidence/methods`` and ``/schema/evidence``
serve them to the web form's "?" popovers, the API docs and later clients, so
the text here is the one source (decision 7.1). Fields the server computes
(median, discard rule, F / A, length-to-diameter class, grid points, ...) are
optional on input and marked ``server_computed`` in the JSON Schema: a client
may omit them or send the value it expects, and the server refuses a value
that differs from its own recomputation (spec Appendix A: "server recomputes
and cross-checks").
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import re
from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.documents import Actor, Timestamp, Vec3
from apps.catalog.vocab import ReinforcementBasis

_FLEX_DATE = re.compile(r'^\d{4}(-\d{2}(-\d{2})?)?$')


def _flex_date(value: str) -> str:
    """A year, a month, a day or a full UTC timestamp ('1968', '1968-03',
    '2026-01-15', '2026-01-15T10:00:00Z')."""
    if _FLEX_DATE.match(value):
        parts = value.split('-')
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        datetime(int(parts[0]), month, day)          # ValueError if invalid
        return value
    if value.endswith('Z'):
        datetime.fromisoformat(value[:-1] + '+00:00')
        return value
    raise ValueError('a date: YYYY, YYYY-MM, YYYY-MM-DD or an ISO-8601 UTC '
                     'timestamp ending in Z')


FlexDate = Annotated[str, AfterValidator(_flex_date)]
SERVER = {'server_computed': True}


def _http_url(value: str) -> str:
    """A link a document was read from (decision 8.106): ``http(s)://`` and
    a host, nothing else (never ``javascript:`` or ``file:``)."""
    from urllib.parse import urlsplit
    text = value.strip()
    parts = urlsplit(text)
    if (parts.scheme not in ('http', 'https') or not parts.netloc
            or not parts.hostname):
        raise ValueError('a link: http:// or https:// and a host')
    if len(text) > 2048 or any(ord(c) <= 32 for c in text):
        raise ValueError('a link: at most 2048 characters, no spaces')
    return text


HttpLink = Annotated[str, AfterValidator(_http_url)]


class Payload(BaseModel):
    """Base of every payload and nested block: unknown keys are errors."""
    model_config = ConfigDict(extra='forbid')


# REBOUND HAMMER (A.1, EN 12504-2:2021) ---------------------------------------
HammerType = Literal['N', 'L', 'NR', 'LR', 'Q_N', 'Q_L']
Q_HAMMERS = ('Q_N', 'Q_L')


class AnvilSeries(Payload):
    performed_at: Optional[FlexDate] = Field(
        None, description='When the anvil readings were taken.')
    readings: List[float] = Field(
        min_length=1, max_length=50,
        description='The anvil readings; EN 12504-2 asks for five, each '
                    'within +-3 of the anvil\'s expected value.')


class SecondAnvil(AnvilSeries):
    expected: float = Field(
        gt=0, description='Expected reading of the softer second anvil '
                          'that EN 12504-2:2021 recommends.')


class AnvilCheck(Payload):
    expected: float = Field(
        gt=0, description='The anvil manufacturer\'s expected reading.')
    before: AnvilSeries = Field(
        description='Readings before the series.')
    after: Optional[AnvilSeries] = Field(
        None, description='Readings after the series.')
    second_anvil: Optional[SecondAnvil] = Field(
        None, description='Readings on a softer second anvil.')
    correction_factor: float = Field(
        1.0, gt=0, description='Factor the operator applied to the '
                               'readings after the anvil check; 1 = none.')


class ReboundInstrument(Payload):
    hammer_type: HammerType = Field(
        description='N (2.207 Nm), L (0.735 Nm), NR / LR (recording) report '
                    'a rebound number R; Q_N / Q_L (energy-based digital '
                    'hammers) report a Q-value. R and Q are different '
                    'quantities and are never aggregated.')
    manufacturer: Optional[str] = Field(None, description='Hammer maker.')
    model: Optional[str] = Field(None, description='Hammer model.')
    serial: Optional[str] = Field(None, description='Hammer serial number.')
    impact_energy_nm: Optional[float] = Field(
        None, gt=0, description='Nominal impact energy in Nm.')
    last_calibration_at: Optional[FlexDate] = Field(
        None, description='Date of the last calibration of the hammer.')
    anvil_check: Optional[AnvilCheck] = Field(
        None, description='Anvil readings before and after the series '
                          '(EN 12504-2, 7.1.2 / 7.3).')


class Grid(Payload):
    origin: Vec3 = Field(
        description='Position of the first impact point, in the stored '
                    'coordinates of position.snapshot_id.')
    u: Vec3 = Field(
        description='Unit direction along a row, in the face plane.')
    v: Vec3 = Field(
        description='Unit direction from row to row, in the face plane, '
                    'orthogonal to u.')
    rows: int = Field(ge=1, le=100, description='Number of rows.')
    cols: int = Field(ge=1, le=100, description='Impacts per row.')
    spacing_mm: float = Field(
        gt=0, description='Distance between neighbouring impacts; at least '
                          'min_spacing_mm.')
    points: Optional[List[Vec3]] = Field(
        None, json_schema_extra=SERVER,
        description='The impact points, row by row (reading i belongs to '
                    'point i). Derived by the server from the grid; never '
                    'sent by the client.')


class ReboundTestArea(Payload):
    label: Optional[str] = Field(
        None, description='Name of the test area on the piece, e.g. TA-1.')
    surface_preparation: Literal['ground', 'as_found'] = Field(
        description='Whether the surface was ground before testing.')
    surface_condition: Literal['dry', 'damp', 'wet'] = Field(
        description='Moisture state of the surface.')
    carbonation_depth_mm: Optional[float] = Field(
        None, ge=0, description='Carbonation depth at the test area. The '
                                'German annex (NA.6 / NA.7) is only used up '
                                'to 5 mm unless the surface was ground.')
    surface_temperature_c: Optional[float] = Field(
        None, description='Surface temperature in deg C; the hammer is '
                          'used between 0 and 50 deg C.')
    min_spacing_mm: float = Field(
        25, gt=0, description='Minimum distance between impacts (EN '
                              '12504-2: 25 mm).')
    min_edge_distance_mm: float = Field(
        25, gt=0, description='Minimum distance of an impact from any edge '
                              '(EN 12504-2: 25 mm). The viewer warns when '
                              'a picked point is closer.')
    grid: Optional[Grid] = Field(
        None, description='Optional: the impact points as a regular grid on '
                          'a face. Needs position.snapshot_id; one reading '
                          'per grid point, row by row.')
    member_thickness_mm: Optional[float] = Field(
        None, gt=0, description='Thickness of the member at the test area; '
                                'at least 100 mm unless firmly supported.')
    support: Optional[Literal['fixed_in_structure', 'clamped', 'loose']] = \
        Field(None, description='How the member was held; a member under '
                                '100 mm needs a firm support (EN 12504-2, '
                                '6.1).')


class ReboundHammerPayload(Payload):
    instrument: ReboundInstrument = Field(description='The hammer used.')
    test_area: ReboundTestArea = Field(
        description='Where and in what state the surface was tested.')
    impact_direction: Literal[
        'horizontal', 'vertically_down', 'vertically_up', 'inclined'] = Field(
        description='Direction of the impacts; needs a correction unless '
                    'horizontal.')
    impact_angle_deg: Optional[float] = Field(
        None, description='Angle for an inclined direction.')
    readings: List[float] = Field(
        min_length=1, max_length=1000,
        description='All readings, in the order taken (at least 9). Rejected '
                    'readings stay in the list and are flagged.')
    reading_unit: Literal['1', 'Q'] = Field(
        description='"1" for a rebound number R, "Q" for a Q-value; must '
                    'match the hammer type.')
    rejected_reading_indices: List[int] = Field(
        default_factory=list,
        description='Zero-based indices of readings the operator rejected; '
                    'flagged, never deleted, so the rule stays auditable.')
    outlier_policy: Literal['en_12504_2', 'none'] = Field(
        'en_12504_2',
        description='en_12504_2: the whole set is discarded if more than '
                    '20 % of the valid readings deviate more than 25 % from '
                    'the median.')
    set_discarded: Optional[bool] = Field(
        None, json_schema_extra=SERVER,
        description='Computed by the server from the outlier policy.')
    n_valid: Optional[int] = Field(
        None, json_schema_extra=SERVER,
        description='Readings that were not rejected. Computed by the '
                    'server.')
    median: Optional[float] = Field(
        None, json_schema_extra=SERVER,
        description='Median of the valid readings as a whole number. '
                    'Computed by the server; this is the result.')
    direction_correction_applied: bool = Field(
        False, description='Whether the readings were corrected for the '
                           'impact direction.')
    deviations: Optional[str] = Field(
        None, description='Deviations from the standard (a mandatory '
                          'report item).')


# CORE IN COMPRESSION (A.2, EN 12504-1:2019, EN 12390-3:2019) -----------------
class CoreSampling(Payload):
    cored_at: Timestamp = Field(
        description='When the core was drilled; becomes the record\'s '
                    'sampled_at and decides which state of the piece the '
                    'result belongs to.')
    paired_rebound_id: Optional[str] = Field(
        None, description='The rebound hammer record taken at this drill '
                          'spot (EN 13791 pairs). Same component, not '
                          'discarded, taken no later than the coring, one '
                          'core per rebound record.')
    drill_diameter_mm: float = Field(
        gt=0, description='Nominal drill diameter (typically 50, 100 or '
                          '150 mm).')
    drilling_method: Optional[Literal['wet', 'dry']] = Field(
        None, description='Wet or dry drilling.')
    orientation_vs_casting: Optional[
        Literal['perpendicular', 'parallel', 'unknown']] = Field(
        None, description='Core axis relative to the casting direction.')
    operator: Optional[Actor] = Field(
        None, description='Who drilled the core.')
    hole_repaired: bool = Field(
        False, description='Whether the core hole was repaired.')


class CoreBar(Payload):
    orientation: Literal['transverse', 'longitudinal'] = Field(
        description='A longitudinal bar makes the core invalid for strength; '
                    'a transverse one is recorded and assessed separately.')
    diameter_mm: Optional[float] = Field(None, gt=0, description='Bar size.')
    position_mm: Optional[float] = Field(
        None, ge=0, description='Position of the bar along the core.')


class CoreSpecimen(Payload):
    label: Optional[str] = Field(None, description='Specimen label, e.g. C-03.')
    measured_diameter_mm: float = Field(
        gt=0, description='Mean measured diameter; the cross-section area '
                          'follows from it.')
    length_as_drilled_mm: Optional[float] = Field(
        None, gt=0, description='Length as drilled.')
    length_prepared_mm: Optional[float] = Field(
        None, gt=0, description='Length after end preparation; the '
                                'length-to-diameter ratio uses it, else '
                                'the length as drilled.')
    end_preparation: Optional[Literal['ground', 'capped', 'sawn', 'none']] = \
        Field(None, description='How the end faces were prepared.')
    length_diameter_ratio: Optional[float] = Field(
        None, json_schema_extra=SERVER,
        description='Length divided by measured diameter. Computed by the '
                    'server.')
    ld_class: Optional[Literal['2:1', '1:1', 'other']] = Field(
        None, json_schema_extra=SERVER,
        description='2:1 for a ratio of 1.95 to 2.05, 1:1 for 0.90 to 1.10, '
                    'else other. Computed by the server.')
    mass_g: Optional[float] = Field(None, gt=0, description='Specimen mass.')
    density_kg_m3: Optional[float] = Field(
        None, gt=0, description='Specimen density.')
    max_aggregate_size_mm: Optional[float] = Field(
        None, gt=0, description='Estimated maximum aggregate size; a '
                                'diameter under 3 times it biases the '
                                'result.')
    storage: Optional[Literal['sealed', 'water']] = Field(
        None, description='Sealed container, or water for at least 48 h at '
                          '20 +- 2 deg C (EN 12504-1).')
    reinforcement: List[CoreBar] = Field(
        default_factory=list,
        description='Bars seen in the core; empty = none seen.')
    valid_for_strength: Optional[bool] = Field(
        None, json_schema_extra=SERVER,
        description='False with a longitudinal bar: the record stays (the '
                    'core was taken) but the property fold skips it. '
                    'Computed by the server.')
    defects_note: Optional[str] = Field(
        None, description='Visible defects of the specimen.')


class CoreMachine(Payload):
    manufacturer: Optional[str] = Field(None, description='Machine maker.')
    model: Optional[str] = Field(None, description='Machine model.')
    serial: Optional[str] = Field(None, description='Machine serial number.')
    class_: Optional[str] = Field(
        None, alias='class', description='Machine class, e.g. EN 12390-4.')
    last_calibration_at: Optional[FlexDate] = Field(
        None, description='Date of the last calibration.')

    model_config = ConfigDict(extra='forbid', populate_by_name=True)


class CoreTest(Payload):
    tested_at: Timestamp = Field(
        description='When the core was crushed; becomes the record\'s '
                    'observed_at.')
    machine: Optional[CoreMachine] = Field(
        None, description='The testing machine.')
    loading_rate_mpa_s: Optional[float] = Field(
        None, gt=0, description='Loading rate; EN 12390-3 asks for '
                                '0.6 +- 0.2 MPa/s.')
    max_load_kn: float = Field(gt=0, description='Maximum load F in kN.')
    cross_section_area_mm2: Optional[float] = Field(
        None, gt=0, description='Cross-section area A_c; defaults to '
                                'pi d^2 / 4 from the mean diameter, and a '
                                'given value must be within 1 % of that.')
    failure_type: Literal['satisfactory', 'unsatisfactory'] = Field(
        description='Failure pattern (EN 12390-3).')
    failure_type_code: Optional[str] = Field(
        None, max_length=4,
        description='Letter of the closest unsatisfactory pattern in '
                    'EN 12390-3, Fig 2 / 4.')
    age_at_test_days: Optional[int] = Field(
        None, ge=0, description='Age of the concrete at the test, if known.')


class CoreResult(Payload):
    fc_core_mpa: Optional[float] = Field(
        None, gt=0, json_schema_extra=SERVER,
        description='Compressive strength of the core, F / A_c to 0.1 MPa. '
                    'A value from the lab report must be within 1 % of '
                    'F / A_c; left out, the server computes it.')
    ld_correction_applied: bool = Field(
        False, description='Whether the lab already applied a '
                           'length-to-diameter correction to the reported '
                           'value.')
    fc_is_cyl_mpa: Optional[float] = Field(
        None, json_schema_extra=SERVER,
        description='In-situ strength as a 150 x 300 mm cylinder (EN '
                    '13791:2019): a 2:1 core is f_c,is, a 1:1 core is '
                    'multiplied by 0.82. Computed by the server.')
    fc_is_cube_mpa: Optional[float] = Field(
        None, json_schema_extra=SERVER,
        description='German annex NA.7: a 1:1 core of 50 to 150 mm equals '
                    'a water-stored 150 mm cube. Computed by the server.')
    conversion_basis: Optional[str] = Field(
        None, json_schema_extra=SERVER,
        description='The documents the conversions follow. Computed by the '
                    'server.')


class CoreCompressionPayload(Payload):
    sampling: CoreSampling = Field(description='Act 1: drilling the core.')
    specimen: CoreSpecimen = Field(description='Act 2: preparing the core.')
    test: CoreTest = Field(description='Act 3: crushing the core.')
    result: CoreResult = Field(
        default_factory=CoreResult,
        description='The strength; the server completes and checks it.')
    deviations: Optional[str] = Field(
        None, description='Deviations from the standard (a mandatory '
                          'report item).')


# NON-INSTRUMENTAL KINDS (A.3) ------------------------------------------------
class ArchivalDocument(Payload):
    title: str = Field(min_length=1, description='Title of the document.')
    date: Optional[FlexDate] = Field(
        None, description='Date of the document (year, month or day).')
    kind: Literal[
        'drawing', 'spec', 'report', 'photo', 'ce_marking', 'ue_mark',
        'type_plate', 'declaration_of_performance', 'other'] = Field(
        description='What kind of document it is.')
    reference: Optional[str] = Field(
        None, description='Archive reference, sheet number or link.')
    url: Optional[HttpLink] = Field(
        None, description='Where the document was read online (http or '
                          'https only); the page shows the host as a link.')
    retrieved_at: Optional[FlexDate] = Field(
        None, description='The day the link was read: such links die.')


class ArchivalClaim(Payload):
    text: str = Field(min_length=1,
                      description='The claim as written, e.g. B225.')
    interpretation: Optional[str] = Field(
        None, description='How the claim is read today.')


class ArchivalDocumentPayload(Payload):
    document: ArchivalDocument = Field(description='The source document.')
    claim: Optional[ArchivalClaim] = Field(
        None, description='What the document says. Without a claim and a '
                          'summary the record is a document: it documents '
                          'the piece and never enters the fold.')


class VisualObservation(Payload):
    quantity: Literal[
        'spalling', 'cracking', 'corrosion', 'condition_grade',
        'crack_width'] = Field(
        description='What was observed. Severities (spalling, cracking, '
                    'corrosion) run 0 none to 3 severe; condition_grade '
                    'runs 0 unusable as is to 3 good; crack_width is the '
                    'widest crack in mm.')
    value: Union[int, float] = Field(
        description='The severity or grade 0 to 3, or the width in mm.')
    note: Optional[str] = Field(None, description='Free text.')


class VisualInspectionPayload(Payload):
    observations: List[VisualObservation] = Field(
        min_length=1,
        description='One record per observed quantity: every observation of '
                    'a record has the same quantity. The summary takes the '
                    'worst one. Photos are the record\'s attachments.')


class EraHeuristicPayload(Payload):
    basis: Literal['construction_year', 'region_practice', 'typology'] = \
        Field(description='What the estimate rests on.')
    year: Optional[int] = Field(
        None, ge=1000, le=2200, description='The year used.')
    source: Optional[str] = Field(
        None, description='Where the rule of thumb comes from.')


class ManufacturerDatasheetPayload(Payload):
    manufacturer: str = Field(min_length=1, description='Manufacturer.')
    product: str = Field(min_length=1, description='Product name.')
    reference: Optional[str] = Field(
        None, description='Datasheet number, version or link.')


# REINFORCEMENT LAYOUT (A.4) --------------------------------------------------
class LayoutDocument(Payload):
    title: str = Field(min_length=1, description='Title of the drawing.')
    date: Optional[FlexDate] = Field(None, description='Date of the drawing.')
    reference: Optional[str] = Field(None, description='Reference.')
    url: Optional[HttpLink] = Field(
        None, description='Where the drawing was read online (http or '
                          'https only).')
    retrieved_at: Optional[FlexDate] = Field(
        None, description='The day the link was read.')


class LayoutInstrument(Payload):
    kind: Literal['covermeter', 'radar', 'other'] = Field(
        description='Kind of scanner.')
    manufacturer: Optional[str] = Field(None, description='Maker.')
    model: Optional[str] = Field(None, description='Model.')
    last_calibration_at: Optional[FlexDate] = Field(
        None, description='Date of the last calibration.')
    site_calibration: Optional[str] = Field(
        None, description='How the scan was calibrated on site.')


class LayoutBar(Payload):
    spec: Optional[str] = Field(None, description='Steel grade, e.g. BSt III.')
    diameter_mm: float = Field(gt=0, description='Bar diameter.')
    diameter_known: bool = Field(
        True, description='Scan: whether the diameter is known from a '
                          'drawing or an exposure, or only assumed.')
    cover_mm: Optional[float] = Field(
        None, ge=0, description='Scan: the measured concrete cover.')
    points: List[Vec3] = Field(
        min_length=2,
        description='Open centreline polyline, in the stored coordinates of '
                    'position.snapshot_id.')


class ReinforcementLayoutPayload(Payload):
    basis: ReinforcementBasis = Field(
        description='drawing (archival), scan (non-destructive) or exposed '
                    '(visual): sets the source tier.')
    document: Optional[LayoutDocument] = Field(
        None, description='For basis drawing: the drawing (the file itself '
                          'is an attachment).')
    instrument: Optional[LayoutInstrument] = Field(
        None, description='For basis scan: the scanner.')
    accuracy_note: Optional[str] = Field(
        None, description='E.g. "size and cover +-20 %, neither known".')
    bars: List[LayoutBar] = Field(
        min_length=1, description='The bars of the layout.')
