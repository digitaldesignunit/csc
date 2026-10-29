/**
 * Where a click on an evidence record of the History graph leads (issue 37).
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { HistoryEvent } from './types'
import { recordAnchor, recordIdOfHash, recordTarget, singleRecordOf } from './recordTarget'

const BAR = { points: [[0, 0, 0], [1, 0, 0]], diameter_mm: 12 }
const layout = (over: Record<string, unknown> = {}) => ({
  _id: 'ev1',
  identity_id: 'piece',
  position: { snapshot_id: 'snap1' },
  payload: { bars: [BAR] },
  ...over,
}) as never

test('a layout on this piece opens in the viewer, as "Show in viewer" does', () => {
  const target = recordTarget({
    recordId: 'ev1', method: 'reinforcement_layout', laneId: 'piece', identityId: 'piece', record: layout(),
  })
  assert.deepEqual(target, {
    kind: 'viewer',
    href: '/components/piece?snapshot=snap1&layout=ev1#component-viewer',
  })
})

test('a layout of another lane opens on that piece, whatever its status', () => {
  for (const status of ['published', 'draft', 'pending', 'rejected']) {
    const target = recordTarget({
      recordId: 'ev2', method: 'reinforcement_layout', laneId: 'parent', identityId: 'piece',
      record: layout({ _id: 'ev2', identity_id: 'parent', status }),
    })
    assert.deepEqual(target, {
      kind: 'viewer',
      href: '/components/parent?snapshot=snap1&layout=ev2#component-viewer',
    }, status)
  }
})

test('a layout without drawable bars or without a position falls back to the card', () => {
  for (const record of [
    layout({ payload: { bars: [] } }),
    layout({ payload: {} }),
    layout({ payload: { bars: [{ points: [[0, 0, 0]], diameter_mm: 12 }] } }),
    layout({ position: { snapshot_id: null } }),
    layout({ position: null }),
  ]) {
    assert.deepEqual(
      recordTarget({ recordId: 'ev1', method: 'reinforcement_layout', laneId: 'piece', identityId: 'piece', record }),
      { kind: 'card', recordId: 'ev1', openCorrected: false },
    )
  }
  // on another lane the card is on that lane's page
  assert.deepEqual(
    recordTarget({
      recordId: 'ev1', method: 'reinforcement_layout', laneId: 'parent', identityId: 'piece', record: layout({ position: null }),
    }),
    { kind: 'other-lane', href: '/components/parent#record-ev1' },
  )
})

test('a layout whose record could not be loaded falls back to the card', () => {
  assert.deepEqual(
    recordTarget({ recordId: 'ev1', method: 'reinforcement_layout', laneId: 'piece', identityId: 'piece', record: null }),
    { kind: 'card', recordId: 'ev1', openCorrected: false },
  )
})

test('another method scrolls to its card, even when its record has bars', () => {
  assert.deepEqual(
    recordTarget({ recordId: 'ev1', method: 'rebound_hammer', laneId: 'piece', identityId: 'piece', record: layout() }),
    { kind: 'card', recordId: 'ev1', openCorrected: false },
  )
  assert.deepEqual(
    recordTarget({ recordId: 'ev1', method: 'archival_document', laneId: 'child', identityId: 'piece' }),
    { kind: 'other-lane', href: '/components/child#record-ev1' },
  )
})

test('a corrected record opens "Show corrected records" first', () => {
  assert.deepEqual(
    recordTarget({
      recordId: 'ev1', method: 'rebound_hammer', laneId: 'piece', identityId: 'piece',
      record: layout({ superseded_by: 'ev9' }),
    }),
    { kind: 'card', recordId: 'ev1', openCorrected: true },
  )
  // a corrected layout with bars still opens in the viewer
  assert.equal(
    recordTarget({
      recordId: 'ev1', method: 'reinforcement_layout', laneId: 'piece', identityId: 'piece',
      record: layout({ superseded_by: 'ev9' }),
    }).kind,
    'viewer',
  )
})

test('the hash of another lane round-trips to the record id', () => {
  const id = 'a b/c'
  const target = recordTarget({ recordId: id, method: 'visual_inspection', laneId: 'p', identityId: 'q' })
  assert.equal(target.kind, 'other-lane')
  const hash = `#${recordAnchor(id)}`
  assert.equal(recordIdOfHash(hash), id)
  assert.equal(recordIdOfHash('#component-viewer'), null)
  assert.equal(recordIdOfHash(''), null)
  assert.equal(recordIdOfHash('#record-%E0%A4%A'), null)
})

test('a group of one record goes on to the record, a group of several only expands', () => {
  const group: HistoryEvent = {
    kind: 'evidence_group', at: '2025-08-12T00:00:00Z', id: 'ev1', method: 'reinforcement_layout',
    day: '2025-08-12', count: 1, ids: ['ev1'], statuses: ['published'],
  }
  const record = singleRecordOf(group)
  assert.equal(record?.kind, 'evidence')
  assert.equal(record?.id, 'ev1')
  assert.equal(record?.method, 'reinforcement_layout')
  assert.equal(record?.at, '2025-08-12T00:00:00Z')
  assert.equal(singleRecordOf({ ...group, count: 2, ids: ['ev1', 'ev2'] }), null)
  assert.equal(singleRecordOf({ ...group, count: 4, ids: ['a', 'b', 'c', 'd'] }), null)
  // a record is not a group, and a group without ids has nothing to open
  assert.equal(singleRecordOf({ ...group, kind: 'evidence' }), null)
  assert.equal(singleRecordOf({ ...group, ids: undefined }), null)
  assert.equal(singleRecordOf({ ...group, count: 2 }), null)
})

test('the record of a one-record group opens the layout in the viewer, any other record its card', () => {
  const group: HistoryEvent = { kind: 'evidence_group', at: null, id: 'ev1', method: 'reinforcement_layout', count: 1, ids: ['ev1'] }
  const record = singleRecordOf(group)
  const target = recordTarget({
    recordId: record?.id ?? '', method: record?.method, laneId: 'piece', identityId: 'piece', record: layout(),
  })
  assert.equal(target.kind, 'viewer')
  const other = singleRecordOf({ ...group, method: 'archival_document' })
  assert.deepEqual(
    recordTarget({ recordId: other?.id ?? '', method: other?.method, laneId: 'piece', identityId: 'piece' }),
    { kind: 'card', recordId: 'ev1', openCorrected: false },
  )
})
