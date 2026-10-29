/**
 * The "Data Model" reference page (decision 8.181): its anchors, its coverage of
 * the vocabularies, and the drift test --- a field the page names that the
 * generated models do not have fails here, so a renamed or dropped field of the
 * backend cannot leave the page behind.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { test } from 'node:test'

import { EXAMPLE_RECORDS, EXAMPLE_EVIDENCE, type ExampleRecord } from './dataModelExamples'
import { exampleExport } from './dataModelExport'
import { exampleRows, valueText } from './dataModelRows'
import {
  ENTITY_SECTIONS,
  METHOD_TIER,
  OVERVIEW,
  QUANTITY_FACTS,
  RULES,
  VOCAB_NAMES,
  VOCAB_SECTIONS,
  humanize,
  isMarked,
  paraText,
  valueLabel,
  type Marked,
  type Para,
  type Run,
} from './dataModelText'
import { anchorPlaces } from './dataModelTabs'
import { VOCABS, vocabEntries } from './dataModelVocab'
import { EVIDENCE_METHOD_LABELS, QUANTITY_LABELS } from '@/generated/Vocab'

// THE GENERATED MODELS ------------------------------------------------------------
const GENERATED = path.join(process.cwd(), 'generated')
const SOURCES = fs.readdirSync(GENERATED).filter((f) => f.endsWith('.ts')).map((f) => fs.readFileSync(path.join(GENERATED, f), 'utf-8'))

/** The field names of `export interface Name { ... }` in the generated models, or null. */
function fieldsOf(name: string): Set<string> | null {
  for (const source of SOURCES) {
    const start = source.search(new RegExp(`^export interface ${name} \\{`, 'm'))
    if (start < 0) continue
    const body = source.slice(start).split('\n')
    const fields = new Set<string>()
    for (const line of body.slice(1)) {
      if (line.startsWith('}')) break
      const match = /^ {2}(\w+)\??:/.exec(line)
      if (match) fields.add(match[1])
    }
    return fields
  }
  return null
}

const interfaceFields = (name: string): Set<string> => {
  const fields = fieldsOf(name)
  assert.ok(fields, `the generated models have no interface ${name}`)
  return fields
}

// ANCHORS -------------------------------------------------------------------------
test('the anchors other pages link to exist (the tab map throws on an anchor set twice)', () => {
  const ids = [...anchorPlaces().keys()]
  for (const id of ['dataset', 'identity', 'snapshot', 'evidence', 'evidence-methods', 'vocabularies', 'rules', 'example']) {
    assert.ok(ids.includes(id), id)
  }
  for (const id of ids) assert.match(id, /^[a-z0-9]+(-[a-z0-9]+)*$/, id)
})

// THE VOCABULARIES -----------------------------------------------------------------
test('every vocabulary the page names has a section, once', () => {
  assert.deepEqual([...VOCAB_SECTIONS.map((s) => s.vocab)].sort(), [...VOCAB_NAMES].sort())
})

test('every value of every vocabulary on the page has a label and a one-line meaning', () => {
  for (const name of VOCAB_NAMES) {
    const { labels, descriptions } = VOCABS[name]
    assert.deepEqual(Object.keys(descriptions).sort(), Object.keys(labels).sort(), name)
    for (const entry of vocabEntries(name)) {
      assert.ok(entry.label, `${name}.${entry.value}`)
      assert.ok(entry.description.length > 0 && entry.description.length <= 120, `${name}.${entry.value}: ${entry.description.length}`)
    }
  }
})

test('a value without a label of its own gets a readable one', () => {
  assert.equal(humanize('self_attested'), 'Self attested')
  assert.equal(valueLabel({ draft: 'draft' }, 'draft'), 'Draft')
  assert.equal(valueLabel({ IfcBeam: 'Beam' }, 'IfcBeam'), 'Beam')
  assert.equal(valueLabel({}, 'bio-based'), 'Bio based')
})

test('the unit, kind and scope of every quantity, and the tier of every method, are listed', () => {
  assert.deepEqual(Object.keys(QUANTITY_FACTS).sort(), Object.keys(QUANTITY_LABELS).sort())
  assert.deepEqual(Object.keys(METHOD_TIER).sort(), Object.keys(EVIDENCE_METHOD_LABELS).sort())
})

// THE DRIFT TEST: FIELDS NAMED ON THE PAGE ------------------------------------------
test('every field a table of the page names is in the generated models', () => {
  for (const section of ENTITY_SECTIONS) {
    for (const table of section.tables ?? []) {
      const fields = interfaceFields(table.model)
      for (const row of table.rows) {
        assert.ok(fields.has(row.name), `${table.id}: "${row.name}" is not a field of ${table.model}`)
      }
      const names = table.rows.map((r) => r.name)
      assert.equal(new Set(names).size, names.length, `${table.id}: a field is listed twice`)
    }
  }
})

test('every field of an example record is in the generated models, and has its comment', () => {
  for (const record of EXAMPLE_RECORDS) {
    const fields = interfaceFields(record.model)
    for (const key of Object.keys(record.json)) {
      assert.ok(fields.has(key), `${record.id}: "${key}" is not a field of ${record.model}`)
      assert.ok(record.comments[key], `${record.id}: no comment for "${key}"`)
    }
    if (record.payloadModel) {
      const payload = record.json.payload as Record<string, unknown>
      const payloadFields = interfaceFields(record.payloadModel)
      for (const key of Object.keys(payload)) {
        assert.ok(payloadFields.has(key), `${record.id}: "${key}" is not a field of ${record.payloadModel}`)
        assert.ok(record.comments[`payload.${key}`], `${record.id}: no comment for "payload.${key}"`)
      }
    }
    for (const key of Object.keys(record.comments)) {
      const known = key.startsWith('payload.') ? key.slice(8) in ((record.json.payload ?? {}) as object) : key in record.json
      assert.ok(known, `${record.id}: a comment for "${key}", which the record does not have`)
    }
  }
})

/** The generated interface of a nested block, per method: the fields inside the payload. */
const PAYLOAD_BLOCKS: Record<string, Record<string, string>> = {
  rebound_hammer: { instrument: 'ReboundInstrument', test_area: 'ReboundTestArea' },
  core_compression: { sampling: 'CoreSampling', specimen: 'CoreSpecimen', test: 'CoreTest', result: 'CoreResult' },
  archival_document: { document: 'ArchivalDocument', claim: 'ArchivalClaim' },
  visual_inspection: { observations: 'VisualObservation' },
  reinforcement_layout: { document: 'LayoutDocument', bars: 'LayoutBar' },
}

test('the fields inside the payload blocks of the examples are in the generated models', () => {
  for (const record of EXAMPLE_EVIDENCE) {
    const blocks = PAYLOAD_BLOCKS[record.json.method as string] ?? {}
    const payload = record.json.payload as Record<string, unknown>
    for (const [name, model] of Object.entries(blocks)) {
      const value = payload[name]
      const items = (Array.isArray(value) ? value : value === undefined ? [] : [value]) as Record<string, unknown>[]
      const fields = interfaceFields(model)
      for (const item of items) {
        for (const key of Object.keys(item)) assert.ok(fields.has(key), `${record.id}: payload.${name}.${key} is not a field of ${model}`)
      }
    }
    // standard, derived results with their model
    if (record.json.standard) for (const key of Object.keys(record.json.standard as object)) assert.ok(interfaceFields('Standard').has(key), `${record.id} standard.${key}`)
    for (const result of (record.json.derived ?? []) as Record<string, unknown>[]) {
      for (const key of Object.keys(result)) assert.ok(interfaceFields('DerivedResult').has(key), `${record.id} derived.${key}`)
      for (const key of Object.keys(result.model as object)) assert.ok(interfaceFields('DerivationModel').has(key), `${record.id} derived.model.${key}`)
    }
  }
  const identity = EXAMPLE_RECORDS.find((r) => r.id === 'example-identity')?.json as Record<string, unknown>
  for (const value of Object.values(identity.properties as Record<string, object>)) {
    for (const key of Object.keys(value)) assert.ok(interfaceFields('PropertyValue').has(key), `properties.${key}`)
  }
  const snapshot = EXAMPLE_RECORDS.find((r) => r.id === 'example-snapshot-v0')?.json as Record<string, unknown>
  for (const key of Object.keys(snapshot.location as object)) assert.ok(interfaceFields('GeoLocation').has(key), `location.${key}`)
  for (const proxy of (snapshot.geometry as { proxies: object[] }).proxies) {
    for (const key of Object.keys(proxy)) assert.ok(interfaceFields('Proxy').has(key), `proxy.${key}`)
  }
})

test('the file the backend test reads is the current examples', () => {
  const file = path.join(process.cwd(), '..', '..', 'tests', 'fixtures', 'data_model_examples.json')
  const committed = fs.readFileSync(file, 'utf-8').split('\r\n').join('\n')
  assert.equal(committed, exampleExport(EXAMPLE_RECORDS),
    'tests/fixtures/data_model_examples.json is out of date: run `npx tsx scripts/export-data-model-examples.ts` in src/frontend')
})

test('the nested blocks of the examples use fields the models have', () => {
  const identity = EXAMPLE_RECORDS.find((r) => r.id === 'example-identity') as ExampleRecord
  const origin = identity.json.origin as Record<string, unknown>
  for (const key of Object.keys(origin)) assert.ok(interfaceFields('Origin').has(key), `origin.${key}`)
  for (const key of Object.keys(origin.construction_work as object)) assert.ok(interfaceFields('ConstructionWork').has(key), `construction_work.${key}`)
  for (const key of Object.keys(origin.place as object)) assert.ok(interfaceFields('Place').has(key), `place.${key}`)
  for (const record of EXAMPLE_EVIDENCE) {
    for (const key of Object.keys(record.json.summary as object)) assert.ok(interfaceFields('Summary').has(key), `${record.id} summary.${key}`)
    for (const key of Object.keys(record.json.position as object)) assert.ok(interfaceFields('Position').has(key), `${record.id} position.${key}`)
    for (const key of Object.keys(record.json.verification as object)) assert.ok(interfaceFields('Verification').has(key), `${record.id} verification.${key}`)
    for (const actor of record.json.performed_by as object[]) {
      for (const key of Object.keys(actor)) assert.ok(interfaceFields('Actor').has(key), `${record.id} actor.${key}`)
    }
  }
})

// THE EXAMPLE PIECE -------------------------------------------------------------------
test('there is one example record for every evidence method, with the tier the method has', () => {
  assert.deepEqual(EXAMPLE_EVIDENCE.map((r) => r.json.method), Object.keys(EVIDENCE_METHOD_LABELS))
  for (const record of EXAMPLE_EVIDENCE) {
    const method = record.json.method as keyof typeof METHOD_TIER
    if (method !== 'reinforcement_layout') assert.equal(record.json.source_tier, METHOD_TIER[method], record.id)
    assert.equal(record.json.identity_id, 'example-identity')
  }
})

test('the example values are values of the vocabularies, and the ids are marked as examples', () => {
  const identity = EXAMPLE_RECORDS.find((r) => r.id === 'example-identity')?.json as Record<string, unknown>
  assert.ok(identity.original_function as string in VOCABS.original_function.labels)
  assert.ok((identity.origin as { kind: string }).kind in VOCABS.origin_kind.labels)
  for (const record of EXAMPLE_RECORDS) {
    assert.match(String(record.json._id), /^example[-_]/, record.id)
    if (record.model === 'ComponentSnapshot') assert.ok(String(record.json.status) in VOCABS.status.labels)
  }
  for (const record of EXAMPLE_EVIDENCE) {
    const summary = record.json.summary as { quantity: string }
    assert.ok(summary.quantity in QUANTITY_LABELS, record.id)
    assert.ok(String(record.json.status) in VOCABS.status.labels, record.id)
    assert.ok((record.json.verification as { state: string }).state in VOCABS.verification_state.labels, record.id)
    assert.ok(String(record.json.source_tier) in VOCABS.source_tier.labels, record.id)
  }
})

test('the example piece names no person and no real organisation', () => {
  const text = JSON.stringify(EXAMPLE_RECORDS.map((r) => r.json))
  // an organisation is named by its role ("A testing laboratory", "The precast plant"), never by a name
  for (const organisation of text.matchAll(/"(?:organization|manufacturer)":"([^"]+)"/g)) {
    assert.match(organisation[1], /^(A|The) [a-z]/, organisation[1])
  }
  assert.ok(!/Corian|Ltd|GmbH/.test(text), 'no brand and no company name')
  assert.ok(!/@/.test(text) && !/orcid/i.test(text.replace(/"orcid"/g, '')), 'no e-mail address, no ORCID')
})

test('the rows of a record are its fields in order, the payload fields after the payload', () => {
  const rebound = EXAMPLE_EVIDENCE[0]
  const rows = exampleRows(rebound)
  const fields = rows.map((r) => r.field)
  assert.equal(fields[0], '_id')
  assert.ok(fields.indexOf('payload.median') > fields.indexOf('payload'))
  assert.ok(rows.filter((r) => r.nested).every((r) => r.field.startsWith('payload.')))
  assert.ok(rows.every((r) => r.comment.length > 0))
  assert.equal(valueText('a'.repeat(200)).length, 90)
  assert.equal(valueText({ a: 1 }), '{"a":1}')
  assert.equal(valueText(null), 'null')
})

// THE WORDING --------------------------------------------------------------------------
function allRuns(): Run[] {
  const runs: Run[] = []
  const push = (para: Para | undefined) => para?.forEach((run) => runs.push(run))
  for (const para of OVERVIEW.lead) push(para)
  for (const rule of RULES) push(rule.body)
  for (const section of ENTITY_SECTIONS) {
    for (const para of section.lead) push(para)
    for (const para of section.after ?? []) push(para)
    for (const table of section.tables ?? []) {
      push(table.intro)
      for (const row of table.rows) push(row.meaning)
    }
  }
  for (const section of VOCAB_SECTIONS) push(section.intro)
  for (const record of EXAMPLE_RECORDS) {
    push(record.intro)
    for (const comment of Object.values(record.comments)) push(typeof comment === 'string' ? [comment] : comment)
  }
  return runs
}

/** The marked sentences with the specification section they read (for the report). */
export function markedRuns(): Marked[] {
  return allRuns().filter(isMarked)
}

test('a marked sentence says which section of the specification it reads and what was loose', () => {
  const marked = markedRuns()
  assert.ok(marked.length > 0)
  for (const run of marked) {
    assert.match(run.spec, /^(\d+(\.\d+)*|A\.\d+)(, (\d+(\.\d+)*|A\.\d+|rule \d))*$/, run.text)
    assert.ok(run.note.length > 10, run.text)
    assert.ok(run.text.trim().length > 0)
  }
})

test('the text is plain ASCII, with no emoji and no raw em dash', () => {
  for (const file of ['dataModelText.ts', 'dataModelExamples.ts', 'dataModelRows.ts', 'dataModelTabs.ts', 'dataModelVocab.ts', 'dataModelExport.ts']) {
    const source = fs.readFileSync(path.join(process.cwd(), 'lib', file), 'utf-8')
    assert.ok(/^[\x00-\x7F]*$/.test(source), `${file} has a character outside ASCII`)
  }
  for (const run of allRuns()) {
    const text = typeof run === 'string' ? run : run.text
    assert.ok(!/\s{2,}/.test(text.trim()), `two spaces in: ${text}`)
  }
  assert.ok(paraText(OVERVIEW.lead[0]).startsWith('The catalog keeps four kinds of record.'))
})
