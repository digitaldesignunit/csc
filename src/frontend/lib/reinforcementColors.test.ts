import assert from 'node:assert/strict'
import test from 'node:test'

import {
  barColour,
  barLegend,
  defaultColourMode,
  diameterColour,
  diameterRange,
  layoutColour,
  layoutLabels,
  LAYOUT_COLOURS,
  rampColour,
} from '@/lib/reinforcementColors'

test('several layouts start coloured by layout, one layout stays steel', () => {
  assert.equal(defaultColourMode(0), 'steel')
  assert.equal(defaultColourMode(1), 'steel')
  assert.equal(defaultColourMode(2), 'layout')
})

test('layout colours differ and wrap around', () => {
  assert.notEqual(layoutColour(0), layoutColour(1))
  assert.equal(layoutColour(LAYOUT_COLOURS.length), layoutColour(0))
  assert.equal(layoutColour(-1), LAYOUT_COLOURS[LAYOUT_COLOURS.length - 1])
})

test('the diameter scale runs from the smallest to the largest bar', () => {
  const bars = [{ diameter_mm: 8 }, { diameter_mm: 12 }, { diameter_mm: 20 }]
  const range = diameterRange(bars)
  assert.deepEqual(range, { min: 8, max: 20 })
  assert.equal(diameterColour(8, range), rampColour(0))
  assert.equal(diameterColour(20, range), rampColour(1))
  assert.notEqual(diameterColour(12, range), diameterColour(20, range))
  // outside the range is clamped
  assert.equal(diameterColour(40, range), rampColour(1))
})

test('one diameter takes the middle of the ramp; no bars give an empty range', () => {
  const range = diameterRange([{ diameter_mm: 10 }, { diameter_mm: 10 }])
  assert.equal(diameterColour(10, range), rampColour(0.5))
  assert.deepEqual(diameterRange([]), { min: 0, max: 0 })
})

test('the ramp is hex colours', () => {
  for (const t of [0, 0.3, 0.5, 1, 7, -1, Number.NaN]) assert.match(rampColour(t), /^#[0-9a-f]{6}$/)
})

test('steel mode has no colour, the other modes do', () => {
  const bar = { diameter_mm: 12, layout: 1 }
  const range = { min: 8, max: 16 }
  assert.equal(barColour('steel', bar, range), null)
  assert.equal(barColour('layout', bar, range), layoutColour(1))
  assert.equal(barColour('diameter', bar, range), diameterColour(12, range))
})

test('layout labels use the title, then the day, and number equal names', () => {
  const labels = layoutLabels([
    { payload: { document: { title: 'Plan S-04' } } },
    { observed_at: '2026-06-15T00:00:00Z', observed_at_precision: 'day' },
    { payload: { document: { title: 'Plan S-04' } } },
    {},
  ])
  assert.equal(labels[0], 'Plan S-04 (1)')
  assert.equal(labels[2], 'Plan S-04 (2)')
  assert.ok(labels[1].startsWith('Layout of '))
  assert.equal(labels[3], 'Layout 4')
})

test('the legend lists the layouts or the diameter range', () => {
  const layouts = [{ id: 'a', label: 'A', count: 3 }, { id: 'b', label: 'B', count: 5 }]
  const bars = [{ diameter_mm: 8 }, { diameter_mm: 16 }]
  const byLayout = barLegend('layout', layouts, bars)
  assert.equal(byLayout?.kind, 'layout')
  assert.equal(byLayout?.kind === 'layout' && byLayout.items.length, 2)
  const byDiameter = barLegend('diameter', layouts, bars)
  assert.equal(byDiameter?.kind === 'diameter' && byDiameter.min, 8)
  assert.equal(byDiameter?.kind === 'diameter' && byDiameter.max, 16)
  assert.equal(barLegend('steel', layouts, bars), null)
})
