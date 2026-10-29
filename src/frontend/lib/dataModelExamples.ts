/**
 * The example piece of the "Data Model" page (decision 8.181 d): one made-up
 * concrete beam followed through the whole model --- its dataset, its identity,
 * two versions and one evidence record of every method. Nothing here is taken
 * from the catalog: no names of people or organisations (roles and "Example"
 * names instead), ids marked as examples, values after the examples of the
 * data model specification (Appendix A).
 *
 * Each record is its JSON and a comment per top-level field; the page shows
 * the JSON as a table of field, value and comment, and folds the raw JSON below
 * it. `model` names the generated interface the fields belong to, so that a test
 * fails when a field is renamed or dropped in the backend.
 */
import { loose, type Run } from '@/lib/dataModelText'

export type ExampleRecord = {
  id: string
  title: string
  /** what the record is, in a sentence or two */
  intro: Run[]
  /** the interface (generated models) of the record's top-level fields */
  model: string
  /** for an evidence record: the interface of its `payload` */
  payloadModel?: string
  json: Record<string, unknown>
  /** a sentence per top-level field of `json` (and per field of `payload`, as `payload.<name>`) */
  comments: Record<string, string | Run[]>
}

// the people and organisations are roles, not names (decision 8.181 d); the name of an account
// comes from its profile when the record is written
const LAB = [{ kind: 'organization', organization: 'A testing laboratory', role: 'laboratory' }]
const DECONSTRUCTION = [{ kind: 'organization', organization: 'The deconstruction contractor', role: 'operator' }]
const RECORDER = [{ kind: 'user', user_id: 'example-recorder', role: 'operator' }]
const REVIEWER = { kind: 'user', user_id: 'example-reviewer' }

const DATASET = 'example_dataset'
const IDENTITY = 'example-identity'
const V0 = 'example-snapshot-v0'
const V1 = 'example-snapshot-v1'

/** The note under every example: ids of the catalog are UUIDs. */
export const EXAMPLE_ID_NOTE =
  'The ids in these examples are marked "example-...". In the catalog, every id is a UUID.'

export const EXAMPLE_PIECE_INTRO: Run[] = [
  'One made-up element runs through this section: a precast concrete beam from a workshop hall. ',
  'It sits in a dataset, has an identity, two versions (as found, and after its damaged end was trimmed) ',
  'and one evidence record of every method. The people and organisations are roles, not names.',
]

export const EXAMPLE_DATASET: ExampleRecord = {
  id: 'example-dataset',
  title: 'The dataset',
  intro: [
    'The project the element belongs to. Members get roles; the visibility says who else can see the elements. ',
    'The member list is left out here.',
  ],
  model: 'DatasetView',
  json: {
    _id: DATASET,
    name: 'Example Dataset',
    description: 'A made-up dataset for the examples of this page.',
    visibility: 'members',
    reviewed: true,
  },
  comments: {
    _id: 'The short name of the dataset: lower-case letters, digits and underscores. The server makes it from the name. It never changes, and elements point to it.',
    name: 'The name people read.',
    description: 'What the dataset is about.',
    visibility: '"members": only members see its elements, unless an element is public. "catalog": every signed-in user sees them.',
    reviewed: 'An administrator has looked at the dataset. Only a reviewed dataset can have public elements.',
  },
}

export const EXAMPLE_IDENTITY: ExampleRecord = {
  id: 'example-identity',
  title: 'The identity',
  intro: [
    'The permanent record of the physical beam. It holds what stays true across states: ',
    'what it was, what it is made of, where it came from, and the results that come from evidence.',
  ],
  model: 'ComponentIdentity',
  json: {
    _id: IDENTITY,
    catalog_number: 90001,
    original_function: 'IfcBeam',
    material: 'concrete',
    material_class: '17 01 01',
    material_class_source: 'derived',
    trade_name: 'ExampleBeam',
    manufacturer: 'The precast plant',
    dataset: DATASET,
    manufactured_at: '1968-01-01T00:00:00Z',
    manufactured_precision: 'year',
    origin: {
      kind: 'deinstallation',
      at: '2026-01-20T00:00:00Z',
      at_precision: 'day',
      place: { name: 'Example Hall', address: 'Example Street 1, Example City' },
      construction_work: { name: 'Example Hall', use: 'workshop hall', year_built: 1968, construction_method: 'prefabricated' },
      position_in_work: 'Roof level, axis B',
      connection_types: ['bolted', 'grouted'],
      method: 'Cut loose with a wire saw and lifted out by crane',
      performed_by: DECONSTRUCTION,
    },
    parent_identities: null,
    exit: null,
    is_public: true,
    current_snapshot_id: V1,
    properties: {
      compressive_strength: {
        range: [38.3, 38.3],
        unit: 'MPa',
        confidence: 0.9,
        source: 'destructive',
        n: 1,
        evidence_ids: ['example-evidence-core'],
        inherited_from: null,
        derived_at: '2026-03-02T10:00:00Z',
      },
      compressive_strength_in_situ: {
        range: [38.3, 38.3],
        unit: 'MPa',
        confidence: 0.9,
        source: 'destructive',
        n: 1,
        evidence_ids: ['example-evidence-core'],
        inherited_from: null,
        derived_at: '2026-03-02T10:00:00Z',
      },
      rebound_number: {
        range: [43, 43],
        unit: '1',
        confidence: 0.42,
        source: 'ndt',
        n: 1,
        evidence_ids: ['example-evidence-rebound'],
        inherited_from: null,
        derived_at: '2026-03-02T10:00:00Z',
      },
      rebar_diameter: {
        range: [8, 20],
        unit: 'mm',
        confidence: 0.28,
        source: 'archival',
        n: 1,
        evidence_ids: ['example-evidence-layout'],
        inherited_from: null,
        derived_at: '2026-03-02T10:00:00Z',
      },
      rebar_spec: {
        range: ['BSt III'],
        unit: null,
        confidence: 0.28,
        source: 'archival',
        n: 1,
        evidence_ids: ['example-evidence-datasheet'],
        inherited_from: null,
        derived_at: '2026-03-02T10:00:00Z',
      },
      concrete_class: {
        range: ['B225'],
        unit: null,
        confidence: 0.28,
        source: 'archival',
        n: 1,
        evidence_ids: ['example-evidence-archival'],
        inherited_from: null,
        derived_at: '2026-03-02T10:00:00Z',
      },
    },
    created: '2026-02-01T09:00:00Z',
  },
  comments: {
    _id: 'The id of the element. The QR tag on the beam carries this id.',
    catalog_number: 'A running number for people to quote. It is never used again. This one is far above the numbers of the catalog, so that it cannot be taken for a real element.',
    original_function: 'What the element was in its first life. See the list of functions below.',
    material: 'The main material, from the catalog list of materials.',
    material_class: 'The waste code of the material (EU list of waste, chapter 17). The server fills it from the material.',
    material_class_source: '"derived": taken from the material. "assigned": a moderator chose another code.',
    trade_name: 'The brand or product name, if there is one. Made up here.',
    manufacturer: 'Who made it, as text. A role here, not a company.',
    dataset: 'The dataset the element belongs to.',
    manufactured_at: 'When the material was made. Not the day it was cut or deinstalled.',
    manufactured_precision: 'How exact the date is. Here only the year is known.',
    origin: 'How the element came into circulation. See "How an element entered circulation".',
    parent_identities: 'The elements this one was cut from, if any. None here.',
    exit: 'How the element left circulation. Empty while it is available.',
    is_public: 'Whether anyone can see the element without signing in.',
    current_snapshot_id: 'The version that is shown by default. The first published version becomes it; a moderator can pick another.',
    properties: 'The results the server worked out from the published evidence, with how sure it is and which records it used. Nobody types them in. For each quantity the most trusted source wins: the core outranks the era estimate for the compressive strength.',
    created: 'When the record was made.',
  },
}

export const EXAMPLE_SNAPSHOT_V0: ExampleRecord = {
  id: 'example-snapshot-v0',
  title: 'The first version',
  intro: ['The beam as it was found: shape, size and the time from which this state counts.'],
  model: 'ComponentSnapshot',
  json: {
    _id: V0,
    identity_id: IDENTITY,
    version: 0,
    status: 'published',
    name: 'Beam as deinstalled',
    effective_from: '2026-02-01T00:00:00Z',
    effective_from_precision: 'day',
    shape_class: 'linear',
    shape_class_source: 'derived',
    geometry: {
      proxies: [
        {
          primitive: 'box',
          role: 'primary',
          params: { size: [4800, 300, 500] },
          placement: { o: [0, 0, 0], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] },
          fit: { method: 'authored' },
        },
      ],
    },
    bbx: [4800, 300, 500],
    complexity: 1,
    complexity_source: 'derived',
    fragment: false,
    quantity: 1,
    location: { lat: 50.0, lon: 8.0 },
    notes: 'Small spalls at the lower edge of the south end.',
    added_by_username: 'example-member',
    created: '2026-02-01T09:30:00Z',
  },
  comments: {
    _id: 'The id of this version.',
    identity_id: 'The element this version belongs to.',
    version: 'The number of the version, from 0.',
    status: 'Where the version is in review. Only published versions are listed.',
    name: 'A short name for this state.',
    effective_from: 'The time from which this state holds. A later version takes over from its own date.',
    effective_from_precision: 'How exact that date is.',
    shape_class: 'The kind of shape, worked out from the geometry.',
    shape_class_source: '"derived": worked out by the server. "assigned": set by hand.',
    geometry: 'The shape of the element: scans, point clouds and simple bodies (proxies). Here one box, drawn by hand; a scanned element also has a mesh or a point cloud.',
    bbx: 'The size of the box around the element in mm, along its own axes. The server works it out.',
    complexity: 'How complicated the shape is, from 0 to 3. The server works it out.',
    complexity_source: '"derived" or "assigned", as for the shape class.',
    fragment: 'Whether the element is a fragment of a larger one.',
    quantity: 'How many identical elements this record stands for. 1 for a single element.',
    location: 'Where the element is stored.',
    notes: 'Free text.',
    added_by_username: 'Who added the version.',
    created: 'When the record was made.',
  },
}

export const EXAMPLE_SNAPSHOT_V1: ExampleRecord = {
  id: 'example-snapshot-v1',
  title: 'The second version',
  intro: [
    'A state change: the damaged end was trimmed, so the beam is shorter. It is a new version with a later date; ',
    'the first version stays as it was.',
  ],
  model: 'ComponentSnapshot',
  json: {
    _id: V1,
    identity_id: IDENTITY,
    version: 1,
    status: 'published',
    name: 'Beam after trimming the damaged end',
    effective_from: '2026-03-10T00:00:00Z',
    effective_from_precision: 'day',
    shape_class: 'linear',
    shape_class_source: 'derived',
    bbx: [4500, 300, 500],
    complexity: 1,
    complexity_source: 'derived',
    geometry: {
      proxies: [
        {
          primitive: 'box',
          role: 'primary',
          params: { size: [4500, 300, 500] },
          placement: { o: [0, 0, 0], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] },
          fit: { method: 'authored' },
        },
      ],
    },
    quantity: 1,
    notes: 'South end cut back by 300 mm.',
  },
  comments: {
    _id: 'The id of this version.',
    identity_id: 'The same element.',
    version: 'The next number.',
    status: 'Published, and made the current version by the moderator.',
    name: 'A short name for this state.',
    effective_from: 'Later than the first version: the beam changed on this day.',
    effective_from_precision: 'Exact to the day.',
    shape_class: 'Still linear.',
    shape_class_source: 'Worked out again by the server.',
    geometry: 'The new shape: the box is 300 mm shorter.',
    bbx: 'The box is 300 mm shorter than before.',
    complexity: 'Worked out again by the server.',
    complexity_source: 'Worked out by the server.',
    quantity: 'Still one element.',
    notes: 'Says what changed.',
  },
}

export const EXAMPLE_REBOUND: ExampleRecord = {
  id: 'example-rebound-hammer',
  title: 'Rebound hammer',
  intro: ['A rebound hammer test on the north face. It records the reading, never a strength.'],
  model: 'EvidenceView',
  payloadModel: 'ReboundHammerPayload',
  json: {
    _id: 'example-evidence-rebound',
    identity_id: IDENTITY,
    method: 'rebound_hammer',
    source_tier: 'ndt',
    standard: { code: 'EN 12504-2', year: 2021 },
    observed_at: '2026-02-19T10:00:00Z',
    observed_at_precision: 'exact',
    performed_by: LAB,
    recorded_by_username: 'example-recorder',
    position: { kind: 'region', snapshot_id: V0, description: 'North face, mid-span' },
    summary: { quantity: 'rebound_number', value: 43, unit: '1', kind: 'measured' },
    payload: {
      instrument: { hammer_type: 'N', impact_energy_nm: 2.207, last_calibration_at: '2026-01-15' },
      test_area: { label: 'TA-1', surface_preparation: 'ground', surface_condition: 'dry', carbonation_depth_mm: null, member_thickness_mm: 300, support: 'loose' },
      impact_direction: 'horizontal',
      readings: [44, 42, 41, 45, 43, 42, 40, 44, 43],
      reading_unit: '1',
      rejected_reading_indices: [],
      outlier_policy: 'en_12504_2',
      set_discarded: false,
      n_valid: 9,
      median: 43,
    },
    status: 'published',
    verification: { state: 'unverified' },
  },
  comments: {
    _id: 'The id of the record.',
    identity_id: 'The element the record is about. Results attach to the identity.',
    method: 'What kind of record this is.',
    source_tier: 'The kind of source. The server sets it from the method.',
    standard: 'The standard the test followed.',
    observed_at: 'When the result was produced. Before the core of the next record was taken next to this test area.',
    observed_at_precision: 'How exact that time is.',
    performed_by: 'Who did it. A laboratory, named by its role.',
    recorded_by_username: 'Who entered the record. The server sets it.',
    position: 'Where on the element, in the coordinates of one version.',
    summary: 'The one result that counts: the median rebound number. It is a reading, not a strength. The server works it out from the readings and refuses another value.',
    payload: 'The details of the test, below.',
    'payload.instrument': 'The hammer: type, impact energy and last calibration.',
    'payload.test_area': [
      'The area tested: surface, thickness and support. ',
      loose(
        'Here the 300 mm side of the beam, lying loose on supports.',
        'A.1',
        'The spec example has a thickness of 180 mm and a support fixed in the structure; the values were chosen to fit this beam.',
      ),
    ],
    'payload.impact_direction': 'The direction of the blows. Horizontal needs no correction.',
    'payload.readings': 'Every reading, in order. At least nine are needed.',
    'payload.reading_unit': '"1" for the rebound number R, "Q" for a Q-type hammer.',
    'payload.rejected_reading_indices': 'Readings that were flagged and left out. They are never deleted.',
    'payload.outlier_policy': 'The rule used to judge the set.',
    'payload.set_discarded': 'The server marks a set as unusable when too many readings are far from the median.',
    'payload.n_valid': 'How many readings count.',
    'payload.median': 'The median of the readings. The server works it out and checks it.',
    status: 'Published: it counts in the results.',
    verification: 'Nobody has confirmed it yet. A second person with the reviewer role could raise it to "reviewed".',
  },
}

export const EXAMPLE_CORE: ExampleRecord = {
  id: 'example-core-compression',
  title: 'Core in compression',
  intro: ['A core drilled out of the beam and crushed in a press. A destructive test, so the result is trusted most.'],
  model: 'EvidenceView',
  payloadModel: 'CoreCompressionPayload',
  json: {
    _id: 'example-evidence-core',
    identity_id: IDENTITY,
    method: 'core_compression',
    source_tier: 'destructive',
    standard: { code: 'EN 12504-1', year: 2019 },
    observed_at: '2026-02-27T14:30:00Z',
    observed_at_precision: 'exact',
    sampled_at: '2026-02-20T11:00:00Z',
    sampled_at_precision: 'exact',
    performed_by: LAB,
    recorded_by_username: 'example-recorder',
    position: { kind: 'point', snapshot_id: V0, point: [2400, 0, 250], description: 'North face, mid-span, next to the rebound test area' },
    summary: { quantity: 'compressive_strength', value: 38.3, unit: 'MPa', kind: 'measured' },
    derived: [
      {
        quantity: 'compressive_strength_in_situ',
        value: 38.3,
        unit: 'MPa',
        kind: 'derived',
        model: { kind: 'en_13791', reference: 'EN 13791:2019 + DIN EN 13791/A20:2022-04', note: '2:1 core: f_c,is equals the core strength' },
      },
    ],
    payload: {
      sampling: { cored_at: '2026-02-20T11:00:00Z', drill_diameter_mm: 100, drilling_method: 'wet', orientation_vs_casting: 'perpendicular' },
      specimen: { label: 'C-03', measured_diameter_mm: 99.6, length_prepared_mm: 199.2, end_preparation: 'ground', ld_class: '2:1', storage: 'sealed', valid_for_strength: true },
      test: { tested_at: '2026-02-27T14:30:00Z', loading_rate_mpa_s: 0.6, max_load_kn: 298.4, failure_type: 'satisfactory' },
      result: { fc_core_mpa: 38.3, fc_is_cyl_mpa: 38.3 },
    },
    destructive: true,
    status: 'published',
    verification: {
      state: 'reviewed',
      by: REVIEWER,
      at: '2026-03-02T10:00:00Z',
      note: 'Checked the load and the area against the report',
    },
  },
  comments: {
    _id: 'The id of the record.',
    identity_id: 'The element the core was taken from.',
    method: 'What kind of record this is.',
    source_tier: 'Destructive: the sample was destroyed in the test.',
    standard: 'The standards the drilling and the test followed.',
    observed_at: 'When the result was produced: the day of the test.',
    observed_at_precision: 'How exact that time is.',
    sampled_at: 'When the core was taken from the element. It can be earlier than the test.',
    sampled_at_precision: 'How exact that time is.',
    performed_by: 'The laboratory.',
    recorded_by_username: 'Who entered the record. The server sets it.',
    position: 'Where the core was taken: a point in the coordinates of one version (in mm).',
    summary: 'The measured strength of the core. The server works it out from the load and the area.',
    derived: 'A value worked out from the result with a named model (here a rule of the standard EN 13791), kept apart from the measured one. The server writes it. For a core with a length to diameter ratio of 2:1 it equals the core value; a 1:1 core is multiplied by 0.82.',
    payload: 'The details of the test, below.',
    'payload.sampling': 'How the core was drilled.',
    'payload.specimen': 'The prepared core: size, ends, storage. The server works out the length-to-diameter class.',
    'payload.test': 'The test run: loading rate, load at failure and how it failed.',
    'payload.result': 'The strength results. The server checks them against the load and the area.',
    status: 'Published: it counts in the results.',
    destructive: 'Whether the work destroyed the sample. The server sets it from the method.',
    verification: 'A second person with the reviewer role confirmed the record: the state, who, when and what they checked.',
  },
}

export const EXAMPLE_ARCHIVAL: ExampleRecord = {
  id: 'example-archival-document',
  title: 'Archival document',
  intro: ['A drawing found in an archive. It says the concrete was of class B225. A claim, not a measurement.'],
  model: 'EvidenceView',
  payloadModel: 'ArchivalDocumentPayload',
  json: {
    _id: 'example-evidence-archival',
    identity_id: IDENTITY,
    method: 'archival_document',
    source_tier: 'archival',
    observed_at: '1968-03-01T00:00:00Z',
    observed_at_precision: 'month',
    performed_by: RECORDER,
    recorded_by_username: 'example-recorder',
    position: { kind: 'none', description: 'Applies to the whole beam' },
    summary: { quantity: 'concrete_class', range: ['B225'], kind: 'claimed' },
    payload: {
      document: { title: 'Structural drawing of the roof beams', date: '1968-03', kind: 'drawing', reference: 'Drawing 12/B' },
      claim: { text: 'B225', interpretation: 'An old German concrete class, as written on the drawing' },
    },
    status: 'published',
    verification: { state: 'unverified' },
  },
  comments: {
    _id: 'The id of the record.',
    identity_id: 'The element the document is about.',
    method: 'What kind of record this is.',
    source_tier: 'Archival: it comes from a document.',
    observed_at: 'The date of the document.',
    observed_at_precision: 'Only the month is known.',
    performed_by: 'Who found and recorded it: the account that entered the record.',
    recorded_by_username: 'Who entered the record. The server sets it.',
    position: 'No point on the element: the claim is about the whole beam.',
    summary: 'The claim: a concrete class. A claim has a range or a value, never a measured result.',
    payload: 'The document and the claim, below.',
    'payload.document': 'Title, date, kind and reference of the document. The file itself is an attachment.',
    'payload.claim': 'What the document says, and how it is read.',
    status: 'Published.',
    verification: 'Nobody has checked the claim yet.',
  },
}

export const EXAMPLE_VISUAL: ExampleRecord = {
  id: 'example-visual-inspection',
  title: 'Visual inspection',
  intro: ['An inspector looked at the beam. One record per thing observed: here the spalling at the south end.'],
  model: 'EvidenceView',
  payloadModel: 'VisualInspectionPayload',
  json: {
    _id: 'example-evidence-visual',
    identity_id: IDENTITY,
    method: 'visual_inspection',
    source_tier: 'visual',
    observed_at: '2026-02-02T10:00:00Z',
    observed_at_precision: 'day',
    performed_by: RECORDER,
    recorded_by_username: 'example-recorder',
    position: { kind: 'region', snapshot_id: V0, description: 'South end' },
    summary: { quantity: 'spalling', value: 1, kind: 'claimed' },
    payload: { observations: [{ quantity: 'spalling', value: 1, note: 'Small spalls at the lower edge' }] },
    status: 'published',
    verification: { state: 'self_attested', by: RECORDER[0], at: '2026-02-02T10:30:00Z' },
  },
  comments: {
    _id: 'The id of the record.',
    identity_id: 'The element that was inspected.',
    method: 'What kind of record this is.',
    source_tier: 'Visual: an observation by a person.',
    observed_at: 'The day of the inspection.',
    observed_at_precision: 'Exact to the day.',
    performed_by: 'The inspector: the account that entered the record. For "self-attested" the recorder must be among the performers.',
    recorded_by_username: 'Who entered the record. The server sets it.',
    position: 'Where on the element, in words, in the coordinates of one version.',
    summary: 'The severity of spalling, from 0 (none) to 3 (severe). The server takes the worst observation from the payload and refuses another value.',
    payload: 'The observation, below.',
    'payload.observations': 'What was seen: the quantity, its value and a note. Photos are attachments of the record.',
    status: 'Published.',
    verification: 'The inspector stands by it (self-attested): the state, who and when. The server sets who and when.',
  },
}

export const EXAMPLE_ERA: ExampleRecord = {
  id: 'example-era-heuristic',
  title: 'Rule of thumb (era, region, typology)',
  intro: ['An estimate from the year of construction: concrete of the 1960s in this region is often in this range.'],
  model: 'EvidenceView',
  payloadModel: 'EraHeuristicPayload',
  json: {
    _id: 'example-evidence-era',
    identity_id: IDENTITY,
    method: 'era_heuristic',
    source_tier: 'heuristic',
    observed_at: '2026-02-01T00:00:00Z',
    observed_at_precision: 'day',
    performed_by: RECORDER,
    recorded_by_username: 'example-recorder',
    position: { kind: 'none', description: 'Applies to the whole beam' },
    summary: { quantity: 'compressive_strength', range: [18, 28], unit: 'MPa', kind: 'claimed' },
    payload: { basis: 'construction_year', year: 1968, source: 'A guide to concrete of the 1960s' },
    status: 'published',
    verification: { state: 'unverified' },
  },
  comments: {
    _id: 'The id of the record.',
    identity_id: 'The element the estimate is for.',
    method: 'What kind of record this is.',
    source_tier: 'Heuristic: the least trusted source.',
    observed_at: 'When the estimate was made.',
    observed_at_precision: 'Exact to the day.',
    performed_by: 'Who made the estimate.',
    recorded_by_username: 'Who entered the record. The server sets it.',
    position: 'The whole beam.',
    summary: 'A range of strengths, claimed, not measured.',
    payload: 'What the estimate rests on, below.',
    'payload.basis': 'The kind of rule: the year of construction, the practice of a region or a type.',
    'payload.year': 'The year used.',
    'payload.source': 'Where the rule comes from.',
    status: 'Published.',
    verification: 'Nobody has checked it.',
  },
}

export const EXAMPLE_DATASHEET: ExampleRecord = {
  id: 'example-manufacturer-datasheet',
  title: 'Manufacturer datasheet',
  intro: ['A datasheet of the manufacturer of the beam. It names the product and where the sheet is kept.'],
  model: 'EvidenceView',
  payloadModel: 'ManufacturerDatasheetPayload',
  json: {
    _id: 'example-evidence-datasheet',
    identity_id: IDENTITY,
    method: 'manufacturer_datasheet',
    source_tier: 'archival',
    observed_at: '1968-01-01T00:00:00Z',
    observed_at_precision: 'year',
    performed_by: RECORDER,
    recorded_by_username: 'example-recorder',
    position: { kind: 'none', description: 'Applies to the whole beam' },
    summary: { quantity: 'rebar_spec', value: 'BSt III', kind: 'claimed' },
    payload: { manufacturer: 'The precast plant', product: 'Roof beam type B', reference: 'Datasheet 1968-04' },
    status: 'published',
    verification: { state: 'unverified' },
  },
  comments: {
    _id: 'The id of the record.',
    identity_id: 'The element the sheet is about.',
    method: 'What kind of record this is.',
    source_tier: 'Archival: it comes from a document.',
    observed_at: 'The date of the sheet.',
    observed_at_precision: 'Only the year is known.',
    performed_by: 'Who entered the sheet. The manufacturer is named in the payload.',
    recorded_by_username: 'Who entered the record. The server sets it.',
    position: 'The whole beam.',
    summary: 'What the sheet claims: here the steel grade of the reinforcement bars.',
    payload: 'Who made it and which sheet, below.',
    'payload.manufacturer': 'The manufacturer, as a role.',
    'payload.product': 'The product named on the sheet.',
    'payload.reference': 'The number or title of the sheet.',
    status: 'Published.',
    verification: 'Nobody has checked it.',
  },
}

export const EXAMPLE_LAYOUT: ExampleRecord = {
  id: 'example-reinforcement-layout',
  title: 'Reinforcement layout',
  intro: ['The reinforcement of the beam as bars, taken from the drawing. The bars are drawn in the viewer on the version named in the position.'],
  model: 'EvidenceView',
  payloadModel: 'ReinforcementLayoutPayload',
  json: {
    _id: 'example-evidence-layout',
    identity_id: IDENTITY,
    method: 'reinforcement_layout',
    source_tier: 'archival',
    observed_at: '1968-03-01T00:00:00Z',
    observed_at_precision: 'month',
    performed_by: RECORDER,
    recorded_by_username: 'example-recorder',
    position: { kind: 'none', snapshot_id: V0, description: 'Whole element; bars in the stored coordinates of this version' },
    summary: { quantity: 'rebar_diameter', range: [8, 20], unit: 'mm', kind: 'claimed' },
    payload: {
      basis: 'drawing',
      document: { title: 'Structural drawing of the roof beams', date: '1968-03', reference: 'Drawing 12/B' },
      accuracy_note: 'Hooks and stirrup corners are not drawn',
      bars: [
        { spec: 'BSt III', diameter_mm: 20, diameter_known: true, points: [[0, 40, 40], [4800, 40, 40]] },
        { spec: 'BSt III', diameter_mm: 8, diameter_known: true, points: [[100, 40, 40], [100, 40, 460]] },
      ],
    },
    status: 'published',
    verification: { state: 'unverified' },
  },
  comments: {
    _id: 'The id of the record.',
    identity_id: 'The element the layout is for.',
    method: 'What kind of record this is.',
    source_tier: 'Follows the basis: a drawing is archival, a scan is non-destructive, an exposed bar is visual.',
    observed_at: 'The date of the drawing.',
    observed_at_precision: 'Only the month is known.',
    performed_by: 'Who entered the layout.',
    recorded_by_username: 'Who entered the record. The server sets it.',
    position: 'Names the version whose coordinates the bars use. A new version with new coordinates needs a new layout.',
    summary: 'The range of bar diameters. The server works it out from the bars.',
    payload: 'The basis, the document and the bars, below.',
    'payload.basis': '"drawing", "scan" or "exposed": where the layout comes from.',
    'payload.document': 'The drawing. The file is an attachment.',
    'payload.accuracy_note': 'What the layout does not show. Only signed-in users see this note.',
    'payload.bars': 'One entry per bar: steel grade, diameter and the centre line as a list of points in mm.',
    status: 'Published.',
    verification: 'Nobody has checked it.',
  },
}

/** The evidence examples, in the order of the list of methods. */
export const EXAMPLE_EVIDENCE: ExampleRecord[] = [
  EXAMPLE_REBOUND,
  EXAMPLE_CORE,
  EXAMPLE_ARCHIVAL,
  EXAMPLE_VISUAL,
  EXAMPLE_ERA,
  EXAMPLE_DATASHEET,
  EXAMPLE_LAYOUT,
]

export const EXAMPLE_RECORDS: ExampleRecord[] = [
  EXAMPLE_DATASET,
  EXAMPLE_IDENTITY,
  EXAMPLE_SNAPSHOT_V0,
  EXAMPLE_SNAPSHOT_V1,
  ...EXAMPLE_EVIDENCE,
]
