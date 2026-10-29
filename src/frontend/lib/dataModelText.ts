/**
 * The text of the "Data Model" reference page (decision 8.181): what the
 * catalog stores, for the people who use it. Written by hand from the data model
 * specification (`docs/adr/DATA_MODEL_SPEC.md`, sections 1 to 3 and Appendix A)
 * and the glossary (`CONTEXT.md`); left out are the API, permissions, invariants,
 * the migration and the mapping to the CPR, which stay in the specification.
 *
 * The page renders this module and nothing else: no sentence is written in JSX.
 * The one-line meaning of each vocabulary value is not here: it comes from the
 * backend (`GET /vocab`, generated into `generated/Vocab.ts`).
 *
 * A sentence where the specification was read loosely, or a choice was made, is
 * a `Marked` run: the specification section and what was loose are kept next to
 * it, shown on the page in development only, so that the wording can be checked
 * there first.
 */
import type { EvidenceMethod, Quantity } from '@/generated/Vocab'

// RUNS ---------------------------------------------------------------------------
/** A sentence marked for the check of the wording: `spec` is the section it reads. */
export type Marked = { text: string; spec: string; note: string }
/** A piece of a paragraph: plain text, or a marked sentence. */
export type Run = string | Marked
export type Para = Run[]

/** Marks a sentence. */
export const loose = (text: string, spec: string, note: string): Marked => ({ text, spec, note })

export function runText(run: Run): string {
  return typeof run === 'string' ? run : run.text
}

export function paraText(para: Para): string {
  return para.map(runText).join('')
}

export function isMarked(run: Run): run is Marked {
  return typeof run !== 'string'
}

// TABLES -------------------------------------------------------------------------
export type FieldRow = {
  /** the field as the API names it: it must exist in `model` of the generated models */
  name: string
  meaning: Para
  /** text, number, date, a list, a vocabulary ... */
  type: string
  example: string
  /** the server works the value out: nobody types it in */
  derived: boolean
}

export type FieldTable = {
  id: string
  title: string
  intro?: Para
  /** the generated interface the field names belong to (a test checks them) */
  model: string
  rows: FieldRow[]
}

export type Section = {
  id: string
  title: string
  lead: Para[]
  tables?: FieldTable[]
  /** more text after the tables */
  after?: Para[]
}

const row = (name: string, type: string, example: string, meaning: Para | string, derived = false): FieldRow => ({
  name, type, example, meaning: typeof meaning === 'string' ? [meaning] : meaning, derived,
})

// OVERVIEW AND RULES -------------------------------------------------------------
export const PAGE_TITLE = 'Data Model'

export const PAGE_LEAD: Para = [
  'What the ',
  'Catalog of Second Chances',
  ' stores about each element, in plain words: the four kinds of record, how they belong together, ',
  'the fields you see and fill in, and the lists of values you choose from.',
]

export const OVERVIEW: Section = {
  id: 'overview',
  title: 'The four records',
  lead: [
    [
      'The catalog keeps four kinds of record. A ',
      'dataset',
      ' is a project: it decides who may see and edit its elements. A ',
      'component identity',
      ' is the permanent record of one physical element. A ',
      'snapshot',
      ' is one state of that element: its shape and condition from a point in time. ',
      'An ',
      'evidence',
      ' record is one thing that was observed or claimed about the element: a test, a document, an inspection.',
    ],
    [
      loose(
        'A dataset holds many identities. An identity has many snapshots and many evidence records. ',
        '1',
        'The relations are read from the diagram of section 1; "has many" is the 1:N of the diagram.',
      ),
      'Evidence can name one snapshot when it refers to a place on the element, because a place needs the coordinates of one shape.',
    ],
  ],
}

export const RULES_TITLE = 'Four rules'
export const RULES_INTRO: Para = ['Four rules decide where a piece of information goes and who may write it.']

export type Rule = { id: string; title: string; body: Para }
export const RULES: Rule[] = [
  {
    id: 'rule-identity',
    title: 'The identity is the anchor',
    body: [
      loose(
        'What we know about an element hangs on its identity: results, documents and properties belong to it. ',
        '1, rule 1',
        'Rule 1 says "evidence and properties attach to the identity"; "results, documents" is a plain-words reading.',
      ),
      'The shape belongs to a snapshot. Nothing hangs on "the element" in the abstract.',
    ],
  },
  {
    id: 'rule-derived',
    title: 'Derived fields are never typed in',
    body: [
      'Some values are worked out by the server from what was stored: the properties of an element, its size and orientation, its shape class, its complexity, the fitted simple bodies, the descriptors, the waste code of the material and the list of inherited fields. ',
      loose(
        'Nobody types them in. Where a person may overrule one, the record says so: "assigned" instead of "derived"; an inherited field that a child changes leaves the list of inherited fields.',
        '1, rule 2',
        'The spec lists the derived fields and the "*_source: assigned" marker; here they are named in words.',
      ),
    ],
  },
  {
    id: 'rule-raw',
    title: 'Raw and derived stay apart',
    body: [
      loose(
        'A measured value stays as it was measured. A value worked out from it, such as a strength from a rebound reading, is stored as a separate, derived value and names the model that made it.',
        '1, rule 3',
        'The spec says "a rebound median is measured; a strength inferred from it is derived and names its model".',
      ),
      'The source tier of a property tells which kind of evidence it rests on.',
    ],
  },
  {
    id: 'rule-time',
    title: 'Time has two clocks',
    body: [
      loose(
        'The time a record was saved (created, last modified) is not the time something happened (effective from, observed at, sampled at). The name of each date field says which one it is.',
        '1, rule 4',
        'The spec calls this "bitemporal-lite"; the term is not used here.',
      ),
    ],
  },
]

// ENTITIES -----------------------------------------------------------------------
export const DATASET_SECTION: Section = {
  id: 'dataset',
  title: 'Dataset',
  lead: [
    [
      'A dataset is a project. It is the unit of membership, permission and visibility: every element belongs to exactly one dataset. ',
      'Members of a dataset have roles: contributor (adds elements and evidence), reviewer (confirms evidence) and moderator (publishes and edits).',
    ],
    [
      loose(
        'A published element is seen by the members of its dataset, by every signed-in user when the dataset is open to the catalog, and by anyone when the element is public. Administrators see everything.',
        '3.6',
        'The spec gives the rule as a table of viewers; this is the same rule in one sentence.',
      ),
    ],
  ],
  tables: [
    {
      id: 'dataset-fields',
      title: 'Fields of a dataset',
      model: 'DatasetView',
      rows: [
        row('_id', 'text (a short name)', 'example_dataset', 'The short name of the dataset, made by the server from its name. It never changes, and elements point to it.', true),
        row('name', 'text', 'Example Dataset', 'The name people read.'),
        row('description', 'text', 'A made-up dataset ...', 'What the dataset is about.'),
        row('visibility', '"members" or "catalog"', 'members', [
          loose(
            '"members": only members see its elements, unless an element is public. "catalog": every signed-in user sees them.',
            '3.6',
            'The spec names the two values and the three tiers; the wording is a summary.',
          ),
        ]),
        row('reviewed', 'yes or no', 'yes', 'An administrator has looked at a dataset that a user created. Only a reviewed dataset can be open to the catalog or have public elements.'),
        row('members', 'a list', 'one entry per person, with roles', 'The people with a role in the dataset. Only moderators and administrators see the list. Administrators hold every role in every dataset.'),
      ],
    },
  ],
}

const IDENTITY_ROWS: FieldRow[] = [
  row('_id', 'id', 'example-identity', 'The id of the element: the UUID of its QR tag, or made by the server when none is given.'),
  row('catalog_number', 'whole number', '90001 (made up)', 'A running number for people to quote. It is never used again.', true),
  row('original_function', 'one of the functions', 'IfcBeam', [
    'What the element was in its first life, named like an IFC element class. ',
    loose(
      'The reuse function is not recorded here: it is decided in design tools.',
      '2.1',
      'The spec says the reuse function is a design decision made outside CSC.',
    ),
  ]),
  row('material', 'one of the materials', 'concrete', 'The main material, from the catalog list of materials. The generic name, never a brand.'),
  row('material_class', 'text', '17 01 01', 'The waste code of the material (EU list of waste, chapter 17). Filled from the material; a moderator may assign another.', true),
  row('trade_name', 'text', 'ExampleBeam (made up)', 'The brand or product name, if there is one.'),
  row('manufacturer', 'text', 'the precast plant', 'Who made it.'),
  row('connection_features', 'text', 'Cast-in plates at both ends', 'Anchors, cast-in plates or holes on the element itself.'),
  row('material_separability', 'a class and a note', 'standard', 'How well the materials of the element can be separated, on the scale of the DGNB (see the classes below).'),
  row('dataset', 'a dataset', 'example_dataset', 'The dataset the element belongs to.'),
  row('manufactured_at', 'date and precision', '1968 (year)', 'When the material was made. Not the day the element was cut or deinstalled.'),
  row('origin', 'a block', 'deinstallation, 2026-01-20', 'How the element entered circulation: see the next section.'),
  row('parent_identities', 'a list of ids', 'the elements it was cut from', [
    'The elements this one was cut from or merged from. ',
    loose(
      'A child takes over origin, manufacture date, material (with its class), trade name, manufacturer, material separability and original function from its parent, unless it states its own; the server does the copying. When an element is merged from several parents, a field is taken over only if all parents agree.',
      '3.1.2',
      'The spec lists the inheritable fields with their units (material with its class, date with its precision) and the merge rule; here they are named in words.',
    ),
  ]),
  row('inherited_fields', 'a list', 'origin, material', 'Which fields a child still takes over from its parent. A field the child changes by hand leaves the list.', true),
  row('exit', 'a block', 'empty while available', 'How the element left circulation: see the next section.'),
  row('past_cycles', 'a list', 'one entry per earlier use', 'The earlier origin and exit of an element that came back into circulation.', true),
  row('withdrawn', 'a block', 'reason and date', [
    loose(
      'An element that was published is not deleted in normal use. It can be withdrawn, for example as a duplicate; members of the dataset still see it, everyone else sees a marker.',
      '3.1.4',
      'The spec also covers redaction and, for an administrator, purge; "not deleted in normal use" is the plain reading.',
    ),
  ]),
  row('is_public', 'yes or no', 'yes', 'Whether anyone can see the element without signing in.'),
  row('current_snapshot_id', 'a snapshot', 'example-snapshot-v1', 'The version that is shown by default. The first published version becomes it, and a correction takes over from the version it replaces; a moderator can choose another. Empty when no published version is left.'),
  row('properties', 'values with confidence', 'compressive strength 38.3 MPa', [
    'The results about the material, worked out from the published evidence: the value or range, how sure the server is, which kind of source it rests on and which records it used. ',
    loose(
      'For each quantity the server uses the most trusted kind of source that is present; records of a lower kind are set aside. The confidence grows with the number of records and with how well they are verified.',
      '2.5, 3.3.3, 4.4',
      'The spec gives a ranking of the source tiers per quantity, base confidences per tier and a factor per verification state; only the principle is told, not the numbers.',
    ),
  ], true),
  row('created', 'time', '2026-02-01T09:00:00Z', 'When the record was saved.', true),
]

export const IDENTITY_SECTION: Section = {
  id: 'identity',
  title: 'Component identity',
  lead: [
    [
      'The identity is the permanent record of one physical element, from its arrival to long after it left. ',
      'It holds what stays true across states: what the element was, what it is made of, where it came from and what we know about the material.',
    ],
  ],
  tables: [{ id: 'identity-fields', title: 'Fields of an identity', model: 'ComponentIdentity', rows: IDENTITY_ROWS }],
}

const ORIGIN_ROWS: FieldRow[] = [
  row('kind', 'one of five kinds', 'deinstallation', 'Which of the five ways the element entered circulation (see the list below).'),
  row('planned', 'yes or no', 'no', [
    loose(
      '"In place": the element is identified in its construction work but not deinstalled yet; the date is the planned one. Recording the deinstallation clears it.',
      '3.1.1, 3.1.6',
      'The spec calls it a planned origin; "in place" is the word of the glossary.',
    ),
  ]),
  row('at', 'date and precision', '2026-01-20 (day)', 'When the element left its previous context. A year alone is fine.'),
  row('place', 'name, address, position', 'Example Hall', 'Where that happened.'),
  row('construction_work', 'name, use, year built', 'Example Hall, workshop hall, 1968', 'The building or civil work the element left, never the company.'),
  row('position_in_work', 'text', 'Roof level, axis B', 'Where in that work the element sat.'),
  row('connection_types', 'several of the connection types', 'bolted, grouted', 'How the element was fixed in the work.'),
  row('detachability', 'a class and a note', 'standard', 'How easily it could be released, on the DGNB scale.'),
  row('method', 'text', 'Cut loose with a wire saw', 'How it was taken out.'),
  row('performed_by', 'a list of actors', 'the deconstruction contractor', 'Who did it (see "Actors" below).'),
  row('notes', 'text', '', 'Anything that fits nowhere else.'),
]

const EXIT_ROWS: FieldRow[] = [
  row('kind', 'one of seven kinds', 'installed', 'Which of the seven ways the element left circulation (see the list below).'),
  row('at', 'date and precision', '2027-05 (month)', 'When it left.'),
  row('construction_work', 'name, use, year built', 'Example Pavilion', 'Where it went, only for an installed element.'),
  row('notes', 'text', '', 'Anything that fits nowhere else.'),
  row('recorded_by_user_id', 'a user', '', [
    loose(
      'Empty when the server set the exit itself: a split or merge is set when the first cut element is published.',
      '3.1.3',
      'The spec explains the split and merge rule in detail; only its effect is named.',
    ),
  ], true),
]

export const ORIGIN_EXIT_SECTION: Section = {
  id: 'origin-exit',
  title: 'How an element entered and left circulation',
  lead: [
    [
      'The origin says how the element came into circulation, the exit how it left. An element without an exit is "in circulation": available and reservable. ',
      loose(
        'An element that is installed, returned or lost can come back with a new origin; the earlier origin and exit are kept as a past cycle. An element that was split, merged, recycled or disposed of cannot.',
        '3.1.3',
        'The spec calls split, merged, recycled and disposed terminal; the code lets installed, returned and lost re-enter. "Cannot come back" is the plain reading.',
      ),
    ],
  ],
  tables: [
    { id: 'origin', title: 'The origin', model: 'Origin', rows: ORIGIN_ROWS },
    { id: 'exit', title: 'The exit', model: 'Exit', rows: EXIT_ROWS },
  ],
}

const SNAPSHOT_ROWS: FieldRow[] = [
  row('_id', 'id', 'example-snapshot-v1', 'The id of this version, made by the server.', true),
  row('identity_id', 'an identity', 'example-identity', 'The element the version belongs to.'),
  row('version', 'whole number', '1', 'The number of the version, from 0.', true),
  row('status', 'one of the statuses', 'published', 'Where the version is in review: see "Review and checking" below.'),
  row('name', 'text', 'Beam after trimming', 'A short name for this state.'),
  row('effective_from', 'date and precision', '2026-03-10 (day)', 'The time from which this state holds. The next version takes over from its own date.'),
  row('supersedes', 'a version', 'empty', 'Set on a correction: the version it replaces. The replaced version stays readable.', true),
  row('geometry', 'meshes, point clouds, proxies', 'a scan and a fitted box', 'The shape of the element. A proxy is a simple body (box, prism, cylinder or hull) that stands for the shape.'),
  row('capture', 'a block', 'photogrammetry, a coordinate system', 'How the shape was recorded: the method, the device, the coordinate system and the markers. Not part of the element.'),
  row('frame', 'an origin and three axes', 'the standard orientation', 'The standard orientation of the element, worked out from its shape.', true),
  row('bbx', '3 numbers in mm', '4500, 300, 500', 'The size of the box around the element, along its own axes.', true),
  row('shape_class', 'one of the classes', 'linear', 'The kind of shape: see the list below. "Composite" is always set by hand.', true),
  row('complexity', '0 to 3', '1', 'How complicated the shape is. The server works it out; a moderator may overrule it.', true),
  row('descriptors', 'numbers', 'shape descriptors', 'Numbers that describe the shape, used to find similar elements.', true),
  row('properties', 'values with confidence', 'spalling 1', 'Results about this state (mass, damage, moisture), worked out from the evidence valid at the time of the version.', true),
  row('fragment', 'yes or no', 'no', 'Whether the element is a fragment of a larger one.'),
  row('quantity', 'whole number', '1', 'How many identical elements the record stands for. More than 1 makes the identity a batch.'),
  row('color', '3 numbers', '168, 168, 162', 'The colour used to draw the element.'),
  row('location', 'latitude and longitude', 'where the element is stored', 'Where the element is.'),
  row('notes', 'text', 'South end cut back', 'Free text.'),
  row('photo_count', 'whole number', '3', 'How many photos the version has.', true),
  row('added_by_username', 'user name', 'example-member', 'Who added the version.', true),
  row('created', 'time', '2026-03-10T09:00:00Z', 'When the record was saved.', true),
]

export const SNAPSHOT_SECTION: Section = {
  id: 'snapshot',
  title: 'Snapshot',
  lead: [
    [
      'A snapshot is one recorded state of an element: its shape and condition from a point in time until the next state. ',
      'The identity stays; the shape belongs to the snapshot. Every version has a number, from 0.',
    ],
    [
      loose(
        'When the element changes (cut, weathered, repaired), a new version with a later date is added. When a recorded fact was wrong, a correction replaces the wrong version: it keeps the date of the version it replaces, and the wrong one stays readable.',
        '3.2.2',
        'The spec calls them "state change" and "correction"; the sentence joins both rules and leaves out the roles.',
      ),
    ],
  ],
  tables: [{ id: 'snapshot-fields', title: 'Fields of a snapshot', model: 'ComponentSnapshot', rows: SNAPSHOT_ROWS }],
}

const EVIDENCE_ROWS: FieldRow[] = [
  row('_id', 'id', 'example-evidence-core', 'The id of the record, made by the server.', true),
  row('identity_id', 'an identity', 'example-identity', 'The element the record is about. Results attach to the identity.'),
  row('method', 'one of the methods', 'core_compression', 'What kind of record this is: see the methods below. The method decides what the payload holds.'),
  row('source_tier', 'one of the tiers', 'destructive', 'The kind of source. The server sets it from the method; for a reinforcement layout it follows the basis.', true),
  row('standard', 'code and year', 'EN 12504-1, 2019', 'The standard the work followed, if any.'),
  row('observed_at', 'date and precision', '2026-02-27 14:30 (exact)', 'When the result was produced.'),
  row('sampled_at', 'date and precision', '2026-02-20 11:00 (exact)', 'When the sample was taken from the element, if that is another time.'),
  row('performed_by', 'a list of actors', 'a laboratory', 'Who did the work (see "Actors" below).'),
  row('recorded_by_username', 'user name', 'example-member', 'Who entered the record.', true),
  row('position', 'kind, version, point, description', 'north face, mid-span', 'Where on the element, in the coordinates of one version. "None" with a description is always enough.'),
  row('summary', 'one result', 'compressive strength 38.3 MPa', 'The one result of the record: see "The result of a record" below. For a rebound test, a core, a reinforcement layout and a visual inspection (the worst observation) the server works it out from the payload and refuses a different value; for the other methods it is typed in. An archival document may have no result at all.'),
  row('derived', 'a list of results', 'in-situ strength', 'Values worked out from the result with a named model. They stay apart from the measured value. The server writes them for a core.'),
  row('payload', 'fields of the method', 'sampling, specimen, test, result', 'The details of the work. They differ by method; the examples show each one.'),
  row('destructive', 'yes or no', 'yes', 'Whether the work destroyed the sample.', true),
  row('attachments', 'a list of files', 'a test report as PDF', 'Files of the record: reports, drawings, photos. After publishing, files can only be added; a moderator can remove one with a reason.'),
  row('notes', 'text', '', 'Free text.'),
  row('status', 'one of the statuses', 'published', 'Where the record is in review: see "Review and checking" below.'),
  row('verification', 'a state, who and when', 'reviewed', 'Whether someone competent has confirmed the record: see "Review and checking" below.'),
  row('supersedes', 'a record', 'empty', 'Set on a correction: the record it replaces.', true),
  row('created', 'time', '2026-02-28T09:00:00Z', 'When the record was saved.', true),
]

const SUMMARY_ROWS: FieldRow[] = [
  row('quantity', 'one of the quantities', 'compressive_strength', 'What was measured or claimed: see the quantities below.'),
  row('value', 'number or text', '38.3', 'A value, for a measurement.'),
  row('range', 'a range', '18 to 28', 'A range, for a claim. A record may have a value, a range or both.'),
  row('unit', 'a unit', 'MPa', 'The unit the server stores.'),
  row('unit_entered', 'a unit', 'N/mm2', 'The unit as it was typed in. The server converts.'),
  row('kind', '"measured" or "claimed"', 'measured', 'A measurement was made on the element. A claim is stated by a document, a rule or an observer, for example an inspector.'),
  row('uncertainty', 'type and value', 'standard deviation 1.2', 'How uncertain the result is, if known.'),
]

const POSITION_ROWS: FieldRow[] = [
  row('kind', 'point, region, face or none', 'region', 'The kind of place.'),
  row('snapshot_id', 'a version', 'example-snapshot-v0', [
    loose(
      'The version whose coordinates the point uses. If the version is corrected later, the record keeps its version and the viewer draws it only there.',
      '3.3.2',
      'The spec also describes the warning when a correction changes the geometry; it is left out.',
    ),
  ]),
  row('point', '3 numbers', 'x, y, z in mm', 'The point, in the stored coordinates of that version.'),
  row('description', 'text', 'North face, mid-span', 'The place in words.'),
]

const VERIFICATION_ROWS: FieldRow[] = [
  row('state', 'one of the states', 'reviewed', 'The state: see the list of verification states below.'),
  row('by', 'an actor', 'a reviewer', 'Who confirmed it. The server sets it.', true),
  row('at', 'time', '2026-03-02T10:00:00Z', 'When.', true),
  row('note', 'text', 'Checked the load against the report', 'What the reviewer checked. Needed for "accredited".'),
]

export const EVIDENCE_SECTION: Section = {
  id: 'evidence',
  title: 'Evidence',
  lead: [
    [
      'An evidence record says what was observed or claimed about an element, by whom and when. ',
      'There is a kind of record for each way of knowing something, the evidence methods. ',
      'A record holds one result in a fixed place, the summary (an archival document may hold none), so that the server can combine the results of many records; the details of the work are in the payload.',
    ],
    [
      loose(
        'Evidence has two times: when the result was produced (observed at) and, if it differs, when the sample was taken from the element (sampled at).',
        '3.3',
        'The spec names them observed_at (result time) and sampled_at (phenomenon time).',
      ),
    ],
  ],
  tables: [
    { id: 'evidence-fields', title: 'Fields of an evidence record', model: 'EvidenceView', rows: EVIDENCE_ROWS },
    { id: 'evidence-result', title: 'The result of a record', model: 'Summary', rows: SUMMARY_ROWS },
    { id: 'evidence-position', title: 'The place on the element', model: 'Position', rows: POSITION_ROWS },
    { id: 'evidence-verification', title: 'The check of a record', model: 'Verification', rows: VERIFICATION_ROWS },
  ],
}

export const LIFECYCLE_SECTION: Section = {
  id: 'lifecycle',
  title: 'Review and checking',
  lead: [
    [
      'Two separate questions are asked of a snapshot or an evidence record. ',
      'Is it allowed in the catalog? That is the status, decided by a moderator. ',
      'Has someone competent confirmed what it claims? That is the verification, which only evidence has.',
    ],
    [
      'A record starts as a draft. Its author edits it and submits it; a moderator publishes or rejects it. ',
      loose(
        'Only a published record that has not been corrected is listed and counts in the results. A published record can later be withdrawn, and a moderator can reinstate it.',
        '3.3.3',
        'The spec gives the arrows draft, pending, published or rejected, withdrawn and back; the sentence names the effects.',
      ),
    ],
    [
      loose(
        'A published record is not edited: a mistake is fixed by a correction, a new record that replaces the old one. The old one stays readable and is marked as corrected. For evidence, the notes, the description of a place and the verification can still change, and files can be added. For a version of an element, the name, notes, location, colour and photos can still change, and a moderator can change its date and overrule its shape class and complexity.',
        '3.3.4, 3.2.2',
        'The spec lists the frozen fields of evidence (3.3.4) and of a snapshot (3.2.2) apart; here both are told by what stays editable.',
      ),
    ],
    [
      loose(
        'The verification has four states. Unverified: nobody has confirmed the record. Self-attested: the person who did the work and recorded it stands by it, so they must be among the performers. Reviewed: a second person with the reviewer role, who neither recorded nor performed the work, confirms it. Accredited: like reviewed, and the work was done by an organisation accredited for the standard. A higher state weighs more in the results; reviewed and accredited weigh the same.',
        '3.3.3',
        'The spec gives the factors 0.70, 0.85, 1.00 and 1.00 and the four-eyes rule (I27); the numbers are left out.',
      ),
    ],
  ],
}

const ACTOR_ROWS: FieldRow[] = [
  row('kind', '"user", "person" or "organization"', 'organization', 'A user has an account in the catalog; a person or an organisation does not.'),
  row('user_id', 'a user', '', 'The account, for a user.'),
  row('name', 'text', '', [
    loose(
      'The name of a person. Shown to signed-in users only.',
      '3.3.1',
      'The spec: anonymous callers get the organisation and the web page only.',
    ),
  ]),
  row('organization', 'text', 'a testing laboratory', 'The organisation, a laboratory or a contractor. Shown to everyone.'),
  row('organization_ror', 'a ROR id', 'https://ror.org/...', 'The id of the organisation in the Research Organization Registry.'),
  row('url', 'a web address', 'https://lab.example.org', 'The website of the organisation. Shown to everyone.'),
  row('orcid', 'an ORCID id', '0000-0002-1825-0097 (a sample id)', 'The ORCID of a person. Shown to signed-in users only.'),
  row('email', 'text', '', 'Shown to administrators and to the moderators of the dataset only, and never in lists.'),
  row('role', 'one of the roles', 'laboratory', 'What the actor did: operator, supervisor, laboratory, client or witness.'),
  row('accreditation', 'scheme, id, body, scope', 'ISO/IEC 17025', 'The accreditation of a laboratory, typed in. An "accredited" record needs one that covers the standard.'),
  row('redacted_at', 'time', '', 'Set when the personal data of the actor was removed on request.', true),
]

export const ACTOR_SECTION: Section = {
  id: 'actor',
  title: 'Actors',
  lead: [
    [
      'An actor is someone who did something: deinstalled an element, took a core, ran a test. ',
      loose(
        'When you add yourself to a record, the catalog copies your profile (name, organisation, website, ORCID) into the actor, so the record says where you worked then. A later change of the profile never changes an old record.',
        '3.3.1',
        'The spec calls this the profile copy; the website field came with 0.6.4.2.',
      ),
    ],
  ],
  tables: [{ id: 'actor-fields', title: 'Fields of an actor', model: 'Actor', rows: ACTOR_ROWS }],
}

export const ENTITY_SECTIONS: Section[] = [
  DATASET_SECTION,
  IDENTITY_SECTION,
  ORIGIN_EXIT_SECTION,
  SNAPSHOT_SECTION,
  EVIDENCE_SECTION,
  LIFECYCLE_SECTION,
  ACTOR_SECTION,
]

// VOCABULARIES -------------------------------------------------------------------
/** The vocabularies the page lists, by the name `GET /vocab` gives them. */
export const VOCAB_NAMES = [
  'original_function',
  'shape_class',
  'origin_kind',
  'exit_kind',
  'status',
  'precision',
  'dgnb_class',
  'connection_type',
  'construction_method',
  'material_group',
  'evidence_method',
  'source_tier',
  'verification_state',
  'quantity',
] as const
export type VocabName = (typeof VOCAB_NAMES)[number]

export type VocabSection = {
  id: string
  title: string
  vocab: VocabName
  intro: Para
  /** the column of the value */
  valueHeader: string
}

export const VOCABULARIES_INTRO: Para = [
  'Every list of values the catalog offers, each value with its label and what it means. ',
  'The lists are fixed in the code of the catalog; only the datasets and the materials grow with the projects.',
]

export const VOCAB_SECTIONS: VocabSection[] = [
  {
    id: 'original-function', title: 'Original function', vocab: 'original_function', valueHeader: 'IFC name',
    intro: ['What the element was in its first life, as the name of an IFC element class. No IFC model is imported.'],
  },
  {
    id: 'shape-class', title: 'Shape class', vocab: 'shape_class', valueHeader: 'Value',
    intro: ['The kind of shape of a version. The server works it out from the geometry; "composite" is always set by hand.'],
  },
  {
    id: 'origin-kind', title: 'How an element entered circulation', vocab: 'origin_kind', valueHeader: 'Value',
    intro: [
      'The kind matters for how the element may be reused later.',
    ],
  },
  {
    id: 'exit-kind', title: 'How an element left circulation', vocab: 'exit_kind', valueHeader: 'Value',
    intro: ['Split, merged, recycled and disposed end the element for good. An installed, returned or lost element can come back.'],
  },
  {
    id: 'status', title: 'Status', vocab: 'status', valueHeader: 'Value',
    intro: ['Where a snapshot or an evidence record is in review (see "Review and checking").'],
  },
  {
    id: 'precision', title: 'Time precision', vocab: 'precision', valueHeader: 'Value',
    intro: ['How exact a date is. It applies to every date a person enters: manufactured, origin, exit, effective from, observed and sampled.'],
  },
  {
    id: 'material-group', title: 'Material groups', vocab: 'material_group', valueHeader: 'Value',
    intro: [
      loose(
        'The materials themselves (about thirty) are kept in the catalog and extended by administrators; each belongs to a group and has a waste code. The groups are fixed.',
        '2.10',
        'The spec gives the seed list of materials with codes; it is not repeated.',
      ),
    ],
  },
  {
    id: 'dgnb-classes', title: 'Detachability and separability classes', vocab: 'dgnb_class', valueHeader: 'Value',
    intro: [
      loose(
        'A scale of the DGNB (a German sustainable-building council) for how easily an element is released from its work and how well its materials can be separated.',
        '2.11',
        'The spec gives both columns of the DGNB table; the one-line meaning here covers the two together.',
      ),
    ],
  },
  {
    id: 'connection-types', title: 'Connection types', vocab: 'connection_type', valueHeader: 'Value',
    intro: ['How an element was fixed in its work. More than one may apply.'],
  },
  {
    id: 'construction-methods', title: 'Construction methods', vocab: 'construction_method', valueHeader: 'Value',
    intro: ['How the construction work was built.'],
  },
  {
    id: 'evidence-methods', title: 'Evidence methods', vocab: 'evidence_method', valueHeader: 'Value',
    intro: ['The kinds of evidence record. Each has its own payload, shown in the examples.'],
  },
  {
    id: 'source-tiers', title: 'Source tiers', vocab: 'source_tier', valueHeader: 'Value',
    intro: [
      loose(
        'How much a kind of source is trusted, from the destructive test (most) to the rule of thumb (least). For each quantity the server uses the most trusted kind that is present; the order differs a little between quantities.',
        '2.5, 2.6',
        'The spec gives base confidences 0.90, 0.60, 0.40, 0.30 and 0.20 and a ranking per quantity; only the general order is told.',
      ),
    ],
  },
  {
    id: 'verification-states', title: 'Verification states', vocab: 'verification_state', valueHeader: 'Value',
    intro: ['Whether someone competent has confirmed an evidence record (see "Review and checking").'],
  },
  {
    id: 'quantities', title: 'Quantities', vocab: 'quantity', valueHeader: 'Value',
    intro: [
      loose(
        'What a result can be about. The scope says where the result lands: identity (a fact about the material, true in every state) or snapshot (a fact about one state).',
        '2.6',
        'The spec also gives the order of source tiers per quantity and rules for findings; they are left out.',
      ),
    ],
  },
]

// FACTS PER VOCABULARY VALUE ----------------------------------------------------
/** Unit, kind and scope of each quantity (spec 2.6). A new quantity is a type error until it is listed. */
export const QUANTITY_FACTS: Record<Quantity, { unit: string; kind: string; scope: 'identity' | 'snapshot' }> = {
  compressive_strength: { unit: 'MPa', kind: 'number', scope: 'identity' },
  compressive_strength_in_situ: { unit: 'MPa', kind: 'number', scope: 'identity' },
  rebound_number: { unit: '1', kind: 'number', scope: 'identity' },
  q_value: { unit: '1', kind: 'number', scope: 'identity' },
  density: { unit: 'kg/m3', kind: 'number', scope: 'identity' },
  rebar_diameter: { unit: 'mm', kind: 'number', scope: 'identity' },
  rebar_spec: { unit: '-', kind: 'category', scope: 'identity' },
  concrete_class: { unit: '-', kind: 'category', scope: 'identity' },
  steel_grade: { unit: '-', kind: 'category', scope: 'identity' },
  cover_depth: { unit: 'mm', kind: 'number', scope: 'identity' },
  exposure_class: { unit: '-', kind: 'category', scope: 'identity' },
  chloride_content: { unit: '% of cement mass', kind: 'number', scope: 'identity' },
  elastic_modulus: { unit: 'GPa', kind: 'number', scope: 'identity' },
  mass: { unit: 'kg', kind: 'number', scope: 'snapshot' },
  carbonation_depth: { unit: 'mm', kind: 'number', scope: 'snapshot' },
  spalling: { unit: '0 to 3', kind: 'severity', scope: 'snapshot' },
  cracking: { unit: '0 to 3', kind: 'severity', scope: 'snapshot' },
  corrosion: { unit: '0 to 3', kind: 'severity', scope: 'snapshot' },
  moisture_content: { unit: '%', kind: 'number', scope: 'snapshot' },
  crack_width: { unit: 'mm', kind: 'number', scope: 'snapshot' },
  condition_grade: { unit: '3 to 0', kind: 'grade (3 = good)', scope: 'snapshot' },
}

/** The source tier of each evidence method (spec 2.5); a layout follows its basis. */
export const METHOD_TIER: Record<EvidenceMethod, string> = {
  rebound_hammer: 'ndt',
  core_compression: 'destructive',
  archival_document: 'archival',
  visual_inspection: 'visual',
  era_heuristic: 'heuristic',
  manufacturer_datasheet: 'archival',
  reinforcement_layout: 'by basis: drawing archival, scan ndt, exposed visual',
}

// ANCHORS ------------------------------------------------------------------------
export const EXAMPLE_SECTION_ID = 'example'

/** A line of the table of contents. */
export type TocEntry = { id: string; title: string; children?: TocEntry[] }

/** The text shown for a vocabulary value that has no label of its own (status, precision, group). */
export function humanize(value: string): string {
  const text = value.replace(/[_-]/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** The label of a value of a vocabulary, with a fallback for the lists that have none. */
export function valueLabel(labels: Record<string, string>, value: string): string {
  const label = labels[value]
  return label && label !== value ? label : humanize(value)
}
