/**
 * The column widths of the Browse table: a minimum per column, the table never
 * narrower than the sum of those of the columns it shows, the room above them
 * shared by weight.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { BASE_COLUMNS, OPTIONAL_COLUMNS } from './browse'
import {
  BROWSE_COLUMN_SIZES,
  columnWidths,
  firstPaintWidths,
  minTableWidth,
  sizeOf,
} from './tableWidths'

const BASE = [...BASE_COLUMNS, 'actions']
const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)

test('every column of Browse has a size', () => {
  for (const id of [...BASE_COLUMNS, 'fit', 'distance', 'actions', ...OPTIONAL_COLUMNS.map((c) => c.key)]) {
    assert.ok(BROWSE_COLUMN_SIZES[id], id)
    assert.ok(BROWSE_COLUMN_SIZES[id].minPx >= 40, id)
  }
  // an unknown column keeps a safe minimum and no share
  assert.deepEqual(sizeOf('mystery'), { minPx: 120, weight: 0 })
})

test('the minimum of the table is the sum of the minimums of its columns', () => {
  assert.equal(minTableWidth(BASE), 864)
  // Match and Distance add their own, an optional column its own width
  assert.equal(minTableWidth([...BASE, 'fit']), 864 + BROWSE_COLUMN_SIZES.fit.minPx)
  assert.equal(minTableWidth([...BASE, 'fit', 'distance']), 864 + 110 + 144)
  assert.equal(minTableWidth([...BASE, '_id']), 864 + 300)
  assert.equal(minTableWidth([]), 0)
})

test('below the minimum the columns keep it and the table is wider than its frame', () => {
  for (const frame of [300, 460, 720, 863]) {
    const found = columnWidths(frame, BASE)!
    assert.deepEqual(found.widths, BASE.map((id) => sizeOf(id).minPx))
    assert.equal(found.total, 864)
    assert.equal(found.scrolls, true)
  }
})

test('above the minimum the table fills its frame and no column is below its minimum', () => {
  for (const ids of [BASE, [...BASE, 'fit'], [...BASE, 'distance'], [...BASE, 'fit', 'distance'], [...BASE, 'location', 'created']]) {
    for (const frame of [864, 865, 900, 1000, 1023, 1337, 2000]) {
      const found = columnWidths(frame, ids)!
      const min = minTableWidth(ids)
      assert.ok(found.widths.every((w, i) => w >= sizeOf(ids[i]).minPx), `${ids.length} columns at ${frame}`)
      assert.equal(found.total, sum(found.widths))
      if (frame >= min) {
        assert.equal(found.total, Math.max(frame, min), `${ids.length} columns at ${frame}`)
        assert.equal(found.scrolls, false)
      } else {
        assert.equal(found.total, min)
        assert.equal(found.scrolls, true)
      }
    }
  }
})

test('the room above the minimums is shared by weight; fixed columns stay', () => {
  const ids = ['name', 'status', 'actions', '_id']
  const found = columnWidths(1000, ids)!
  // minimums 150 + 100 + 44 + 300 = 594, so 406 to share between name (23) and status (10)
  assert.equal(found.widths[2], 44)
  assert.equal(found.widths[3], 300)
  assert.equal(found.total, 1000)
  const nameExtra = found.widths[0] - 150
  const statusExtra = found.widths[1] - 100
  assert.ok(Math.abs(nameExtra / statusExtra - 23 / 10) < 0.1)
  // only columns without weight: nothing to share, the table keeps its own width
  const fixed = columnWidths(1000, ['actions', '_id'])!
  assert.deepEqual(fixed.widths, [44, 300])
  assert.equal(fixed.scrolls, false)
})

test('an unmeasured or empty frame gives no widths', () => {
  assert.equal(columnWidths(null, BASE), null)
  assert.equal(columnWidths(0, BASE), null)
  assert.equal(columnWidths(Number.NaN, BASE), null)
})

test('the first paint uses the weights as percentages and the minimum for fixed columns', () => {
  const first = firstPaintWidths(['name', 'status', 'actions'])
  assert.equal(first[2], '44px')
  assert.ok(first[0].endsWith('%') && first[1].endsWith('%'))
  assert.ok(Math.abs(parseFloat(first[0]) + parseFloat(first[1]) - 100) < 0.05)
})
