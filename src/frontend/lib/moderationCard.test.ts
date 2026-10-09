import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  isOwnRecord,
  snapshotChanges,
  snapshotFacts,
  snapshotKind,
  submittedLine,
  truncateNote,
  waitingLabel,
} from './moderationCard'

const NOW = Date.parse('2026-10-10T12:00:00Z')

test('the waiting time counts whole days', () => {
  assert.equal(waitingLabel('2026-10-10T01:00:00Z', NOW), 'waiting since today')
  assert.equal(waitingLabel('2026-10-09T01:00:00Z', NOW), 'waiting 1 day')
  assert.equal(waitingLabel('2026-10-07T01:00:00Z', NOW), 'waiting 3 days')
  assert.equal(waitingLabel(null, NOW), '')
  assert.equal(waitingLabel('nonsense', NOW), '')
})

test('the meta line says who, when and how long', () => {
  assert.equal(submittedLine('Submitted', 'dev-contrib', '2026-10-07T08:00:00Z', NOW),
    'Submitted by dev-contrib on 07.10.2026, waiting 3 days')
  assert.equal(submittedLine('Recorded', null, null, NOW), 'Recorded')
})

test('a waiting version is a new piece, a new state, a correction, a cut or a draw', () => {
  assert.equal(snapshotKind({ version: 0, parents: 0, drawn: false }), 'New piece')
  assert.equal(snapshotKind({ version: 2, parents: 0, drawn: false }), 'New state')
  assert.equal(snapshotKind({ version: 2, supersedes: 'x', parents: 0, drawn: false }), 'Correction')
  assert.equal(snapshotKind({ version: 0, parents: 1, drawn: false }), 'Cut')
  assert.equal(snapshotKind({ version: 0, parents: 1, drawn: true }), 'Draw')
})

test('a correction lists what it changes, an unchanged field is not listed', () => {
  const before = { name: 'A', bbx: [1000, 200, 100], quantity: 1, color: [1, 2, 3], shape_class: 'linear' }
  assert.deepEqual(snapshotChanges(before, { ...before }), [])
  assert.deepEqual(
    snapshotChanges(before, { ...before, name: 'B', bbx: [900, 200, 100], quantity: 3 }),
    ['name "A" to "B"', 'size 1000 x 200 x 100 to 900 x 200 x 100 mm', 'quantity 1 to 3'])
  assert.deepEqual(snapshotChanges(null, before), [])
})

test('the facts of a snapshot skip what is empty and say Authored without a capture', () => {
  const facts = snapshotFacts(
    { original_function: 'beam', material: 'concrete' },
    { bbx: [4256.5, 662.9, 545.1], shape_class: 'linear', capture: null },
    [])
  assert.deepEqual(facts.map((f) => f.label), ['Function', 'Material', 'Size', 'Shape class', 'Capture'])
  assert.equal(facts.find((f) => f.label === 'Size')?.value, '4257 x 663 x 545 mm')
  assert.equal(facts.find((f) => f.label === 'Capture')?.value, 'Authored')
  assert.equal(snapshotFacts({}, null, ['colour']).at(-1)?.label, 'Changes')
})

test('a long note is cut at a word and says there is more', () => {
  assert.deepEqual(truncateNote('short note'), { text: 'short note', more: false })
  const long = truncateNote('word '.repeat(60), 40)
  assert.equal(long.more, true)
  assert.ok(long.text.endsWith('...') && long.text.length <= 44)
})

test('a record is own when the viewer and the author names match', () => {
  assert.equal(isOwnRecord('mod', 'mod'), true)
  assert.equal(isOwnRecord('mod', 'other'), false)
  assert.equal(isOwnRecord(null, 'mod'), false)
  assert.equal(isOwnRecord('mod', undefined), false)
})
