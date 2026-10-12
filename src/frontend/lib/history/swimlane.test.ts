import assert from 'node:assert/strict'
import test from 'node:test'

import { applyLayers, describeEvent, expandGroups, groupKey, layoutSwimlane, laneTitle } from '@/lib/history/swimlane'
import type { HistoryEvent, HistoryResponse } from '@/lib/history/types'

const lane = (id: string, level: number, role: 'parent' | 'piece' | 'child', events: HistoryEvent[]) => ({
  id, level, role, visible: true, catalog_number: level + 10, name: `piece ${id}`, events,
})

const history = (): HistoryResponse => ({
  root: 'p', depth: 1, expand: 'groups', more: 0,
  lanes: [
    lane('parent', -1, 'parent', [
      { kind: 'origin', at: '2022-10-26T00:00:00Z', precision: 'day', detail: 'offcut' },
      { kind: 'version', at: '2022-10-26T00:00:00Z', id: 'v-parent', version: 0, status: 'published' },
      { kind: 'exit', at: '2026-04-29T11:00:00Z', precision: 'exact', detail: 'split' },
    ]),
    lane('p', 0, 'piece', [
      { kind: 'origin', at: null },
      { kind: 'version', at: '2026-04-29T11:00:00Z', id: 'v-piece', version: 0, status: 'published' },
      { kind: 'evidence_group', at: '2026-05-01T00:00:00Z', day: '2026-05-01', method: 'rebound_hammer', count: 2, ids: ['e1', 'e2'] },
      { kind: 'evidence_group', at: '2026-05-01T00:00:00Z', day: '2026-05-01', method: 'visual_inspection', count: 1, ids: ['e3'] },
    ]),
  ],
  links: [{ kind: 'cut', from: 'parent', to: 'p', at: '2026-04-29T11:00:00Z', precision: 'exact', version_id: 'v-piece' }],
})

test('events of one day line up across the lanes, undated events come first', () => {
  const layout = layoutSwimlane(history())
  const x = (lane: string, id: string) => layout.events.find((e) => e.laneId === lane && (e.event.id === id))!.x
  assert.equal(x('parent', 'v-parent') <= x('p', 'v-piece'), true)
  const undated = layout.events.find((e) => e.event.kind === 'origin' && e.laneId === 'p')!
  assert.equal(undated.x < x('parent', 'v-parent'), true)
  assert.equal(layout.sections[0].label, 'Undated')
  assert.deepEqual(layout.sections.map((s) => s.label), ['Undated', '2022', '2026'])
})

test('the exit of the parent and the first version of the child share a column', () => {
  const layout = layoutSwimlane(history())
  const exit = layout.events.find((e) => e.event.kind === 'exit')!
  const first = layout.events.find((e) => e.event.id === 'v-piece')!
  assert.equal(exit.x, first.x)
})

test('a cut link falls on the first version of the child and joins the lanes', () => {
  const layout = layoutSwimlane(history())
  const link = layout.links[0]
  const first = layout.events.find((e) => e.event.id === 'v-piece')!
  assert.equal(link.x, first.x)
  assert.equal(link.from, 0)
  assert.equal(link.to, 1)
  assert.ok(link.y1 < link.y2)
})

test('two events of one lane on one day sit side by side', () => {
  const layout = layoutSwimlane(history())
  const groups = layout.events.filter((e) => e.event.kind === 'evidence_group')
  assert.equal(groups.length, 2)
  assert.ok(groups[1].x - groups[0].x >= 30)
})

test('a dense year is cut into months, a sparse one is not', () => {
  const events: HistoryEvent[] = []
  for (let m = 1; m <= 12; m += 1) {
    events.push({ kind: 'version', at: `2025-${String(m).padStart(2, '0')}-10T00:00:00Z`, id: `v${m}`, version: m })
  }
  const dense = layoutSwimlane({ ...history(), lanes: [lane('p', 0, 'piece', events)], links: [] })
  assert.equal(dense.hasMonths, true)
  assert.equal(dense.sections[0].months.length, 12)
  assert.equal(dense.sections[0].months[0].label, 'Jan')
  assert.equal(layoutSwimlane(history()).hasMonths, false)
})

test('opening a group replaces it by its records, in place', () => {
  const records = new Map<string, HistoryEvent>([
    ['e1', { kind: 'evidence', at: '2026-05-01T00:00:00Z', id: 'e1', method: 'rebound_hammer' }],
    ['e2', { kind: 'evidence', at: '2026-05-01T00:00:00Z', id: 'e2', method: 'rebound_hammer' }],
    ['e3', { kind: 'evidence', at: '2026-05-01T00:00:00Z', id: 'e3', method: 'visual_inspection' }],
  ])
  const key = groupKey('p', history().lanes[1].events![2])
  const opened = expandGroups(history(), new Set([key]), records)
  const kinds = opened.lanes[1].events!.map((e) => e.kind)
  assert.deepEqual(kinds, ['origin', 'version', 'evidence', 'evidence', 'evidence_group'])
  assert.equal(opened.lanes[1].events![2].groupKey, key)
  const all = expandGroups(history(), 'all', records)
  assert.equal(all.lanes[1].events!.filter((e) => e.kind === 'evidence').length, 3)
})

test('a group whose records are not loaded stays a group', () => {
  const key = groupKey('p', history().lanes[1].events![2])
  const opened = expandGroups(history(), new Set([key]), new Map())
  assert.equal(opened.lanes[1].events!.filter((e) => e.kind === 'evidence_group').length, 2)
})

test('the layers drop lanes, versions and evidence', () => {
  const none = applyLayers(history(), { lineage: false, states: true, evidence: true })
  assert.deepEqual(none.lanes.map((l) => l.id), ['p'])
  assert.deepEqual(none.links, [])
  const noStates = applyLayers(history(), { lineage: true, states: false, evidence: true })
  assert.equal(noStates.lanes[1].events!.some((e) => e.kind === 'version'), false)
  const noEvidence = applyLayers(history(), { lineage: true, states: true, evidence: false })
  assert.equal(noEvidence.lanes[1].events!.some((e) => e.kind === 'evidence_group'), false)
})

test('a stub lane has a place but no events; the count of lanes left out is kept', () => {
  const h = history()
  h.lanes.push({ id: 'hidden', level: 1, role: 'child', visible: false, label: 'not visible' })
  h.more = 3
  const layout = layoutSwimlane(h)
  assert.equal(layout.lanes.length, 3)
  assert.equal(layout.events.some((e) => e.laneId === 'hidden'), false)
  assert.equal(layout.more, 3)
  assert.equal(laneTitle(h.lanes[2]), 'not visible')
})

test('describing an event gives a title, a date and a short label', () => {
  const version = describeEvent({ kind: 'version', at: '2022-10-26T00:00:00Z', precision: 'day', version: 1, corrected: true, name: 'beam' })
  assert.equal(version.title, 'Version v1')
  assert.equal(version.short, 'v1')
  assert.ok(version.lines.some((line) => line.includes('replaced by a correction')))
  assert.ok(describeEvent({ kind: 'exit', at: null, detail: 'split' }).lines.includes('date unknown'))
})
