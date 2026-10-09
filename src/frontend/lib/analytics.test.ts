import assert from 'node:assert/strict'
import { test } from 'node:test'

import { EMPTY_STATS, circulationItems, functionItems, materialItems, statsQuery, summaryLine, topN } from './analytics'

test('the stats query carries the filters of the URL, every circulation and a wide Top-N', () => {
  const q = new URLSearchParams(statsQuery(new URLSearchParams('material=concrete&dataset=a&page=3&q=beam&circulation=exited&fragment=true')))
  assert.equal(q.get('material'), 'concrete')
  assert.equal(q.get('dataset'), 'a')
  assert.equal(q.get('fragment'), 'true')
  assert.equal(q.get('circulation'), 'all')
  assert.equal(q.get('limit_dim'), '1000')
  assert.equal(q.get('page'), null)
  assert.equal(q.get('q'), null)
})

test('one line says components, datasets and, for batches, pieces', () => {
  const base = { ...EMPTY_STATS, total: 655, byDataset: [{ label: 'a', count: 600 }, { label: 'b', count: 55 }] }
  assert.equal(summaryLine(base), '655 components in 2 datasets')
  assert.equal(summaryLine({ ...base, pieces: 655 }), '655 components in 2 datasets')
  assert.equal(summaryLine({ ...base, pieces: 1011 }), '655 components in 2 datasets, 1,011 pieces')
  assert.equal(summaryLine({ ...EMPTY_STATS, total: 1, pieces: 1, byDataset: [{ label: 'a', count: 1 }] }), '1 component in 1 dataset')
  assert.equal(summaryLine({ ...base, byDataset: [{ label: 'a', count: 5 }, { label: 'others', count: 7 }] }), '655 components in 1 dataset')
})

test('the circulation chart goes from in place to out of circulation, only what is there', () => {
  assert.deepEqual(
    circulationItems([{ label: 'exited', count: 4 }, { label: 'deinstalled', count: 10 }, { label: 'in_place', count: 2 }]),
    [
      { label: 'In place', count: 2 },
      { label: 'Not in place', count: 10 },
      { label: 'Out of circulation', count: 4 },
    ],
  )
  assert.deepEqual(circulationItems([{ label: 'deinstalled', count: 3 }]), [{ label: 'Not in place', count: 3 }])
  assert.deepEqual(circulationItems(undefined), [])
})

test('chart labels use the vocabulary and the materials list', () => {
  assert.deepEqual(functionItems([{ label: 'IfcBeam', count: 2 }]), [{ label: 'Beam', count: 2 }])
  assert.deepEqual(
    materialItems([{ label: 'concrete', count: 2 }, { label: 'others', count: 1 }], (id) => id.toUpperCase()),
    [{ label: 'CONCRETE', count: 2 }, { label: 'others', count: 1 }],
  )
})

test('the top values stay, the rest become others', () => {
  const rows = Array.from({ length: 5 }, (_, i) => ({ label: `m${i}`, count: 10 - i }))
  assert.deepEqual(topN(rows, 5), rows)
  assert.deepEqual(topN(rows, 3), [...rows.slice(0, 3), { label: 'others', count: 7 + 6 }])
  assert.deepEqual(topN([...rows.slice(0, 2), { label: 'others', count: 4 }], 5), [...rows.slice(0, 2), { label: 'others', count: 4 }])
  assert.deepEqual(topN(undefined), [])
})
