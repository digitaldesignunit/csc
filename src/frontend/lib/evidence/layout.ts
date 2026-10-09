/**
 * How the form lays out a method. Only structure lives here: which parts of
 * a payload several records share, and what is emptied when a record is
 * repeated. Labels, choices and help texts come from the registry
 * (`GET /evidence/methods`), never from this file (decision 7.1).
 */

/** What one submission fans out into (spec section 7.6). */
export type FanOut =
  | 'areas' // one record per test area / specimen, shared lab details
  | 'observations' // one record per observed finding, photos per finding
  | 'pieces' // one claim, one record per selected piece
  | 'single' // exactly one record

export type MethodLayout = {
  fanOut: FanOut
  /** What one record is called ("test area", "core"). */
  recordLabel: string
  /** Top-level payload keys edited once and copied into every record. */
  shared: string[]
  /** Payload paths (dotted) emptied when a record is repeated or cloned. */
  blankOnRepeat: string[]
  /** Payload paths holding a date: shown as date inputs. */
  dateFields: string[]
  /** Payload paths shown as a multi-line text. */
  longText: string[]
  /** Payload paths the server reads as the record's dates: a date is sent as a UTC midnight. */
  timestampFields: string[]
}

export const LAYOUTS: Record<string, MethodLayout> = {
  rebound_hammer: {
    fanOut: 'areas',
    recordLabel: 'test area',
    shared: ['instrument'],
    blankOnRepeat: [
      'readings',
      'rejected_reading_indices',
      'impact_angle_deg',
      'deviations',
      'test_area.label',
      'test_area.grid',
      'test_area.carbonation_depth_mm',
      'test_area.member_thickness_mm',
    ],
    dateFields: ['instrument.last_calibration_at', 'instrument.anvil_check.before.performed_at',
      'instrument.anvil_check.after.performed_at'],
    longText: ['deviations'],
    timestampFields: [],
  },
  core_compression: {
    fanOut: 'areas',
    recordLabel: 'core',
    shared: [],
    blankOnRepeat: [
      'sampling.paired_rebound_id',
      'specimen.label',
      'specimen.measured_diameter_mm',
      'specimen.length_as_drilled_mm',
      'specimen.length_prepared_mm',
      'specimen.mass_g',
      'specimen.density_kg_m3',
      'specimen.reinforcement',
      'specimen.defects_note',
      'test.max_load_kn',
      'test.cross_section_area_mm2',
      'test.failure_type',
      'test.failure_type_code',
      'test.age_at_test_days',
      'result',
      'deviations',
    ],
    dateFields: ['sampling.cored_at', 'test.tested_at', 'test.machine.last_calibration_at'],
    longText: ['deviations', 'specimen.defects_note'],
    timestampFields: ['sampling.cored_at', 'test.tested_at'],
  },
  visual_inspection: {
    fanOut: 'observations',
    recordLabel: 'observation',
    shared: [],
    blankOnRepeat: [],
    dateFields: [],
    longText: [],
    timestampFields: [],
  },
  archival_document: {
    fanOut: 'pieces',
    recordLabel: 'claim',
    shared: [],
    blankOnRepeat: ['claim', 'document.title', 'document.reference'],
    dateFields: [],
    longText: ['claim.interpretation'],
    timestampFields: [],
  },
  manufacturer_datasheet: {
    fanOut: 'pieces',
    recordLabel: 'claim',
    shared: [],
    blankOnRepeat: [],
    dateFields: [],
    longText: [],
    timestampFields: [],
  },
  era_heuristic: {
    fanOut: 'pieces',
    recordLabel: 'claim',
    shared: [],
    blankOnRepeat: [],
    dateFields: [],
    longText: [],
    timestampFields: [],
  },
  reinforcement_layout: {
    fanOut: 'single',
    recordLabel: 'layout',
    shared: [],
    blankOnRepeat: ['bars', 'document.title', 'document.reference'],
    dateFields: ['instrument.last_calibration_at'],
    longText: ['accuracy_note'],
    timestampFields: [],
  },
}

export function layoutOf(method: string): MethodLayout {
  return LAYOUTS[method] ?? {
    fanOut: 'single',
    recordLabel: 'record',
    shared: [],
    blankOnRepeat: [],
    dateFields: [],
    longText: [],
    timestampFields: [],
  }
}
