import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { MySnapshotItem } from '@/generated/SnapshotModels'
import {
  isSubmittable,
  mergeMyRecords,
  pieceLabel,
  recordKey,
  rejectionReason,
  submitRecords,
  submittableKeys,
  waitingLines,
  type MyRecord,
} from './myWork'

const PIECES = new Map([
  ['i1', { name: 'Beam 07', catalog_number: 7, dataset: 'zirkus' }],
  ['i2', { name: null, catalog_number: 9, dataset: 'later_dataset' }],
])

const SNAP = (over: Partial<MySnapshotItem>): MySnapshotItem => ({
  _id: 's1', identity_id: 'i1', version: 2, status: 'draft', is_current: false,
  created: '2026-09-01T00:00:00Z', ...over,
})

test('a piece is its number and its name', () => {
  assert.equal(pieceLabel({ name: ' Beam 07 ', catalog_number: 7 }), '#7 Beam 07')
  assert.equal(pieceLabel({ catalog_number: 9 }), '#9')
  assert.equal(pieceLabel({ name: 'x' }), 'x')
  assert.equal(pieceLabel(null), '')
})

test('the reason of a rejection is the last rejection in the history', () => {
  assert.equal(rejectionReason(undefined), '')
  assert.equal(rejectionReason([{ to: 'pending' }]), '')
  assert.equal(
    rejectionReason([
      { to: 'rejected', reason: 'first' },
      { to: 'draft' },
      { to: 'pending' },
      { to: 'rejected', reason: ' second ' },
    ]),
    'second',
  )
})

test('own snapshots and evidence form one list, the latest change first', () => {
  const rows = mergeMyRecords(
    [
      SNAP({ _id: 's1', created: '2026-09-01T00:00:00Z' }),
      SNAP({ _id: 's2', identity_id: 'i2', version: 0, status: 'rejected', status_changed_at: '2026-10-03T00:00:00Z', rejection_reason: 'Too small.' }),
    ],
    [
      { _id: 'e1', identity_id: 'i1', method: 'rebound_hammer', status: 'pending', created: '2026-09-20T00:00:00Z' },
      {
        _id: 'e2', identity_id: 'i1', method: 'archival_document', status: 'rejected', created: '2026-08-01T00:00:00Z',
        status_changed_at: '2026-10-01T00:00:00Z', status_history: [{ to: 'rejected', reason: 'No source.' }],
      },
    ],
    PIECES,
  )
  assert.deepEqual(rows.map((r) => r.id), ['s2', 'e2', 'e1', 's1'])
  const [snap, evidence] = rows
  assert.equal(snap.title, 'Snapshot v0')
  assert.equal(snap.piece, '#9')
  assert.equal(snap.dataset, 'later_dataset')
  assert.equal(snap.reason, 'Too small.')
  assert.equal(snap.href, '/components/i2?snapshots=s2')
  assert.equal(evidence.title, 'Evidence: Archival document')
  assert.equal(evidence.reason, 'No source.')
  assert.equal(evidence.href, '/components/i1')
  // a record that is not rejected carries no reason
  assert.equal(rows.find((r) => r.id === 'e1')?.reason, '')
})

test('a snapshot of a piece that could not be read falls back to its own name', () => {
  const rows = mergeMyRecords([SNAP({ name: 'Draft name', catalog_number: 3, dataset: 'x' })], [], new Map())
  assert.equal(rows[0].piece, '#3 Draft name')
  assert.equal(rows[0].dataset, 'x')
})

test('waiting for you lists only what waits', () => {
  assert.deepEqual(waitingLines({ snapshots: 0, evidence: 0, verification: 0 }), [])
  assert.deepEqual(waitingLines({ snapshots: 1, evidence: 3, verification: 0 }), [
    { key: 'snapshots', text: '1 version to moderate', tab: 'snapshots' },
    { key: 'evidence', text: '3 records to moderate', tab: 'evidence' },
  ])
  assert.deepEqual(waitingLines({ snapshots: 0, evidence: 0, verification: 6 }), [
    { key: 'verification', text: '6 records to verify', tab: 'verification' },
  ])
})


// BULK SUBMIT (decision 8.127) -------------------------------------------------
const ROW = (over: Partial<MyRecord>): MyRecord => ({
  kind: 'snapshot', id: 's1', identityId: 'i1', title: 'Snapshot v2', piece: '#7 Beam 07',
  dataset: 'zirkus', status: 'draft', at: '2026-10-01T00:00:00Z', reason: '', href: '/x', ...over,
})

test('only a draft can be submitted, and a snapshot and a record may share an id', () => {
  const rows = [
    ROW({ id: 'a' }),
    ROW({ id: 'a', kind: 'evidence', title: 'Evidence: Rebound hammer' }),
    ROW({ id: 'b', status: 'pending' }),
    ROW({ id: 'c', status: 'rejected' }),
    ROW({ id: 'd', kind: 'evidence', status: 'published' }),
  ]
  assert.equal(isSubmittable(rows[0]), true)
  assert.equal(isSubmittable(rows[2]), false)
  assert.deepEqual(submittableKeys(rows), ['snapshot:a', 'evidence:a'])
  assert.equal(recordKey(rows[1]), 'evidence:a')
})

test('a refused record does not stop the others and each result says what happened', async () => {
  const rows = [
    ROW({ id: 'a' }),
    ROW({ id: 'b', kind: 'evidence', title: 'Evidence: Core' }),
    ROW({ id: 'c' }),
    ROW({ id: 'd', status: 'pending' }),
    ROW({ id: 'e' }),
  ]
  const asked: string[] = []
  const results = await submitRecords(
    rows,
    new Set(['snapshot:a', 'evidence:b', 'snapshot:c', 'snapshot:d']),   // d is pending, e is not chosen
    async (row) => {
      asked.push(recordKey(row))
      if (row.id === 'b') throw new Error('Add the photos first')
      return 'pending'
    },
  )
  assert.deepEqual(asked, ['snapshot:a', 'evidence:b', 'snapshot:c'])
  assert.deepEqual(results.map((r) => [r.key, r.ok, r.message]), [
    ['snapshot:a', true, 'pending'],
    ['evidence:b', false, 'Add the photos first'],
    ['snapshot:c', true, 'pending'],
  ])
  assert.equal(results[1].title, 'Evidence: Core')
})

test('nothing chosen submits nothing', async () => {
  let calls = 0
  const results = await submitRecords([ROW({})], new Set(), async () => { calls += 1; return 'pending' })
  assert.deepEqual(results, [])
  assert.equal(calls, 0)
})
