// Auto-generated from backend OpenAPI schema
// Generated on: 2026-10-02T21:09:59.090Z
// Source: http://127.0.0.1:8011/schema/create-evidence
import type { Actor } from './CatalogModels';
import type { Standard } from './EvidenceModels';

export interface DerivedInput {
  quantity: string;
  value?: number | number | string | null;
  range?: (number | number | string)[] | null;
  unit?: string | null;
  kind?: string;
  model: DerivedModelInput;
}

export interface DerivedModelInput {
  kind: string; // A model kind of the method (GET /evidence/methods, derived_models)
  reference?: string | null; // The document or report it rests on
  note?: string | null; // E.g. the table row a class was read from
}

export interface EvidenceBulk {
  records: EvidenceBulkItem[];
  submit?: boolean; // Submit every record
}

export interface EvidenceBulkItem {
  method: 'rebound_hammer' | 'core_compression' | 'archival_document' | 'visual_inspection' | 'era_heuristic' | 'manufacturer_datasheet' | 'reinforcement_layout';
  standard?: Standard | null; // Defaults to the standard of the method
  observed_at?: string | null; // When the result was produced (a core: the test date, taken from the payload)
  observed_at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  sampled_at?: string | null; // When the component was sampled (a core: the drilling date, taken from the payload)
  sampled_at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown' | null;
  performed_by?: Actor[];
  position?: PositionInput | null;
  summary?: SummaryInput | null;
  derived?: DerivedInput[];
  payload: Record<string, unknown>; // Per method: GET /evidence/methods, payload_schema
  notes?: string | null;
  self_attested?: boolean; // "I performed this and stand by the result": needs the recorder among performed_by (8.12)
  identity_id: string; // The component the record is about
}

export interface EvidenceCreate {
  method: 'rebound_hammer' | 'core_compression' | 'archival_document' | 'visual_inspection' | 'era_heuristic' | 'manufacturer_datasheet' | 'reinforcement_layout';
  standard?: Standard | null; // Defaults to the standard of the method
  observed_at?: string | null; // When the result was produced (a core: the test date, taken from the payload)
  observed_at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  sampled_at?: string | null; // When the component was sampled (a core: the drilling date, taken from the payload)
  sampled_at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown' | null;
  performed_by?: Actor[];
  position?: PositionInput | null;
  summary?: SummaryInput | null;
  derived?: DerivedInput[];
  payload: Record<string, unknown>; // Per method: GET /evidence/methods, payload_schema
  notes?: string | null;
  self_attested?: boolean; // "I performed this and stand by the result": needs the recorder among performed_by (8.12)
}

export interface PositionInput {
  kind?: 'point' | 'region' | 'face' | 'none' | null; // point, region, face or none; a rebound grid is always a region
  snapshot_id?: string | null; // The snapshot whose stored coordinates `point` is in (authored, never derived)
  point?: number[] | null; // Picked point in stored coordinates; for a rebound grid the server sets the grid centre
  description?: string | null; // Where on the piece, in words, e.g. "north face, mid-span"
}

export interface ReasonBody {
  reason: string;
}

export interface SummaryInput {
  quantity: string; // A quantity of the vocabulary (GET /evidence/quantities)
  value?: number | number | string | null; // A measured value
  range?: (number | number | string)[] | null; // [low, high], or the claimed classes of a categorical quantity
  unit?: string | null; // The unit the values are in; converted to the canonical unit and remembered as unit_entered
  unit_entered?: string | null; // Set by the server
  kind?: 'measured' | 'claimed' | null; // measured or claimed; the method decides
  uncertainty?: UncertaintyInput | null;
}

export interface UncertaintyInput {
  type: 'stddev' | 'expanded' | 'range' | 'none'; // expanded widens the folded range; the others are recorded only
  value?: number | null; // In the unit of the result
  k?: number | null; // Coverage factor
}

export interface VerificationBody {
  state: string; // unverified, self_attested, reviewed or accredited
  note?: string | null; // What the reviewer checked; required for accredited
}

export interface AnvilCheck {
  expected: number; // The anvil manufacturer's expected reading.
  before: AnvilSeries; // Readings before the series.
  after?: AnvilSeries | null; // Readings after the series.
  second_anvil?: SecondAnvil | null; // Readings on a softer second anvil.
  correction_factor?: number; // Factor the operator applied to the readings after the anvil check; 1 = none.
}

export interface AnvilSeries {
  performed_at?: string | null; // When the anvil readings were taken.
  readings: number[]; // The anvil readings; EN 12504-2 asks for five, each within +-3 of the anvil's expected value.
}

export interface ArchivalClaim {
  text: string; // The claim as written, e.g. B225.
  interpretation?: string | null; // How the claim is read today.
}

export interface ArchivalDocument {
  title: string; // Title of the document.
  date?: string | null; // Date of the document (year, month or day).
  kind: 'drawing' | 'spec' | 'report' | 'photo' | 'ce_marking' | 'ue_mark' | 'type_plate' | 'declaration_of_performance' | 'other'; // What kind of document it is.
  reference?: string | null; // Archive reference, sheet number or link.
}

export interface ArchivalDocumentPayload {
  document: ArchivalDocument; // The source document.
  claim: ArchivalClaim; // What the document says.
}

export interface CoreBar {
  orientation: 'transverse' | 'longitudinal'; // A longitudinal bar makes the core invalid for strength; a transverse one is recorded and assessed separately.
  diameter_mm?: number | null; // Bar size.
  position_mm?: number | null; // Position of the bar along the core.
}

export interface CoreCompressionPayload {
  sampling: CoreSampling; // Act 1: drilling the core.
  specimen: CoreSpecimen; // Act 2: preparing the core.
  test: CoreTest; // Act 3: crushing the core.
  result?: CoreResult; // The strength; the server completes and checks it.
  deviations?: string | null; // Deviations from the standard (a mandatory report item).
}

export interface CoreMachine {
  manufacturer?: string | null; // Machine maker.
  model?: string | null; // Machine model.
  serial?: string | null; // Machine serial number.
  class?: string | null; // Machine class, e.g. EN 12390-4.
  last_calibration_at?: string | null; // Date of the last calibration.
}

export interface CoreResult {
  fc_core_mpa?: number | null; // Compressive strength of the core, F / A_c to 0.1 MPa. A value from the lab report must be within 1 % of F / A_c; left out, the server computes it.
  ld_correction_applied?: boolean; // Whether the lab already applied a length-to-diameter correction to the reported value.
  fc_is_cyl_mpa?: number | null; // In-situ strength as a 150 x 300 mm cylinder (EN 13791:2019): a 2:1 core is f_c,is, a 1:1 core is multiplied by 0.82. Computed by the server.
  fc_is_cube_mpa?: number | null; // German annex NA.7: a 1:1 core of 50 to 150 mm equals a water-stored 150 mm cube. Computed by the server.
  conversion_basis?: string | null; // The documents the conversions follow. Computed by the server.
}

export interface CoreSampling {
  cored_at: string; // When the core was drilled; becomes the record's sampled_at and decides which state of the piece the result belongs to.
  paired_rebound_id?: string | null; // The rebound hammer record taken at this drill spot (EN 13791 pairs). Same component, not discarded, taken no later than the coring, one core per rebound record.
  drill_diameter_mm: number; // Nominal drill diameter (typically 50, 100 or 150 mm).
  drilling_method?: 'wet' | 'dry' | null; // Wet or dry drilling.
  orientation_vs_casting?: 'perpendicular' | 'parallel' | 'unknown' | null; // Core axis relative to the casting direction.
  operator?: Actor | null; // Who drilled the core.
  hole_repaired?: boolean; // Whether the core hole was repaired.
}

export interface CoreSpecimen {
  label?: string | null; // Specimen label, e.g. C-03.
  measured_diameter_mm: number; // Mean measured diameter; the cross-section area follows from it.
  length_as_drilled_mm?: number | null; // Length as drilled.
  length_prepared_mm?: number | null; // Length after end preparation; the length-to-diameter ratio uses it, else the length as drilled.
  end_preparation?: 'ground' | 'capped' | 'sawn' | 'none' | null; // How the end faces were prepared.
  length_diameter_ratio?: number | null; // Length divided by measured diameter. Computed by the server.
  ld_class?: '2:1' | '1:1' | 'other' | null; // 2:1 for a ratio of 1.95 to 2.05, 1:1 for 0.90 to 1.10, else other. Computed by the server.
  mass_g?: number | null; // Specimen mass.
  density_kg_m3?: number | null; // Specimen density.
  max_aggregate_size_mm?: number | null; // Estimated maximum aggregate size; a diameter under 3 times it biases the result.
  storage?: 'sealed' | 'water' | null; // Sealed container, or water for at least 48 h at 20 +- 2 deg C (EN 12504-1).
  reinforcement?: CoreBar[]; // Bars seen in the core; empty = none seen.
  valid_for_strength?: boolean | null; // False with a longitudinal bar: the record stays (the core was taken) but the property fold skips it. Computed by the server.
  defects_note?: string | null; // Visible defects of the specimen.
}

export interface CoreTest {
  tested_at: string; // When the core was crushed; becomes the record's observed_at.
  machine?: CoreMachine | null; // The testing machine.
  loading_rate_mpa_s?: number | null; // Loading rate; EN 12390-3 asks for 0.6 +- 0.2 MPa/s.
  max_load_kn: number; // Maximum load F in kN.
  cross_section_area_mm2?: number | null; // Cross-section area A_c; defaults to pi d^2 / 4 from the mean diameter, and a given value must be within 1 % of that.
  failure_type: 'satisfactory' | 'unsatisfactory'; // Failure pattern (EN 12390-3).
  failure_type_code?: string | null; // Letter of the closest unsatisfactory pattern in EN 12390-3, Fig 2 / 4.
  age_at_test_days?: number | null; // Age of the concrete at the test, if known.
}

export interface EraHeuristicPayload {
  basis: 'construction_year' | 'region_practice' | 'typology'; // What the estimate rests on.
  year?: number | null; // The year used.
  source?: string | null; // Where the rule of thumb comes from.
}

export interface Grid {
  origin: number[]; // Position of the first impact point, in the stored coordinates of position.snapshot_id.
  u: number[]; // Unit direction along a row, in the face plane.
  v: number[]; // Unit direction from row to row, in the face plane, orthogonal to u.
  rows: number; // Number of rows.
  cols: number; // Impacts per row.
  spacing_mm: number; // Distance between neighbouring impacts; at least min_spacing_mm.
  points?: number[][] | null; // The impact points, row by row (reading i belongs to point i). Derived by the server from the grid; never sent by the client.
}

export interface LayoutBar {
  spec?: string | null; // Steel grade, e.g. BSt III.
  diameter_mm: number; // Bar diameter.
  diameter_known?: boolean; // Scan: whether the diameter is known from a drawing or an exposure, or only assumed.
  cover_mm?: number | null; // Scan: the measured concrete cover.
  points: number[][]; // Open centreline polyline, in the stored coordinates of position.snapshot_id.
}

export interface LayoutDocument {
  title: string; // Title of the drawing.
  date?: string | null; // Date of the drawing.
  reference?: string | null; // Reference.
}

export interface LayoutInstrument {
  kind: 'covermeter' | 'radar' | 'other'; // Kind of scanner.
  manufacturer?: string | null; // Maker.
  model?: string | null; // Model.
  last_calibration_at?: string | null; // Date of the last calibration.
  site_calibration?: string | null; // How the scan was calibrated on site.
}

export interface ManufacturerDatasheetPayload {
  manufacturer: string; // Manufacturer.
  product: string; // Product name.
  reference?: string | null; // Datasheet number, version or link.
}

export interface ReboundHammerPayload {
  instrument: ReboundInstrument; // The hammer used.
  test_area: ReboundTestArea; // Where and in what state the surface was tested.
  impact_direction: 'horizontal' | 'vertically_down' | 'vertically_up' | 'inclined'; // Direction of the impacts; needs a correction unless horizontal.
  impact_angle_deg?: number | null; // Angle for an inclined direction.
  readings: number[]; // All readings, in the order taken (at least 9). Rejected readings stay in the list and are flagged.
  reading_unit: '1' | 'Q'; // "1" for a rebound number R, "Q" for a Q-value; must match the hammer type.
  rejected_reading_indices?: number[]; // Zero-based indices of readings the operator rejected; flagged, never deleted, so the rule stays auditable.
  outlier_policy?: 'en_12504_2' | 'none'; // en_12504_2: the whole set is discarded if more than 20 % of the valid readings deviate more than 25 % from the median.
  set_discarded?: boolean | null; // Computed by the server from the outlier policy.
  n_valid?: number | null; // Readings that were not rejected. Computed by the server.
  median?: number | null; // Median of the valid readings as a whole number. Computed by the server; this is the result.
  direction_correction_applied?: boolean; // Whether the readings were corrected for the impact direction.
  deviations?: string | null; // Deviations from the standard (a mandatory report item).
}

export interface ReboundInstrument {
  hammer_type: 'N' | 'L' | 'NR' | 'LR' | 'Q_N' | 'Q_L'; // N (2.207 Nm), L (0.735 Nm), NR / LR (recording) report a rebound number R; Q_N / Q_L (energy-based digital hammers) report a Q-value. R and Q are different quantities and are never aggregated.
  manufacturer?: string | null; // Hammer maker.
  model?: string | null; // Hammer model.
  serial?: string | null; // Hammer serial number.
  impact_energy_nm?: number | null; // Nominal impact energy in Nm.
  last_calibration_at?: string | null; // Date of the last calibration of the hammer.
  anvil_check?: AnvilCheck | null; // Anvil readings before and after the series (EN 12504-2, 7.1.2 / 7.3).
}

export interface ReboundTestArea {
  label?: string | null; // Name of the test area on the piece, e.g. TA-1.
  surface_preparation: 'ground' | 'as_found'; // Whether the surface was ground before testing.
  surface_condition: 'dry' | 'damp' | 'wet'; // Moisture state of the surface.
  carbonation_depth_mm?: number | null; // Carbonation depth at the test area. The German annex (NA.6 / NA.7) is only used up to 5 mm unless the surface was ground.
  surface_temperature_c?: number | null; // Surface temperature in deg C; the hammer is used between 0 and 50 deg C.
  min_spacing_mm?: number; // Minimum distance between impacts (EN 12504-2: 25 mm).
  min_edge_distance_mm?: number; // Minimum distance of an impact from any edge (EN 12504-2: 25 mm). The viewer warns when a picked point is closer.
  grid?: Grid | null; // Optional: the impact points as a regular grid on a face. Needs position.snapshot_id; one reading per grid point, row by row.
  member_thickness_mm?: number | null; // Thickness of the member at the test area; at least 100 mm unless firmly supported.
  support?: 'fixed_in_structure' | 'clamped' | 'loose' | null; // How the member was held; a member under 100 mm needs a firm support (EN 12504-2, 6.1).
}

export interface ReinforcementLayoutPayload {
  basis: 'drawing' | 'scan' | 'exposed'; // drawing (archival), scan (non-destructive) or exposed (visual): sets the source tier.
  document?: LayoutDocument | null; // For basis drawing: the drawing (the file itself is an attachment).
  instrument?: LayoutInstrument | null; // For basis scan: the scanner.
  accuracy_note?: string | null; // E.g. "size and cover +-20 %, neither known".
  bars: LayoutBar[]; // The bars of the layout.
}

export interface SecondAnvil {
  performed_at?: string | null; // When the anvil readings were taken.
  readings: number[]; // The anvil readings; EN 12504-2 asks for five, each within +-3 of the anvil's expected value.
  expected: number; // Expected reading of the softer second anvil that EN 12504-2:2021 recommends.
}

export interface VisualInspectionPayload {
  observations: VisualObservation[]; // One record per observed quantity: every observation of a record has the same quantity. The summary takes the worst one. Photos are the record's attachments.
}

export interface VisualObservation {
  quantity: 'spalling' | 'cracking' | 'corrosion' | 'condition_grade' | 'crack_width'; // What was observed. Severities (spalling, cracking, corrosion) run 0 none to 3 severe; condition_grade runs 0 unusable as is to 3 good; crack_width is the widest crack in mm.
  value: number | number; // The severity or grade 0 to 3, or the width in mm.
  note?: string | null; // Free text.
}

export interface EvidencePayloads {
  rebound_hammer: ReboundHammerPayload;
  core_compression: CoreCompressionPayload;
  archival_document: ArchivalDocumentPayload;
  visual_inspection: VisualInspectionPayload;
  era_heuristic: EraHeuristicPayload;
  manufacturer_datasheet: ManufacturerDatasheetPayload;
  reinforcement_layout: ReinforcementLayoutPayload;
}

export interface EvidenceInputEnvelope {
  create: EvidenceCreate;
  bulk: EvidenceBulk;
  verification: VerificationBody;
  reason: ReasonBody;
  payloads: EvidencePayloads;
}

