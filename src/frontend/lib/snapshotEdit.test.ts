import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { ComponentSnapshot } from '@/generated/CatalogModels'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import {
  editPatch,
  editValuesOf,
  emptyCaptureFields,
  versionLabel,
  versionToEdit,
} from './snapshotEdit'

const snapshot = (extra: Partial<ComponentSnapshot> = {}): ComponentSnapshot => ({
  _id: 's1', identity_id: 'i1', version: 1, status: 'published',
  effective_from: '2024-07-24T00:00:00Z', effective_from_precision: 'day',
  name: 'Beam', notes: null, capture: { method: 'photogrammetry', notes: 'first scan' },
  ...extra,
} as ComponentSnapshot)

const row = (extra: Partial<SnapshotSummaryItem>): SnapshotSummaryItem => ({
  _id: 'a', identity_id: 'i1', version: 0, status: 'published', is_current: false,
  effective_from: '2024-01-01T00:00:00Z', created: 'x', lastmodified: 'x', ...extra,
} as SnapshotSummaryItem)

test('only the empty capture fields are offered, a set one is not', () => {
  assert.deepEqual(emptyCaptureFields(snapshot()), ['device', 'software', 'captured_at'])
  assert.deepEqual(emptyCaptureFields(snapshot({ capture: null })), ['method', 'device', 'software', 'captured_at'])
})

test('the patch holds only what changed, and fills only what is empty', () => {
  const s = snapshot()
  const before = editValuesOf(s)
  assert.deepEqual(editPatch(s, before, before), {})
  const after = {
    ...before,
    name: 'Beam B',
    effectiveFrom: '2024-08-01',
    captureNotes: 'second look',
    device: ' Rig A ',
    method: 'lidar' as const,          // set already: never sent
    capturedAt: '2024-07-20',
  }
  assert.deepEqual(editPatch(s, before, after), {
    name: 'Beam B',
    effective_from: '2024-08-01T00:00:00Z',
    capture: { notes: 'second look', device: 'Rig A', captured_at: '2024-07-20T00:00:00Z' },
  })
})

test('the precision follows only a date that is there', () => {
  const s = snapshot()
  const before = editValuesOf(s)
  assert.deepEqual(editPatch(s, before, { ...before, precision: 'month' }), { effective_from_precision: 'month' })
  assert.deepEqual(editPatch(s, { ...before, effectiveFrom: '' }, { ...before, effectiveFrom: '', precision: 'month' }), {})
})

test('the version to edit: the one asked for, else the current, else the latest', () => {
  const rows = [row({ _id: 'a', version: 0 }), row({ _id: 'b', version: 1, is_current: true }), row({ _id: 'c', version: 2, status: 'draft' })]
  assert.equal(versionToEdit(rows, 'a')?._id, 'a')
  assert.equal(versionToEdit(rows, 'nope')?._id, 'b')
  assert.equal(versionToEdit(rows.map((r) => ({ ...r, is_current: false })), null)?._id, 'c')
  assert.equal(versionToEdit([], null), undefined)
})

test('a correction is labelled with the version it corrects', () => {
  const rows = [row({ _id: 'a', version: 0, superseded_by: 'c' }), row({ _id: 'b', version: 1, is_current: true }),
    row({ _id: 'c', version: 2, supersedes: 'a' }), row({ _id: 'd', version: 3, supersedes: 'c' })]
  assert.equal(versionLabel(rows[0], rows), 'v0 (published, corrected)')
  assert.equal(versionLabel(rows[1], rows), 'v1 (published, current)')
  assert.equal(versionLabel(rows[2], rows), 'v2 (published), a correction of v0')
  assert.equal(versionLabel(rows[3], rows), 'v3 (published), a correction of v0')
})

test('the photo credit is sent when it changed, and cleared by an empty text (8.128 a)', () => {
  const s = snapshot()
  const before = editValuesOf(s)
  assert.equal(before.creditText, '')
  assert.equal('photo_credit' in editPatch(s, before, before)!, false)
  const set = editPatch(s, before, { ...before, creditText: ' Photo: archive ', creditUrl: ' https://x.org ' })!
  assert.deepEqual(set.photo_credit, { text: 'Photo: archive', url: 'https://x.org' })
  const withCredit = snapshot({ photo_credit: { text: 'Photo: archive', url: 'https://x.org' } } as Partial<ComponentSnapshot>)
  const had = editValuesOf(withCredit)
  assert.equal(had.creditUrl, 'https://x.org')
  assert.equal(editPatch(withCredit, had, had)!.photo_credit, undefined)
  const cleared = editPatch(withCredit, had, { ...had, creditText: '', creditUrl: '' })!
  assert.equal(cleared.photo_credit, null)
})
