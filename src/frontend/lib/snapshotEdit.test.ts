import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { ComponentSnapshot } from '@/generated/CatalogModels'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import {
  canEditVersion,
  editPatch,
  editValuesOf,
  emptyCaptureFields,
  reducedEdit,
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
  const withCredit = snapshot({ photo_credit: { text: 'Photo: archive', url: 'https://x.org' } })
  const had = editValuesOf(withCredit)
  assert.equal(had.creditUrl, 'https://x.org')
  assert.equal(editPatch(withCredit, had, had)!.photo_credit, undefined)
  const cleared = editPatch(withCredit, had, { ...had, creditText: '', creditUrl: '' })!
  assert.equal(cleared.photo_credit, null)
})

test('a stored location fills the boxes as plain decimals, so an untouched form is never blocked by it', () => {
  for (const location of [{ lat: 1e-7, lon: -0 }, { lat: -1e-7, lon: 1e-9 }, { lat: 49.861444, lon: 8.676556 }, { lat: -33.86, lon: 151.21 }]) {
    const s = snapshot({ location } as Partial<ComponentSnapshot>)
    const before = editValuesOf(s)
    assert.ok(!/e/i.test(before.lat + before.lon), `${before.lat} ${before.lon}`)
    assert.deepEqual(editPatch(s, before, before), {})
  }
  const tiny = editValuesOf(snapshot({ location: { lat: 1e-7, lon: -0 } } as Partial<ComponentSnapshot>))
  assert.deepEqual([tiny.lat, tiny.lon], ['0', '0'])
  assert.deepEqual(
    editPatch(snapshot({ location: { lat: 1e-7, lon: -0 } } as Partial<ComponentSnapshot>), tiny, { ...tiny, lat: '49.5', lon: '8.5' }),
    { location: { lat: 49.5, lon: 8.5 } })
})

test('who edits the details of a version (the edit page rule)', () => {
  // a draft: its author or a moderator
  assert.equal(canEditVersion('draft', true, false), true)
  assert.equal(canEditVersion('draft', false, true), true)
  assert.equal(canEditVersion('draft', false, false), false)
  // pending, published, withdrawn: a moderator only (#48 case 5)
  for (const status of ['pending', 'published', 'withdrawn']) {
    assert.equal(canEditVersion(status, false, true), true, status)
    assert.equal(canEditVersion(status, true, false), false, status)
  }
  // rejected: nobody
  assert.equal(canEditVersion('rejected', true, true), false)
})

test('the reduced form: a withdrawn version, or any version of a withdrawn element', () => {
  assert.equal(reducedEdit('withdrawn', false), true)
  assert.equal(reducedEdit('published', true), true)
  assert.equal(reducedEdit('draft', true), true)
  assert.equal(reducedEdit('published', false), false)
  assert.equal(reducedEdit('draft', false), false)
})

test('a save from the reduced form sends name, notes and date only', () => {
  const s = snapshot({ capture: { notes: 'first scan' } } as Partial<ComponentSnapshot>)
  const before = editValuesOf(s)
  const everything: typeof before = {
    ...before, name: 'New', notes: 'n', effectiveFrom: '2024-08-01', precision: 'month',
    color: [1, 2, 3], lat: '49.5', lon: '8.5', creditText: 'Photo', creditUrl: 'https://x.org',
    captureNotes: 'changed', method: 'lidar', device: 'dev', software: 'sw', capturedAt: '2024-08-02',
  }
  assert.deepEqual(editPatch(s, before, everything, true), {
    name: 'New', notes: 'n', effective_from: '2024-08-01T00:00:00Z', effective_from_precision: 'month',
  })
  // the full form sends the rest
  const full = editPatch(s, before, everything, false)!
  for (const key of ['color', 'location', 'photo_credit', 'capture']) assert.ok(key in full, key)
  // an unchanged reduced form is empty, and a bad location text is not read
  assert.deepEqual(editPatch(s, before, { ...before, lat: 'x' }, true), {})
})
