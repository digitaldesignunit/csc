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
  layoutsOnSnapshot,
  layoutsWithPicked,
  layoutStatusText,
  layoutViewerHref,
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


// TWO LAYOUTS ON ONE PIECE (RL1, 0.6.3.1) -----------------------------------------
const bar = (diameter: number, x: number) => ({
  spec: `B${diameter}`, diameter_mm: diameter, points: [[x, 0, 0], [x, 0, 100]],
})

test('two layouts on one snapshot are two layouts with their own bars', () => {
  const records = [
    { _id: 'a', observed_at: '2026-01-05', position: { snapshot_id: 's1' },
      payload: { bars: [bar(12, 0), bar(12, 50)], document: { title: 'Drawing A' } } },
    { _id: 'b', observed_at: '2026-02-09', position: { snapshot_id: 's1' },
      payload: { bars: [bar(8, 10), bar(8, 20), bar(8, 30)], document: { title: 'Drawing B' } } },
  ]
  const { bars, layouts } = layoutsOnSnapshot(records, 's1')
  assert.equal(bars.length, 5)
  assert.deepEqual(layouts, [
    { id: 'a', label: 'Drawing A', count: 2 },
    { id: 'b', label: 'Drawing B', count: 3 },
  ])
  assert.deepEqual(bars.map((b) => b.layout), [0, 0, 1, 1, 1])
  assert.equal(defaultColourMode(layouts.length), 'layout')
  // each layout has its own colour in the legend
  assert.notEqual(layoutColour(0), layoutColour(1))
  const legend = barLegend('layout', layouts, bars)
  assert.equal(legend?.kind, 'layout')
})

test('a layout of another snapshot, or without a drawable bar, is not a layout here', () => {
  const records = [
    { _id: 'a', position: { snapshot_id: 's1' }, payload: { bars: [bar(12, 0)] } },
    { _id: 'other', position: { snapshot_id: 's2' }, payload: { bars: [bar(12, 0)] } },
    { _id: 'empty', position: { snapshot_id: 's1' }, payload: { bars: [] } },
    { _id: 'flat', position: { snapshot_id: 's1' },
      payload: { bars: [{ spec: 'x', diameter_mm: 0, points: [[0, 0, 0], [1, 0, 0]] }] } },
    { _id: 'none', position: null, payload: { bars: [bar(12, 0)] } },
  ]
  const { bars, layouts } = layoutsOnSnapshot(records, 's1')
  assert.deepEqual(layouts, [{ id: 'a', label: 'Layout 1', count: 1 }])
  assert.equal(bars.length, 1)
})

test('two layouts with the same title are told apart in the legend', () => {
  const records = ['a', 'b'].map((id) => ({
    _id: id, position: { snapshot_id: 's1' },
    payload: { bars: [bar(10, 0)], document: { title: 'Ground floor' } } }))
  const { layouts } = layoutsOnSnapshot(records, 's1')
  assert.deepEqual(layouts.map((l) => l.label), ['Ground floor (1)', 'Ground floor (2)'])
})

test('a piece without a layout has no bars and starts steel', () => {
  const { bars, layouts } = layoutsOnSnapshot([], 's1')
  assert.deepEqual([bars, layouts], [[], []])
  assert.equal(defaultColourMode(layouts.length), 'steel')
})


// A RECORD NAMED BY THE LINK, WHATEVER ITS STATUS (8.178) -------------------------
const published = [
  { _id: 'p1', status: 'published', position: { snapshot_id: 's1' },
    payload: { bars: [bar(12, 0), bar(12, 50)], document: { title: 'Drawing A' } } },
]
const draft = {
  _id: 'd1', status: 'draft', position: { snapshot_id: 's1' },
  payload: { bars: [bar(8, 10), bar(8, 20), bar(8, 30)], document: { title: 'T4 test layout' } },
}

test('the named record is drawn in addition to the published layouts, with its status', () => {
  const { bars, layouts, picked, problem } = layoutsWithPicked(published, draft, 's1')
  assert.equal(problem, null)
  assert.equal(picked, 1)
  assert.equal(bars.length, 5)
  assert.deepEqual(bars.map((b) => b.layout), [0, 0, 1, 1, 1])
  assert.deepEqual(layouts, [
    { id: 'p1', label: 'Drawing A', count: 2 },
    { id: 'd1', label: 'T4 test layout', count: 3, status: 'draft', picked: true },
  ])
})

test('the named record that is one of the published layouts is not drawn twice', () => {
  const { bars, layouts, picked } = layoutsWithPicked(published, published[0], 's1')
  assert.equal(bars.length, 2)
  assert.equal(layouts.length, 1)
  assert.equal(picked, 0)
  assert.equal(layouts[0].status, null)
  assert.equal(layouts[0].picked, true)
})

test('the named record of another version is rejected and nothing extra is drawn', () => {
  const other = { ...draft, position: { snapshot_id: 's2' } }
  const result = layoutsWithPicked(published, other, 's1')
  assert.equal(result.problem, 'other_version')
  assert.equal(result.picked, null)
  assert.equal(result.bars.length, 2)
  assert.deepEqual(result.layouts, [{ id: 'p1', label: 'Drawing A', count: 2 }])
  assert.equal(layoutsWithPicked(published, { ...draft, position: null }, 's1').problem, 'other_version')
})

test('the named record without a drawable bar is a problem, not a layout', () => {
  const result = layoutsWithPicked(published, { ...draft, payload: { bars: [] } }, 's1')
  assert.equal(result.problem, 'no_bars')
  assert.equal(result.bars.length, 2)
})

test('without a named record the published layouts are what layoutsOnSnapshot returns', () => {
  const result = layoutsWithPicked(published, null, 's1')
  assert.deepEqual({ bars: result.bars, layouts: result.layouts }, layoutsOnSnapshot(published, 's1'))
  assert.equal(result.picked, null)
  assert.equal(result.problem, null)
})

test('a named layout alone on a piece without published layouts is drawn', () => {
  const result = layoutsWithPicked([], draft, 's1')
  assert.equal(result.picked, 0)
  assert.equal(result.bars.length, 3)
})

test('the status text names draft, pending, rejected, withdrawn and superseded, not published', () => {
  assert.equal(layoutStatusText({ status: 'draft' }), 'draft')
  assert.equal(layoutStatusText({ status: 'pending' }), 'pending')
  assert.equal(layoutStatusText({ status: 'rejected' }), 'rejected')
  assert.equal(layoutStatusText({ status: 'withdrawn' }), 'withdrawn')
  assert.equal(layoutStatusText({ status: 'published', superseded_by: 'x' }), 'superseded')
  assert.equal(layoutStatusText({ status: 'published', superseded_by: null }), null)
  assert.equal(layoutStatusText({}), null)
})

test('"Show in viewer" links the version and the record, only for a drawable positioned layout', () => {
  const record = { ...draft, identity_id: 'i 1' }
  assert.equal(layoutViewerHref(record), '/components/i%201?snapshot=s1&layout=d1#component-viewer')
  assert.equal(layoutViewerHref({ ...record, position: null }), null)
  assert.equal(layoutViewerHref({ ...record, position: { snapshot_id: null } }), null)
  assert.equal(layoutViewerHref({ ...record, payload: { bars: [] } }), null)
  assert.equal(layoutViewerHref({ ...record, payload: {} }), null)
  assert.equal(layoutViewerHref({ ...record, identity_id: undefined }), null)
  for (const status of ['draft', 'pending', 'rejected', 'published', 'withdrawn']) {
    assert.ok(layoutViewerHref({ ...record, status }))
  }
})
