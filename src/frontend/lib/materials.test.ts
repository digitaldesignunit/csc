import assert from 'node:assert/strict'
import { test } from 'node:test'

import { filterMaterials, hiddenCount, isLive, stateNote } from './materials'

const M = [
  { _id: 'concrete', label: 'Concrete', group: 'mineral', default_class: '17 01 01', uniclass: 'Ma_40_19' },
  { _id: 'old_steel', label: 'Old steel', group: 'metal', default_class: '17 04 05', retired: true },
  { _id: 'brick', label: 'Fired clay', group: 'mineral', default_class: '17 01 02', merged_into: 'concrete' },
  { _id: 'timber', label: 'Solid timber', group: 'organic', default_class: '17 02 01', notes: 'sawn lumber' },
]

test('retired and merged materials are hidden unless asked for', () => {
  assert.deepEqual(filterMaterials(M, '', false).map((m) => m._id), ['concrete', 'timber'])
  assert.deepEqual(filterMaterials(M, '', true).map((m) => m._id), ['concrete', 'old_steel', 'brick', 'timber'])
  assert.equal(hiddenCount(M), 2)
  assert.equal(isLive(M[1]), false)
})

test('the search looks at label, id, waste class, Uniclass and notes', () => {
  assert.deepEqual(filterMaterials(M, 'CONC', false).map((m) => m._id), ['concrete'])
  assert.deepEqual(filterMaterials(M, '17 02', false).map((m) => m._id), ['timber'])
  assert.deepEqual(filterMaterials(M, 'ma_40', false).map((m) => m._id), ['concrete'])
  assert.deepEqual(filterMaterials(M, 'lumber', false).map((m) => m._id), ['timber'])
  assert.deepEqual(filterMaterials(M, 'steel', false), [])
  assert.deepEqual(filterMaterials(M, 'steel', true).map((m) => m._id), ['old_steel'])
})

test('the state note says retired or merged', () => {
  assert.equal(stateNote(M[0]), '')
  assert.equal(stateNote(M[1]), 'retired')
  assert.equal(stateNote(M[2]), 'merged into concrete')
})
