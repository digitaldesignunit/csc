/**
 * The facts of a row in the records and bars tables (decision 8.134 d, h).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { emptyDerived, emptyPosition, type RecordState } from '@/components/evidence/form/state'
import {
  barRow,
  barsWithProblems,
  parsePointsText,
  readingCounts,
  recordRow,
  removeBars,
  setOnBars,
  whereWords,
} from '@/lib/evidence/rows'
import type { FormObject } from '@/lib/evidence/schema'

function record(payload: FormObject, position = emptyPosition()): RecordState {
  return { key: 'k', payload, position, derived: emptyDerived() }
}

test('readings are counted: entered, rejected and valid', () => {
  assert.deepEqual(readingCounts({ readings: ['40', '41', '55', '56'], rejected_reading_indices: [] }),
    { entered: 4, rejected: 0, valid: 4 })
  assert.deepEqual(readingCounts({ readings: ['40', '41', '55'], rejected_reading_indices: ['2', '2', '9'] }),
    { entered: 3, rejected: 1, valid: 2 })
  assert.deepEqual(readingCounts({}), { entered: 0, rejected: 0, valid: 0 })
})

test('a rebound row has the label of its area, its readings and where it is', () => {
  const row = recordRow('rebound_hammer', record({
    test_area: { label: 'North face' }, readings: ['40', '41', '42'], rejected_reading_indices: ['1'],
  }, { ...emptyPosition(), description: 'mid-span' }), 0)
  assert.equal(row.title, 'North face')
  assert.equal(row.where, 'mid-span')
  assert.deepEqual(row.facts, ['2 valid readings, 1 rejected'])
})

test('a row without a label is named by its number and an empty one says so', () => {
  const row = recordRow('rebound_hammer', record({ test_area: { label: ' ' } }), 2)
  assert.equal(row.title, 'Test area 3')
  assert.deepEqual(row.facts, ['no readings'])
  assert.equal(row.where, '')
  assert.deepEqual(recordRow('rebound_hammer', record({ readings: ['40'] }), 0).facts, ['1 valid reading'])
})

test('a core row has its date, diameter and load', () => {
  const row = recordRow('core_compression', record({
    specimen: { label: 'C1', measured_diameter_mm: '100' }, sampling: { cored_at: '2024-05-03' }, test: { max_load_kn: '' },
  }), 0)
  assert.equal(row.title, 'C1')
  assert.deepEqual(row.facts, ['cored 2024-05-03', 'diameter 100 mm'])
  assert.deepEqual(recordRow('core_compression', record({}), 0).facts, ['not filled in yet'])
})

test('a derived result and a grid or a picked point show on the row', () => {
  const withDerived: RecordState = { ...record({ readings: ['1'] }), derived: { ...emptyDerived(), model: 'din_annex' } }
  assert.ok(recordRow('rebound_hammer', withDerived, 0).facts.includes('derived result'))
  const grid = { test_area: { grid: { rows: '3', cols: '4' } } }
  assert.equal(whereWords(emptyPosition(), grid), '3 x 4 grid')
  assert.equal(whereWords({ ...emptyPosition(), kind: 'point', point: [1, 2, 3] }, {}), 'point picked on the model')
  assert.equal(whereWords({ ...emptyPosition(), description: 'edge' }, grid), 'edge')
})

test('a bar row shows diameter, grade, cover, points and problems', () => {
  const ok = barRow({ diameter_mm: '8', spec: 'BSt III', cover_mm: '25', points: [['0', '0', '0'], ['1', '0', '0']] }, 0)
  assert.deepEqual(ok, { title: 'Bar 1', diameter: '8 mm', grade: 'BSt III', cover: '25 mm', points: 2, problems: [] })
  const bad = barRow({ diameter_mm: '', points: [['0', '0', '0']] }, 4)
  assert.equal(bad.title, 'Bar 5')
  assert.equal(bad.diameter, '')
  assert.deepEqual(bad.problems, ['Diameter is missing.', 'A bar needs at least two points.'])
})

test('a field is set on the selected bars only and bars are removed by selection', () => {
  const bars: FormObject[] = [{ diameter_mm: '8', spec: 'a' }, { diameter_mm: '10', spec: 'b' }, { diameter_mm: '12', spec: 'c' }]
  const set = setOnBars(bars, new Set([0, 2]), 'diameter_mm', '16')
  assert.deepEqual(set.map((b) => b.diameter_mm), ['16', '10', '16'])
  assert.deepEqual(set.map((b) => b.spec), ['a', 'b', 'c'])
  assert.deepEqual(bars.map((b) => b.diameter_mm), ['8', '10', '12'])        // not changed
  assert.deepEqual(setOnBars(bars, new Set([1]), 'spec', 'BSt IV').map((b) => b.spec), ['a', 'BSt IV', 'c'])
  assert.deepEqual(removeBars(bars, new Set([1])).map((b) => b.spec), ['a', 'c'])
  assert.deepEqual(removeBars(bars, new Set()), bars)
})

test('the bars with a problem are found by index', () => {
  const good = { diameter_mm: '8', points: [['0', '0', '0'], ['1', '0', '0']] }
  assert.deepEqual(barsWithProblems([good, { diameter_mm: '', points: [] }, good, { diameter_mm: 'x', points: [] }]), [1, 3])
  assert.deepEqual(barsWithProblems([]), [])
})

test('points are read one per line, split on space, comma or semicolon', () => {
  assert.deepEqual(parsePointsText('0 0 0\n1, 2; 3\n\n  4 5 6  '), [['0', '0', '0'], ['1', '2', '3'], ['4', '5', '6']])
  assert.deepEqual(parsePointsText(''), [])
})
