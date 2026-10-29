/**
 * What the evidence form says is missing, by section (decision 8.134 a, e).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { initialState, newObservation } from '@/components/evidence/form/state'
import type { JsonSchema, MethodInfo } from '@/lib/evidence/api'
import {
  barIssues,
  formIssues,
  issuesOf,
  payloadIssues,
  sectionOfPath,
  sectionStates,
  serverIssues,
  targetOfPath,
} from '@/lib/evidence/issues'

const REBOUND: JsonSchema = {
  type: 'object',
  required: ['instrument', 'readings', 'test_area'],
  properties: {
    instrument: { $ref: '#/$defs/Instrument' },
    test_area: { $ref: '#/$defs/Area' },
    readings: { type: 'array', items: { type: 'number' }, minItems: 9, title: 'Readings' },
    deviations: { anyOf: [{ type: 'string' }, { type: 'null' }], default: null },
  },
  $defs: {
    Instrument: {
      type: 'object', required: ['hammer_type'],
      properties: {
        hammer_type: { type: 'string', enum: ['N', 'L'], title: 'Hammer type' },
        last_calibration_at: { anyOf: [{ type: 'string' }, { type: 'null' }], default: null, title: 'Last calibration at' },
      },
    },
    Area: {
      type: 'object', required: ['surface_preparation'],
      properties: {
        surface_preparation: { type: 'string', enum: ['ground', 'as_found'], title: 'Surface preparation' },
        label: { anyOf: [{ type: 'string' }, { type: 'null' }], default: null },
        min_spacing_mm: { type: 'number', default: 25, title: 'Min spacing mm' },
      },
    },
  },
}

const LAYOUT: JsonSchema = {
  type: 'object',
  required: ['basis', 'bars'],
  properties: {
    basis: { type: 'string', enum: ['drawing', 'scan', 'exposed'], title: 'Basis' },
    bars: { type: 'array', items: { $ref: '#/$defs/Bar' }, title: 'Bars' },
  },
  $defs: {
    Bar: {
      type: 'object', required: ['diameter_mm', 'points'],
      properties: {
        diameter_mm: { type: 'number', title: 'Diameter mm' },
        points: { type: 'array', items: { type: 'array', items: { type: 'number' } }, minItems: 2, title: 'Points' },
      },
    },
  },
}

function method(name: string, schema: JsonSchema, extra: Partial<MethodInfo> = {}): MethodInfo {
  return {
    name, label: name, description: '', source_tier: null, tier_from_payload: false, destructive: false,
    default_standard: null, summary_quantities: [], summary_from_client: false, summary_kind: null,
    context_time: 'observed_at', position_required: false, version: 1, derived_models: [],
    payload_schema: schema, ...extra,
  }
}

test('an empty required field, a required number list and a required choice are missing', () => {
  const m = method('rebound_hammer', REBOUND)
  const state = initialState(m, 'id')
  const issues = formIssues(state, m)
  const messages = issues.filter((i) => i.section === 'what').map((i) => i.message)
  assert.ok(messages.some((t) => t.includes('Hammer type is missing')), messages.join(' | '))
  assert.ok(messages.some((t) => t.includes('Surface preparation is missing')), messages.join(' | '))
  assert.ok(messages.some((t) => t.includes('Readings is missing')), messages.join(' | '))
  // a shared field is named once, without a record number, and points at the shared block
  const instrument = issues.find((i) => i.message.includes('Hammer type'))
  assert.ok(instrument && !instrument.message.startsWith('Test area') && instrument.target === 'record-shared-instrument-hammer_type')
  assert.equal(instrument.record, undefined)
  // a record's own field names the record and its field
  const area = issues.find((i) => i.message.includes('Surface preparation'))
  assert.ok(area && area.message.startsWith('Test area 1:') && area.target === 'record-r0-test_area-surface_preparation')
  assert.equal(area.record, 0)
})

test('a filled form has no issue of its own; a number that is none and too few readings are named', () => {
  const m = method('rebound_hammer', REBOUND)
  const state = initialState(m, 'id')
  state.shared = { instrument: { hammer_type: 'N', last_calibration_at: '' } }
  state.records[0].payload = {
    test_area: { surface_preparation: 'ground', label: '', min_spacing_mm: 'abc' },
    readings: ['40', '41', '42'], deviations: '',
  }
  const messages = formIssues(state, m).map((i) => i.message)
  assert.ok(messages.some((t) => t.includes('Min spacing mm is not a number')), messages.join(' | '))
  assert.ok(messages.some((t) => t.includes('Readings: at least 9 needed')), messages.join(' | '))
  state.records[0].payload.readings = Array.from({ length: 9 }, () => '40')
  ;(state.records[0].payload.test_area as Record<string, string>).min_spacing_mm = '25'
  assert.deepEqual(formIssues(state, m), [])
})

test('the observation date is checked unless the method dates itself', () => {
  const m = method('rebound_hammer', { type: 'object', properties: {} })
  const state = initialState(m, 'id')
  state.observedAt = ''
  assert.deepEqual(formIssues(state, m).map((i) => [i.section, i.target]), [['who', 'observed-at']])
  state.observedAt = '2026-02-30'
  assert.equal(formIssues(state, m)[0].message, '2026-02 has 28 days.')
  state.observedAt = '2026-02-27'
  assert.deepEqual(formIssues(state, m), [])
  const core = method('core_compression', { type: 'object', properties: {} }, { context_time: 'sampled_at' })
  const coreState = initialState(core, 'id')
  coreState.observedAt = ''
  assert.deepEqual(formIssues(coreState, core), [])
})

test('a date field of the payload is checked as a day, a flexible one as year, month or day', () => {
  const schema: JsonSchema = {
    type: 'object',
    properties: {
      cored_at: { type: 'string', title: 'Cored at' },
      document: { $ref: '#/$defs/Doc' },
    },
    $defs: { Doc: { type: 'object', properties: { date: { type: 'string', title: 'Date' } } } },
    required: ['cored_at'],
  }
  const options = { dateFields: ['cored_at'], flexDateFields: ['document.date'] }
  const bad = payloadIssues(schema, schema, { cored_at: '2024', document: { date: '1974-13' } }, 'x', options)
  assert.deepEqual(bad.map((i) => i.message), ['Cored at: Finish the date: YYYY-MM-DD.', 'Date: 13 is not a month (1 to 12).'])
  const good = payloadIssues(schema, schema, { cored_at: '2024-05-03', document: { date: '1974' } }, 'x', options)
  assert.deepEqual(good, [])
})

test('a bar needs a diameter above zero and two points of three numbers', () => {
  assert.deepEqual(barIssues({ diameter_mm: '8', points: [['0', '0', '0'], ['1', '0', '0']] }), [])
  assert.deepEqual(barIssues({ diameter_mm: '', points: [] }), ['Diameter is missing.', 'A bar needs at least two points.'])
  assert.deepEqual(barIssues({ diameter_mm: '0', points: [['0', '0', '0'], ['1', '0', '0']] }),
    ['Diameter must be a number above zero.'])
  assert.deepEqual(barIssues({ diameter_mm: '8', cover_mm: '-3', points: [['0', '0', '0'], ['1', '0', '0']] }),
    ['Cover must be a number, zero or more.'])
  assert.deepEqual(barIssues({ diameter_mm: '8', points: [['0', '0'], ['1', '0', '0']] }),
    ['Each point needs three numbers: x y z.'])
})

test('a layout names the bars that cannot be saved and asks for at least one', () => {
  const m = method('reinforcement_layout', LAYOUT, { position_required: false })
  const state = initialState(m, 'id')
  state.records[0].payload = { basis: 'scan', bars: [] }
  assert.deepEqual(formIssues(state, m).map((i) => i.message), ['Add at least one bar.'])
  state.records[0].payload = {
    basis: 'scan',
    bars: [
      { diameter_mm: '8', points: [['0', '0', '0'], ['1', '0', '0']] },
      { diameter_mm: '', points: [['0', '0', '0']] },
    ],
  }
  const issues = formIssues(state, m)
  assert.deepEqual(issues.map((i) => i.message), ['Bar 2: Diameter is missing.', 'Bar 2: A bar needs at least two points.'])
  assert.ok(issues.every((i) => i.record === 1 && i.target === 'claim-bars'))
})

test('findings: what was observed and the value are required', () => {
  const m = method('visual_inspection', { type: 'object', properties: {} })
  const state = initialState(m, 'id')
  assert.deepEqual(formIssues(state, m).map((i) => i.message), ['Finding 1: say what was observed.'])
  state.observations = [{ ...newObservation('spalling'), value: '' }]
  assert.deepEqual(formIssues(state, m).map((i) => i.message), ['Finding 1: the severity or width is missing.'])
  state.observations = [{ ...newObservation('spalling'), value: 'x' }]
  assert.deepEqual(formIssues(state, m).map((i) => i.message), ['Finding 1: the value is not a number.'])
  state.observations = [{ ...newObservation('spalling'), value: '2' }]
  assert.deepEqual(formIssues(state, m), [])
  state.observations = []
  assert.deepEqual(formIssues(state, m).map((i) => i.message), ['Add at least one finding.'])
})

test('a claim needs its property unless the document may stand alone, and a piece', () => {
  const claim = method('era_heuristic', { type: 'object', properties: {} }, { summary_optional: false })
  const state = initialState(claim, 'id')
  assert.deepEqual(formIssues(state, claim).map((i) => i.target), ['summary-quantity'])
  const doc = method('archival_document', { type: 'object', properties: {} }, { summary_optional: true })
  assert.deepEqual(formIssues(initialState(doc, 'id'), doc), [])
  state.pieces = []
  state.summary.quantity = 'x'
  assert.deepEqual(formIssues(state, claim).map((i) => i.message), ['Name at least one element.'])
})

test('the server problems go to the section of their path and to the field', () => {
  assert.equal(sectionOfPath('observed_at'), 'who')
  assert.equal(sectionOfPath('standard.code'), 'who')
  assert.equal(sectionOfPath('performed_by.0.name'), 'who')
  assert.equal(sectionOfPath('payload.readings'), 'what')
  assert.equal(sectionOfPath('position.description'), 'what')
  assert.equal(sectionOfPath('summary'), 'what')
  assert.equal(sectionOfPath('notes'), 'notes')
  assert.equal(sectionOfPath(''), 'what')
  const m = method('rebound_hammer', REBOUND)
  const rows = [
    { path: 'payload.readings', message: 'too few', record: 1 },
    { path: 'payload.instrument.hammer_type', message: 'required', record: 0 },
    { path: 'observed_at', message: 'future' },
    { path: 'position.description', message: 'where', record: 2 },
  ]
  const issues = serverIssues(rows, m)
  assert.deepEqual(issues.map((i) => i.section), ['what', 'what', 'who', 'what'])
  assert.deepEqual(issues.map((i) => i.target), [
    'record-r1-readings', 'record-shared-instrument-hammer_type', 'observed-at', 'record-r2-position',
  ])
  assert.ok(issues.every((i) => i.source === 'server'))
  const layout = method('reinforcement_layout', LAYOUT)
  assert.equal(targetOfPath('payload.bars.0.diameter_mm', layout, undefined), 'claim-bars')
  assert.equal(targetOfPath('payload.basis', layout, undefined), 'claim-basis')
  assert.equal(targetOfPath('position.description', layout, undefined), 'layout-position')
})

test('the state of each section: missing, error, done or optional', () => {
  const none = sectionStates([], { hasMethod: true, files: 0, notes: '' })
  assert.deepEqual(none, { method: 'done', who: 'done', what: 'done', files: 'optional', notes: 'optional' })
  const withFiles = sectionStates([], { hasMethod: true, files: 1, notes: 'x' })
  assert.equal(withFiles.files, 'done')
  assert.equal(withFiles.notes, 'done')
  assert.equal(sectionStates([], { hasMethod: true, files: 0, notes: '', carried: 2 }).files, 'done')
  const issues = [
    { section: 'what' as const, message: 'a', source: 'form' as const },
    { section: 'who' as const, message: 'b', source: 'server' as const },
    { section: 'who' as const, message: 'c', source: 'form' as const },
  ]
  const states = sectionStates(issues, { hasMethod: true, files: 0, notes: '' })
  assert.equal(states.what, 'missing')
  assert.equal(states.who, 'error')            // the server's word wins
  assert.equal(sectionStates([], { hasMethod: false, files: 0, notes: '' }).method, 'missing')
  assert.equal(sectionStates([], { hasMethod: false, files: 0, notes: '' }).what, 'missing')
  assert.deepEqual(issuesOf(issues, 'who').map((i) => i.message), ['b', 'c'])
})

test('a shared field that is missing is named once, however many records there are', () => {
  const m = method('rebound_hammer', REBOUND)
  const state = initialState(m, 'id')
  state.records = [state.records[0], { ...state.records[0], key: 'k2' }, { ...state.records[0], key: 'k3' }]
  const hammer = formIssues(state, m).filter((i) => i.message.includes('Hammer type'))
  assert.equal(hammer.length, 1)
  const areas = formIssues(state, m).filter((i) => i.message.includes('Surface preparation'))
  assert.deepEqual(areas.map((i) => i.record), [0, 1, 2])
})
